#pragma once

#include "trech/ml/EventFeatures.hpp"

#include <string>
#include <vector>

namespace trech::ml {

class FeaturePipeline {
public:
  static constexpr const char* kSchemaId = "trech_event_features_v1";

  std::vector<float> ToVector(const EventFeatures& features) const;
  std::vector<std::string> FeatureNames() const;
};

} // namespace trech::ml
