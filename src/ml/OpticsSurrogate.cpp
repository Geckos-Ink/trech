#include "trech/ml/OpticsSurrogate.hpp"

#if defined(TRECH_ENABLE_TORCH)
#include <torch/script.h>
#include <torch/torch.h>
#endif

#include <algorithm>
#include <fstream>
#include <unordered_map>

#include <nlohmann/json.hpp>

namespace trech::ml {

namespace {

bool endsWith(const std::string& s, const std::string& suffix) {
  return s.size() >= suffix.size() &&
         s.compare(s.size() - suffix.size(), suffix.size(), suffix) == 0;
}

}  // namespace

OpticsSurrogate::OpticsSurrogate() = default;
OpticsSurrogate::~OpticsSurrogate() = default;

// Load a ridge-regression model from JSON. Expected shape:
//   {"model":"ridge_optics_n_v1", "elements":[...], "weights":[...],
//    "mean":[...], "std":[...], "bias":<float>}
// The element list must match kCompositionElements so the feature ordering the
// engine encodes lines up with what the model was trained on.
bool OpticsSurrogate::loadRidgeJson(const std::string& path) {
  ridge_ = RidgeModel{};
  std::ifstream in(path);
  if (!in) {
    note_ = "cannot open ridge json: " + path;
    return false;
  }
  nlohmann::json j;
  try {
    in >> j;
  } catch (const std::exception& e) {
    note_ = std::string("ridge json parse failed: ") + e.what();
    return false;
  }
  const auto n = static_cast<std::size_t>(kInputFeatureCount);
  auto readVec = [&](const char* key, std::vector<double>& out) -> bool {
    if (!j.contains(key) || !j.at(key).is_array() ||
        j.at(key).size() != n) {
      return false;
    }
    out = j.at(key).get<std::vector<double>>();
    return true;
  };
  if (!readVec("weights", ridge_.weights) || !readVec("mean", ridge_.mean) ||
      !readVec("std", ridge_.std)) {
    note_ = "ridge json missing/wrong-length weights|mean|std (need " +
            std::to_string(n) + " features)";
    return false;
  }
  // Guard the element ordering when the file records it.
  if (j.contains("elements") && j.at("elements").is_array()) {
    const auto elems = j.at("elements").get<std::vector<std::string>>();
    if (elems.size() != kCompositionElements.size()) {
      note_ = "ridge json element list length mismatch";
      return false;
    }
    for (std::size_t i = 0; i < elems.size(); ++i) {
      if (elems[i] != kCompositionElements[i]) {
        note_ = "ridge json element order mismatch at index " +
                std::to_string(i);
        return false;
      }
    }
  }
  for (double& s : ridge_.std) {
    if (s < 1e-9) {
      s = 1.0;  // mirror the trainer's zero-variance guard
    }
  }
  ridge_.bias = j.value("bias", 0.0);
  ridge_.valid = true;
  note_ = "ridge model loaded (" + std::to_string(n) + " features)";
  return true;
}

bool OpticsSurrogate::load(const std::string& path) {
  modelPath_ = path;
  note_.clear();
  ridge_ = RidgeModel{};
#if defined(TRECH_ENABLE_TORCH)
  module_.reset();
#endif
  if (modelPath_.empty()) {
    note_ = "empty modelPath";
    return false;
  }
  // A .json model is the LibTorch-free ridge backend; anything else is treated
  // as a TorchScript module (only usable when Torch is built).
  if (endsWith(modelPath_, ".json")) {
    return loadRidgeJson(modelPath_);
  }
#if defined(TRECH_ENABLE_TORCH)
  try {
    module_ = std::make_unique<torch::jit::Module>(torch::jit::load(modelPath_));
    module_->eval();
    note_ = "torchscript model loaded";
    return true;
  } catch (const c10::Error& err) {
    module_.reset();
    note_ = std::string("torch::jit::load failed: ") + err.what();
    return false;
  }
#else
  note_ = "non-json model needs LibTorch, which is off (TRECH_ENABLE_TORCH); "
          "supply a ridge .json model instead";
  return false;
#endif
}

bool OpticsSurrogate::loaded() const {
  if (ridge_.valid) {
    return true;
  }
#if defined(TRECH_ENABLE_TORCH)
  return static_cast<bool>(module_);
#else
  return false;
#endif
}

bool OpticsSurrogate::predict(const std::vector<float>& composition,
                              std::array<float, 3>* out) const {
  if (!out) {
    return false;
  }
  if (composition.size() != static_cast<std::size_t>(kInputFeatureCount)) {
    return false;
  }
  // Ridge backend (no LibTorch): n = bias + sum_i w_i * (x_i - mean_i)/std_i.
  // Predicts n only; absorption/scatter are signalled "not predicted" with a
  // negative sentinel so the caller keeps its own (extractor-derived) values.
  if (ridge_.valid) {
    double n = ridge_.bias;
    for (std::size_t i = 0; i < composition.size(); ++i) {
      n += ridge_.weights[i] *
           ((static_cast<double>(composition[i]) - ridge_.mean[i]) /
            ridge_.std[i]);
    }
    (*out)[0] = static_cast<float>(n);
    (*out)[1] = -1.0f;
    (*out)[2] = -1.0f;
    return true;
  }
#if defined(TRECH_ENABLE_TORCH)
  if (!module_) {
    return false;
  }
  torch::NoGradGuard noGrad;
  auto input = torch::from_blob(const_cast<float*>(composition.data()),
                                {1, static_cast<long>(composition.size())},
                                torch::kFloat32)
                   .clone();
  std::vector<torch::jit::IValue> inputs;
  inputs.emplace_back(input);
  torch::jit::IValue output;
  try {
    output = module_->forward(inputs);
  } catch (const c10::Error&) {
    return false;
  }
  if (!output.isTensor()) {
    return false;
  }
  auto tensor =
      output.toTensor().to(torch::kCPU).to(torch::kFloat32).flatten().contiguous();
  if (tensor.numel() < 3) {
    return false;
  }
  auto accessor = tensor.accessor<float, 1>();
  (*out)[0] = accessor[0];
  (*out)[1] = accessor[1];
  (*out)[2] = accessor[2];
  return true;
#else
  (void)composition;
  return false;
#endif
}

std::vector<float> OpticsSurrogate::encodeComposition(
    const std::vector<std::pair<std::string, double>>& massFractions,
    double densityGcm3) {
  std::vector<float> out(kInputFeatureCount, 0.0f);
  std::unordered_map<std::string, std::size_t> indexFor;
  for (std::size_t i = 0; i < kCompositionElements.size(); ++i) {
    indexFor[kCompositionElements[i]] = i;
  }
  const std::size_t otherIndex = kCompositionElements.size() - 1;
  for (const auto& [name, fraction] : massFractions) {
    const auto it = indexFor.find(name);
    const std::size_t idx = it != indexFor.end() ? it->second : otherIndex;
    out[idx] += static_cast<float>(std::max(0.0, fraction));
  }
  // Renormalize element fractions to sum <= 1.
  double sum = 0.0;
  for (std::size_t i = 0; i + 1 < out.size() - 1; ++i) {
    sum += out[i];
  }
  if (sum > 1.0) {
    for (std::size_t i = 0; i + 1 < out.size() - 1; ++i) {
      out[i] = static_cast<float>(out[i] / sum);
    }
  }
  out.back() = static_cast<float>(densityGcm3);
  return out;
}

}  // namespace trech::ml
