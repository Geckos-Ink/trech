#pragma once

#include "trech/core/Config.hpp"

#include <string>
#include <vector>

#include <nlohmann/json.hpp>

namespace trech {

// The part of a config an initialized Geant4 kernel is bound to: everything except the batch
// event count/seed and the lab planner. Two configs with equal signatures can share a kernel.
std::string labKernelSignature(const TrechConfig& cfg);

struct LabCommandResult {
  bool ok = true;
  bool continueSession = true;
  bool requestSimulation = false;
  // Scenario-backed lab: re-evaluate the JavaScript scenario (`reload`, `params`) before the
  // next batch. `scriptParameterChanges` maps TRECH_VALUE names to new JSON values (null
  // restores the authored default); the CLI owns the evaluation and calls adoptConfig().
  bool requestScriptReload = false;
  nlohmann::json scriptParameterChanges = nlohmann::json::object();
  bool hasSnapshot = false;
  bool adaptiveSimulation = false;
  int simulationRounds = 0;
  std::string snapshotJson;
  std::string message;
  std::vector<std::string> ignoredConfigKeys;
};

struct LabRoundTelemetry {
  int plannedRounds = 0;
  int observations = 0;
  bool adaptive = true;
  double targetSeconds = 0.0;
  double lastWallSeconds = 0.0;
  double secondsPerRoundEwma = 0.0;
  double achievedHz = 0.0;
};

class LabSession {
 public:
  explicit LabSession(TrechConfig initialConfig = {}, bool strictConfig = false,
                      bool scriptBacked = false);

  const TrechConfig& config() const;
  std::string configJson() const;
  std::string snapshotJson() const;
  std::string roundTelemetryJson() const;
  const LabRoundTelemetry& roundTelemetry() const;

  // Feed one completed Geant4 batch back into the online planner. Every run,
  // including an explicit override, is a useful timing observation for the
  // current scenario; the override affects only selection, not learning.
  void observeSimulation(double wallSeconds);

  // Commands are JSON objects. Supported actions:
  // help, patch, simulate, snapshot, quit; reload and params in a scenario-backed lab.
  LabCommandResult applyCommandJson(const std::string& commandJson);

  // Scenario-backed lab: the config a re-evaluated scenario yields once this session's state
  // is layered on it. Every accepted `patch` is replayed in order, then the current batch
  // event count and seed are kept and the lab block is re-enabled. Throws when a patch no
  // longer applies; the session itself is not changed.
  TrechConfig rebasedConfig(const TrechConfig& scenarioConfig) const;
  // Make `cfg` (normally a rebasedConfig result) the session config.
  void adoptConfig(TrechConfig cfg);
  bool scriptBacked() const { return scriptBacked_; }
  // Extra object merged into snapshots as lab.script (the CLI's script status).
  void setScriptStatus(nlohmann::json status);

 private:
  int planAdaptiveRounds() const;
  TrechConfig cfg_;
  bool strictConfig_;
  bool scriptBacked_ = false;
  std::vector<nlohmann::json> patches_;
  nlohmann::json scriptStatus_;
  LabRoundTelemetry roundTelemetry_;
};

} // namespace trech
