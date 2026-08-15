// Unit test for PairInteraction: the engine-side pair/neighbour inference
// operator that replaces hand-written force/bond/neighbour-sum loops in
// scenario JavaScript.  Covers the deterministic cell list and canonical pair
// ordering, equal-and-opposite vs shared accumulation, the reserved geometry /
// member / dt inputs, persistent per-pair (bond) state, declared bounds,
// missing-input and unapplied-output reporting, aggregated per-pair coverage,
// pair-count-bounded search, invalid/duplicate link reporting, and graceful
// skipping of unloaded stages.  Geant4-free: builds tiny generic surrogates
// from temp JSON files.

#include "trech/ml/PairInteraction.hpp"

#include <cmath>
#include <cstdio>
#include <fstream>
#include <memory>
#include <string>
#include <vector>

#include "trech/ml/GenericSurrogate.hpp"

namespace {

int failures = 0;

void expect(bool cond, const char* msg) {
  if (!cond) {
    std::fprintf(stderr, "FAIL: %s\n", msg);
    ++failures;
  }
}

bool approx(double a, double b, double tol = 1e-9) {
  return std::abs(a - b) <= tol;
}

std::string jsonStringArray(const std::vector<std::string>& items) {
  std::string out = "[";
  for (std::size_t i = 0; i < items.size(); ++i) {
    out += "\"" + items[i] + "\"";
    if (i + 1 < items.size()) out += ",";
  }
  return out + "]";
}

// A one-layer linear generic model with unit scaling:
//   out_o = bias[o] + sum_i weights[o][i] * in_i
// `radius` >= 0 attaches a MEASURED per-input training hull so coverage is
// precisely controllable; a negative radius leaves the model hull-free.
std::unique_ptr<trech::ml::GenericSurrogate> makeLinear(
    const std::string& file, const std::vector<std::string>& in,
    const std::vector<std::string>& out,
    const std::vector<std::vector<double>>& weights,
    const std::vector<double>& bias, double radius = -1.0) {
  std::string wjson = "[";
  for (std::size_t o = 0; o < weights.size(); ++o) {
    wjson += "[";
    for (std::size_t i = 0; i < weights[o].size(); ++i) {
      wjson += std::to_string(weights[o][i]);
      if (i + 1 < weights[o].size()) wjson += ",";
    }
    wjson += "]";
    if (o + 1 < weights.size()) wjson += ",";
  }
  wjson += "]";
  std::string bjson = "[";
  for (std::size_t o = 0; o < bias.size(); ++o) {
    bjson += std::to_string(bias[o]);
    if (o + 1 < bias.size()) bjson += ",";
  }
  bjson += "]";
  std::string means = "[", stds = "[", radii = "[";
  for (std::size_t i = 0; i < in.size(); ++i) {
    means += "0.0";
    stds += "1.0";
    radii += std::to_string(radius);
    if (i + 1 < in.size()) {
      means += ",";
      stds += ",";
      radii += ",";
    }
  }
  means += "]";
  stds += "]";
  radii += "]";

  const std::string path = std::string("./") + file;
  {
    std::ofstream f(path);
    f << "{\"model\":\"generic_surrogate_v1\","
      << "\"input_features\":" << jsonStringArray(in) << ","
      << "\"output_features\":" << jsonStringArray(out) << ","
      << "\"input_mean\":" << means << ",\"input_std\":" << stds << ",";
    if (radius >= 0.0) {
      f << "\"input_domain\":{\"standardized_radius\":" << radii << "},";
    }
    f << "\"layers\":[{\"weights\":" << wjson << ",\"bias\":" << bjson
      << ",\"activation\":\"none\"}]}";
  }
  auto m = std::make_unique<trech::ml::GenericSurrogate>();
  m->load(path);
  std::remove(path.c_str());
  return m;
}

// Three elements on a line at x = 0, 1, 5 with one field (heat) and one aux
// (mass).  Cutoff 2 therefore sees exactly one pair: (0,1).
trech::ml::PairInteractionRequest lineRequest(double dt) {
  using trech::ml::PairElementField;
  using trech::ml::PairSymmetry;
  trech::ml::PairInteractionRequest req;
  req.elementCount = 3;
  req.fields.push_back({"heat", PairSymmetry::kAntisymmetric, -1e9, 1e9});
  req.auxNames.push_back("mass");
  req.state = {10.0, 4.0, 100.0};
  req.aux = {2.0, 3.0, 5.0};
  req.positions = {0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 5.0, 0.0, 0.0};
  req.cutoff = 2.0;
  req.dt = dt;
  return req;
}

}  // namespace

