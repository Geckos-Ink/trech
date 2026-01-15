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
  explicit EventStratifier(const StratifyConfig& cfg);
  StratifyResult Evaluate(const EventFeatures& features);

private:
  StratifyResult EvaluateThresholds(const EventFeatures& features) const;

  StratifyConfig cfg_;
  FeaturePipeline pipeline_;
  TorchScriptStub model_;
  bool modelLoaded_ = false;
};

} // namespace trech::ml
