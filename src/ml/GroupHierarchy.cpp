#include "trech/ml/GroupHierarchy.hpp"

#include <algorithm>
#include <cmath>
#include <limits>
#include <map>
#include <tuple>
#include <utility>

#include "trech/ml/GenericSurrogate.hpp"

namespace trech::ml {

namespace {

constexpr double kNaN = std::numeric_limits<double>::quiet_NaN();

// The population one level reads: features are named, element-major.
struct Population {
  std::size_t count = 0;
  std::vector<std::string> names;
  std::vector<double> features;
  bool hasPositions = false;
  std::vector<double> positions;
  std::vector<double> weights;
  std::vector<unsigned char> valid;
  std::vector<unsigned char> inDomain;
  std::vector<unsigned char> starved;
};

enum class Synth { kNone, kPresent, kWeight, kRelX, kRelY, kRelZ };

Synth synthesized(const std::string& name) {
  if (name == "present") return Synth::kPresent;
  if (name == "weight") return Synth::kWeight;
  if (name == "rel_x") return Synth::kRelX;
  if (name == "rel_y") return Synth::kRelY;
  if (name == "rel_z") return Synth::kRelZ;
  return Synth::kNone;
}

const char* groupingName(GroupLevelSpec::Grouping grouping) {
  switch (grouping) {
    case GroupLevelSpec::Grouping::kCell:
      return "cell";
    case GroupLevelSpec::Grouping::kExplicit:
      return "explicit";
    case GroupLevelSpec::Grouping::kAll:
      break;
  }
  return "all";
}

// Lean pair Trech.Methods.Group (formal/Trech/Methods/Group.lean): every element gets one
// parent, and the summed group weights and weighted centroids below keep the level's total
// weight and weighted first moment (for groups of nonzero weight). The run loop below feeds
// each level's groups to the next; liftWeight_eq and liftPos_eq_centroid show that any depth
// equals grouping the base elements once by their composed ancestor, and liftWeight_pos that
// positive base weights never leave a zero-weight (NaN-centroid) group at any depth.
// Partition `pop` into ordered groups. Returns false (with a reason) when the
// grouping cannot be formed from what the population carries.
bool partition(const Population& pop, const GroupLevelSpec& spec,
               const std::array<double, 3>& origin,
               std::vector<std::vector<std::size_t>>* members,
               std::vector<long long>* keys, std::string* reason) {
  members->clear();
  keys->clear();
  if (spec.grouping == GroupLevelSpec::Grouping::kAll) {
    std::vector<std::size_t> all(pop.count);
    for (std::size_t i = 0; i < pop.count; ++i) all[i] = i;
    if (!all.empty()) members->push_back(std::move(all));
    return true;
  }
  if (spec.grouping == GroupLevelSpec::Grouping::kExplicit) {
    if (spec.groupIds.size() != pop.count) {
      *reason = "group_ids_mismatch";
      return false;
    }
    std::map<long long, std::vector<std::size_t>> byId;
    for (std::size_t i = 0; i < pop.count; ++i) byId[spec.groupIds[i]].push_back(i);
    for (auto& [id, list] : byId) {
      keys->push_back(id);
      members->push_back(std::move(list));
    }
    return true;
  }
  if (!pop.hasPositions) {
    *reason = "positions_required";
    return false;
  }
  using Cell = std::tuple<long long, long long, long long>;
  std::map<Cell, std::vector<std::size_t>> byCell;
  for (std::size_t i = 0; i < pop.count; ++i) {
    long long c[3];
    for (int a = 0; a < 3; ++a) {
      const double p = pop.positions[i * 3 + a];
      const double scaled = std::floor((p - origin[a]) / spec.cellSize);
      if (!std::isfinite(p) || !std::isfinite(scaled) || std::abs(scaled) > 1e15) {
        *reason = "non_finite_positions";
        return false;
      }
      c[a] = static_cast<long long>(scaled);
    }
    byCell[Cell{c[0], c[1], c[2]}].push_back(i);
  }
  for (auto& [cell, list] : byCell) {
    keys->push_back(std::get<0>(cell));
    keys->push_back(std::get<1>(cell));
    keys->push_back(std::get<2>(cell));
    members->push_back(std::move(list));
  }
  return true;
}

void skipRemaining(GroupHierarchyResult* result,
                   const std::vector<GroupLevelSpec>& levels, std::size_t from) {
  for (std::size_t k = from; k < levels.size(); ++k) {
    GroupLevelResult lr;
    lr.model = levels[k].name;
    lr.scale = levels[k].scale;
    lr.grouping = groupingName(levels[k].grouping);
    lr.cellSize = levels[k].cellSize;
    lr.skipReason = "lower_level_unavailable";
    result->levels.push_back(std::move(lr));
  }
}

}  // namespace

GroupHierarchyResult GroupHierarchy::run(const GroupLiftInput& input,
                                         const std::vector<GroupLevelSpec>& levels) {
  GroupHierarchyResult result;

  Population pop;
  pop.count = input.count;
  pop.names = input.featureNames;
  pop.features = input.features;
  pop.hasPositions = input.hasPositions && input.positions.size() == input.count * 3;
  if (pop.hasPositions) pop.positions = input.positions;
  pop.weights = input.weights.size() == input.count
                    ? input.weights
                    : std::vector<double>(input.count, 1.0);
  // A weight is how many base elements a member stands for: it must be finite and positive.
  // Trech.Methods.Group's moment and centroid theorems need non-negative weights, and only
  // positive ones rule out a zero-weight group (NaN centroid) or cancelling weights at any depth
  // (liftWeight_pos), so the run refuses anything else rather than lifting it.
  for (double w : pop.weights) {
    if (!(std::isfinite(w) && w > 0.0)) {
      result.stopReason = "invalid_weight";
      skipRemaining(&result, levels, 0);
      for (auto& lr : result.levels) lr.skipReason = "invalid_weight";
      return result;
    }
  }
  pop.valid.assign(input.count, 1);
  pop.inDomain.assign(input.count, 1);
  pop.starved.assign(input.count, 0);
  if (pop.features.size() != pop.count * pop.names.size()) {
    pop.features.resize(pop.count * pop.names.size(), kNaN);
  }

  bool inheritedMismatch = false;
  GenericSurrogate::Workspace workspace;
  std::vector<double> raw;
  std::vector<double> out;

  for (std::size_t k = 0; k < levels.size(); ++k) {
    const GroupLevelSpec& spec = levels[k];
    GroupLevelResult lr;
    lr.model = spec.name;
    lr.scale = spec.scale;
    lr.grouping = groupingName(spec.grouping);
    lr.cellSize = spec.grouping == GroupLevelSpec::Grouping::kCell ? spec.cellSize : 0.0;

    auto stop = [&](const std::string& reason) {
      lr.skipReason = reason;
      result.levels.push_back(std::move(lr));
      result.stopReason = "level_skipped";
      skipRemaining(&result, levels, k + 1);
      return result;
    };

    const GenericSurrogate* model = spec.model;
    if (!model || !model->loaded()) return stop("model_unavailable");
    const GenericSurrogate::GroupLift& lift = model->groupLift();
    const GenericSurrogate::SetLayout layout = model->setLayout();
    if (!lift.declared || layout.elements == 0) return stop("not_group_lift");
    if (spec.grouping == GroupLevelSpec::Grouping::kCell && !(spec.cellSize > 0.0)) {
      return stop("length_required");
    }
    // rel_* normaliser: the call's explicit length, else the lattice edge, else
    // the length the model was trained with.
    lr.length = spec.length > 0.0 ? spec.length
                : lr.cellSize > 0.0 ? lr.cellSize
                                    : lift.length;
    lr.capacity = layout.elements;
    lr.featureNames = model->outputNames();
    lr.domainMeasured = model->domainMeasured();
    lr.latentOutputs = lift.latentOutputs;

    // ---- bind member features to population columns or synthesized facts ----
    std::vector<Synth> synth(layout.features, Synth::kNone);
    std::vector<std::size_t> column(layout.features, 0);
    bool needsGeometry = false;
    for (std::size_t f = 0; f < layout.features; ++f) {
      const std::string& name = lift.memberFeatures[f];
      synth[f] = synthesized(name);
      if (synth[f] == Synth::kRelX || synth[f] == Synth::kRelY || synth[f] == Synth::kRelZ) {
        needsGeometry = true;
      }
      if (synth[f] != Synth::kNone) continue;
      const auto it = std::find(pop.names.begin(), pop.names.end(), name);
      if (it == pop.names.end()) {
        lr.missingMemberFeatures.push_back(name);
      } else {
        column[f] = static_cast<std::size_t>(it - pop.names.begin());
      }
    }
    if (!lr.missingMemberFeatures.empty()) return stop("missing_member_features");
    std::vector<double> contextValues;
    for (const std::string& name : lift.contextFeatures) {
      const auto it = input.context.find(name);
      if (it == input.context.end() || !std::isfinite(it->second)) {
        lr.missingContext.push_back(name);
      } else {
        contextValues.push_back(it->second);
      }
    }
    if (!lr.missingContext.empty()) return stop("missing_context");
    if (needsGeometry && !pop.hasPositions) return stop("positions_required");
    if (needsGeometry && !(lr.length > 0.0)) return stop("length_required");

    // ---- partition -----------------------------------------------------------
    std::vector<std::vector<std::size_t>> members;
    std::string reason;
    if (!partition(pop, spec, input.origin, &members, &lr.keys, &reason)) {
      return stop(reason);
    }

    // ---- trained-band provenance (level-wide) --------------------------------
    const std::vector<std::string>& bands = model->trainedScaleBands();
    for (std::size_t bi = 0; bi < bands.size(); ++bi) {
      lr.trainedScale += (bi ? "," : "") + bands[bi];
    }
    const bool localMismatch =
        !bands.empty() && spec.scale != DimensionScale::kUnscaled &&
        std::find(bands.begin(), bands.end(), dimensionScaleName(spec.scale)) == bands.end();
    lr.scaleMismatch = localMismatch || inheritedMismatch;
    lr.hasHoldout = model->hasHoldout();
    lr.holdoutR2 = model->holdoutR2Min();
    lr.holdoutSamples = model->holdoutSamples();
    lr.outputAccuracy = collectOutputAccuracy(*model);

    // ---- evaluate every group ------------------------------------------------
    const std::size_t groups = members.size();
    const std::size_t nOut = lr.featureNames.size();
    const std::size_t nIn = model->inputNames().size();
    const std::vector<double>& means = model->inputMean();
    lr.groups = groups;
    lr.features.assign(groups * nOut, kNaN);
    lr.positions.assign(groups * 3, kNaN);
    lr.weights.assign(groups, 0.0);
    lr.memberCount.assign(groups, 0);
    lr.valid.assign(groups, 0);
    lr.inDomain.assign(groups, 1);
    lr.groupStarved.assign(groups, 0);
    lr.parent.assign(pop.count, -1);
    raw.assign(nIn, 0.0);
    out.assign(nOut, 0.0);

    for (std::size_t g = 0; g < groups; ++g) {
      const std::vector<std::size_t>& list = members[g];
      lr.memberCount[g] = static_cast<long long>(list.size());
      lr.maxMembers = std::max(lr.maxMembers, list.size());
      double weight = 0.0;
      double centroid[3] = {0.0, 0.0, 0.0};
      bool memberBlocked = false;
      bool memberOutOfDomain = false;
      bool memberStarved = false;
      for (std::size_t m : list) {
        lr.parent[m] = static_cast<long long>(g);
        const double w = pop.weights[m];
        weight += w;
        if (pop.hasPositions) {
          for (int a = 0; a < 3; ++a) centroid[a] += w * pop.positions[m * 3 + a];
        }
        memberBlocked = memberBlocked || !pop.valid[m];
        memberOutOfDomain = memberOutOfDomain || !pop.inDomain[m];
        memberStarved = memberStarved || pop.starved[m];
      }
      lr.weights[g] = weight;
      if (pop.hasPositions) {
        for (int a = 0; a < 3; ++a) {
          centroid[a] = weight != 0.0 ? centroid[a] / weight : kNaN;
          lr.positions[g * 3 + a] = centroid[a];
        }
      }
      // Lineage flags pass to a blocked group too (Trech.Methods.Group.flag_of_descendant): a
      // group whose evaluation is blocked still descends from its members' out-of-domain or
      // starved elements, so its effective flags never read cleaner than its members'.
      lr.inDomain[g] = memberOutOfDomain ? 0 : 1;
      lr.groupStarved[g] = memberStarved ? 1 : 0;
      if (list.size() > layout.elements) {
        ++lr.overflow;
        ++lr.blocked;
        continue;
      }
      if (memberBlocked) {
        ++lr.blockedByMembers;
        ++lr.blocked;
        continue;
      }
      // Assemble the raw input row: member slots (ascending member index),
      // mean-filled absent slots with present = 0, then the context.
      for (std::size_t slot = 0; slot < layout.elements; ++slot) {
        double* row = raw.data() + slot * layout.features;
        if (slot >= list.size()) {
          for (std::size_t f = 0; f < layout.features; ++f) {
            row[f] = synth[f] == Synth::kPresent ? 0.0 : means[slot * layout.features + f];
          }
          continue;
        }
        const std::size_t m = list[slot];
        for (std::size_t f = 0; f < layout.features; ++f) {
          switch (synth[f]) {
            case Synth::kPresent:
              row[f] = 1.0;
              break;
            case Synth::kWeight:
              row[f] = pop.weights[m];
              break;
            case Synth::kRelX:
            case Synth::kRelY:
            case Synth::kRelZ: {
              const int a = synth[f] == Synth::kRelX ? 0 : (synth[f] == Synth::kRelY ? 1 : 2);
              row[f] = (pop.positions[m * 3 + a] - centroid[a]) / lr.length;
              break;
            }
            case Synth::kNone:
              row[f] = pop.features[m * pop.names.size() + column[f]];
              break;
          }
        }
      }
      std::copy(contextValues.begin(), contextValues.end(),
                raw.begin() + static_cast<std::ptrdiff_t>(layout.elements * layout.features));
      bool finite = true;
      for (double v : raw) finite = finite && std::isfinite(v);
      if (!finite || !model->predictInto(raw.data(), nIn, out.data(), nOut, workspace)) {
        ++lr.blocked;
        continue;
      }
      ++lr.evaluated;
      std::copy(out.begin(), out.end(), lr.features.begin() + static_cast<std::ptrdiff_t>(g * nOut));
      lr.valid[g] = 1;
      const GenericSurrogate::Coverage cov = model->coverageVector(raw, workspace);
      const bool localStarved = !cov.starvedInputs.empty() || cov.jointStarved;
      if (!cov.inDomain) ++lr.localOutOfDomain;
      if (localStarved) ++lr.localStarved;
      const bool effectiveOod = !cov.inDomain || memberOutOfDomain;
      const bool effectiveStarved = localStarved || memberStarved;
      lr.inDomain[g] = effectiveOod ? 0 : 1;
      lr.groupStarved[g] = effectiveStarved ? 1 : 0;
      if (effectiveOod) ++lr.outOfDomain;
      if (effectiveStarved) ++lr.starved;
    }

    lr.ran = true;
    ++result.levelsRun;
    result.inferenceCount += lr.evaluated;
    result.outOfDomainInferences += lr.outOfDomain;
    result.starvedInferences += lr.starved;
    if (lr.scaleMismatch) result.scaleMismatchedInferences += lr.evaluated;
    inheritedMismatch = lr.scaleMismatch;

    // ---- the groups become the next level's elements -------------------------
    Population next;
    next.count = groups;
    next.names = lr.featureNames;
    next.features = lr.features;
    next.hasPositions = pop.hasPositions;
    next.positions = lr.positions;
    next.weights = lr.weights;
    next.valid = lr.valid;
    next.inDomain = lr.inDomain;
    next.starved = lr.groupStarved;
    pop = std::move(next);
    result.levels.push_back(std::move(lr));
  }
  return result;
}

}  // namespace trech::ml
