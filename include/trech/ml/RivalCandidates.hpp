#pragma once

#include <cstddef>
#include <string>
#include <vector>

namespace trech::ml {

// Rival arbitration. Where two or more rivals of one set (same scale band,
// a shared output) produced a value for an element, their outputs are either alternative descriptions of one
// quantity (choose one) or cooperating contributions (combine them); a model
// alone cannot say which. A batched operator collects, per such set and
// element, the value each candidate would give -- every rival alone and their
// cooperating combination -- before applying anything, and hands them to the
// caller's `arbitrateRivals` callback (the engine's MethodArbiter, fed with
// evidence the caller holds). The callback writes `choice`; the operator then
// applies the chosen candidate. Without a callback, or with choice -1, the
// operator behaves exactly as before arbitration existed.
//   StateEvolution:     values = total rate per rated field; combination = sum.
//   DiscreteTransition: values = per-channel transition probability for the
//                       step; combination = base + every rival's change.
//   ScaleCascade:       values = each shared output (one context = one
//                       element); combination = the ensemble mean.
struct RivalCandidates {
  std::size_t set = 0;                  // index of the set in the operator's report
  std::vector<std::string> members;     // rival stage names, execution order
  std::vector<std::size_t> fields;      // indices into the caller's arbitrated names
  std::vector<std::size_t> elements;    // elements covered by >= 2 members
  // [element][candidate][field], candidate = member index, then members.size()
  // = the cooperating combination. NaN where the member did not run.
  std::vector<double> totals;
  std::vector<double> extrapolation;    // [element][member], NaN when it did not run
  // Optional per-set context (fixed names per set): when non-empty, the
  // arbiter reads these instead of the caller's per-element features.
  std::vector<std::string> featureNames;
  std::vector<double> features;         // [element in `elements` order][feature]
  // Per element: candidate index (members.size() = the combination), -1 = unchanged.
  std::vector<int> choice;
  std::size_t candidates() const { return members.size() + 1; }
};

}  // namespace trech::ml
