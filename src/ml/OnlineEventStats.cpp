#include "trech/ml/OnlineEventStats.hpp"
#include "trech/ml/FeaturePipeline.hpp"

#if defined(TRECH_ENABLE_TORCH)
#include <torch/torch.h>
#endif

#include <algorithm>
#include <cmath>
#include <limits>

namespace trech::ml {

struct OnlineEventStats::Impl {
  long long count = 0;
  std::vector<double> mean;
  std::vector<double> m2;
  std::vector<double> minValue;
  std::vector<double> maxValue;
#if defined(TRECH_ENABLE_TORCH)
  // Mirror tensor accumulators for vectorized downstream consumers.
  torch::Tensor tensorMean;
  torch::Tensor tensorM2;
#endif

  void resize(std::size_t n) {
    mean.assign(n, 0.0);
    m2.assign(n, 0.0);
    minValue.assign(n, std::numeric_limits<double>::infinity());
    maxValue.assign(n, -std::numeric_limits<double>::infinity());
#if defined(TRECH_ENABLE_TORCH)
    tensorMean = torch::zeros({static_cast<long>(n)}, torch::kFloat64);
    tensorM2 = torch::zeros({static_cast<long>(n)}, torch::kFloat64);
#endif
  }
};

OnlineEventStats::OnlineEventStats()
    : OnlineEventStats(FeaturePipeline{}.FeatureNames()) {}

OnlineEventStats::OnlineEventStats(const std::vector<std::string>& featureNames)
    : impl_(std::make_unique<Impl>()), featureNames_(featureNames) {
  impl_->resize(featureNames_.size());
}

OnlineEventStats::~OnlineEventStats() = default;

void OnlineEventStats::update(const EventFeatures& features) {
  const FeaturePipeline pipeline;
  update(pipeline.ToVector(features));
}

void OnlineEventStats::update(const std::vector<float>& values) {
  if (!impl_) {
    return;
  }
  if (values.size() != impl_->mean.size()) {
    // Schema mismatch — skip update to avoid corrupting moments.
    return;
  }
  ++impl_->count;
  for (std::size_t i = 0; i < values.size(); ++i) {
    const double x = static_cast<double>(values[i]);
    const double delta = x - impl_->mean[i];
    impl_->mean[i] += delta / static_cast<double>(impl_->count);
    const double delta2 = x - impl_->mean[i];
    impl_->m2[i] += delta * delta2;
    if (x < impl_->minValue[i]) {
      impl_->minValue[i] = x;
    }
    if (x > impl_->maxValue[i]) {
      impl_->maxValue[i] = x;
    }
  }
#if defined(TRECH_ENABLE_TORCH)
  // Vectorized mirror: same Welford update but on tensors.  This is a small
  // amount of duplicated math but it gives Torch-aware consumers (e.g., a
  // future density estimator) tensor handles without copying out of the
  // scalar buffers.
  const auto n = impl_->count;
  auto x_tensor = torch::from_blob(
      const_cast<float*>(values.data()), {static_cast<long>(values.size())},
      torch::kFloat32).to(torch::kFloat64).clone();
  auto delta = x_tensor - impl_->tensorMean;
  impl_->tensorMean += delta / static_cast<double>(n);
  auto delta2 = x_tensor - impl_->tensorMean;
  impl_->tensorM2 += delta * delta2;
#endif
}

long long OnlineEventStats::count() const {
  return impl_ ? impl_->count : 0;
}

std::vector<OnlineFeatureMoments> OnlineEventStats::moments() const {
  std::vector<OnlineFeatureMoments> out;
  if (!impl_) {
    return out;
  }
  out.reserve(featureNames_.size());
  for (std::size_t i = 0; i < featureNames_.size(); ++i) {
    OnlineFeatureMoments m;
    m.name = featureNames_[i];
    m.count = impl_->count;
    m.mean = impl_->mean[i];
    if (impl_->count > 1) {
      m.variance = impl_->m2[i] / static_cast<double>(impl_->count - 1);
      m.stddev = std::sqrt(std::max(0.0, m.variance));
    }
    m.min = std::isfinite(impl_->minValue[i]) ? impl_->minValue[i] : 0.0;
    m.max = std::isfinite(impl_->maxValue[i]) ? impl_->maxValue[i] : 0.0;
    out.push_back(std::move(m));
  }
  return out;
}

bool OnlineEventStats::torchEnabled() const {
#if defined(TRECH_ENABLE_TORCH)
  return true;
#else
  return false;
#endif
}

}  // namespace trech::ml
