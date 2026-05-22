#pragma once

#include "trech/ml/EventFeatures.hpp"

#include <memory>
#include <string>
#include <vector>

namespace trech::ml {

struct OnlineFeatureMoments {
  std::string name;
  double mean = 0.0;
  double variance = 0.0;
  double stddev = 0.0;
  double min = 0.0;
  double max = 0.0;
  long long count = 0;
};

// Running per-feature moments over the FeaturePipeline schema.  Uses Welford's
// online algorithm so the moments are numerically stable for any event count.
// When TRECH_ENABLE_TORCH is on, an additional tensor accumulator (M1, M2)
// runs in parallel so callers can pull a torch::Tensor view directly without
// rebuilding from the scalar fields.  Without Torch the tensor path is
// inactive but the scalar moments are still produced.
class OnlineEventStats {
 public:
  OnlineEventStats();
  explicit OnlineEventStats(const std::vector<std::string>& featureNames);
  ~OnlineEventStats();

  OnlineEventStats(const OnlineEventStats&) = delete;
  OnlineEventStats& operator=(const OnlineEventStats&) = delete;

  void update(const EventFeatures& features);
  void update(const std::vector<float>& values);

  long long count() const;
  std::vector<OnlineFeatureMoments> moments() const;
  const std::vector<std::string>& featureNames() const { return featureNames_; }

  bool torchEnabled() const;

 private:
  struct Impl;
  std::unique_ptr<Impl> impl_;
  std::vector<std::string> featureNames_;
};

}  // namespace trech::ml
