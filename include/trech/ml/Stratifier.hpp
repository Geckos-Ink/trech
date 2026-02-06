#pragma once

#include "trech/core/Config.hpp"
#include "trech/ml/EventFeatures.hpp"
#include "trech/ml/FeaturePipeline.hpp"
#include "trech/ml/TorchScriptStub.hpp"

#include <string>

namespace trech::ml {

struct StratifyResult {
  std::string label;
  std::string reason;
  std::string source;
  bool exceptional = false;
};

class EventStratifier {
public:
  explicit EventStratifier(const StratifyConfig& cfg,
                           const DeterminismConfig& determinism = {});
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
