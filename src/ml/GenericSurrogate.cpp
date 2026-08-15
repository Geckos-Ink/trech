#include "trech/ml/GenericSurrogate.hpp"

#if defined(TRECH_ENABLE_TORCH)
#include <torch/script.h>
#include <torch/torch.h>
#endif

#include <algorithm>
#include <cmath>
#include <fstream>
#include <limits>
#include <utility>

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
    const auto rows =
        layerJson.at("weights").get<std::vector<std::vector<double>>>();
    Layer layer;
    layer.bias = layerJson.at("bias").get<std::vector<double>>();
    layer.activation = parseActivation(
        layerJson.value("activation", std::string("none")));
    if (rows.empty() || rows.size() != layer.bias.size()) {
      note_ = "generic model layer weights/bias size mismatch";
      return false;
    }
    for (const auto& row : rows) {
      if (row.size() != layerInputs) {
        note_ = "generic model layer input width mismatch";
        return false;
      }
    }
    layer.rows = rows.size();
    layer.cols = layerInputs;
    // Transpose into the input-major layout the evaluation loop wants.
    layer.weights.assign(layer.rows * layer.cols, 0.0);
    for (std::size_t o = 0; o < layer.rows; ++o) {
      for (std::size_t i = 0; i < layer.cols; ++i) {
        layer.weights[i * layer.rows + o] = rows[o][i];
      }
    }
    layerInputs = layer.rows;  // this layer's output width
    layers_.push_back(std::move(layer));
  }
  if (layers_.empty() || layerInputs != nOut) {
    note_ = "generic model final layer width != output_features";
    return false;
  }
  loadInputDomain(&j, nIn);
  loadTrainingProvenance(&j);
  modelId_ = j.value("model", std::string("generic_surrogate_v1"));
  valid_ = true;
  note_ = "generic model loaded (" + std::to_string(nIn) + " in -> " +
          std::to_string(nOut) + " out, " + std::to_string(layers_.size()) +
          " layer(s)" + (domainMeasured_ ? ", measured domain" : "") + ")";
  return true;
}

void GenericSurrogate::loadInputDomain(const void* jsonPtr, std::size_t nIn) {
  // Default: no measured hull -> a heuristic radius for every input, no range
  // or occupancy histogram (so the starved-region signal stays off).
  domainMeasured_ = false;
  inputDomainRadius_.assign(nIn, kDefaultStandardizedDomainRadius);
  inputMin_.clear();
  inputMax_.clear();
  occupancyCounts_.clear();
  occupancyBins_ = 0;
  jointCenters_.clear();
  jointCenterCount_ = 0;
  jointRadius_ = 0.0;
  if (!jsonPtr) {
    return;
  }
  const auto& j = *static_cast<const nlohmann::json*>(jsonPtr);
  if (!j.contains("input_domain") || !j.at("input_domain").is_object()) {
    return;
  }
  const auto& dom = j.at("input_domain");
  if (dom.contains("standardized_radius")) {
    const auto& r = dom.at("standardized_radius");
    if (r.is_number()) {
      inputDomainRadius_.assign(nIn, std::max(0.0, r.get<double>()));
      domainMeasured_ = true;
    } else if (r.is_array() && r.size() == nIn) {
      inputDomainRadius_ = r.get<std::vector<double>>();
      for (double& v : inputDomainRadius_) {
        v = std::max(0.0, v);
      }
      domainMeasured_ = true;
    }
    // A malformed/length-mismatched radius leaves the heuristic default in place.
  }

  // Per-feature training range + occupancy histogram (the starved-region signal:
  // a value in-range but in an empty bin is a hole the model interpolated).
  auto readVec = [&](const char* key, std::vector<double>& out) {
    if (dom.contains(key) && dom.at(key).is_array() &&
        dom.at(key).size() == nIn) {
      out = dom.at(key).get<std::vector<double>>();
    }
  };
  readVec("input_min", inputMin_);
  readVec("input_max", inputMax_);
  if (dom.contains("occupancy") && dom.at("occupancy").is_object() &&
      inputMin_.size() == nIn && inputMax_.size() == nIn) {
    const auto& occ = dom.at("occupancy");
    const int bins = occ.value("bins", 0);
    if (bins > 0 && occ.contains("counts") && occ.at("counts").is_array() &&
        occ.at("counts").size() == nIn) {
      std::vector<std::vector<int>> counts;
      counts.reserve(nIn);
      bool ok = true;
      for (const auto& row : occ.at("counts")) {
        if (!row.is_array() || row.size() != static_cast<std::size_t>(bins)) {
          ok = false;
          break;
        }
        counts.push_back(row.get<std::vector<int>>());
      }
      if (ok) {
        occupancyCounts_ = std::move(counts);
        occupancyBins_ = bins;
      }
    }
  }

  // Joint (multivariate) training reference: a covering set of standardized
  // training rows plus the distance that covers the training set's own
  // quantile.  Both blocks above are per-feature and cannot see a point that is
  // in range on every axis yet far from every training point.
  if (dom.contains("joint") && dom.at("joint").is_object()) {
    const auto& joint = dom.at("joint");
    const double radius = joint.value("radius", -1.0);
    if (radius >= 0.0 && joint.contains("centers") &&
        joint.at("centers").is_array()) {
      std::vector<double> flat;
      std::size_t count = 0;
      bool ok = true;
      for (const auto& center : joint.at("centers")) {
        if (!center.is_array() || center.size() != nIn) {
          ok = false;  // a malformed reference is ignored, never half-applied
          break;
        }
        for (const auto& value : center) {
          if (!value.is_number()) {
            ok = false;
            break;
          }
          flat.push_back(value.get<double>());
        }
        if (!ok) {
          break;
        }
        ++count;
      }
      if (ok && count > 0) {
        jointCenters_ = std::move(flat);
        jointCenterCount_ = count;
        jointRadius_ = radius;
      }
    }
  }
}

