#pragma once

#include "trech/core/Config.hpp"

#include <string>

namespace trech {

struct LabCommandResult {
  bool ok = true;
  bool continueSession = true;
  bool requestSimulation = false;
  bool hasSnapshot = false;
  bool adaptiveSimulation = false;
  int simulationRounds = 0;
  std::string snapshotJson;
  std::string message;
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
  explicit LabSession(TrechConfig initialConfig = {});

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
  // help, patch, simulate, snapshot, quit.
  LabCommandResult applyCommandJson(const std::string& commandJson);

 private:
  int planAdaptiveRounds() const;
  TrechConfig cfg_;
  LabRoundTelemetry roundTelemetry_;
};

} // namespace trech
