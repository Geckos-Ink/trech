#include "TemporaryDirectory.hpp"

#include "trech/ml/DiscreteTransition.hpp"

#include "trech/ml/GenericSurrogate.hpp"
#include "trech/ml/RivalArbitration.hpp"

#include <cmath>
#include <cstdio>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <string>
#include <vector>

namespace fs = std::filesystem;

namespace {

int expect(bool condition, const std::string& message) {
  if (!condition) {
    std::cerr << message << "\n";
    return 1;
  }
  return 0;
}

fs::path writeModel(const std::string& stem, const std::string& inputs,
                    const std::string& outputs, const std::string& weights,
                    const std::string& bias, const std::string& metadata = "") {
  static int sequence = 0;
  static const trech::test::TemporaryDirectory directory;
  const fs::path path = directory.path() /
                        ("trech_transition_" + stem + "_" +
                         std::to_string(++sequence) + ".json");
  std::ofstream out(path);
  out << "{\"model\":\"generic_surrogate_v1\","
      << "\"input_features\":" << inputs << ","
      << "\"output_features\":" << outputs << ","
      << metadata << "\"layers\":[{\"weights\":" << weights << ","
      << "\"bias\":" << bias << ",\"activation\":\"none\"}]}";
  return path;
}

trech::ml::DiscreteTransitionRequest waterRequest(std::size_t elements) {
  trech::ml::DiscreteTransitionRequest request;
  request.speciesNames = {"water", "hydrogen", "oxygen"};
  request.elementCount = elements;
  request.state.assign(elements * 3, 0);
  request.channels = {
      {"electrolysis", {-2, 2, 1}},
      {"combustion", {2, -2, -1}},
  };
  request.conservation = {
      {"hydrogen_atoms", {2, 2, 0}},
      {"oxygen_atoms", {1, 0, 2}},
      {"charge", {0, 0, 0}},
  };
  request.shared["drive"] = 1.0;
  request.seed = 12345;
  return request;
}

}  // namespace

