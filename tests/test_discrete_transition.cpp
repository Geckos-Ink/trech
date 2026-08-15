#include "trech/ml/DiscreteTransition.hpp"

#include "trech/ml/GenericSurrogate.hpp"

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
                    const std::string& bias) {
  static int sequence = 0;
  const fs::path path = fs::temp_directory_path() /
                        ("trech_transition_" + stem + "_" +
                         std::to_string(++sequence) + ".json");
  std::ofstream out(path);
  out << "{\"model\":\"generic_surrogate_v1\","
      << "\"input_features\":" << inputs << ","
      << "\"output_features\":" << outputs << ","
      << "\"layers\":[{\"weights\":" << weights << ","
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
  failures += expect(materialResult.stages.size() == 2 &&
                         materialResult.stages[0].elementsMatched == 1 &&
                         materialResult.stages[1].elementsMatched == 1 &&
                         materialResult.stages[0].elementKind == "batch_solid" &&
                         materialResult.stages[1].elementKind == "melt",
                     "each stage reports its material and matched cells");

  fs::remove(solidPath, ec);
  fs::remove(meltPath, ec);
  fs::remove(directPath, ec);
  fs::remove(weightedPath, ec);
  fs::remove(renormalizedPath, ec);
  fs::remove(chargePath, ec);
  fs::remove(mixedPath, ec);
  return failures == 0 ? 0 : 1;
}
