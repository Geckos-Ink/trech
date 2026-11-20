#pragma once

#include "trech/ml/MethodArbiter.hpp"
#include "trech/ml/RivalCandidates.hpp"

#include <cstdint>
#include <map>
#include <memory>
#include <string>
#include <vector>

#include <nlohmann/json.hpp>

namespace trech::ml {

// Evidence-driven choice among overlapping rival operators (domain routing in
// StateEvolution and DiscreteTransition). One persistent MethodArbiter per
// rival set (keyed by its members and arbitrated names, so no caller names it)
// learns, per context domain, whether one rival alone or their cooperating
// combination reproduces the reference values. Each operator path keeps its
// own RivalArbitration, so evolve and react rivals never share evidence.
//
// Candidates: every rival alone, then the combination (the fallback):
// "cooperating_sum" for ctx.evolve (its pre-arbitration behaviour) and
// ctx.react, "ensemble_mean" for ctx.cascade. Context: the element's declared
// facts plus each rival's extrapolation distance. A call with a reference (per
// element and arbitrated name: a total d_f/dt for ctx.evolve, a per-step
// channel probability for ctx.react, an output value for ctx.cascade) grades and learns; a call without one
// applies what was learned, but only once the evidence has separated the
// candidates. With no arbiter yet and no reference nothing changes, so
// existing runs stay byte-identical.
class RivalArbitration {
 public:
  static constexpr const char* kSum = "cooperating_sum";
  static constexpr const char* kMean = "ensemble_mean";

  struct Call {
    std::vector<std::string> fieldNames;    // arbitrated names (fields, channels), request order
    std::vector<std::string> featureNames;  // per-element facts, fixed per call shape
    std::vector<double> features;           // [element][feature] for every element of the call
    std::vector<double> reference;          // [element][name]; empty = ungraded, NaN skips
    std::size_t minElements = 16;
    std::uint64_t seed = 0;
    // Name of the combination candidate (the operator decides what combining means).
    std::string combination = kSum;
  };

  // Writes `choice` into every set; returns one report per set (empty array when nothing ran).
  nlohmann::json arbitrate(std::vector<RivalCandidates>& sets, const Call& call);
  // Run summary of every arbiter, keyed by rival set.
  nlohmann::json summary() const;
  bool empty() const { return arbiters_.empty(); }

  // Every arbiter of the pool with its key, rated names, scales and call clock
  // (`trech_rival_arbitration_v1`), so a later run can continue or deploy it.
  nlohmann::json exportState(bool includeRows = false) const;
  // Replace the pool with an exported one. A frozen pool selects from what it
  // learned and grades graded calls, but learns nothing and creates no arbiter
  // for a rival set it has not seen (that set stays unchanged).
  void restore(const nlohmann::json& state, bool frozen);
  bool frozen() const { return frozen_; }


 private:
  struct Entry {
    std::unique_ptr<MethodArbiter> arbiter;
    std::vector<std::string> fields;
    std::vector<double> scale;  // per rated field: largest |reference| seen
    std::string combination;
    long calls = 0;
  };
  std::map<std::string, Entry> arbiters_;
  bool frozen_ = false;
};

}  // namespace trech::ml
