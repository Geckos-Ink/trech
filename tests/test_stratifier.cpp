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

  return 0;
}
