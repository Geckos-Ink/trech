// Unit test for GroupHierarchy (ctx.lift): recursive group lifting of a
// population, elements -> cells -> blocks -> system, through trained v3 set
// networks carrying `group_lift`. Covers NumPy parity of every level against
// the trainer's reference evaluator (tests/fixtures/ml_group_hierarchy),
// invariance to the order of base elements, engine-identical lattice keys, the
// blocking rules (capacity overflow, blocked members, missing member features
// or context, positions required), trust propagation up the hierarchy, and the
// loader's fail-closed `group_lift` validation. Geant4-free.

#include "trech/ml/GroupHierarchy.hpp"

#include <algorithm>
#include <cmath>
#include <cstdio>
#include <fstream>
#include <numeric>
#include <random>
#include <string>
#include <vector>

#include <nlohmann/json.hpp>

#include "trech/ml/GenericSurrogate.hpp"

namespace {

int failures = 0;

void expect(bool cond, const char* msg) {
  if (!cond) {
    std::fprintf(stderr, "FAIL: %s\n", msg);
    ++failures;
  }
}

const std::string kDir = std::string(TRECH_SOURCE_DIR) + "/tests/fixtures/ml_group_hierarchy/";

trech::ml::GroupLiftInput inputFromCase(const nlohmann::json& c) {
  trech::ml::GroupLiftInput input;
  const auto q = c.at("features").at("q").get<std::vector<double>>();
  input.count = q.size();
  input.featureNames = {"q"};
  input.features = q;
  input.hasPositions = true;
  const auto x = c.at("positions").at("x").get<std::vector<double>>();
  const auto y = c.at("positions").at("y").get<std::vector<double>>();
  const auto z = c.at("positions").at("z").get<std::vector<double>>();
  for (std::size_t i = 0; i < q.size(); ++i) {
    input.positions.insert(input.positions.end(), {x[i], y[i], z[i]});
  }
  input.context["g"] = c.at("context").at("g").get<double>();
  return input;
}

std::vector<trech::ml::GroupLevelSpec> fixtureLevels(const trech::ml::GenericSurrogate& cell,
                                                     const trech::ml::GenericSurrogate& block,
                                                     const trech::ml::GenericSurrogate& system) {
  using Spec = trech::ml::GroupLevelSpec;
  std::vector<Spec> levels(3);
  levels[0].name = "cell";
  levels[0].scale = trech::ml::DimensionScale::kNano;
  levels[0].model = &cell;
  levels[0].grouping = Spec::Grouping::kCell;
  levels[0].cellSize = cell.groupLift().cellSize;
  levels[1].name = "block";
  levels[1].scale = trech::ml::DimensionScale::kMicro;
  levels[1].model = &block;
  levels[1].grouping = Spec::Grouping::kCell;
  levels[1].cellSize = block.groupLift().cellSize;
  levels[2].name = "system";
  levels[2].scale = trech::ml::DimensionScale::kMeso;
  levels[2].model = &system;
  levels[2].grouping = Spec::Grouping::kAll;
  levels[2].length = 4.0;
  return levels;
}

std::string keyString(const trech::ml::GroupLevelResult& level, std::size_t g) {
  if (level.grouping == "all") return "all";
  if (level.grouping == "explicit") return std::to_string(level.keys[g]);
  return std::to_string(level.keys[g * 3]) + "," + std::to_string(level.keys[g * 3 + 1]) + "," +
         std::to_string(level.keys[g * 3 + 2]);
}

std::string writeTemp(const std::string& text, const std::string& name) {
  const std::string path = std::string(TRECH_BINARY_DIR) + "/" + name;
  std::ofstream(path) << text;
  return path;
}

}  // namespace

