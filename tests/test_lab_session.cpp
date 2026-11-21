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
  if (expect(!simulateResult.adaptiveSimulation && simulateResult.simulationRounds == 9,
             "Explicit simulate.events should be an override.")) {
    return 1;
  }

  // One timing observation teaches the next omitted event count.  Nine rounds
  // in 0.9 s => 0.1 s/round; at 60 Hz only one round fits (minimum clamp).
  session.observeSimulation(0.9);
  const auto adaptiveResult = session.applyCommandJson(R"({"action":"simulate"})");
  if (expect(adaptiveResult.ok && adaptiveResult.adaptiveSimulation,
             "Omitted simulate.events should use the adaptive planner.")) {
    return 1;
  }
  if (expect(adaptiveResult.simulationRounds == 1 && session.config().run.nEvents == 1,
             "Adaptive planner should target targetHz and respect the minimum.")) {
    return 1;
  }
  if (expect(session.roundTelemetry().observations == 1,
             "Adaptive planner should retain timing observations.")) {
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
  if (expect(snapshotResult.snapshotJson.find("\"roundPlanner\"") != std::string::npos,
             "Snapshot JSON should expose adaptive-round precision.")) {
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

  trech::LabSession fast(initial);
  fast.applyCommandJson(R"({"action":"simulate","events":1})");
  fast.observeSimulation(1e-20);
  const auto fastPlan = fast.applyCommandJson(R"({"action":"simulate"})");
  if (expect(fastPlan.simulationRounds == initial.lab.maxRoundsPerTick,
             "Very fast observations must clamp before integer conversion")) return 1;

  trech::LabSession strict(initial, true);
  const auto before = strict.snapshotJson();
  for (const auto* command : {
           R"({"action":"patch","patch":{"run":{"nEvents":4.0}}})",
           R"({"action":"patch","patch":{"run":{"nEvents":9},"lab":{"targetHZ":90}}})",
           R"({"action":"simulate","events":8,"seed":-1})",
           R"({"action":"simulate","events":8,"run":{"nEvents":4294967297}})",
           R"({"action":"simulate","events":8,"run":true})",
           // A scalar object-only block used to fall back to the defaults.
           R"({"action":"patch","patch":{"run":5}})",
           R"({"action":"patch","patch":{"beam":{"spread":1}}})"}) {
    const auto result = strict.applyCommandJson(command);
    if (expect(!result.ok && !result.requestSimulation && strict.snapshotJson() == before,
               "A rejected command must leave configuration and telemetry intact")) return 1;
  }
  const auto scalarRun = strict.applyCommandJson(R"({"action":"patch","patch":{"run":5}})");
  if (expect(scalarRun.message.find("run must be an object (got number)") != std::string::npos,
             "A scalar run patch must name the block and type")) return 1;
  const auto typo = strict.applyCommandJson(
      R"({"action":"patch","patch":{"lab":{"targetHZ":90}}})");
  if (expect(typo.message.find("lab.targetHZ") != std::string::npos,
             "Expected a qualified path in the strict patch error")) return 1;
  const auto valid = strict.applyCommandJson(
      R"({"action":"patch","patch":{"run":{"nEvents":9},"lab":{"targetHz":90},"hooks":{"inputs":{"custom":true}}}})");
  if (expect(valid.ok && strict.config().run.nEvents == 9 && strict.config().lab.targetHz == 90,
             "Known keys and opaque hook inputs should pass strict patch validation")) return 1;
  const auto permissive = session.applyCommandJson(
      R"({"action":"patch","patch":{"run":{"nEventsTypo":30}}})");
  if (expect(permissive.ok && permissive.ignoredConfigKeys == std::vector<std::string>{"run.nEventsTypo"},
             "Permissive patches should report ignored keys")) return 1;

  // Scenario re-evaluation actions need a scenario-backed session.
  const auto noScript = session.applyCommandJson(R"({"action":"reload"})");
  if (expect(!noScript.ok && noScript.message.find("scenario-backed") != std::string::npos,
             "reload without a scenario must fail and say why")) return 1;

  trech::TrechConfig scenario;
  scenario.run.nEvents = 10;
  scenario.run.seed = 7;
  scenario.beam.particle = "e-";
  scenario.beam.energyMeV = 1.0;
  trech::LabSession live(scenario, false, true);
  if (expect(live.scriptBacked(), "scriptBacked flag")) return 1;
  const auto reload = live.applyCommandJson(R"({"action":"reload"})");
  if (expect(reload.ok && reload.requestScriptReload && reload.scriptParameterChanges.empty() &&
                 !reload.requestSimulation,
             "reload requests a re-evaluation with no parameter changes")) return 1;
  const auto params = live.applyCommandJson(
      R"({"action":"params","values":{"threshold":0.5,"label":null}})");
  if (expect(params.ok && params.requestScriptReload &&
                 params.scriptParameterChanges.at("threshold") == 0.5 &&
                 params.scriptParameterChanges.at("label").is_null(),
             "params carries the TRECH_VALUE changes, null included")) return 1;
  for (const char* bad : {R"({"action":"params"})", R"({"action":"params","values":3})"}) {
    const auto result = live.applyCommandJson(bad);
    if (expect(!result.ok && !result.requestScriptReload, "params needs an object")) return 1;
  }
  const auto help = live.applyCommandJson(R"({"action":"help"})");
  if (expect(help.message.find("reload") != std::string::npos, "help lists reload")) return 1;

  // Rebasing a re-evaluated scenario replays every accepted patch in order (including a
  // null deletion) and keeps the session's batch event count and seed.
  if (expect(live.applyCommandJson(R"({"action":"patch","patch":{"beam":{"energyMeV":2.0}}})").ok &&
                 live.applyCommandJson(R"({"action":"patch","patch":{"beam":{"energyMeV":3.0},"hooks":{"inputs":{"a":1,"b":2}}}})").ok &&
                 live.applyCommandJson(R"({"action":"patch","patch":{"hooks":{"inputs":{"b":null}}}})").ok &&
                 live.applyCommandJson(R"({"action":"patch","patch":{"bogus":{"x":1}}})").ok == true,
             "patches apply")) return 1;
  if (expect(!live.applyCommandJson(R"({"action":"patch","patch":{"run":5}})").ok,
             "an invalid patch is rejected and not recorded")) return 1;
  if (expect(live.applyCommandJson(R"({"action":"simulate","events":3,"seed":99})").ok,
             "simulate sets the batch")) return 1;
  trech::TrechConfig reevaluated = scenario;
  reevaluated.beam.particle = "gamma";
  reevaluated.beam.energyMeV = 5.0;
  reevaluated.run.nEvents = 1000;
  reevaluated.run.seed = 1;
  const auto rebased = live.rebasedConfig(reevaluated);
  if (expect(rebased.beam.particle == "gamma" && rebased.beam.energyMeV == 3.0,
             "scenario values change, patched values are replayed")) return 1;
  if (expect(rebased.run.nEvents == 3 && rebased.run.seed == 99 && rebased.lab.enable,
             "batch count, seed and lab mode are session state")) return 1;
  const auto rebasedJson = nlohmann::json::parse(trech::configToJsonString(rebased));
  if (expect(rebasedJson.at("hooks").at("inputs") == nlohmann::json({{"a", 1}}),
             "null deletions replay in order")) return 1;
  if (expect(live.config().beam.particle == "e-", "rebasedConfig does not change the session"))
    return 1;
  live.adoptConfig(rebased);
  live.setScriptStatus({{"generation", 2}});
  const auto snapshot = nlohmann::json::parse(live.snapshotJson());
  if (expect(live.config().beam.particle == "gamma" &&
                 snapshot.at("lab").at("script").at("generation") == 2,
             "adoptConfig and the snapshot script status")) return 1;

  // Kernel signature: batch count, seed and lab planner are free; anything else binds.
  trech::TrechConfig a = scenario;
  trech::TrechConfig b = scenario;
  b.run.nEvents = 77;
  b.run.seed = 5;
  b.lab.targetHz = 120;
  if (expect(trech::labKernelSignature(a) == trech::labKernelSignature(b),
             "batch/planner changes keep the kernel signature")) return 1;
  b.beam.energyMeV = 9.0;
  if (expect(trech::labKernelSignature(a) != trech::labKernelSignature(b),
             "a beam change binds the kernel")) return 1;

  return 0;
}
