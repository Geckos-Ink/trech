#pragma once

#include <algorithm>
#include <cstddef>
#include <cstdint>
#include <limits>
#include <string>
#include <vector>

#include "trech/ml/GenericSurrogate.hpp"
#include "trech/ml/ScaleCascade.hpp"

namespace trech::ml {

// Domain routing: dynamic, unnamed grouping of elements by the trained domains
// of the models that compete to describe them, decided band by band up the
// scale ladder.
//
// A batched operator (StateEvolution, DiscreteTransition) normally runs every
// selected stage on every element of its kind, and kinds are labels a scenario
// author writes. In routing mode the population is not labelled. Stages that
// sit at the SAME scale band and produce at least one SAME output are rivals:
// alternative descriptions of that quantity. For each element, a rival stage
// runs only when its measured training domain covers the element's current
// context -- the element's own state and aux facts plus the intermediates the
// lower bands just produced for it -- so the decision at the meso band depends
// on what the nano band inferred for that element. Rivals that were trained on
// the same regime both cover and both contribute, as cooperating stages always
// did; alternative laws with separate domains split the population; an element
// no rival covers is left untouched by that quantity and counted, never pushed
// through a law trained elsewhere. Stages without a rival run as before.
//
// An element's group is the ordered list of rival stages that covered it: its
// path through the ladder. Groups carry no name -- only a content-derived id
// ("d" + 8 hex digits of FNV-1a over the path) that is stable across calls,
// ticks and runs, and the path itself for anyone who wants to read it.
//
// Coverage is the model's own check (GenericSurrogate::coverageVector): inside
// the per-input domain radius (the measured training hull when the model
// carries `input_domain`, the documented default otherwise), not jointly
// starved when the model carries a joint reference, and -- when the model
// carries a `routing_domain` -- every routing feature (a per-element fact the
// law does not read, such as the phase fraction that separated its training
// population) inside its measured range. Nothing here is physics.
//
// Measured ranges come from finite samples, so neighbouring regimes leave thin
// gaps at their boundary. An element no rival covers but that lies inside the
// rivals' combined envelope (per feature, the union of their measured ranges)
// is in such a gap: the single nearest rival runs on it (smallest overflow in
// each model's own scale units) and it is counted as `elementsNearest`; the
// stage trace still reports it as an out-of-domain inference. An element
// outside the envelope belongs to no trained regime and is left untouched.

struct DomainRouterStage {
  std::string name;
  const GenericSurrogate* model = nullptr;
  DimensionScale scale = DimensionScale::kUnscaled;
  std::vector<std::string> outputs;
  bool routable = true;  // false: kind-bound or unplanned, never a rival
};

struct DomainRivalSet {
  DimensionScale scale = DimensionScale::kUnscaled;
  std::vector<std::string> models;              // members, execution order
  std::vector<bool> domainMeasured;             // per member
  std::vector<std::size_t> elementsCovered;     // per member
  std::size_t elementsUncovered = 0;            // outside every member and the envelope
  std::size_t elementsNearest = 0;              // in a gap: nearest member ran
  std::size_t elementsOverlapping = 0;          // >= 2 members covered
  std::size_t elementsUnscorable = 0;           // no member had its inputs
};

struct DomainGroup {
  std::string id;
  std::vector<std::string> path;  // covering rival stages, execution order
  std::size_t elements = 0;
};

struct DomainRouting {
  bool active = false;                    // at least one rival set exists
  std::vector<DomainRivalSet> sets;
  std::vector<DomainGroup> groups;        // sorted by id
  std::vector<std::size_t> elementGroup;  // index into groups, per element
};

// Stable id of a path ("d" + FNV-1a-32 hex of the joined names).
std::string domainGroupId(const std::vector<std::string>& path);

class DomainRouter {
 public:
  static constexpr std::size_t kNoSet = std::numeric_limits<std::size_t>::max();

  // Plan once per call, over the stages in EXECUTION order.
  void plan(const std::vector<DomainRouterStage>& stages, std::size_t elementCount);
  bool active() const { return !sets_.empty(); }
  std::size_t setOf(std::size_t stage) const {
    return stage < setOf_.size() ? setOf_[stage] : kNoSet;
  }

  void beginElement();
  // Whether `stage` may run for the current element. The first time a rival
  // set is reached for an element, every member is checked: `fill(member, x)`
  // writes that member's input vector and returns false when an input is not
  // available yet. `workspace` is the caller's scratch (only read/written
  // during the check).
  //  `value(name, v)` writes a per-element fact (state, aux or shared) and
  // returns false when the element has none; it serves routing features.
  template <class Fill, class Value>
  bool admits(std::size_t stage, Fill&& fill, Value&& value,
              GenericSurrogate::Workspace& workspace);
  void endElement(std::size_t element);
  DomainRouting finish();