int main() {
  trech::ml::GenericSurrogate cell, block, system;
  expect(cell.load(kDir + "cell.json"), "cell lift loads");
  expect(block.load(kDir + "block.json"), "block lift loads");
  expect(system.load(kDir + "system.json"), "system lift loads");
  expect(cell.groupLift().declared && block.groupLift().declared && system.groupLift().declared,
         "fixture models declare group_lift");
  expect(cell.groupLift().cellSize == 1.0 && block.groupLift().cellSize == 2.0 &&
             system.groupLift().cellSize == 0.0,
         "trained lattice edges are carried");
  expect(cell.groupLift().latentOutputs && !system.groupLift().latentOutputs,
         "latent outputs are flagged per model");
  expect(system.groupLift().contextFeatures == std::vector<std::string>{"g"},
         "context features follow the member blocks");
  expect(std::string(block.networkKind()) == "mpnn", "the block level is a message-passing lift");

  std::ifstream expectedIn(kDir + "expected.json");
  const auto expected = nlohmann::json::parse(expectedIn);
  const auto levels = fixtureLevels(cell, block, system);

  // ---- parity with the NumPy reference, level by level -----------------------
  double worst = 0.0;
  for (const auto& c : expected.at("cases")) {
    const auto input = inputFromCase(c);
    const auto run = trech::ml::GroupHierarchy::run(input, levels);
    expect(run.levelsRun == 3 && run.stopReason == "complete", "all three levels run");
    for (std::size_t k = 0; k < 3; ++k) {
      const auto& ref = c.at("levels").at(k);
      const auto& lr = run.levels[k];
      expect(lr.groups == ref.at("keys").size(), "group count matches the trainer");
      for (std::size_t g = 0; g < lr.groups && g < ref.at("keys").size(); ++g) {
        expect(keyString(lr, g) == ref.at("keys").at(g).get<std::string>(),
               "group keys and order match the trainer's partition");
        expect(static_cast<bool>(lr.valid[g]) == ref.at("valid").at(g).get<bool>(),
               "validity matches");
        for (std::size_t o = 0; o < lr.featureNames.size(); ++o) {
          const auto& v = ref.at("features").at(g).at(o);
          if (v.is_null()) continue;
          const double r = v.get<double>();
          worst = std::max(worst, std::abs(lr.features[g * lr.featureNames.size() + o] - r) /
                                      std::max(1.0, std::abs(r)));
        }
      }
    }
    expect(run.inferenceCount == run.levels[0].evaluated + run.levels[1].evaluated +
                                     run.levels[2].evaluated,
           "every group evaluation counts as one inference");
  }
  if (worst > 1e-9) std::fprintf(stderr, "  worst relative difference %.3g\n", worst);
  expect(worst <= 1e-9, "C++ GroupHierarchy matches the NumPy reference at every level (1e-9)");

  const auto& case0 = expected.at("cases").at(0);
  const auto base = inputFromCase(case0);
  const auto reference = trech::ml::GroupHierarchy::run(base, levels);
  const double topRef = reference.levels[2].features[0];

  // ---- the trained rel_* length travels with the model ------------------------
  {
    auto carried = levels;
    carried[2].length = 0.0;
    expect(system.groupLift().length == 4.0, "the observer level carries its trained length");
    const auto run = trech::ml::GroupHierarchy::run(base, carried);
    expect(run.levels[2].length == 4.0 && run.levels[2].features[0] == topRef,
           "an omitted length falls back to the model's carried one");
  }

  // ---- base-element order does not matter ------------------------------------
  {
    std::vector<std::size_t> perm(base.count);
    std::iota(perm.begin(), perm.end(), 0);
    std::mt19937 rng(7);
    std::shuffle(perm.begin(), perm.end(), rng);
    auto shuffled = base;
    for (std::size_t i = 0; i < base.count; ++i) {
      shuffled.features[i] = base.features[perm[i]];
      for (int a = 0; a < 3; ++a) shuffled.positions[i * 3 + a] = base.positions[perm[i] * 3 + a];
    }
    const auto run = trech::ml::GroupHierarchy::run(shuffled, levels);
    expect(std::abs(run.levels[2].features[0] - topRef) <= 1e-9 * std::max(1.0, std::abs(topRef)),
           "the lifted observer is invariant to the order of base elements");
    expect(run.levels[0].parent[0] == reference.levels[0].parent[perm[0]],
           "parent maps follow the elements");
  }

  // ---- capacity overflow blocks, and blocking propagates up ------------------
  {
    auto lumped = levels;
    lumped[0].grouping = trech::ml::GroupLevelSpec::Grouping::kExplicit;
    lumped[0].groupIds.assign(base.count, 5);  // every element in one group
    lumped[0].length = 1.0;
    const auto run = trech::ml::GroupHierarchy::run(base, lumped);
    expect(run.levels[0].groups == 1 && run.levels[0].overflow == 1 && run.levels[0].evaluated == 0,
           "a group larger than the model's capacity is blocked, never truncated");
    expect(run.levels[0].keys == std::vector<long long>{5}, "explicit ids become the keys");
    expect(run.levels[1].blockedByMembers == 1 && run.levels[2].blocked == 1,
           "a blocked member blocks every group above it");
    expect(std::isnan(run.levels[2].features[0]) && !run.levels[2].valid[0],
           "blocked groups publish NaN and valid=false");
  }

  // ---- missing inputs stop the hierarchy -------------------------------------
  {
    auto noContext = base;
    noContext.context.clear();
    const auto run = trech::ml::GroupHierarchy::run(noContext, levels);
    expect(run.levelsRun == 2 && run.levels[2].skipReason == "missing_context" &&
               run.levels[2].missingContext == std::vector<std::string>{"g"},
           "a missing context input skips the level instead of using zero");
    std::vector<trech::ml::GroupLevelSpec> wrong = {levels[2], levels[0]};
    const auto missing = trech::ml::GroupHierarchy::run(base, wrong);
    expect(missing.levels[0].skipReason == "missing_member_features" &&
               missing.levels[1].skipReason == "lower_level_unavailable" &&
               missing.levelsRun == 0 && missing.stopReason == "level_skipped",
           "a member feature the level below does not produce stops the hierarchy");
    auto noPositions = base;
    noPositions.hasPositions = false;
    noPositions.positions.clear();
    const auto unplaced = trech::ml::GroupHierarchy::run(noPositions, levels);
    expect(unplaced.levels[0].skipReason == "positions_required",
           "lattice grouping without positions is refused");
  }

  // ---- trust propagates: an out-of-domain member taints its ancestors -------
  {
    auto hot = base;
    hot.features[0] = 1e3;  // far outside the trained charge range
    const auto run = trech::ml::GroupHierarchy::run(hot, levels);
    expect(run.levels[0].localOutOfDomain >= 1, "the cell holding the outlier is out of domain");
    expect(run.levels[1].outOfDomain >= 1 && run.levels[2].outOfDomain == 1 &&
               !run.levels[2].inDomain[0],
           "out-of-domain lineage reaches the observer");
    expect(run.outOfDomainInferences >= 3, "effective out-of-domain inferences are counted");
    expect(reference.levels[2].inDomain[0] || reference.levels[2].localOutOfDomain == 0 ||
               reference.levels[2].outOfDomain >= reference.levels[2].localOutOfDomain,
           "effective counts include local ones");
  }

  // ---- unusable models --------------------------------------------------------
  {
    trech::ml::GenericSurrogate dense;
    const std::string densePath = writeTemp(
        R"({"model":"generic_surrogate_v1","input_features":["a"],"output_features":["b"],)"
        R"("layers":[{"weights":[[1.0]],"bias":[0.0],"activation":"none"}]})",
        "group_hierarchy_dense.json");
    expect(dense.load(densePath), "a dense model loads");
    auto plain = levels;
    plain[0].model = &dense;
    expect(trech::ml::GroupHierarchy::run(base, plain).levels[0].skipReason == "not_group_lift",
           "a model without group_lift is never used as a level");
    plain[0].model = nullptr;
    expect(trech::ml::GroupHierarchy::run(base, plain).levels[0].skipReason == "model_unavailable",
           "an undeclared model skips the level");

    std::ifstream cellIn(kDir + "cell.json");
    const auto cellJson = nlohmann::json::parse(cellIn);
    auto rejects = [&](nlohmann::json bad, const char* what) {
      trech::ml::GenericSurrogate model;
      expect(!model.load(writeTemp(bad.dump(), "group_hierarchy_bad.json")), what);
    };
    auto bad = cellJson;
    bad["input_features"][6] = "m1_charge";
    rejects(bad, "member slots must repeat the slot-0 feature names");
    bad = cellJson;
    bad["group_lift"]["member_features"] = {"present", "rel_x", "rel_y", "rel_z", "charge"};
    rejects(bad, "declared member_features must agree with the inputs");
    bad = cellJson;
    bad["network"]["mask_feature"] = 4;
    rejects(bad, "the set mask must be the member feature named present");
    bad = cellJson;
    bad["group_lift"]["cell_size"] = -1.0;
    rejects(bad, "a non-positive cell_size is rejected");
    bad = cellJson;
    bad["group_lift"]["latent_outputs"] = {"nope"};
    rejects(bad, "latent_outputs must name outputs");
    auto denseLift = nlohmann::json::parse(
        R"({"model":"generic_surrogate_v1","input_features":["a"],"output_features":["b"],)"
        R"("layers":[{"weights":[[1.0]],"bias":[0.0],"activation":"none"}],"group_lift":{}})");
    rejects(denseLift, "group_lift on a dense model fails closed");
  }

  if (failures) {
    std::fprintf(stderr, "%d failure(s)\n", failures);
    return 1;
  }
  std::printf("test_group_hierarchy: all checks passed\n");
  return 0;
}
