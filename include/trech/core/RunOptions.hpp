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
}

enum class CliCommand {
  Run,
  Lab,
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
  // Names of scenario-declared learned-inference models that actually loaded
  // (for provenance); sorted deterministically by JsRuntime.
  std::vector<std::string> modelsLoaded;
  std::shared_ptr<std::vector<sim::DerivedOpticsResult>> derivedOptics;
  // Classical-formula predictions computed after Geant4 initialization (see
  // sim::computeAnalyticChecks). RunAction pairs each with the run's measured
  // tally at run end and emits the comparison.
  std::shared_ptr<std::vector<sim::AnalyticCheckResult>> analyticChecks;
  bool showHelp = false;
  bool valid = true;
  std::string error;
};

std::string runUsage();
RunOptions parseRunOptions(int argc, char** argv);
void applyRunOverrides(TrechConfig& cfg, const RunOptions& options);

} // namespace trech