void GenericSurrogate::loadTrainingProvenance(const void* jsonPtr) {
  trainedScaleBands_.clear();
  hasHoldout_ = false;
  holdoutR2Min_ = 0.0;
  holdoutSamples_ = 0;
  outputAccuracy_.clear();
  hasOutputAccuracy_ = false;
  if (!jsonPtr) {
    return;
  }
  const auto& j = *static_cast<const nlohmann::json*>(jsonPtr);
  // Dimension-scale band(s) the training data came from (harvester tags each
  // run); used by the cascade to flag a stage applied off its trained band.
  if (j.contains("trained_scale_bands") &&
      j.at("trained_scale_bands").is_array()) {
    for (const auto& b : j.at("trained_scale_bands")) {
      if (b.is_string()) {
        trainedScaleBands_.push_back(b.get<std::string>());
      }
    }
  }
  // Held-out accuracy carried with the model (grade-the-gap). Require r2_min so
  // a partial/malformed block is treated as "no metrics" rather than a fake 0.
  if (j.contains("holdout") && j.at("holdout").is_object()) {
    const auto& h = j.at("holdout");
    if (h.contains("r2_min") && h.at("r2_min").is_number()) {
      holdoutR2Min_ = h.at("r2_min").get<double>();
      holdoutSamples_ = h.value("n", 0);
      hasHoldout_ = true;
    }
    // Per-output split: `r2`/`mae`/`rmse` are name->value objects keyed by
    // output feature. Each is optional and read independently, so a model
    // trained before a metric existed reports the ones it has and nothing more.
    outputAccuracy_.assign(outputNames_.size(), OutputAccuracy{});
    auto readMetric = [&](const char* key, bool OutputAccuracy::*present,
                          double OutputAccuracy::*value) {
      if (!h.contains(key) || !h.at(key).is_object()) {
        return;
      }
      const auto& block = h.at(key);
      for (std::size_t o = 0; o < outputNames_.size(); ++o) {
        const auto it = block.find(outputNames_[o]);
        if (it != block.end() && it->is_number()) {
          outputAccuracy_[o].*present = true;
          outputAccuracy_[o].*value = it->get<double>();
          hasOutputAccuracy_ = true;
        }
      }
    };
    readMetric("r2", &OutputAccuracy::hasR2, &OutputAccuracy::r2);
    readMetric("mae", &OutputAccuracy::hasMeanAbsoluteError,
               &OutputAccuracy::meanAbsoluteError);
    readMetric("rmse", &OutputAccuracy::hasRootMeanSquaredError,
               &OutputAccuracy::rootMeanSquaredError);
    if (!hasOutputAccuracy_) {
      outputAccuracy_.clear();
    }
  }
}