int main() {
  int failures = 0;
  std::error_code ec;

  // Direct competing hazards: a certain electrolysis attempt is accepted only
  // for the element with enough water. The second attempt is honestly counted
  // and rejected without allowing a negative inventory.
  const fs::path directPath = writeModel(
      "direct", "[\"drive\"]",
      "[\"hazard_electrolysis\",\"hazard_combustion\"]",
      "[[0.0],[0.0]]", "[1.5,-0.5]");
  trech::ml::GenericSurrogate directModel;
  failures += expect(directModel.load(directPath.string()),
                     "direct hazard model should load");
  trech::ml::DiscreteTransition direct;
  direct.addStage("reaction", trech::ml::DimensionScale::kMeso,
                  &directModel);
  auto directRequest = waterRequest(2);
  directRequest.state = {2, 0, 0, 1, 0, 0};
  const auto directResult = direct.react(directRequest);
  failures += expect(directResult.ran && directResult.hazardSchemaValid,
                     "direct hazard operator should run");
  failures += expect(directResult.hazardMode == "direct",
                     "direct hazards should select direct mode");
  failures += expect(directResult.inferenceCount == 2 &&
                         directResult.drawCount == 2 &&
                         directResult.transitionAttempts == 2 &&
                         directResult.hazardsClamped == 4,
                     "two elements should produce two inferences/draws/attempts");
  failures += expect(directResult.transitionsAccepted == 1 &&
                         directResult.rejectedAvailability == 1,
                     "availability should accept one and reject one transition");
  failures += expect(
      directResult.state == std::vector<std::int64_t>({0, 2, 1, 1, 0, 0}),
      "stoichiometry should apply atomically without negative species");

  // Missing Geant4/condition input must not become a constant-biased hazard.
  auto absentRequest = directRequest;
  absentRequest.shared.clear();
  const auto absentResult = direct.react(absentRequest);
  failures += expect(!absentResult.ran && absentResult.stagesRun == 0 &&
                         absentResult.inferenceCount == 0 && absentResult.drawCount == 0 &&
                         absentResult.state == absentRequest.state &&
                         absentResult.stages[0].missingInputs == std::vector<std::string>{"drive"},
                     "missing reaction facts skip inference, draws and mutation");
  // A producer for a different material cannot supply this reaction's drive.
  const fs::path producerPath = writeModel("producer", "[\"dt\"]", "[\"signal\"]", "[[0.0]]", "[1.0]");
  const fs::path consumerPath = writeModel("consumer", "[\"signal\"]", "[\"hazard_electrolysis\"]", "[[0.0]]", "[1.0]");
  trech::ml::GenericSurrogate producerModel, consumerModel;
  failures += expect(producerModel.load(producerPath.string()) && consumerModel.load(consumerPath.string()),
                     "dependency models should load");
  trech::ml::DiscreteTransition dependency;
  dependency.addStage("producer", trech::ml::DimensionScale::kNano, &producerModel, 0);
  dependency.addStage("consumer", trech::ml::DimensionScale::kMeso, &consumerModel);
  auto dependencyRequest = waterRequest(2);
  dependencyRequest.state = {2, 0, 0, 2, 0, 0};
  dependencyRequest.elementKindNames = {"water", "other"};
  dependencyRequest.elementKindIndex = {0, 1};
  const auto dependencyResult = dependency.react(dependencyRequest);
  failures += expect(dependencyResult.inferenceCount == 2 && dependencyResult.drawCount == 1 &&
                         dependencyResult.state == std::vector<std::int64_t>{0, 2, 1, 2, 0, 0} &&
                         dependencyResult.stages[1].missingInputs == std::vector<std::string>{"signal"},
                     "missing material-local reaction signal never draws or mutates");
  trech::ml::DiscreteTransition blockedHazard;
  blockedHazard.addStage("property", trech::ml::DimensionScale::kNano, &producerModel);
  blockedHazard.addStage("reaction", trech::ml::DimensionScale::kMeso, &directModel);
  auto spoofedRequest = absentRequest;
  spoofedRequest.shared["hazard_electrolysis"] = 1.0;
  const auto spoofed = blockedHazard.react(spoofedRequest);
  failures += expect(spoofed.inferenceCount == 2 && spoofed.drawCount == 0 &&
                         spoofed.state == spoofedRequest.state,
                     "shared hazard keys cannot replace a blocked reaction model's outputs");
  fs::remove(producerPath, ec);
  fs::remove(consumerPath, ec);

  // Weighted mode: one certain event hazard and two relative channel weights.
  // Repeating the same seed must produce byte-identical integer state and
  // channel counts; both channels should be sampled across the ensemble.
  const fs::path weightedPath = writeModel(
      "weighted", "[\"drive\"]",
      "[\"hazard\",\"weight_to_b\",\"weight_to_c\"]",
      "[[0.0],[0.0],[0.0]]", "[1.0,0.25,0.75]");
  trech::ml::GenericSurrogate weightedModel;
  failures += expect(weightedModel.load(weightedPath.string()),
                     "weighted hazard model should load");
  trech::ml::DiscreteTransition weighted;
  weighted.addStage("routing", trech::ml::DimensionScale::kMicro,
                    &weightedModel);
  trech::ml::DiscreteTransitionRequest weightedRequest;
  weightedRequest.speciesNames = {"a", "b", "c"};
  weightedRequest.elementCount = 256;
  weightedRequest.state.assign(256 * 3, 0);
  for (std::size_t i = 0; i < weightedRequest.elementCount; ++i) {
    weightedRequest.state[i * 3] = 1;
  }
  weightedRequest.channels = {
      {"to_b", {-1, 1, 0}},
      {"to_c", {-1, 0, 1}},
  };
  weightedRequest.conservation = {{"packet_count", {1, 1, 1}}};
  weightedRequest.shared["drive"] = 1.0;
  weightedRequest.seed = 987654321;
  const auto weightedA = weighted.react(weightedRequest);
  const auto weightedB = weighted.react(weightedRequest);
  failures += expect(weightedA.hazardMode == "weighted" &&
                         weightedA.transitionsAccepted == 256 &&
                         weightedA.drawCount == 256,
                     "weighted mode should accept one transition per element");
  failures += expect(weightedA.state == weightedB.state &&
                         weightedA.channelTrace[0].accepted ==
                             weightedB.channelTrace[0].accepted &&
                         weightedA.channelTrace[1].accepted ==
                             weightedB.channelTrace[1].accepted,
                     "same seed should reproduce every discrete choice");
  failures += expect(weightedA.channelTrace[0].accepted > 0 &&
                         weightedA.channelTrace[1].accepted > 0,
                     "both positive channel weights should be sampled");

  const fs::path renormalizedPath = writeModel(
      "renormalized", "[\"drive\"]",
      "[\"hazard_to_b\",\"hazard_to_c\"]",
      "[[0.0],[0.0]]", "[0.8,0.8]");
  trech::ml::GenericSurrogate renormalizedModel;
  failures += expect(renormalizedModel.load(renormalizedPath.string()),
                     "renormalized direct-hazard model should load");
  trech::ml::DiscreteTransition renormalized;
  renormalized.addStage("routing", trech::ml::DimensionScale::kMicro,
                        &renormalizedModel);
  const auto renormalizedResult = renormalized.react(weightedRequest);
  failures += expect(
      renormalizedResult.transitionsAccepted == 256 &&
          renormalizedResult.hazardRenormalizedElements == 256 &&
          renormalizedResult.channelTrace[0].accepted > 0 &&
          renormalizedResult.channelTrace[1].accepted > 0,
      "direct hazards above unity should renormalize and sample both channels");

  // A non-conserving matrix is rejected before inference or RNG consumption.
  auto invalidRequest = waterRequest(1);
  invalidRequest.state = {2, 0, 0};
  invalidRequest.channels[0].delta = {-2, 1, 1};  // loses two H atoms
  const auto invalid = direct.react(invalidRequest);
  failures += expect(!invalid.transitionSchemaValid && !invalid.ran &&
                         invalid.inferenceCount == 0 &&
                         invalid.drawCount == 0 &&
                         invalid.state == invalidRequest.state,
                     "non-conserving topology must not infer, draw, or mutate");
  failures += expect(
      !invalid.channelTrace[0].violatedConservation.empty(),
      "invalid channel should name its violated conservation invariant");

  // Non-trivial signed charge conservation: a cation/anion pair becomes one
  // neutral packet while net charge and constituent count remain exact.
  const fs::path chargePath = writeModel(
      "charge", "[\"drive\"]", "[\"hazard_neutralize\"]",
      "[[0.0]]", "[1.0]");
  trech::ml::GenericSurrogate chargeModel;
  failures += expect(chargeModel.load(chargePath.string()),
                     "charge transition model should load");
  trech::ml::DiscreteTransition charge;
  charge.addStage("neutralization", trech::ml::DimensionScale::kAtomic,
                  &chargeModel);
  trech::ml::DiscreteTransitionRequest chargeRequest;
  chargeRequest.speciesNames = {"cation", "anion", "neutral"};
  chargeRequest.elementCount = 1;
  chargeRequest.state = {1, 1, 0};
  chargeRequest.shared["drive"] = 1.0;
  chargeRequest.channels = {{"neutralize", {-1, -1, 1}}};
  chargeRequest.conservation = {
      {"charge", {1, -1, 0}},
      {"constituents", {1, 1, 2}},
  };
  chargeRequest.seed = 42;
  const auto chargeResult = charge.react(chargeRequest);
  failures += expect(
      chargeResult.transitionSchemaValid &&
          chargeResult.transitionsAccepted == 1 &&
          chargeResult.state == std::vector<std::int64_t>({0, 0, 1}),
      "signed charge and constituent conservation should accept exactly");

  // Mixing direct hazards with a total-hazard/weight interface is ambiguous.
  // Inference remains honestly counted, but no draw or state mutation occurs.
  const fs::path mixedPath = writeModel(
      "mixed", "[\"drive\"]",
      "[\"hazard\",\"hazard_electrolysis\",\"weight_electrolysis\"]",
      "[[0.0],[0.0],[0.0]]", "[1.0,1.0,1.0]");
  trech::ml::GenericSurrogate mixedModel;
  failures += expect(mixedModel.load(mixedPath.string()),
                     "mixed hazard model should load");
  trech::ml::DiscreteTransition mixed;
  mixed.addStage("mixed", trech::ml::DimensionScale::kMeso, &mixedModel);
  auto mixedRequest = waterRequest(1);
  mixedRequest.state = {2, 0, 0};
  const auto mixedResult = mixed.react(mixedRequest);
  failures += expect(mixedResult.ran && !mixedResult.hazardSchemaValid &&
                         mixedResult.inferenceCount == 1 &&
                         mixedResult.drawCount == 0 &&
                         mixedResult.state == mixedRequest.state,
                     "ambiguous hazard schema must infer but never draw/mutate");

  // Several MATERIALS in one call: each cell's chemistry is chosen by its own
  // material class. A batch cell that is still solid and a molten cell in the
  // same inventory arrays evaluate different learned hazards, and a cell whose
  // material has no operator draws nothing at all -- which is what a run that
  // CREATES a material needs, since a cell changes class as it transforms.
  const fs::path solidPath = writeModel(
      "solid_hazard", "[\"drive\"]", "[\"hazard_electrolysis\"]", "[[0.0]]",
      "[1.0]");
  const fs::path meltPath = writeModel(
      "melt_hazard", "[\"drive\"]", "[\"hazard_combustion\"]", "[[0.0]]",
      "[1.0]");
  trech::ml::GenericSurrogate solidModel;
  trech::ml::GenericSurrogate meltModel;
  failures += expect(solidModel.load(solidPath.string()) &&
                         meltModel.load(meltPath.string()),
                     "per-material hazard models should load");
  trech::ml::DiscreteTransition perMaterial;
  perMaterial.addStage("solid_op", trech::ml::DimensionScale::kMeso, &solidModel,
                       /*elementKind=*/0);
  perMaterial.addStage("melt_op", trech::ml::DimensionScale::kMeso, &meltModel,
                       /*elementKind=*/1);
  auto materialRequest = waterRequest(3);
  //          cell 0 (solid): 2 water     cell 1 (melt): 0 water, 2 H2, 1 O2
  //          cell 2 (inert material, no operator): 2 water
  materialRequest.state = {2, 0, 0, 0, 2, 1, 2, 0, 0};
  materialRequest.elementKindNames = {"batch_solid", "melt", "inert"};
  materialRequest.elementKindIndex = {0, 1, 2};
  const auto materialResult = perMaterial.react(materialRequest);
  failures += expect(materialResult.ran && materialResult.hazardSchemaValid &&
                         materialResult.hazardMode == "direct",
                     "per-material discrete operators should run");
  failures += expect(materialResult.inferenceCount == 2 &&
                         materialResult.drawCount == 2 &&
                         materialResult.elementsEvaluated == 2,
                     "only the claimed cells infer and draw");
  failures += expect(
      materialResult.state ==
          std::vector<std::int64_t>({0, 2, 1, 2, 0, 0, 2, 0, 0}),
      "each material ran its own channel and the unclaimed cell is untouched");

  // The same three cells with NO labels: two rival hazard models (both predict
  // both hazards) trained on separate `regime` domains. Domain routing gives
  // each cell the law whose domain covers it and leaves the cell no domain
  // covers untouched -- the unnamed grouping, with the same outcome as the
  // labelled call above.
  const std::string regimeDomain =
      "\"input_std\":[1],\"input_domain\":{\"standardized_radius\":[1]},";
  const fs::path lowPath = writeModel(
      "regime_low", "[\"regime\"]", "[\"hazard_electrolysis\",\"hazard_combustion\"]",
      "[[0.0],[0.0]]", "[1.0,0.0]", "\"input_mean\":[-5]," + regimeDomain);
  const fs::path highPath = writeModel(
      "regime_high", "[\"regime\"]", "[\"hazard_electrolysis\",\"hazard_combustion\"]",
      "[[0.0],[0.0]]", "[0.0,1.0]", "\"input_mean\":[5]," + regimeDomain);
  trech::ml::GenericSurrogate lowModel;
  trech::ml::GenericSurrogate highModel;
  failures += expect(lowModel.load(lowPath.string()) && highModel.load(highPath.string()),
                     "regime hazard models should load");
  trech::ml::DiscreteTransition routed;
  routed.addStage("low_op", trech::ml::DimensionScale::kMeso, &lowModel);
  routed.addStage("high_op", trech::ml::DimensionScale::kMeso, &highModel);
  auto routedRequest = waterRequest(3);
  routedRequest.state = {2, 0, 0, 0, 2, 1, 2, 0, 0};
  routedRequest.auxNames = {"regime"};
  routedRequest.aux = {-5.0, 5.0, 50.0};
  routedRequest.routeByDomain = true;
  const auto routedResult = routed.react(routedRequest);
  failures += expect(routedResult.routing.active && routedResult.routing.sets.size() == 1 &&
                         routedResult.routing.sets[0].elementsUncovered == 1 &&
                         routedResult.routing.groups.size() == 3,
                     "routed hazards form one rival set and three unnamed groups");
  failures += expect(routedResult.inferenceCount == 2 && routedResult.drawCount == 2,
                     "only covered cells infer and draw");
  failures += expect(
      routedResult.state == std::vector<std::int64_t>({0, 2, 1, 2, 0, 0, 2, 0, 0}),
      "each cell ran the law its domain selected; the uncovered cell is untouched");
  fs::remove(lowPath, ec);
  fs::remove(highPath, ec);

  // Rival arbitration: two hazard laws cover the SAME cells for the same
  // channel. Coverage cannot tell alternatives (choose one) from cooperating
  // processes (combine them); reference transition probabilities decide.
  //   up:   hazard_electrolysis = 0.4 x      down: hazard_electrolysis = 0.4 (1 - x)
  {
    const std::string wide =
        "\"input_mean\":[0],\"input_std\":[1],\"input_domain\":{\"standardized_radius\":[10]},";
    const fs::path upPath = writeModel("rival_up", "[\"x\"]",
                                       "[\"hazard_electrolysis\",\"hazard_combustion\"]",
                                       "[[0.4],[0.0]]", "[0.0,0.0]", wide);
    const fs::path downPath = writeModel("rival_down", "[\"x\"]",
                                         "[\"hazard_electrolysis\",\"hazard_combustion\"]",
                                         "[[-0.4],[0.0]]", "[0.4,0.0]", wide);
    trech::ml::GenericSurrogate upModel, downModel;
    failures += expect(upModel.load(upPath.string()) && downModel.load(downPath.string()),
                       "rival hazard models should load");
    trech::ml::DiscreteTransition rivalsOp;
    rivalsOp.addStage("law_up", trech::ml::DimensionScale::kMeso, &upModel);
    rivalsOp.addStage("law_down", trech::ml::DimensionScale::kMeso, &downModel);
    constexpr std::size_t kCells = 64;
    auto request = [&](int call) {
      auto req = waterRequest(kCells);
      for (std::size_t e = 0; e < kCells; ++e) req.state[e * 3] = 4;
      req.auxNames = {"x"};
      for (std::size_t e = 0; e < kCells; ++e)
        req.aux.push_back(static_cast<double>((e * 37 + static_cast<std::size_t>(call) * 11) % kCells) / 63.0);
      req.routeByDomain = true;
      req.seed = 777 + static_cast<std::uint64_t>(call);
      return req;
    };
    auto callFor = [&](const trech::ml::DiscreteTransitionRequest& req, auto truth, bool graded) {
      trech::ml::RivalArbitration::Call c;
      c.fieldNames = {"electrolysis", "combustion"};
      c.featureNames = {"water", "hydrogen", "oxygen", "x"};
      for (std::size_t e = 0; e < kCells; ++e) {
        for (std::size_t sp = 0; sp < 3; ++sp) c.features.push_back(static_cast<double>(req.state[e * 3 + sp]));
        c.features.push_back(req.aux[e]);
        if (graded) { c.reference.push_back(truth(req.aux[e])); c.reference.push_back(0.0); }
      }
      c.seed = 5;
      return c;
    };

    // Without a callback the last rival to run sets the hazard, as before.
    const auto plain = rivalsOp.react(request(0));
    failures += expect(plain.rivals.empty() && plain.routing.sets.size() == 1 &&
                           plain.routing.sets[0].elementsOverlapping == kCells,
                       "overlapping hazard rivals form one set without arbitration");

    struct Outcome { double lateError = 0, lateCombinedShare = 0; std::vector<std::int64_t> lastState; std::size_t lastDraws = 0; };
    auto run = [&](auto truth) {
      trech::ml::RivalArbitration pool;
      Outcome out;
      double err = 0, n = 0, combined = 0, chosen = 0;
      for (int call = 0; call < 40; ++call) {
        auto req = request(call);
        const auto c = callFor(req, truth, true);
        req.arbitrateRivals = [&](std::vector<trech::ml::RivalCandidates>& sets) { pool.arbitrate(sets, c); };
        const auto r = rivalsOp.react(req);
        if (call >= 30) {
          for (const auto& rc : r.rivals) {
            const std::size_t C = rc.candidates();
            for (std::size_t j = 0; j < rc.elements.size(); ++j) {
              const int ch = rc.choice[j];
              chosen += 1;
              if (ch < 0) { err += 1.0; n += 1; continue; }  // unarbitrated late cell counts as a miss
              combined += ch == static_cast<int>(rc.members.size()) ? 1 : 0;
              const double d = rc.totals[(j * C + static_cast<std::size_t>(ch)) * 2] - truth(req.aux[rc.elements[j]]);
              err += d * d; n += 1;
            }
          }
        }
        out.lastState = r.state;
        out.lastDraws = r.drawCount;
      }
      out.lateError = n > 0 ? std::sqrt(err / n) : 1.0;
      out.lateCombinedShare = chosen > 0 ? combined / chosen : 0.0;
      return out;
    };
    // Alternatives by context domain: law_up is right below x = 0.5, law_down above.
    auto alternatives = [](double x) { return x < 0.5 ? 0.4 * x : 0.4 * (1.0 - x); };
    const Outcome alt = run(alternatives);
    // Cooperating processes: the truth is the combination of both hazards.
    const Outcome coop = run([](double) { return 0.4; });
    std::printf("react rival arbitration: alternatives late rmse %.4f (combined share %.2f); "
                "cooperation late rmse %.4f (combined share %.2f)\n",
                alt.lateError, alt.lateCombinedShare, coop.lateError, coop.lateCombinedShare);
    failures += expect(alt.lateError < 0.02 && alt.lateCombinedShare < 0.1,
                       "alternative hazard rivals: the evidence picks the right law per context domain");
    failures += expect(coop.lateError < 1e-9 && coop.lateCombinedShare > 0.9,
                       "cooperating hazard rivals: the evidence keeps their combination");
    // The choice precedes every draw: the same evidence replays byte-identically.
    const Outcome again = run(alternatives);
    failures += expect(again.lastState == alt.lastState && again.lastDraws == alt.lastDraws,
                       "arbitrated draws are deterministic");

    // Ungraded with a fresh pool: nothing learned, nothing changes.
    trech::ml::RivalArbitration fresh;
    auto req = request(0);
    const auto c = callFor(req, alternatives, false);
    req.arbitrateRivals = [&](std::vector<trech::ml::RivalCandidates>& sets) { fresh.arbitrate(sets, c); };
    const auto same = rivalsOp.react(req);
    failures += expect(same.state == plain.state && same.drawCount == plain.drawCount &&
                           same.transitionsAccepted == plain.transitionsAccepted && fresh.empty(),
                       "no evidence and no learned arbiter: byte-identical draws and state");
    fs::remove(upPath, ec);
    fs::remove(downPath, ec);
  }
  failures += expect(materialResult.stages.size() == 2 &&
                         materialResult.stages[0].elementsMatched == 1 &&
                         materialResult.stages[1].elementsMatched == 1 &&
                         materialResult.stages[0].elementKind == "batch_solid" &&
                         materialResult.stages[1].elementKind == "melt",
                     "each stage reports its material and matched cells");

  // Feature and joint starvation can both mark one evaluation; count their
  // union once and retain off-band evidence independently of hull failures.
  {
    const auto trustPath = writeModel("trust_counts", "[\"drive\"]",
        "[\"hazard_electrolysis\",\"hazard_combustion\"]",
        "[[0],[0]]", "[0,0]", R"("trained_scale_bands":["atomic"],
      "input_domain":{"standardized_radius":[10],"input_min":[0],"input_max":[4],
        "occupancy":{"bins":4,"counts":[[1,0,0,1]]},
        "joint":{"centers":[[0]],"radius":0.25}},)");
    trech::ml::GenericSurrogate model;
    failures += expect(model.load(trustPath.string()) && model.hasJointDomain() && model.hasOccupancy(),
                       "reaction trust fixture carries both density checks");
    trech::ml::DiscreteTransition op;
    op.addStage("off_band", trech::ml::DimensionScale::kMeso, &model);
    auto req = waterRequest(2);
    req.shared["drive"] = 2;
    const auto res = op.react(req);
    failures += expect(res.inferenceCount == 2 && res.starvedInferenceCount == 2 &&
                           res.scaleMismatchedInferenceCount == 2 && res.outOfDomainInferenceCount == 0,
                       "overlapping reaction density checks count once per element");
    failures += expect(res.stages[0].elementsStarved == 2 && res.stages[0].elementsJointStarved == 2,
                       "reaction fixture actually exercises overlapping density failures");
    req.shared["drive"] = 0;
    const auto covered = op.react(req);
    failures += expect(covered.starvedInferenceCount == 0 && covered.scaleMismatchedInferenceCount == 2,
                       "reaction band counts are independent of density failures");
    req.shared["drive"] = 2;
    trech::ml::DiscreteTransition onBand;
    onBand.addStage("on_band", trech::ml::DimensionScale::kAtomic, &model);
    const auto starved = onBand.react(req);
    failures += expect(starved.starvedInferenceCount == 2 && starved.scaleMismatchedInferenceCount == 0,
                       "reaction density failures are independent of band matching");
    req.shared.clear();
    const auto blocked = op.react(req);
    failures += expect(blocked.inferenceCount == 0 && blocked.starvedInferenceCount == 0 &&
                           blocked.scaleMismatchedInferenceCount == 0 && blocked.drawCount == 0,
                       "blocked reaction stages contribute no density/band count or draw");
    fs::remove(trustPath, ec);
  }

  fs::remove(solidPath, ec);
  fs::remove(meltPath, ec);
  fs::remove(directPath, ec);
  fs::remove(weightedPath, ec);
  fs::remove(renormalizedPath, ec);
  fs::remove(chargePath, ec);
  fs::remove(mixedPath, ec);
  return failures == 0 ? 0 : 1;
}
