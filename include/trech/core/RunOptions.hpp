#pragma once

#include <cstdint>
#include <memory>
#include <string>
#include <vector>

namespace trech {

struct TrechConfig;
class JsRuntime;
class SimulationBudget;

namespace ml {
struct StratifierModelSnapshot;
}

namespace sim {
struct DerivedOpticsResult;
struct AnalyticCheckResult;
struct MaterialProbeResult;
struct GeometryResolutionReport;
}

enum class CliCommand {
  Run,
  Inspect,
  Lab,
  Arch,
  Budget,
};

// onInit tallies one batch reports (patch/emit/predict counts and unapplied override paths).
struct HookInitTallies {
  bool dispatched = false;
  int patchCount = 0;
  std::vector<std::string> ignoredPatchPaths;
  int emitCount = 0;
  int emitDroppedCount = 0;
  int predictCount = 0;
  int outOfDomainCount = 0;
};

// Mutable only between BeamOn calls. A real-time lab keeps one initialized
// Geant4 kernel alive, while each compatible batch still needs truthful
// per-batch event counts and canonical configuration provenance.
struct RuntimeRunMetadata {
  int nEvents = 0;
  std::uint64_t seed = 0;
  std::string configJson;
  // Scenario-backed lab only (`trech lab <experiment.js>`). When set, this batch reports
  // `hookInit` instead of the RunOptions tallies copied when the kernel was built: onInit
  // runs once per script (re)load, so only the first batch after a load counts it.
  bool hasHookInit = false;
  HookInitTallies hookInit;
  // Canonical JSON identity of the hook script generation that drives this batch (provenance
  // `lab_script`); empty outside a scenario-backed lab.
  std::string labScriptJson;
};

struct RunOptions {
  CliCommand command = CliCommand::Run;
  std::string experimentPath;
  std::string configPath;
  std::string commandsPath;
  std::string macroPath;
  std::string outputDir = ".";
  bool enableUi = false;
  // --strict-config: refuse a config with keys the engine never reads.
  bool strictConfig = false;
  bool hasSeedOverride = false;
  std::uint64_t seedOverride = 0;
  bool hasEventOverride = false;
  int eventOverride = 0;
  // Zero leaves scenario defaults untouched. Refinement is resolved in JS;
  // wall time is an explicit predictive-only, event-boundary budget.
  double refinement = 0.0;
  double timeBudgetSeconds = 0.0;
  // Observation-only 3D capture (`--viz`/`--viz-all`/`--viz-max-trajectories`):
  // turns on the Geant4 trajectory recorder + scene manifest for this run
  // without editing the scenario, so any experiment can be replayed in the
  // classic 3D viewer. Recording never alters transport, but the captured
  // run's serialized config (and hash) honestly records viz as enabled.
  bool captureViz = false;
  bool captureVizNonOptical = false;
  int captureVizMaxTrajectories = 0;
  // Repeatable `name=<json>` overrides consumed by TRECH_VALUE calls while
  // evaluating a JavaScript scenario. Ordinary runs leave this empty, so each
  // declaration returns its authored default.
  std::vector<std::string> scriptParameterOverrides;
  // `trech lab <experiment.js> --watch`: before each batch, re-evaluate the scenario when a
  // file it read changed on disk (same transactional rules as the `reload` command).
  bool labWatch = false;
  // `trech arch <job.json>`: generator override (evolvo|classic) and
  // Python interpreter for the Evolvo worker; empty keeps the job's values.
  std::string archGenerator;
  std::string archPython;
  // `trech budget`: the learner shape the capacity is computed for.
  int budgetFeatures = 4;
  int budgetTargets = 2;
  std::string physicsList;
  std::string rngEngine;
  std::vector<std::string> cliArgs;
  bool dnaPhysicsEnabled = false;
  int dnaPhysicsOption = 0;
  bool dnaChemistryEnabled = false;
  int dnaChemistryOption = 0;
  JsRuntime* hookRuntime = nullptr;
  // True once the CLI dispatched onInit through a JS runtime. A config-only lab
  // runs no JavaScript, so a registered onInit is not counted there; a scenario-backed
  // lab reports each load's onInit through RuntimeRunMetadata instead.
  bool hookInitDispatched = false;
  int hookInitPatchCount = 0;
  // Leaf paths of the onInit override that were not applied (HookDispatchReport).
  std::vector<std::string> hookInitIgnoredPatchPaths;
  int hookInitEmitCount = 0;
  int hookInitEmitDroppedCount = 0;
  int hookInitPredictCount = 0;
  int hookInitOutOfDomainCount = 0;
  // Names of scenario-declared learned-inference models that actually loaded
  // (for provenance); sorted deterministically by JsRuntime.
  std::vector<std::string> modelsLoaded;
  std::string modelArtifactsJson;
  std::shared_ptr<const ml::StratifierModelSnapshot> stratifierModelSnapshot;
  std::shared_ptr<std::vector<sim::DerivedOpticsResult>> derivedOptics;
  // Classical-formula predictions computed after Geant4 initialization (see
  // sim::computeAnalyticChecks). RunAction pairs each with the run's measured
  // tally at run end and emits the comparison.
  std::shared_ptr<std::vector<sim::AnalyticCheckResult>> analyticChecks;
  // Geant4 material-composition probes (opt-in via cfg.materialProbe). Filled
  // after Geant4 initialization in GeantRunner (the material table must exist),
  // then RunAction emits them to scores and exposes them to hooks as
  // ctx.materials. Same shared-carrier pattern as analyticChecks above.
  std::shared_ptr<std::vector<sim::MaterialProbeResult>> materialProbes;
  // Filled by DetectorConstruction::Construct() during Initialize: material and
  // parent substitutions plus volumes that were not built. RunAction copies a
  // non-empty report into provenance.
  std::shared_ptr<sim::GeometryResolutionReport> geometryResolution;
  std::shared_ptr<RuntimeRunMetadata> runtimeMetadata;
  std::shared_ptr<SimulationBudget> simulationBudget;
  bool showHelp = false;
  bool valid = true;
  std::string error;
};

std::string runUsage();
RunOptions parseRunOptions(int argc, char** argv);
void applyRunOverrides(TrechConfig& cfg, const RunOptions& options);

} // namespace trech
