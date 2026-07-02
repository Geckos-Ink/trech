#include "trech/ml/TorchScriptStub.hpp"

#include "trech/ml/FeaturePipeline.hpp"

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

}  // namespace

void TorchScriptStub::SetLabels(const std::string& predictable, const std::string& exceptional) {
  predictableLabel_ = predictable;
  exceptionalLabel_ = exceptional;
}

// Load a logistic stratifier model from JSON. Expected shape:
//   {"model":"logistic_stratifier_v1",
//    "feature_schema":"trech_event_features_v1",
//    "feature_names":[...], "weights":[...], "mean":[...], "std":[...],
//    "bias":<float>, "threshold":<float in (0,1)>}
// feature_names must match FeaturePipeline::FeatureNames() exactly so the
// vector the engine encodes lines up with what the model was trained on.
bool TorchScriptStub::LoadLogisticJson(const std::string& path) {
  logistic_ = LogisticModel{};
  std::ifstream in(path);
  if (!in) {
    note_ = "cannot open logistic json: " + path;
    return false;
  }
  nlohmann::json j;
  try {
    in >> j;
  } catch (const std::exception& e) {
    note_ = std::string("logistic json parse failed: ") + e.what();
    return false;
  }
  const FeaturePipeline pipeline;
  const auto expectedNames = pipeline.FeatureNames();
  const auto n = expectedNames.size();
  if (j.contains("feature_schema") && j.at("feature_schema").is_string() &&
      j.at("feature_schema").get<std::string>() != FeaturePipeline::kSchemaId) {
    note_ = "logistic json feature_schema mismatch (need " +
            std::string(FeaturePipeline::kSchemaId) + ")";
    return false;
  }
  auto readVec = [&](const char* key, std::vector<double>& out) -> bool {
    if (!j.contains(key) || !j.at(key).is_array() || j.at(key).size() != n) {
      return false;
    }
    out = j.at(key).get<std::vector<double>>();
    return true;
  };
  if (!readVec("weights", logistic_.weights) ||
      !readVec("mean", logistic_.mean) || !readVec("std", logistic_.std)) {
    note_ = "logistic json missing/wrong-length weights|mean|std (need " +
            std::to_string(n) + " features)";
    return false;
  }
  // Guard the feature ordering when the file records it.
  if (j.contains("feature_names") && j.at("feature_names").is_array()) {
    const auto names = j.at("feature_names").get<std::vector<std::string>>();
    if (names.size() != n) {
      note_ = "logistic json feature list length mismatch";
      return false;
    }
    for (std::size_t i = 0; i < n; ++i) {
      if (names[i] != expectedNames[i]) {
        note_ = "logistic json feature order mismatch at index " +
                std::to_string(i);
        return false;
      }
    }
  }
  for (double& s : logistic_.std) {
    if (s < 1e-9) {
      s = 1.0;  // mirror the trainer's zero-variance guard
    }
  }
  logistic_.bias = j.value("bias", 0.0);
  logistic_.threshold = j.value("threshold", 0.5);
  if (!(logistic_.threshold > 0.0 && logistic_.threshold < 1.0)) {
    logistic_.threshold = 0.5;
  }
  logistic_.valid = true;
  note_ = "logistic model loaded (" + std::to_string(n) + " features)";
  return true;
}

bool TorchScriptStub::Load(const std::string& path) {
  modelPath_ = path;
  note_.clear();
  logistic_ = LogisticModel{};
#if defined(TRECH_ENABLE_TORCH)
  module_.reset();
#endif
  if (modelPath_.empty()) {
    note_ = "empty modelPath";
    return false;
  }
  // A .json model is the LibTorch-free logistic backend; anything else is
  // treated as a TorchScript module (only usable when Torch is built).
  if (endsWith(modelPath_, ".json")) {
    return LoadLogisticJson(modelPath_);
  }
#if defined(TRECH_ENABLE_TORCH)
  try {
    module_ = std::make_unique<torch::jit::Module>(torch::jit::load(modelPath_));
    module_->eval();
    note_ = "torchscript model loaded";
  } catch (const c10::Error&) {
    module_.reset();
    note_ = "torch::jit::load failed";
    return false;
  }
  return true;
#else
  note_ = "non-json model needs LibTorch, which is off (TRECH_ENABLE_TORCH); "
          "supply a logistic .json model instead";
  return false;
#endif
}

bool TorchScriptStub::PredictLabel(const std::vector<float>& features,
                                   std::string* outLabel,
                                   float* outScore) const {
  if (!outLabel) {
    return false;
  }
  // Logistic backend (no LibTorch): deterministic standardised sigmoid.
  if (logistic_.valid) {
    if (features.size() != logistic_.weights.size()) {
      return false;
    }
    double logit = logistic_.bias;
    for (std::size_t i = 0; i < features.size(); ++i) {
      logit += logistic_.weights[i] *
               ((static_cast<double>(features[i]) - logistic_.mean[i]) /
                logistic_.std[i]);
    }
    const double p = 1.0 / (1.0 + std::exp(-logit));
    *outLabel = p >= logistic_.threshold ? exceptionalLabel_ : predictableLabel_;
    if (outScore) {
      *outScore = static_cast<float>(p);
    }
    return true;
  }
#if defined(TRECH_ENABLE_TORCH)
  if (!module_ || features.empty()) {
    return false;
  }
  torch::NoGradGuard noGrad;
  auto input = torch::from_blob(const_cast<float*>(features.data()),
                                {1, static_cast<long>(features.size())},
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

  if (output.isString()) {
    *outLabel = output.toStringRef();
    return true;
  }
  if (output.isTensor()) {
    auto tensor =
      output.toTensor().to(torch::kCPU).to(torch::kFloat32).flatten().contiguous();
    if (tensor.numel() == 1) {
      const float score = tensor.item<float>();
      *outLabel = score >= 0.5f ? exceptionalLabel_ : predictableLabel_;
      if (outScore) {
        *outScore = score;
      }
      return true;
    }
    if (tensor.numel() == 2) {
      auto scores = tensor.accessor<float, 1>();
      *outLabel = scores[1] >= scores[0] ? exceptionalLabel_ : predictableLabel_;
      if (outScore) {
        *outScore = scores[1];
      }
      return true;
    }
  }
  return false;
#else
  return false;
#endif
}

const std::string& TorchScriptStub::modelPath() const {
  return modelPath_;
}

} // namespace trech::ml