 private:
  struct Verdict {
    bool scorable = false;
    bool covered = false;
    double distance = 0.0;  // overflow beyond the member's own ranges, scale units
  };
  struct EnvelopeFeature {
    std::string name;
    double lo = 0.0;
    double hi = 0.0;
  };
  void decide(std::size_t set, const std::vector<Verdict>& verdicts, bool inEnvelope);
  void noteValue(const std::string& name, double v);

  std::vector<std::vector<EnvelopeFeature>> envelope_;  // per set
  std::vector<std::pair<std::string, double>> values_;  // current element, current set

  std::vector<DomainRouterStage> stages_;
  std::vector<std::size_t> setOf_;
  std::vector<std::vector<std::size_t>> members_;  // stage indices per set
  std::vector<DomainRivalSet> sets_;
  // Per element: 0 = not decided, 1 = decided. And per stage: admitted?
  std::vector<unsigned char> decided_;
  std::vector<unsigned char> admitted_;
  std::vector<std::string> path_;
  std::vector<std::vector<std::string>> groupPaths_;
  std::vector<std::size_t> groupCounts_;
  std::vector<std::size_t> elementGroup_;
  std::vector<double> x_;
};

template <class Fill, class Value>
bool DomainRouter::admits(std::size_t stage, Fill&& fill, Value&& value,
                          GenericSurrogate::Workspace& workspace) {
  const std::size_t set = setOf(stage);
  if (set == kNoSet) return true;
  if (!decided_[set]) {
    const std::vector<std::size_t>& members = members_[set];
    std::vector<Verdict> verdicts(members.size());
    values_.clear();
    for (std::size_t m = 0; m < members.size(); ++m) {
      const GenericSurrogate& model = *stages_[members[m]].model;
      x_.assign(model.inputNames().size(), 0.0);
      if (!fill(members[m], x_)) continue;
      const GenericSurrogate::RoutingDomain& routing = model.routingDomain();
      double routingOverflow = 0.0;
      bool routable = true;
      for (std::size_t f = 0; f < routing.features.size(); ++f) {
        double v = 0.0;
        if (!value(routing.features[f], v)) {
          routable = false;
          break;
        }
        noteValue(routing.features[f], v);
        const double below = routing.min[f] - v;
        const double above = v - routing.max[f];
        routingOverflow += std::max(0.0, std::max(below, above)) / routing.scale[f];
      }
      if (!routable) continue;
      for (std::size_t i = 0; i < x_.size(); ++i) noteValue(model.inputNames()[i], x_[i]);
      const GenericSurrogate::Coverage cov = model.coverageVector(x_, workspace);
      const bool jointStarved = cov.jointMeasured && cov.jointStarved;
      Verdict& verdict = verdicts[m];
      verdict.scorable = true;
      verdict.covered = cov.inDomain && !jointStarved && routingOverflow == 0.0;
      verdict.distance = cov.extrapolation + routingOverflow;
      if (jointStarved && cov.jointRadius > 0.0) {
        verdict.distance += (cov.jointDistance - cov.jointRadius) / cov.jointRadius;
      }
    }
    bool inEnvelope = true;
    for (const EnvelopeFeature& feature : envelope_[set]) {
      for (const auto& [name, v] : values_) {
        if (name == feature.name && (v < feature.lo || v > feature.hi)) inEnvelope = false;
      }
    }
    decide(set, verdicts, inEnvelope);
  }
  return admitted_[stage] != 0;
}

// Rival arbitration (routing only). Where two or more rivals of one set
// covered an element, their outputs are either alternative descriptions of one
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
struct RivalCandidates {
  std::size_t set = 0;                  // index into the result's routing.sets
  std::vector<std::string> members;     // rival stage names, execution order
  std::vector<std::size_t> fields;      // indices into the caller's arbitrated names
  std::vector<std::size_t> elements;    // elements covered by >= 2 members
  // [element][candidate][field], candidate = member index, then members.size()
  // = the cooperating combination. NaN where the member did not run.
  std::vector<double> totals;
  std::vector<double> extrapolation;    // [element][member], NaN when it did not run
  // Per element: candidate index (members.size() = the combination), -1 = unchanged.
  std::vector<int> choice;
  std::size_t candidates() const { return members.size() + 1; }
};

}  // namespace trech::ml
