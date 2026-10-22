#include "trech/core/SimulationBudget.hpp"

#include <cmath>

namespace trech {
void SimulationBudget::begin() {
  previous_ = eventSeconds_ = 0.0;
  exhausted_ = false;
  started_ = std::chrono::steady_clock::now();
}

double SimulationBudget::elapsed() const {
  return std::chrono::duration<double>(std::chrono::steady_clock::now() - started_).count();
}

bool SimulationBudget::finishEvent() { return observeElapsed(elapsed()); }

bool SimulationBudget::observeElapsed(double elapsedSeconds) {
  if (!std::isfinite(elapsedSeconds) || elapsedSeconds < previous_) return exhausted_;
  const double event = elapsedSeconds - previous_;
  eventSeconds_ = eventSeconds_ > 0.0 ? 0.35 * event + 0.65 * eventSeconds_ : event;
  previous_ = elapsedSeconds;
  exhausted_ = exhausted_ || (limit_ > 0.0 && elapsedSeconds + eventSeconds_ >= limit_);
  return exhausted_;
}
} // namespace trech