GenericSurrogate::OutputAccuracy GenericSurrogate::outputAccuracy(
    std::size_t outputIndex) const {
  if (outputIndex < outputAccuracy_.size()) {
    return outputAccuracy_[outputIndex];
  }
  return OutputAccuracy{};  // absent, never a fabricated 0
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
  layer.rows = 1;
  layer.cols = weights.size();
  layer.weights = std::move(weights);
  layer.bias = {j.value("bias", 0.0)};
  layer.activation = Activation::kNone;
  layers_.push_back(std::move(layer));
  loadInputDomain(&j, n);  // ridge models carry no hull today -> heuristic
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
  layer.rows = 1;
  layer.cols = weights.size();
  layer.weights = std::move(weights);
  layer.bias = {j.value("bias", 0.0)};
  layer.activation = Activation::kSigmoid;
  layers_.push_back(std::move(layer));
  loadInputDomain(&j, n);  // stratifier models carry no hull today -> heuristic
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
  inputDomainRadius_.clear();
  domainMeasured_ = false;
  inputMin_.clear();
  inputMax_.clear();
  occupancyCounts_.clear();
  occupancyBins_ = 0;
  trainedScaleBands_.clear();
  hasHoldout_ = false;
  holdoutR2Min_ = 0.0;
  holdoutSamples_ = 0;
  outputAccuracy_.clear();
  hasOutputAccuracy_ = false;
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

double GenericSurrogate::activate(Activation activation, double sum) {
  switch (activation) {
    case Activation::kRelu:
      return sum > 0.0 ? sum : 0.0;
    case Activation::kSilu:
      return sum / (1.0 + std::exp(-sum));
    case Activation::kTanh:
      return std::tanh(sum);
    case Activation::kSigmoid:
      return 1.0 / (1.0 + std::exp(-sum));
    case Activation::kNone:
      break;
  }
  return sum;
}

bool GenericSurrogate::predictInto(const double* inputs,
                                   std::size_t inputCount, double* out,
                                   std::size_t outCount,
                                   Workspace& workspace) const {
  if (!inputs || !out) {
    return false;
  }
  if (valid_) {
    if (inputCount != inputNames_.size() || outCount != outputNames_.size()) {
      return false;
    }
    // Ping-pong between the two workspace buffers: after the first call each
    // resize() is a no-op, so a per-step operator over N elements performs
    // zero allocations.  Every element read below is written first.
    std::vector<double>* current = &workspace.a;
    std::vector<double>* next = &workspace.b;
    current->resize(inputCount);
    for (std::size_t i = 0; i < inputCount; ++i) {
      (*current)[i] = (inputs[i] - inputMean_[i]) / inputStd_[i];
    }
    for (const Layer& layer : layers_) {
      next->resize(layer.rows);
      const double* activations = current->data();
      const double* weights = layer.weights.data();
      double* accumulator = next->data();
      // Every neuron accumulates bias first, then input 0, 1, 2, ... -- the
      // same term order as a per-neuron dot product, so the result is
      // bit-identical while the inner loop stays vectorisable.
      for (std::size_t o = 0; o < layer.rows; ++o) {
        accumulator[o] = layer.bias[o];
      }
      for (std::size_t i = 0; i < layer.cols; ++i) {
        const double activation = activations[i];
        const double* column = weights + i * layer.rows;
        for (std::size_t o = 0; o < layer.rows; ++o) {
          // Explicit single-rounding fused multiply-add: naming the fusion
          // fixes the rounding of every accumulation step instead of leaving
          // it to whether an optimiser chose to contract `a += b * c`.
          accumulator[o] = std::fma(column[o], activation, accumulator[o]);
        }
      }
      for (std::size_t o = 0; o < layer.rows; ++o) {
        accumulator[o] = activate(layer.activation, accumulator[o]);
      }
      std::swap(current, next);
    }
    for (std::size_t o = 0; o < outCount; ++o) {
      // Destandardise with an explicit single-rounding fused multiply-add.
      // Written as `a * std + mean` this is exactly the expression a compiler
      // is free to contract or not; naming the fusion makes the result the
      // same on every compiler instead of an optimiser setting.
      out[o] = std::fma((*current)[o], outputStd_[o], outputMean_[o]);
    }
    return true;
  }
#if defined(TRECH_ENABLE_TORCH)
  if (!module_) {
    return false;
  }
  torch::NoGradGuard noGrad;
  std::vector<float> f(inputs, inputs + inputCount);
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
  if (static_cast<std::size_t>(tensor.numel()) != outCount) {
    return false;  // caller sized `out` from a different output width
  }
  auto acc = tensor.accessor<float, 1>();
  for (std::size_t i = 0; i < outCount; ++i) {
    out[i] = static_cast<double>(acc[i]);
  }
  return true;
#else
  (void)outCount;
  (void)workspace;
  return false;
#endif
}

bool GenericSurrogate::predictVector(const std::vector<double>& inputs,
                                     std::vector<double>* out) const {
  if (!out) {
    return false;
  }
  if (valid_) {
    // One arithmetic implementation: the convenience form allocates its own
    // scratch and delegates, so it can never drift from the batched path.
    Workspace workspace;
    out->resize(outputNames_.size());
    if (!predictInto(inputs.data(), inputs.size(), out->data(), out->size(),
                     workspace)) {
      out->clear();
      return false;
    }
    return true;
  }
#if defined(TRECH_ENABLE_TORCH)
  if (!module_) {
    return false;
  }
  // A positional-only TorchScript module carries no declared output width, so
  // the vector form sizes itself from the returned tensor.
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

GenericSurrogate::Coverage GenericSurrogate::coverage(
    const std::unordered_map<std::string, double>& inputs) const {
  // Build the positional layout predict() would use (missing inputs -> 0) and
  // delegate, so the named and positional coverage forms cannot drift apart.
  std::vector<double> x(inputNames_.size(), 0.0);
  for (std::size_t i = 0; i < inputNames_.size(); ++i) {
    const auto it = inputs.find(inputNames_[i]);
    if (it != inputs.end()) {
      x[i] = it->second;
    }
  }
  return coverageVector(x);
}

GenericSurrogate::Coverage GenericSurrogate::coverageVector(
    const std::vector<double>& inputs) const {
  Coverage cov;
  cov.domainMeasured = domainMeasured_;
  if (!valid_) {
    // A positional-only model (raw .pt) carries no named domain; report
    // in-domain rather than fabricating a signal we cannot ground.
    return cov;
  }
  for (std::size_t i = 0; i < inputNames_.size(); ++i) {
    const double x = (i < inputs.size()) ? inputs[i] : 0.0;  // missing -> 0
    const double z = (x - inputMean_[i]) / inputStd_[i];  // std_ floored at load
    const double absZ = std::abs(z);
    if (absZ > cov.maxStandardizedDeviation) {
      cov.maxStandardizedDeviation = absZ;
    }
    const double radius = (i < inputDomainRadius_.size())
                              ? inputDomainRadius_[i]
                              : kDefaultStandardizedDomainRadius;
    const double over = absZ - radius;
    if (over > 1e-9) {  // tolerance so float noise on a constant feature is safe
      cov.outOfDomainInputs.push_back(inputNames_[i]);
      if (over > cov.extrapolation) {
        cov.extrapolation = over;
      }
    }

    // Starved-region check: within the trained range but in an unpopulated bin
    // (a hole the model interpolated through). Only when an occupancy histogram
    // is carried; a genuinely out-of-range value is already out-of-domain above.
    if (occupancyBins_ > 0 && i < occupancyCounts_.size() &&
        i < inputMin_.size() && i < inputMax_.size()) {
      const double lo = inputMin_[i];
      const double hi = inputMax_[i];
      if (hi > lo && x >= lo && x <= hi) {
        int bin = static_cast<int>((x - lo) / (hi - lo) * occupancyBins_);
        if (bin >= occupancyBins_) bin = occupancyBins_ - 1;  // x==hi edge
        if (bin < 0) bin = 0;
        if (bin < static_cast<int>(occupancyCounts_[i].size()) &&
            occupancyCounts_[i][bin] == 0) {
          cov.starvedInputs.push_back(inputNames_[i]);
        }
      }
    }
  }
  cov.inDomain = cov.outOfDomainInputs.empty();
  std::sort(cov.outOfDomainInputs.begin(), cov.outOfDomainInputs.end());
  std::sort(cov.starvedInputs.begin(), cov.starvedInputs.end());

  // Joint starvation: distance in standardized space to the nearest training
  // region the model carries.  This is the check the two per-feature ones
  // structurally cannot make -- a point inside every feature's range can still
  // sit in a hole between the clusters training actually covered.  Skipped
  // entirely (and reported unmeasured) for a model with no joint reference, so
  // it costs nothing for models that do not carry one.
  if (jointCenterCount_ > 0 && !inputNames_.empty()) {
    const std::size_t nIn = inputNames_.size();
    // Tolerance so a training point sitting exactly on the covering radius is
    // not flagged by float noise.
    const double accept = jointRadius_ * (1.0 + 1e-9) + 1e-12;
    const double acceptSquared = accept * accept;
    double best = std::numeric_limits<double>::infinity();
    bool covered = false;
    for (std::size_t c = 0; c < jointCenterCount_ && !covered; ++c) {
      const double* center = jointCenters_.data() + c * nIn;
      double sum = 0.0;
      for (std::size_t i = 0; i < nIn; ++i) {
        const double x = (i < inputs.size()) ? inputs[i] : 0.0;  // missing -> 0
        const double d = (x - inputMean_[i]) / inputStd_[i] - center[i];
        sum += d * d;
        if (sum >= best) {
          break;  // this center cannot win; stop before finishing the row
        }
      }
      if (sum < best) {
        best = sum;
        // The VERDICT only needs one covering center, so stop as soon as one is
        // found: the expensive full scan is reserved for the starved case,
        // which is the one worth measuring exactly.  Centers are exported in
        // farthest-point order from the training mean, so a typical
        // in-distribution point matches an early one.
        covered = sum <= acceptSquared;
      }
    }
    cov.jointMeasured = true;
    cov.jointRadius = jointRadius_;
    cov.jointDistance = std::sqrt(best);
    cov.jointStarved = !covered;
  }
  return cov;
}

}  // namespace trech::ml
