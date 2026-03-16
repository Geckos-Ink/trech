#pragma once

#include "trech/core/Config.hpp"

#include <string>

namespace trech {

struct LabCommandResult {
  bool ok = true;
  bool continueSession = true;
  bool requestSimulation = false;
  bool hasSnapshot = false;
  std::string snapshotJson;
  std::string message;
};

class LabSession {
 public:
  explicit LabSession(TrechConfig initialConfig = {});

  const TrechConfig& config() const;
  std::string configJson() const;

  // Commands are JSON objects. Supported actions:
  // help, patch, simulate, snapshot, quit.
  LabCommandResult applyCommandJson(const std::string& commandJson);

 private:
  TrechConfig cfg_;
};

} // namespace trech
