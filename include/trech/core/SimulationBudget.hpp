#pragma once

#include <chrono>

namespace trech {

// Runtime scheduling only: never estimates physics accuracy. The next event
// must fit the remaining measured budget; one full event is always allowed.
class SimulationBudget {
 public:
  explicit SimulationBudget(double seconds) : limit_(seconds) {}
  void begin();
  bool finishEvent();
  bool observeElapsed(double elapsed);
  double elapsed() const;
  bool exhausted() const { return exhausted_; }
 private:
  double limit_;
  double previous_ = 0.0;
  double eventSeconds_ = 0.0;
  bool exhausted_ = false;
  std::chrono::steady_clock::time_point started_;
};

} // namespace trech
