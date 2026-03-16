#include "trech/core/LabSession.hpp"

#include <iostream>

namespace {

int expect(bool condition, const char* message) {
  if (!condition) {
    std::cerr << message << "\n";
    return 1;
  }
  return 0;
}

} // namespace

int main() {
  trech::TrechConfig initial;
  initial.run.nEvents = 4;
  initial.run.seed = 15;

  trech::LabSession session(initial);
  if (expect(session.config().lab.enable, "Lab mode should be enabled in session.")) {
    return 1;
  }

  const auto patchResult = session.applyCommandJson(
      R"({"action":"patch","patch":{"beam":{"particle":"gamma","energyMeV":2.5},"chemistry":{"enable":true,"solver":"stub"}}})");
  if (expect(patchResult.ok, "Patch command should succeed.")) {
    return 1;
  }
  if (expect(session.config().beam.particle == "gamma", "Patch beam particle mismatch.")) {
    return 1;
  }
  if (expect(session.config().chemistry.enable, "Patch chemistry enable mismatch.")) {
    return 1;
  }

  const auto simulateResult =
      session.applyCommandJson(R"({"action":"simulate","events":9,"seed":1234})");
  if (expect(simulateResult.ok, "Simulate command should succeed.")) {
    return 1;
  }
  if (expect(simulateResult.requestSimulation, "Simulate should request execution.")) {
    return 1;
  }
  if (expect(session.config().run.nEvents == 9, "Simulate events mismatch.")) {
    return 1;
  }
  if (expect(session.config().run.seed == 1234, "Simulate seed mismatch.")) {
    return 1;
  }

  const auto snapshotResult = session.applyCommandJson(R"({"action":"snapshot"})");
  if (expect(snapshotResult.ok && snapshotResult.hasSnapshot,
             "Snapshot should return config JSON.")) {
    return 1;
  }
  if (expect(snapshotResult.snapshotJson.find("\"particle\":\"gamma\"") != std::string::npos,
             "Snapshot JSON should include patched beam.")) {
    return 1;
  }

  const auto badResult = session.applyCommandJson(R"({"action":"unknown"})");
  if (expect(!badResult.ok, "Unknown action should fail.")) {
    return 1;
  }

  const auto quitResult = session.applyCommandJson(R"({"action":"quit"})");
  if (expect(quitResult.ok && !quitResult.continueSession,
             "Quit action should stop the session.")) {
    return 1;
  }

  return 0;
}
