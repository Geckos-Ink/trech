#pragma once

#include <cstdint>
#include <memory>
#include <string>
#include <vector>

namespace trech {

struct TrechConfig;
class JsRuntime;

namespace sim {
struct DerivedOpticsResult;
struct AnalyticCheckResult;
struct MaterialProbeResult;
}

enum class CliCommand {
  Run,
  Inspect,
  Lab,
};

// Mutable only between BeamOn calls. A real-time lab keeps one initialized
// Geant4 kernel alive, while each compatible batch still needs truthful
// per-batch event counts and canonical configuration provenance.
struct RuntimeRunMetadata {
  int nEvents = 0;
  std::uint64_t seed = 0;
  std::string configJson;
};

struct RunOptions {
  CliCommand command = CliCommand::Run;
  std::string experimentPath;
  std::string configPath;
  std::string commandsPath;
  std::string macroPath;
  std::string outputDir = ".";
  bool enableUi = false;
  bool hasSeedOverride = false;
  std::uint64_t seedOverride = 0;
  bool hasEventOverride = false;
  int eventOverride = 0;
  // Repeatable `name=<json>` overrides consumed by TRECH_VALUE calls while
  // evaluating a JavaScript scenario. Ordinary runs leave this empty, so each
  // declaration returns its authored default.
  std::vector<std::string> scriptParameterOverrides;
  std::string physicsList;
  std::string rngEngine;
  std::vector<std::string> cliArgs;
  bool dnaPhysicsEnabled = false;
  int dnaPhysicsOption = 0;
  bool dnaChemistryEnabled = false;
  int dnaChemistryOption = 0;
  JsRuntime* hookRuntime = nullptr;
  int hookInitPatchCount = 0;
  int hookInitEmitCount = 0;
  int hookInitEmitDroppedCount = 0;
  int hookInitPredictCount = 0;
  int hookInitOutOfDomainCount = 0;
  // Names of scenario-declared learned-inference models that actually loaded
  // (for provenance); sorted deterministically by JsRuntime.
  std::vector<std::string> modelsLoaded;
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
  std::shared_ptr<RuntimeRunMetadata> runtimeMetadata;
  bool showHelp = false;
  bool valid = true;
  std::string error;
};

std::string runUsage();
RunOptions parseRunOptions(int argc, char** argv);
void applyRunOverrides(TrechConfig& cfg, const RunOptions& options);

} // namespace trech
