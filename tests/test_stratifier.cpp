#include "trech/core/Config.hpp"
#include "trech/ml/FeaturePipeline.hpp"
#include "trech/ml/Stratifier.hpp"
#include "trech/ml/TorchScriptStub.hpp"

#include <cmath>
#include <cstdio>
#include <fstream>
#include <iostream>
#include <sstream>
#include <string>

namespace {

int expect(bool condition, const char* message) {
  if (!condition) {
    std::cerr << message << "\n";
    return 1;
  }
  return 0;
}

// Serialize a logistic stratifier model JSON over the canonical feature
// schema (trech_event_features_v1).  Only the total_edep_mev weight is
// non-zero so the expected sigmoid is hand-computable.
std::string makeLogisticJson(bool correctFeatureOrder) {
  const trech::ml::FeaturePipeline pipeline;
  const auto names = pipeline.FeatureNames();
  std::ostringstream os;
  os << "{\"model\":\"logistic_stratifier_v1\","
     << "\"feature_schema\":\"trech_event_features_v1\","
     << "\"feature_names\":[";
  for (std::size_t i = 0; i < names.size(); ++i) {
    const std::string name =
        (!correctFeatureOrder && i == 0) ? "bogus_feature" : names[i];
    os << (i ? "," : "") << "\"" << name << "\"";
  }
  os << "],\"weights\":[2";
  for (std::size_t i = 1; i < names.size(); ++i) os << ",0";
  os << "],\"mean\":[1";
  for (std::size_t i = 1; i < names.size(); ++i) os << ",0";
  os << "],\"std\":[1";
  for (std::size_t i = 1; i < names.size(); ++i) os << ",1";
  os << "],\"bias\":0.0,\"threshold\":0.5}";
  return os.str();
}

std::string writeTemp(const std::string& contents, const std::string& name) {
  const std::string path = std::string("./") + name;
  std::ofstream out(path);
  out << contents;
  out.close();
  return path;
}

} // namespace

int main() {
  trech::StratifyConfig cfg;
  cfg.enable = true;
  cfg.edepMeVThreshold = 5.0;
  cfg.totalTrackCountThreshold = 3;
  cfg.labelPredictable = "ok";
  cfg.labelExceptional = "alert";
  cfg.labelUnclassified = "skip";

  trech::ml::EventStratifier stratifier(cfg);

  trech::ml::EventFeatures features;
  features.totalEdepMeV = 1.0;
  features.totalTrackCount = 2;

  auto result = stratifier.Evaluate(features);
  if (expect(result.label == "ok", "Expected predictable label.")) {
    return 1;
  }
  if (expect(!result.exceptional, "Expected predictable to be non-exceptional.")) {
    return 1;
  }

  features.totalTrackCount = 4;
  result = stratifier.Evaluate(features);
  if (expect(result.label == "alert", "Expected exceptional label.")) {
    return 1;
  }
  if (expect(result.exceptional, "Expected exceptional flag.")) {
    return 1;
  }
  if (expect(result.reason == "track_count_threshold",
             "Expected track_count_threshold reason.")) {
    return 1;
  }

  trech::ml::FeaturePipeline pipeline;
  const auto vec = pipeline.ToVector(features);
  const auto names = pipeline.FeatureNames();
  if (expect(vec.size() == names.size(), "Feature names/vector size mismatch.")) {
    return 1;
  }

  trech::StratifyConfig modelCfg = cfg;
  modelCfg.modelPath = "models/stratify.pt";
  trech::DeterminismConfig strictDeterminism;
  strictDeterminism.mode = "strict";
  trech::ml::EventStratifier strictStratifier(modelCfg, strictDeterminism);
  if (expect(!strictStratifier.predictiveModeEnabled(),
             "Strict mode should disable predictive model path usage.")) {
    return 1;
  }
  if (expect(strictStratifier.modelConfigured(),
             "Strict mode should still report configured model metadata.")) {
    return 1;
  }
  if (expect(!strictStratifier.modelLoaded(),
             "Strict mode should not load the model.")) {
    return 1;
  }

  trech::DeterminismConfig predictiveDeterminism;
  predictiveDeterminism.mode = "predictive";
  trech::ml::EventStratifier predictiveStratifier(modelCfg, predictiveDeterminism);
  if (expect(predictiveStratifier.predictiveModeEnabled(),
             "Predictive mode should enable model inference path.")) {
    return 1;
  }

  // LibTorch-free logistic .json backend: p = sigmoid(2*(edep - 1)).
  const std::string goodPath =
      writeTemp(makeLogisticJson(true), "test_stratify_logistic.json");
  trech::ml::TorchScriptStub logisticModel;
  logisticModel.SetLabels("ok", "alert");
  if (expect(logisticModel.Load(goodPath),
             "Logistic json model should load without LibTorch.")) {
    return 1;
  }
  const trech::ml::FeaturePipeline logisticPipeline;
  trech::ml::EventFeatures hot;
  hot.totalEdepMeV = 2.0;  // logit = 2*(2-1) = 2 -> p ~ 0.881 -> exceptional
  std::string label;
  float score = -1.0f;
  if (expect(logisticModel.PredictLabel(logisticPipeline.ToVector(hot), &label,
                                        &score),
             "Logistic PredictLabel should succeed.")) {
    return 1;
  }
  if (expect(label == "alert", "Logistic model should label hot event alert.")) {
    return 1;
  }
  if (expect(std::abs(score - 0.880797f) < 1e-4f,
             "Logistic score should equal sigmoid(2).")) {
    return 1;
  }
  trech::ml::EventFeatures cold;
  cold.totalEdepMeV = 0.5;  // logit = -1 -> p ~ 0.269 -> predictable
  if (expect(logisticModel.PredictLabel(logisticPipeline.ToVector(cold), &label),
             "Logistic PredictLabel (cold) should succeed.")) {
    return 1;
  }
  if (expect(label == "ok", "Logistic model should label cold event ok.")) {
    return 1;
  }

  // The stratifier consumes the json model in predictive mode: source "model".
  trech::StratifyConfig jsonCfg = cfg;
  jsonCfg.modelPath = goodPath;
  trech::ml::EventStratifier jsonStratifier(jsonCfg, predictiveDeterminism);
  if (expect(jsonStratifier.modelLoaded(),
             "Predictive stratifier should load the logistic json model.")) {
    return 1;
  }
  auto modelResult = jsonStratifier.Evaluate(hot);
  if (expect(modelResult.source == "model",
             "Stratify source should be 'model' with a loaded json model.")) {
    return 1;
  }
  if (expect(modelResult.label == "alert" && modelResult.exceptional,
             "Stratifier should propagate the logistic exceptional label.")) {
    return 1;
  }

  // Feature-order mismatch must fail to load and fall back to thresholds.
  const std::string badPath =
      writeTemp(makeLogisticJson(false), "test_stratify_logistic_bad.json");
  trech::StratifyConfig badCfg = cfg;
  badCfg.modelPath = badPath;
  trech::ml::EventStratifier badStratifier(badCfg, predictiveDeterminism);
  if (expect(!badStratifier.modelLoaded(),
             "Wrong feature order should fail the json model load.")) {
    return 1;
  }
  auto fallbackResult = badStratifier.Evaluate(hot);
  if (expect(fallbackResult.source == "thresholds",
             "Failed model load should fall back to threshold stratification.")) {
    return 1;
  }

  std::remove(goodPath.c_str());
  std::remove(badPath.c_str());

  return 0;
}