int main() {
  using trech::ml::DimensionScale;
  using trech::ml::PairElementField;
  using trech::ml::PairInteraction;
  using trech::ml::PairInteractionRequest;
  using trech::ml::PairInteractionResult;
  using trech::ml::PairStateField;
  using trech::ml::PairSymmetry;

  // The naming convention is engine-owned and exposed, so callers/trainers
  // agree with the engine instead of guessing.
  expect(PairInteraction::rateOutputName("heat") == "d_heat_dt", "rate name");
  expect(PairInteraction::incrementOutputName("rho") == "add_rho", "add name");
  expect(PairInteraction::assignOutputName("rest") == "set_rest", "assign name");
  expect(PairInteraction::memberInputName(0, "mass") == "a_mass", "a_ name");
  expect(PairInteraction::memberInputName(1, "mass") == "b_mass", "b_ name");

  // --- 1. equal-and-opposite exchange over one cutoff pair ------------------
  // A "conduction" stage: rate = 0.5 * (b_heat - a_heat).  Element 0 is hotter
  // than 1, so 0 must LOSE exactly what 1 gains; element 2 is out of range and
  // must stay bit-identical.
  {
    auto model = makeLinear("pi_conduct.json", {"a_heat", "b_heat"},
                            {"d_heat_dt"}, {{-0.5, 0.5}}, {0.0});
    expect(model->loaded(), "conduction model loads");
    PairInteraction op;
    op.addStage("conduct", DimensionScale::kMicro, model.get());
    PairInteractionRequest req = lineRequest(0.1);
    const PairInteractionResult run = op.interact(req);
    expect(run.ran, "conduction ran");
    expect(run.pairCount == 1, "cutoff finds exactly one pair");
    expect(run.neighborPairCount == 1 && run.linkPairCount == 0,
           "the pair is a neighbour, not a link");
    expect(run.stagesRun == 1, "one stage ran");
    expect(run.inferenceCount == 1, "pairs x stages inference count");
    // rate = 0.5*(4-10) = -3 ; dt 0.1 -> a: 10-0.3, b: 4+0.3
    expect(approx(run.state[0], 9.7), "member a lost heat");
    expect(approx(run.state[1], 4.3), "member b gained the same heat");
    expect(approx(run.state[0] + run.state[1], 14.0),
           "antisymmetric pair conserves the field exactly");
    expect(run.state[2] == req.state[2], "untouched element is bit-identical");
    expect(run.stages.size() == 1 && run.stages[0].ratedElementFields.size() == 1 &&
               run.stages[0].ratedElementFields[0] == "heat",
           "trace names the rated element field");
  }

  // --- 2. symmetric (shared) accumulation -----------------------------------
  // A neighbourhood density sum: both members gain the same contribution, and
  // the caller pre-loads the field with its own self term.
  {
    auto model = makeLinear("pi_density.json", {"r"}, {"add_rho"}, {{-0.25}},
                            {1.0});
    PairInteraction op;
    op.addStage("density", DimensionScale::kMicro, model.get());
    PairInteractionRequest req;
    req.elementCount = 3;
    req.fields.push_back({"rho", PairSymmetry::kSymmetric, 0.0, 1e9});
    req.elementCount = 3;
    req.state = {1.0, 1.0, 1.0};  // self term
    req.positions = {0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 5.0, 0.0, 0.0};
    req.cutoff = 2.0;
    req.dt = 0.5;  // an `add_` output must NOT be scaled by dt
    const PairInteractionResult run = op.interact(req);
    expect(run.ran, "density ran");
    // contribution = 1 - 0.25*1 = 0.75, shared by both members, no dt.
    expect(approx(run.state[0], 1.75) && approx(run.state[1], 1.75),
           "symmetric contribution adds to both members without dt");
    expect(approx(run.state[2], 1.0), "isolated element keeps its self term");
    expect(run.stages[0].incrementedElementFields.size() == 1,
           "trace names the incremented field");
  }

  // --- 3. persistent bonds: pair state, out-of-cutoff evaluation, bounds ----
  // A stretched bond (elements 0 and 2, distance 5 > cutoff 2) is STILL
  // evaluated, its rest length grows at a learned rate, and the caller's
  // declared bound clamps it.
  {
    auto model = makeLinear("pi_bond.json", {"r", "rest"},
                            {"d_rest_dt", "d_heat_dt"},
                            {{0.0, 2.0}, {1.0, 0.0}}, {0.0, 0.0});
    PairInteraction op;
    op.addStage("bond", DimensionScale::kMeso, model.get());
    PairInteractionRequest req = lineRequest(0.5);
    req.cutoff = 0.0;  // links only
    req.links.push_back({2, 0});  // declared out of order: canonicalised to 0,2
    req.pairFields.push_back({"rest", 0.0, 1.4});
    req.pairState = {1.0};
    const PairInteractionResult run = op.interact(req);
    expect(run.pairCount == 1 && run.linkPairCount == 1,
           "declared link evaluated with no cutoff search");
    // d_rest_dt = 2*rest = 2 -> rest = 1 + 2*0.5 = 2, clamped to the declared 1.4
    expect(approx(run.pairState[0], 1.4), "pair state respects declared bounds");
    // d_heat_dt = r = 5 -> a gains 2.5, b loses 2.5 (canonical a = element 0)
    expect(approx(run.state[0], 12.5) && approx(run.state[2], 97.5),
           "canonical orientation drives the equal-and-opposite exchange");
    expect(run.stages[0].ratedPairFields.size() == 1 &&
               run.stages[0].ratedPairFields[0] == "rest",
           "trace names the rated pair field");
  }

  // --- 4. a bond inside the cutoff is one pair, evaluated once --------------
  {
    auto model = makeLinear("pi_once.json", {"r"}, {"d_heat_dt"}, {{1.0}}, {0.0});
    PairInteraction op;
    op.addStage("once", DimensionScale::kMicro, model.get());
    PairInteractionRequest req = lineRequest(1.0);
    req.links.push_back({0, 1});  // also within the cutoff
    const PairInteractionResult run = op.interact(req);
    expect(run.pairCount == 1, "a link inside the cutoff is not double-counted");
    expect(run.linkPairCount == 1 && run.neighborPairCount == 0,
           "the duplicate resolves to the link (it carries the state)");
    expect(approx(run.state[0], 11.0), "exchange applied exactly once");
  }

  // --- 5. malformed topology is reported, never silently dropped -----------
  {
    auto model = makeLinear("pi_topo.json", {"r"}, {"d_heat_dt"}, {{0.0}}, {1.0});
    PairInteraction op;
    op.addStage("topo", DimensionScale::kMicro, model.get());
    PairInteractionRequest req = lineRequest(1.0);
    req.cutoff = 0.0;
    req.links = {{0, 0}, {0, 9}, {0, 2}, {2, 0}};
    const PairInteractionResult run = op.interact(req);
    expect(run.invalidLinks == 2, "self-pair and out-of-range link reported");
    expect(run.duplicateLinks == 1, "the repeated pair is reported and kept once");
    expect(run.pairCount == 1, "one valid pair survives");
  }

  // --- 6. two stages chain by scale band through a pair intermediate --------
  {
    auto lower = makeLinear("pi_lower.json", {"r"}, {"stiffness"}, {{2.0}}, {1.0});
    auto upper = makeLinear("pi_upper.json", {"stiffness", "a_mass"},
                            {"d_heat_dt"}, {{1.0, 10.0}}, {0.0});
    PairInteraction op;
    // Registered high-band-first: execution order must follow the SCALE, not
    // the registration order, or the forward reference would go missing.
    op.addStage("upper", DimensionScale::kMeso, upper.get());
    op.addStage("lower", DimensionScale::kMicro, lower.get());
    PairInteractionRequest req = lineRequest(1.0);
    const PairInteractionResult run = op.interact(req);
    expect(run.stagesRun == 2, "both stages ran");
    expect(run.inferenceCount == 2, "pairs x stages = 1 x 2");
    expect(run.stages[0].model == "lower" && run.stages[1].model == "upper",
           "stages execute in ascending scale order");
    expect(run.stages[1].missingInputs.empty(),
           "the higher stage resolves the lower stage's intermediate");
    // stiffness = 1 + 2*1 = 3 ; rate = 3 + 10*mass_a(2) = 23
    expect(approx(run.state[0], 33.0), "chained pair inference applied");
    expect(approx(run.state[1], -19.0), "and its equal-and-opposite half");
  }

  // --- 7. missing inputs and unapplied outputs are reported ----------------
  {
    auto model = makeLinear("pi_report.json", {"a_heat", "nowhere"},
                            {"d_ghost_dt", "set_heat", "d_heat_dt"},
                            {{0.0, 0.0}, {0.0, 0.0}, {0.0, 0.0}},
                            {1.0, 99.0, 0.0});
    PairInteraction op;
    op.addStage("report", DimensionScale::kMicro, model.get());
    PairInteractionRequest req = lineRequest(1.0);
    const PairInteractionResult run = op.interact(req);
    expect(run.stages[0].missingInputs.size() == 1 &&
               run.stages[0].missingInputs[0] == "nowhere",
           "an input nothing provides is reported, not hidden");
    expect(run.stages[0].unappliedFieldOutputs.size() == 2,
           "undeclared-field rate and member assignment are both unapplied");
    expect(approx(run.state[0], 10.0),
           "an assignment to a member field changes no state");
  }

  // --- 8. a shared fact and the reserved dt reach the model ----------------
  {
    auto model = makeLinear("pi_shared.json", {"dt", "ambient_k"},
                            {"d_heat_dt"}, {{100.0, 1.0}}, {0.0});
    PairInteraction op;
    op.addStage("shared", DimensionScale::kMicro, model.get());
    PairInteractionRequest req = lineRequest(0.25);
    req.shared["ambient_k"] = 5.0;
    const PairInteractionResult run = op.interact(req);
    expect(run.stages[0].missingInputs.empty(), "dt and shared both resolve");
    // rate = 100*0.25 + 5 = 30 ; applied over dt 0.25 -> 7.5
    expect(approx(run.state[0], 17.5), "reserved dt and shared context applied");
  }

  // --- 9. aggregated per-pair trust profile --------------------------------
  {
    // Measured hull of 1 sigma on a unit-std input: the (0,1) pair sits at
    // r = 1 (in domain), the (0,2)/(1,2) links at r = 5 and 4 (far outside).
    auto model = makeLinear("pi_cov.json", {"r"}, {"d_heat_dt"}, {{0.0}}, {1.0},
                            /*radius=*/1.0);
    PairInteraction op;
    op.addStage("cov", DimensionScale::kMicro, model.get());
    PairInteractionRequest req = lineRequest(1.0);
    req.links = {{0, 2}, {1, 2}};
    const PairInteractionResult run = op.interact(req);
    expect(run.pairCount == 3, "one neighbour pair plus two links");
    expect(run.stages[0].domainMeasured, "measured hull reported as measured");
    expect(run.stages[0].pairsOutOfDomain == 2, "both stretched pairs flagged");
    expect(run.outOfDomainInferenceCount == 2,
           "out-of-domain inferences counted per pair");
    expect(run.stagesExtrapolating == 1, "the stage is flagged extrapolating");
    expect(approx(run.stages[0].maxExtrapolation, 4.0),
           "worst pair's overflow past the hull edge, in sigma");
    expect(run.stages[0].outOfDomainInputs.size() == 1 &&
               run.stages[0].outOfDomainInputs[0] == "r",
           "flagged input union reported");
  }

  // --- 10. the pair budget bounds the search and says so -------------------
  {
    auto model = makeLinear("pi_cap.json", {"r"}, {"d_heat_dt"}, {{0.0}}, {1.0});
    PairInteraction op;
    op.addStage("cap", DimensionScale::kMicro, model.get());
    PairInteractionRequest req;
    req.elementCount = 4;
    req.fields.push_back({"heat", PairSymmetry::kAntisymmetric, -1e9, 1e9});
    req.state = {0.0, 0.0, 0.0, 0.0};
    req.positions = {0.0, 0.0, 0.0, 0.1, 0.0, 0.0,
                     0.2, 0.0, 0.0, 0.3, 0.0, 0.0};
    req.cutoff = 10.0;  // all six pairs are within range
    req.dt = 1.0;
    const PairInteractionResult full = op.interact(req);
    expect(full.pairCount == 6, "dense cutoff finds every pair");
    req.maxNeighborPairs = 2;
    const PairInteractionResult capped = op.interact(req);
    expect(capped.pairCount == 2, "the budget bounds the evaluated pairs");
    expect(capped.neighborPairsSkipped == 4 && capped.neighborPairsTruncated,
           "the skipped pairs are counted and disclosed");
    // The canonical prefix is (0,1) and (0,2): element 3 stays untouched.
    expect(capped.state[3] == 0.0, "truncation keeps the canonical prefix");
  }

  // --- 11. an unloaded stage degrades gracefully ---------------------------
  {
    trech::ml::GenericSurrogate missing;  // never loaded
    PairInteraction op;
    op.addStage("missing", DimensionScale::kMicro, &missing);
    PairInteractionRequest req = lineRequest(1.0);
    const PairInteractionResult run = op.interact(req);
    expect(!run.ran && run.stagesRun == 0, "no stage could run");
    expect(run.state == req.state, "state left untouched");
    expect(run.stages.size() == 1 && !run.stages[0].ran,
           "the skipped stage is still recorded");
  }

  // --- 12. determinism / purity -------------------------------------------
  {
    auto model = makeLinear("pi_pure.json", {"a_heat", "b_heat", "r"},
                            {"d_heat_dt"}, {{-0.5, 0.5, 0.1}}, {0.0});
    PairInteraction op;
    op.addStage("pure", DimensionScale::kMicro, model.get());
    PairInteractionRequest req = lineRequest(0.2);
    req.links = {{1, 2}};
    const PairInteractionResult a = op.interact(req);
    const PairInteractionResult b = op.interact(req);
    expect(a.state == b.state, "repeat call is bit-identical");
    expect(a.inferenceCount == b.inferenceCount, "and reports the same count");
    expect(req.state[0] == 10.0, "the request is not mutated");
  }

  // --- 13. one call, several MATERIAL COMBINATIONS -------------------------
  // Three cells in a line: two still-solid grains and one melt. What happens
  // between two grains, a grain and its melt, and two melt cells are three
  // different interactions, so each canonical pair kind runs its own operator
  // and a combination nobody declared is simply not evaluated.
  {
    expect(PairInteraction::pairKindName("melt", "sand") ==
               PairInteraction::pairKindName("sand", "melt"),
           "pair kind is canonical (unordered)");
    expect(PairInteraction::pairKindName("sand", "melt") == "melt|sand",
           "pair kind composes sorted names");

    auto solidSolid = makeLinear("pi_ss.json", {"r"}, {"d_heat_dt"}, {{0.0}},
                                 {1.0});
    auto solidMelt = makeLinear("pi_sm.json", {"r"}, {"d_heat_dt"}, {{0.0}},
                                {10.0});
    PairInteraction op;
    op.addStage("grain_grain", DimensionScale::kMicro, solidSolid.get(),
                /*pairKind=*/0);
    op.addStage("grain_melt", DimensionScale::kMicro, solidMelt.get(),
                /*pairKind=*/1);

    PairInteractionRequest req;
    req.elementCount = 3;
    req.fields.push_back({"heat", PairSymmetry::kAntisymmetric, -1e9, 1e9});
    req.state = {0.0, 0.0, 0.0};
    req.positions = {0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 2.0, 0.0, 0.0};
    req.cutoff = 1.5;  // pairs (0,1) and (1,2), not (0,2)
    req.dt = 1.0;
    req.elementKindNames = {"melt", "sand"};
    req.elementKindIndex = {1, 1, 0};  // sand, sand, melt
    req.pairKindNames = {PairInteraction::pairKindName("sand", "sand"),
                         PairInteraction::pairKindName("sand", "melt")};

    const PairInteractionResult run = op.interact(req);
    expect(run.pairCount == 2, "two neighbour pairs inside the cutoff");
    expect(run.inferenceCount == 2,
           "each pair evaluated only by its own combination's operator");
    expect(approx(run.state[0], 1.0) && approx(run.state[2], -10.0),
           "grain-grain and grain-melt pairs used different operators");
    expect(approx(run.state[1], 9.0),
           "the shared member accumulated both interactions");
    expect(run.stages[0].pairsMatched == 1 && run.stages[1].pairsMatched == 1,
           "each stage reports the pairs it evaluated");
    expect(run.stages[0].pairKind == "sand|sand" &&
               run.stages[1].pairKind == "melt|sand",
           "each stage reports the pair kind it was bound to");

    // An undeclared combination is evaluated by nobody: make cell 2 a third
    // material and the grain-melt operator must stop firing.
    req.elementKindNames = {"glass", "sand"};
    req.elementKindIndex = {1, 1, 0};  // sand, sand, glass -> sand|glass
    const PairInteractionResult unknown = op.interact(req);
    expect(unknown.inferenceCount == 1,
           "only the declared sand|sand combination still runs");
    expect(unknown.state[2] == req.state[2],
           "an undeclared material combination leaves its member untouched");
  }

  if (failures == 0) {
    std::printf("test_pair_interaction: OK\n");
  }
  return failures == 0 ? 0 : 1;
}
