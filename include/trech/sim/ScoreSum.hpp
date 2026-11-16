#pragma once

#include "trech/sim/ExactSum.hpp"
#include "G4VAccumulable.hh"

#include <memory>

class G4AccumulableManager;

namespace trech::sim {

// Retain ordinary addition on the serial and predictive paths. Strict parallel
// workers merge their exact sums before the master reads a rounded score.
class ScoreSum final : public G4VAccumulable {
public:
  void Register(G4AccumulableManager* manager, bool exact);

  void operator+=(double value) {
    if (exact_) exact_->add(value);
    else sum_ += value;
  }

  double GetValue() const { return exact_ ? exact_->value() : sum_; }

  void Merge(const G4VAccumulable& other) override {
    const auto& worker = static_cast<const ScoreSum&>(other);
    if (exact_) exact_->merge(*worker.exact_);
    else sum_ += worker.sum_;
  }

  void Reset() override {
    if (exact_) *exact_ = {};
    sum_ = 0.0;
  }

private:
  std::unique_ptr<ExactSum> exact_;
  double sum_ = 0.0;
};

} // namespace trech::sim
