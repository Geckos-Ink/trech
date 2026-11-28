#include "trech/core/PrecisionTarget.hpp"

#include <cmath>
#include <limits>

namespace trech {

void PrecisionTarget::begin() {
  n_ = 0;
  mean_ = m2_ = 0.0;
  reached_ = false;
}

double PrecisionTarget::relativeStderr() const {
  if (n_ < 2 || mean_ == 0.0) return std::numeric_limits<double>::infinity();
  const double n = static_cast<double>(n_);
  return std::sqrt(m2_ / (n * (n - 1.0))) / std::fabs(mean_);
}

bool PrecisionTarget::observe(double value) {
  if (!std::isfinite(value)) return reached_;  // a non-finite tally never counts as evidence
  ++n_;
  const double delta = value - mean_;
  mean_ += delta / static_cast<double>(n_);
  m2_ += delta * (value - mean_);
  reached_ = reached_ || (n_ >= minEvents_ && relativeStderr() <= target_);
  return reached_;
}

}  // namespace trech
