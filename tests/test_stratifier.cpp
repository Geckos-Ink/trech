#include "trech/core/Config.hpp"
#include "trech/ml/FeaturePipeline.hpp"
#include "trech/ml/Stratifier.hpp"

#include <iostream>

namespace {

int expect(bool condition, const char* message) {
  if (!condition) {
    std::cerr << message << "\n";
    return 1;
  }
  return 0;
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

  return 0;
}
