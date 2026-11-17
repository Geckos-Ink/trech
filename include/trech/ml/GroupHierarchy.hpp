#pragma once

#include <array>
#include <cstddef>
#include <string>
#include <unordered_map>
#include <vector>

#include "trech/ml/ScaleCascade.hpp"

namespace trech::ml {

class GenericSurrogate;

// Recursive group lifting: the "elements -> groups -> groups of groups" half of
// the multi-scale doctrine.
//
// ScaleCascade lifts ONE context vector from band to band. Many observables are
// instead properties of a POPULATION: atoms make molecules, molecules make
// clusters, clusters make parcels, parcels make a glass of water. GroupHierarchy
// lifts a population scale by scale:
//
//   level 0 input  : N base elements, each with named features (+ position,
//                    + weight = how many base elements it stands for, 1)
//   level k        : partition the current elements into groups (a cubic
//                    lattice of edge `cellSize`, explicit group ids, or one
//                    group of everything), evaluate the level's trained SET
//                    model on each group's members, and make each group a new
//                    element whose features are the model's named outputs,
//                    whose position is its members' weight-centroid and whose
//                    weight is the sum of its members' weights.
//   top            : the last level's groups (often one: the observer).
//
// Each level is a v3 set network (DeepSets / MPNN) carrying a `group_lift`
// block (GenericSurrogate::GroupLift). Its member features are either names the
// level below supplies or engine-synthesised member facts:
//   present           1 for a real member, 0 for an absent slot (the set mask)
//   weight            base elements the member stands for
//   rel_x/rel_y/rel_z (member position - group centroid) / level length
// Dividing by the level length makes the member geometry dimensionless, so one
// trained lift can be applied at several levels when the behaviour is
// self-similar (a coarse-graining that is reused, not re-specified).
//
// Honesty rules, the same as every operator:
//   * No implicit zero physics. A group with more members than the model has
//     slots is BLOCKED (never truncated); a group with a blocked member is
//     blocked; a missing member feature or context input blocks the level and
//     every level above it. Blocked groups publish NaN and valid=false.
//   * Trust propagates up the hierarchy. A group is effectively out of domain
//     (or starved) when its own inputs are, or when any member's lineage is.
//   * Deterministic: lattice cells are ordered by (ix, iy, iz), explicit ids
//     ascending, members by ascending index; centroids accumulate in that order.
//   * Absent member slots are filled with the model's input means (present = 0)
//     so they standardize to zero: they take no part in the set arithmetic and
//     cannot trip the training-domain check.
struct GroupLevelSpec {
  enum class Grouping { kCell, kExplicit, kAll };
  std::string name;  // model registry name (trace/provenance)
  DimensionScale scale = DimensionScale::kUnscaled;
  const GenericSurrogate* model = nullptr;
  Grouping grouping = Grouping::kAll;
  double cellSize = 0.0;            // kCell: lattice edge (> 0)
  std::vector<long long> groupIds;  // kExplicit: one id per current element
  double length = 0.0;  // rel_* normaliser; 0 -> cellSize, else the model's
                        // carried group_lift.length
};

struct GroupLiftInput {
  std::size_t count = 0;
  std::vector<std::string> featureNames;
  std::vector<double> features;  // count x featureNames.size(), element-major
  bool hasPositions = false;
  std::vector<double> positions;  // count x 3
  std::vector<double> weights;    // count, or empty -> 1 each
  std::unordered_map<std::string, double> context;
  std::array<double, 3> origin{0.0, 0.0, 0.0};  // lattice origin
};

struct GroupLevelResult {
  std::string model;
  DimensionScale scale = DimensionScale::kUnscaled;
  std::string grouping;  // cell | explicit | all
  double cellSize = 0.0;
  double length = 0.0;
  bool ran = false;
  // model_unavailable | not_group_lift | lower_level_unavailable |
  // missing_member_features | missing_context | positions_required |
  // length_required | group_ids_mismatch | non_finite_positions
  std::string skipReason;
  std::vector<std::string> missingMemberFeatures;
  std::vector<std::string> missingContext;
  std::size_t capacity = 0;   // member slots of the model
  std::size_t maxMembers = 0; // largest group seen
  std::size_t groups = 0;
  std::size_t evaluated = 0;  // model evaluations (inferences)
  std::size_t blocked = 0;    // overflow + blocked members + failed predictions
  std::size_t overflow = 0;   // groups larger than the model's capacity
  std::size_t blockedByMembers = 0;
  std::size_t outOfDomain = 0;       // effective (local or inherited)
  std::size_t localOutOfDomain = 0;  // this model's own coverage check
  std::size_t starved = 0;           // effective per-feature or joint starvation
  std::size_t localStarved = 0;
  bool domainMeasured = false;
  bool latentOutputs = false;
  std::vector<std::string> featureNames;  // the model's outputs
  std::vector<double> features;           // groups x featureNames (NaN when blocked)
  std::vector<double> positions;          // groups x 3 (NaN without positions)
  std::vector<double> weights;            // groups
  std::vector<long long> memberCount;     // groups
  std::vector<long long> parent;          // lower element -> group index
  std::vector<long long> keys;            // cell: 3 per group; explicit: 1; all: 0
  std::vector<unsigned char> valid;       // groups
  std::vector<unsigned char> inDomain;    // groups (effective)
  std::vector<unsigned char> groupStarved;  // groups (effective)
  bool hasHoldout = false;
  double holdoutR2 = 0.0;
  int holdoutSamples = 0;
  std::string trainedScale;
  bool scaleMismatch = false;  // applied at a band its model was not trained on
  std::vector<NamedOutputAccuracy> outputAccuracy;
};

struct GroupHierarchyResult {
  std::vector<GroupLevelResult> levels;
  int levelsRun = 0;
  std::size_t inferenceCount = 0;
  std::size_t outOfDomainInferences = 0;  // effective
  std::size_t starvedInferences = 0;      // effective
  std::size_t scaleMismatchedInferences = 0;
  std::string stopReason = "complete";  // complete | level_skipped
};

class GroupHierarchy {
 public:
  static GroupHierarchyResult run(const GroupLiftInput& input,
                                  const std::vector<GroupLevelSpec>& levels);
};

}  // namespace trech::ml
