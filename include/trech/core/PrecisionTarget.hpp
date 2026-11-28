#pragma once

#include <cstdint>

namespace trech {

// Statistical stopping rule for a Monte Carlo run (`run.precisionTarget`): after each event the
// engine adds that event's total deposited energy and stops the run once the standard error of
// the mean, relative to the mean, is at most `relativeStderr` (and at least `minEvents` events
// ran). This is the engine's own sampling-error estimate of the run's main tally, the same
// estimator as `system_event_edep_stderr_mev`; it says nothing about the physics model's
// accuracy. A run whose events deposit nothing (mean 0) never reaches it.
//
// Evaluated on the event order, so runs use a serial kernel: the stop is then a pure function
// of the seed and config, and strict runs stay byte-reproducible.
class PrecisionTarget {
 public:
  PrecisionTarget(double relativeStderr, int minEvents)
      : target_(relativeStderr), minEvents_(minEvents) {}
  void begin();
  // Adds one event's tally; returns true once the target is reached (and stays true).
  bool observe(double value);
  bool reached() const { return reached_; }
  std::int64_t events() const { return n_; }
  double mean() const { return mean_; }
  // Standard error of the mean over |mean|; +infinity before two events or with a zero mean.
  double relativeStderr() const;
  double target() const { return target_; }
  int minEvents() const { return minEvents_; }

 private:
  double target_;
  int minEvents_;
  std::int64_t n_ = 0;
  double mean_ = 0.0;
  double m2_ = 0.0;  // Welford sum of squared deviations
  bool reached_ = false;
};

}  // namespace trech
