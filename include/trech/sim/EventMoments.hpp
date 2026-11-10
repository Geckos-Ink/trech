#pragma once

// Run-level shape summary of a per-event scalar (the event energy deposit),
// built from additive power sums so it merges across worker threads through
// ordinary G4Accumulable addition (plus min/max merge modes). Pure and
// Geant4-free so it can be unit tested without a transport build.
//
// These are descriptive statistics of what Geant4 sampled. They are a system
// observable, never a physics law: skewness, excess kurtosis and the
// zero-deposit fraction describe the event distribution's shape (heavy tails,
// pass-through events) that a mean/stddev pair hides.
//
// Population (biased) moments are used so the variance matches the existing
// `system_event_edep_variance_mev2` definition. Central moments are recovered
// from raw sums, which loses precision when the spread is tiny compared with
// the mean; the shape is then reported as undefined rather than as noise.

#include <algorithm>
#include <cmath>
#include <limits>

namespace trech {
namespace sim {
namespace event_moments {

struct PowerSums {
  double count = 0.0;
  double sum1 = 0.0;
  double sum2 = 0.0;
  double sum3 = 0.0;
  double sum4 = 0.0;
  double zeroCount = 0.0;
  double minimum = std::numeric_limits<double>::max();
  double maximum = std::numeric_limits<double>::lowest();
};

struct Summary {
  double mean = 0.0;
  double variance = 0.0;
  double stddev = 0.0;
  double stderrMean = 0.0;
  double skewness = 0.0;
  double excessKurtosis = 0.0;
  double zeroFraction = 0.0;
  double minimum = 0.0;
  double maximum = 0.0;
  // False when there are fewer than three events, the distribution is
  // degenerate (all values equal), or the variance is below the raw-sum
  // cancellation floor. Skewness/kurtosis are then 0 and must not be read.
  bool shapeDefined = false;
};

// Relative floor below which variance recovered from raw sums is dominated by
// floating-point cancellation (variance / mean^2 compared to this value).
inline constexpr double kCancellationFloor = 1e-10;

inline void add(PowerSums& sums, double value) {
  const double v2 = value * value;
  sums.count += 1.0;
  sums.sum1 += value;
  sums.sum2 += v2;
  sums.sum3 += v2 * value;
  sums.sum4 += v2 * v2;
  if (value == 0.0) {
    sums.zeroCount += 1.0;
  }
  sums.minimum = std::min(sums.minimum, value);
  sums.maximum = std::max(sums.maximum, value);
}

// Merge two partial power sums the way G4Accumulable merges worker results:
// additive sums plus minimum/maximum merge modes.
inline PowerSums merge(const PowerSums& a, const PowerSums& b) {
  PowerSums out;
  out.count = a.count + b.count;
  out.sum1 = a.sum1 + b.sum1;
  out.sum2 = a.sum2 + b.sum2;
  out.sum3 = a.sum3 + b.sum3;
  out.sum4 = a.sum4 + b.sum4;
  out.zeroCount = a.zeroCount + b.zeroCount;
  out.minimum = std::min(a.minimum, b.minimum);
  out.maximum = std::max(a.maximum, b.maximum);
  return out;
}

inline Summary summarize(const PowerSums& sums) {
  Summary out;
  const double n = sums.count;
  if (!(n > 0.0)) {
    return out;
  }
  const double m = sums.sum1 / n;
  const double r2 = sums.sum2 / n;
  const double r3 = sums.sum3 / n;
  const double r4 = sums.sum4 / n;
  const double mu2 = std::max(0.0, r2 - m * m);
  out.mean = m;
  out.variance = mu2;
  out.stddev = std::sqrt(mu2);
  out.stderrMean = n > 1.0 ? std::sqrt(mu2 / (n - 1.0)) : 0.0;
  out.zeroFraction = sums.zeroCount / n;
  out.minimum = sums.minimum;
  out.maximum = sums.maximum;

  const double scale = std::max(m * m, std::numeric_limits<double>::min());
  const bool spread = sums.maximum > sums.minimum && mu2 > kCancellationFloor * scale;
  if (n >= 3.0 && spread) {
    const double mu3 = r3 - 3.0 * m * r2 + 2.0 * m * m * m;
    const double mu4 = r4 - 4.0 * m * r3 + 6.0 * m * m * r2 - 3.0 * m * m * m * m;
    const double skew = mu3 / std::pow(mu2, 1.5);
    const double kurt = mu4 / (mu2 * mu2) - 3.0;
    if (std::isfinite(skew) && std::isfinite(kurt)) {
      out.skewness = skew;
      // A population excess kurtosis is bounded below by skew^2 - 2; clamp
      // the rounding residue so the reported pair stays admissible.
      out.excessKurtosis = std::max(kurt, skew * skew - 2.0);
      out.shapeDefined = true;
    }
  }
  return out;
}

// Index of dispersion (variance / mean) of a non-negative count variable such
// as the per-event secondary multiplicity. 1 for a Poisson count, < 1 for a
// sub-Poisson (more regular) count, > 1 for clustered/over-dispersed counts.
// Descriptive only. Returns NaN when the mean is not positive, so callers can
// report it as undefined instead of as 0 or infinity.
inline double dispersionIndex(const Summary& summary) {
  if (!(summary.mean > 0.0) || !std::isfinite(summary.variance)) {
    return std::numeric_limits<double>::quiet_NaN();
  }
  return summary.variance / summary.mean;
}

} // namespace event_moments
} // namespace sim
} // namespace trech
