#pragma once

#include "trech/ml/MethodArbiter.hpp"
#include "trech/ml/StateEvolution.hpp"

#include <cstdint>
#include <map>
#include <memory>
#include <string>
#include <vector>

#include <nlohmann/json.hpp>

namespace trech::ml {

// Evidence-driven choice among overlapping rival operators (StateEvolution
// routing). One persistent MethodArbiter per rival set (keyed by its members
// and rated fields, so no caller names it) learns, per context domain, whether
// one rival alone or their cooperating sum reproduces the reference rates.
//
// Candidates: every rival alone, then "cooperating_sum" (the pre-arbitration
// behaviour, also the fallback). Context: the element's declared state fields
// and aux facts plus each rival's extrapolation distance. A call with a
// reference (per element and field, total d_f/dt) grades and learns; a call
// without one applies what was learned, but only once the evidence has
// separated the candidates. With no arbiter yet and no reference nothing
// changes, so existing runs stay byte-identical.
class RivalArbitration {
 public:
  struct Call {
    std::vector<std::string> fieldNames;    // declared fields, request order
    std::vector<std::string> featureNames;  // per-element facts, fixed per call shape
    std::vector<double> features;           // [element][feature] for every element of the call
    std::vector<double> reference;          // [element][field] total rates; empty = ungraded
    std::size_t minElements = 16;
    std::uint64_t seed = 0;
  };

  // Writes `choice` into every set; returns one report per set (empty array when nothing ran).
  nlohmann::json arbitrate(std::vector<RivalCandidates>& sets, const Call& call);
  // Run summary of every arbiter, keyed by rival set.
  nlohmann::json summary() const;
  bool empty() const { return arbiters_.empty(); }

  static constexpr const char* kSum = "cooperating_sum";

 private:
  struct Entry {
    std::unique_ptr<MethodArbiter> arbiter;
    std::vector<std::string> fields;
    std::vector<double> scale;  // per rated field: largest |reference| seen
    long calls = 0;
  };
  std::map<std::string, Entry> arbiters_;
};

}  // namespace trech::ml
