#pragma once

#include "trech/core/Config.hpp"
#include "trech/ml/EventFeatures.hpp"
#include "trech/ml/FeaturePipeline.hpp"
#include "trech/ml/TorchScriptStub.hpp"

#include <string>
#include <memory>

namespace trech::ml {

struct StratifyResult {
  std::string label;
  std::string reason;
  std::string source;
  bool exceptional = false;
};

// Captured once before constructing Geant4 actions. Workers instantiate their
// own classifier from these bytes, never from a path that may have changed.
struct StratifierModelSnapshot {
  std::string path;
  std::string bytes;
  std::string status;
  std::string loadNote;
  std::string contentId;
  std::string sha256;
  std::size_t sizeBytes = 0;
};

std::shared_ptr<const StratifierModelSnapshot> captureStratifierModel(
    const StratifyConfig& cfg, const DeterminismConfig& determinism);

class EventStratifier {
public:
  explicit EventStratifier(const StratifyConfig& cfg,
                           const DeterminismConfig& determinism = {},
                           std::shared_ptr<const StratifierModelSnapshot> snapshot = {});
  StratifyResult Evaluate(const EventFeatures& features);
  bool predictiveModeEnabled() const;
  bool modelConfigured() const;
  bool modelLoaded() const;

private:
  StratifyResult EvaluateThresholds(const EventFeatures& features) const;

  StratifyConfig cfg_;
  DeterminismConfig determinism_;
  FeaturePipeline pipeline_;
  TorchScriptStub model_;
  bool predictiveModeEnabled_ = false;
  bool modelLoaded_ = false;
};

} // namespace trech::ml
