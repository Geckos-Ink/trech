#include "trech/ml/GenericSurrogate.hpp"

#if defined(TRECH_ENABLE_TORCH)
#include <torch/script.h>
#include <torch/torch.h>
#endif

#include <cmath>
#include <fstream>

#include <nlohmann/json.hpp>

namespace trech::ml {

namespace {

bool endsWith(const std::string& s, const std::string& suffix) {
  return s.size() >= suffix.size() &&
         s.compare(s.size() - suffix.size(), suffix.size(), suffix) == 0;
}

// The 14 optics composition element slots (mirrors OpticsSurrogate); density is
// the implicit 15th input for ridge_optics_n_v1 models.
const char* const kOpticsElements[] = {"H",  "C",  "N", "O",  "F",
                                       "Na", "Mg", "Al", "Si", "P",
                                       "S",  "Cl", "I",  "other"};

}  // namespace

GenericSurrogate::GenericSurrogate() = default;
GenericSurrogate::~GenericSurrogate() = default;

GenericSurrogate::Activation GenericSurrogate::parseActivation(
    const std::string& name) {
  if (name == "relu") return Activation::kRelu;
  if (name == "silu" || name == "swish") return Activation::kSilu;
  if (name == "tanh") return Activation::kTanh;
  if (name == "sigmoid" || name == "logistic") return Activation::kSigmoid;
  return Activation::kNone;  // "none"/"linear"/identity/unknown
}

bool GenericSurrogate::buildFromGeneric(const void* jsonPtr) {
  const auto& j = *static_cast<const nlohmann::json*>(jsonPtr);
  if (!j.contains("input_features") || !j.at("input_features").is_array() ||
      !j.contains("output_features") || !j.at("output_features").is_array() ||
      !j.contains("layers") || !j.at("layers").is_array()) {
    note_ = "generic model missing input_features|output_features|layers";
    return false;
  }
  inputNames_ = j.at("input_features").get<std::vector<std::string>>();
  outputNames_ = j.at("output_features").get<std::vector<std::string>>();
  const std::size_t nIn = inputNames_.size();
  const std::size_t nOut = outputNames_.size();
  if (nIn == 0 || nOut == 0) {
    note_ = "generic model has empty input/output feature list";
    return false;
  }

  auto readScaler = [&](const char* key, std::size_t len, double fill,
                        std::vector<double>& out) -> bool {
    if (!j.contains(key)) {
      out.assign(len, fill);
      return true;
    }
    if (!j.at(key).is_array() || j.at(key).size() != len) {
      note_ = std::string("generic model ") + key + " wrong length";
      return false;
    }
    out = j.at(key).get<std::vector<double>>();
    return true;
  };
  if (!readScaler("input_mean", nIn, 0.0, inputMean_) ||
      !readScaler("input_std", nIn, 1.0, inputStd_) ||
      !readScaler("output_mean", nOut, 0.0, outputMean_) ||
      !readScaler("output_std", nOut, 1.0, outputStd_)) {
    return false;
  }
  for (double& s : inputStd_) {
    if (std::abs(s) < 1e-12) s = 1.0;
  }

  std::size_t layerInputs = nIn;
  for (const auto& layerJson : j.at("layers")) {
    if (!layerJson.contains("weights") || !layerJson.at("weights").is_array() ||
        !layerJson.contains("bias") || !layerJson.at("bias").is_array()) {
      note_ = "generic model layer missing weights|bias";
      return false;
    }
    Layer layer;
    layer.weights =
        layerJson.at("weights").get<std::vector<std::vector<double>>>();
    layer.bias = layerJson.at("bias").get<std::vector<double>>();
    layer.activation = parseActivation(
        layerJson.value("activation", std::string("none")));
    if (layer.weights.empty() || layer.weights.size() != layer.bias.size()) {
      note_ = "generic model layer weights/bias size mismatch";
      return false;
    }
    for (const auto& row : layer.weights) {
      if (row.size() != layerInputs) {
        note_ = "generic model layer input width mismatch";
        return false;
      }
    }
    layerInputs = layer.weights.size();  // this layer's output width
    layers_.push_back(std::move(layer));
  }
  if (layers_.empty() || layerInputs != nOut) {
    note_ = "generic model final layer width != output_features";
    return false;
  }
  modelId_ = j.value("model", std::string("generic_surrogate_v1"));
  valid_ = true;
  note_ = "generic model loaded (" + std::to_string(nIn) + " in -> " +
          std::to_string(nOut) + " out, " + std::to_string(layers_.size()) +
          " layer(s))";
  return true;
}

bool GenericSurrogate::buildFromRidge(const void* jsonPtr) {
  const auto& j = *static_cast<const nlohmann::json*>(jsonPtr);
  // ridge_optics_n_v1: standardised linear n = bias + sum w_i (x_i-mean_i)/std_i
  // over 14 element slots + density.
  const std::size_t n = sizeof(kOpticsElements) / sizeof(kOpticsElements[0]) + 1;
  auto readVec = [&](const char* key, std::vector<double>& out) -> bool {
    if (!j.contains(key) || !j.at(key).is_array() || j.at(key).size() != n) {
      return false;
    }
    out = j.at(key).get<std::vector<double>>();
    return true;
  };
  std::vector<double> weights, mean, std_;
  if (!readVec("weights", weights) || !readVec("mean", mean) ||
      !readVec("std", std_)) {
    note_ = "ridge_optics_n_v1 missing/wrong-length weights|mean|std";
    return false;
  }
  inputNames_.assign(kOpticsElements,
                     kOpticsElements + (n - 1));
  inputNames_.push_back("density_gcm3");
  outputNames_ = {"refractive_index"};
  inputMean_ = mean;
  inputStd_ = std_;
  for (double& s : inputStd_) {
    if (std::abs(s) < 1e-12) s = 1.0;
  }
  outputMean_ = {0.0};
  outputStd_ = {1.0};
  Layer layer;
  layer.weights = {weights};
  layer.bias = {j.value("bias", 0.0)};
  layer.activation = Activation::kNone;
  layers_.push_back(std::move(layer));
  modelId_ = "ridge_optics_n_v1";
  valid_ = true;
  note_ = "ridge optics model loaded as generic (n)";
  return true;
}

bool GenericSurrogate::buildFromLogistic(const void* jsonPtr) {
  const auto& j = *static_cast<const nlohmann::json*>(jsonPtr);
  if (!j.contains("feature_names") || !j.at("feature_names").is_array()) {
    note_ = "logistic_stratifier_v1 missing feature_names";
    return false;
  }
  inputNames_ = j.at("feature_names").get<std::vector<std::string>>();
  const std::size_t n = inputNames_.size();
  auto readVec = [&](const char* key, std::vector<double>& out) -> bool {
    if (!j.contains(key) || !j.at(key).is_array() || j.at(key).size() != n) {
      return false;
    }
    out = j.at(key).get<std::vector<double>>();
    return true;
  };
  std::vector<double> weights, mean, std_;
  if (!readVec("weights", weights) || !readVec("mean", mean) ||
      !readVec("std", std_)) {
    note_ = "logistic_stratifier_v1 missing/wrong-length weights|mean|std";
    return false;
  }
  outputNames_ = {"p_exceptional"};
  inputMean_ = mean;
  inputStd_ = std_;
  for (double& s : inputStd_) {
    if (std::abs(s) < 1e-12) s = 1.0;
  }
  outputMean_ = {0.0};
  outputStd_ = {1.0};
  Layer layer;
  layer.weights = {weights};
  layer.bias = {j.value("bias", 0.0)};
  layer.activation = Activation::kSigmoid;
  layers_.push_back(std::move(layer));
  modelId_ = "logistic_stratifier_v1";
  valid_ = true;
  note_ = "logistic stratifier model loaded as generic (p_exceptional)";
  return true;
}

bool GenericSurrogate::loadJson(const std::string& path) {
  std::ifstream in(path);
  if (!in) {
    note_ = "cannot open model json: " + path;
    return false;
  }
  nlohmann::json j;
  try {
    in >> j;
  } catch (const std::exception& e) {
    note_ = std::string("model json parse failed: ") + e.what();
    return false;
  }
  const std::string kind = j.value("model", std::string(""));
  if (kind == "ridge_optics_n_v1") {
    return buildFromRidge(&j);
  }
  if (kind == "logistic_stratifier_v1") {
    return buildFromLogistic(&j);
  }
  // Default: the general feed-forward representation.
  return buildFromGeneric(&j);
}

bool GenericSurrogate::load(const std::string& path) {
  modelPath_ = path;
  modelId_.clear();
  note_.clear();
  inputNames_.clear();
  outputNames_.clear();
  inputMean_.clear();
  inputStd_.clear();
  outputMean_.clear();
  outputStd_.clear();
  layers_.clear();
  valid_ = false;
#if defined(TRECH_ENABLE_TORCH)
  module_.reset();
  torchInputCount_ = 0;
#endif
  if (modelPath_.empty()) {
    note_ = "empty modelPath";
    return false;
  }
  if (endsWith(modelPath_, ".json")) {
    return loadJson(modelPath_);
  }
#if defined(TRECH_ENABLE_TORCH)
  try {
    module_ = std::make_unique<torch::jit::Module>(torch::jit::load(modelPath_));
    module_->eval();
    note_ = "torchscript model loaded (positional; use predictVector)";
    return true;
  } catch (const c10::Error&) {
    module_.reset();
    note_ = "torch::jit::load failed";
    return false;
  }
#else
  note_ = "non-json model needs LibTorch, which is off (TRECH_ENABLE_TORCH); "
          "supply a generic .json model instead";
  return false;
#endif
}

bool GenericSurrogate::loaded() const {
  if (valid_) {
    return true;
  }
#if defined(TRECH_ENABLE_TORCH)
  return static_cast<bool>(module_);
#else
  return false;
#endif
}

bool GenericSurrogate::predictVector(const std::vector<double>& inputs,
                                     std::vector<double>* out) const {
  if (!out) {
    return false;
  }
  if (valid_) {
    if (inputs.size() != inputNames_.size()) {
      return false;
    }
    std::vector<double> activations(inputs.size());
    for (std::size_t i = 0; i < inputs.size(); ++i) {
      activations[i] = (inputs[i] - inputMean_[i]) / inputStd_[i];
    }
    for (const auto& layer : layers_) {
      std::vector<double> next(layer.weights.size());
      for (std::size_t o = 0; o < layer.weights.size(); ++o) {
        double sum = layer.bias[o];
        const auto& row = layer.weights[o];
        for (std::size_t i = 0; i < row.size(); ++i) {
          sum += row[i] * activations[i];
        }
        switch (layer.activation) {
          case Activation::kRelu:
            sum = sum > 0.0 ? sum : 0.0;
            break;
          case Activation::kSilu:
            sum = sum / (1.0 + std::exp(-sum));
            break;
          case Activation::kTanh:
            sum = std::tanh(sum);
            break;
          case Activation::kSigmoid:
            sum = 1.0 / (1.0 + std::exp(-sum));
            break;
          case Activation::kNone:
            break;
        }
        next[o] = sum;
      }
      activations = std::move(next);
    }
    out->resize(activations.size());
    for (std::size_t o = 0; o < activations.size(); ++o) {
      (*out)[o] = activations[o] * outputStd_[o] + outputMean_[o];
    }
    return true;
  }
#if defined(TRECH_ENABLE_TORCH)
  if (!module_) {
    return false;
  }
  torch::NoGradGuard noGrad;
  std::vector<float> f(inputs.begin(), inputs.end());
  auto input = torch::from_blob(f.data(), {1, static_cast<long>(f.size())},
                                torch::kFloat32)
                   .clone();
  std::vector<torch::jit::IValue> ivals;
  ivals.emplace_back(input);
  torch::jit::IValue output;
  try {
    output = module_->forward(ivals);
  } catch (const c10::Error&) {
    return false;
  }
  if (!output.isTensor()) {
    return false;
  }
  auto tensor =
      output.toTensor().to(torch::kCPU).to(torch::kFloat32).flatten().contiguous();
  out->resize(static_cast<std::size_t>(tensor.numel()));
  auto acc = tensor.accessor<float, 1>();
  for (std::size_t i = 0; i < out->size(); ++i) {
    (*out)[i] = static_cast<double>(acc[i]);
  }
  return true;
#else
  return false;
#endif
}

bool GenericSurrogate::predict(
    const std::unordered_map<std::string, double>& inputs,
    std::unordered_map<std::string, double>* out) const {
  if (!out || !valid_) {
    return false;  // named prediction requires a JSON model with names
  }
  std::vector<double> x(inputNames_.size(), 0.0);
  for (std::size_t i = 0; i < inputNames_.size(); ++i) {
    const auto it = inputs.find(inputNames_[i]);
    if (it != inputs.end()) {
      x[i] = it->second;
    }
  }
  std::vector<double> y;
  if (!predictVector(x, &y) || y.size() != outputNames_.size()) {
    return false;
  }
  out->clear();
  for (std::size_t o = 0; o < outputNames_.size(); ++o) {
    (*out)[outputNames_[o]] = y[o];
  }
  return true;
}

}  // namespace trech::ml
