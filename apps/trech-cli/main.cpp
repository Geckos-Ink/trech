#include "trech/core/Config.hpp"
#include "trech/core/LabSession.hpp"
#include "trech/core/RunOptions.hpp"
#include "trech/js/JsRuntime.hpp"
#include "trech/js/LabScriptHost.hpp"
#include "trech/ml/ArchitectureGenerator.hpp"
#include "trech/ml/ComputeBudget.hpp"

#ifdef TRECH_HAS_GEANT4
#include "trech/sim/GeantRunner.hpp"
#endif

#include <chrono>
#include <fstream>
#include <iostream>
#include <memory>
#include <sstream>
#include <stdexcept>
#include <string>
#include <utility>
#include <vector>

#include <nlohmann/json.hpp>

namespace {

std::string readFileContents(const std::string& path) {
  std::ifstream in(path);
  if (!in) {
    throw std::runtime_error("Cannot open config file: " + path);
  }
  std::ostringstream buffer;
  buffer << in.rdbuf();
  return buffer.str();
}

// One stderr line per config key the engine never reads (a misspelling or a
// field another tool consumes); the run proceeds, and provenance records them.
void warnIgnoredConfigKeys(const std::vector<std::string>& keys) {
  for (const auto& key : keys) {
    std::cerr << "TRECH config: ignoring unknown key '" << key << "' (the engine does not read it)\n";
  }
}

void warnUnknownConfigKeys(const trech::TrechConfig& cfg, const trech::RunOptions& options) {
  if (options.strictConfig) {
    trech::requireNoUnknownConfigKeys(cfg);  // refuse before any run or lab session starts
  }
  warnIgnoredConfigKeys(cfg.unknownKeys);
}

void warnIgnoredInitPaths(const trech::HookInitTallies& init) {
  for (const auto& path : init.ignoredPatchPaths) {
    std::cerr << "TRECH hooks: onInit override '" << path
              << "' was not applied (not a patchable field, or wrong type)\n";
  }
}

int runLabSession(const trech::RunOptions& options, int argc, char** argv) {
  trech::TrechConfig cfg;
  // Scenario-backed lab: the scenario's hooks drive every batch, and `reload` / `params`
  // re-evaluate it between batches on the same Geant4 kernel.
  std::unique_ptr<trech::LabScriptHost> script;
  if (!options.experimentPath.empty()) {
    script = std::make_unique<trech::LabScriptHost>(
        options.experimentPath, options.scriptParameterOverrides, options.strictConfig);
    auto candidate = script->prepare();
    warnIgnoredInitPaths(candidate.init);
    cfg = candidate.config;
    script->commit(std::move(candidate));
    warnUnknownConfigKeys(cfg, options);
  } else if (!options.configPath.empty()) {
    cfg = trech::configFromJsonString(readFileContents(options.configPath));
    warnUnknownConfigKeys(cfg, options);
  }
  cfg.lab.enable = true;
  if (cfg.lab.mode.empty() || cfg.lab.mode == "scenario") {
    cfg.lab.mode = "realtime";
  }
  trech::applyRunOverrides(cfg, options);

  trech::LabSession session(cfg, options.strictConfig, script != nullptr);
  if (script) session.setScriptStatus(script->status());
#ifdef TRECH_HAS_GEANT4
  trech::RunOptions labRunOptions = options;
  // A stable address: reloads swap a re-evaluated runtime into it between batches.
  labRunOptions.hookRuntime = script ? script->runtime() : nullptr;
  labRunOptions.experimentPath.clear();
  trech::GeantLabRunner geantRunner(std::move(labRunOptions), argc, argv);
#endif
  std::ifstream commandFile;
  std::istream* input = &std::cin;
  const bool interactive = options.commandsPath.empty();
  if (!options.commandsPath.empty()) {
    commandFile.open(options.commandsPath);
    if (!commandFile) {
      std::cerr << "TRECH error: cannot open command file: "
                << options.commandsPath << "\n";
      return 1;
    }
    input = &commandFile;
  } else {
    std::cout << "TRECH lab session started. Enter JSON commands or use "
                 "{\"action\":\"help\"}.\n";
  }
  if (script) {
    std::cout << script->status().dump() << "\n";
  }

  // Transactional: evaluate beside the active runtime, check the kernel, then swap. Returns
  // the refusal, or "" once the new generation is active.
  auto reloadScript = [&](const nlohmann::json& changes, const std::string& trigger) -> std::string {
    try {
      auto candidate = script->prepare(changes);
      auto next = session.rebasedConfig(candidate.config);
#ifdef TRECH_HAS_GEANT4
      if (!geantRunner.accepts(next)) {
        throw std::runtime_error(
            "the re-evaluated scenario changes initialized Geant4 state (geometry, beam, "
            "physics, scoring, output, models or the set of registered hooks); restart the "
            "lab session to use it. The previous script stays active.");
      }
#endif
      warnIgnoredInitPaths(candidate.init);
      script->commit(std::move(candidate), trigger);
      session.adoptConfig(std::move(next));
      warnIgnoredConfigKeys(session.config().unknownKeys);
      session.setScriptStatus(script->status());
      std::cout << "Scenario re-evaluated (script generation " << script->generation()
                << ", " << trigger << ").\n"
                << script->status().dump() << "\n";
      return {};
    } catch (const std::exception& error) {
      return error.what();
    }
  };

  std::string line;
  while (true) {
    if (interactive) {
      std::cout << "trech-lab> " << std::flush;
    }
    if (!std::getline(*input, line)) {
      break;
    }
    const auto first = line.find_first_not_of(" \t\r\n");
    if (first == std::string::npos || line[first] == '#') {
      continue;
    }

    const auto result = session.applyCommandJson(line);
    if (!result.ok) {
      std::cerr << "lab error: " << result.message << "\n";
      if (!interactive) {
        return 1;
      }
      continue;
    }

    warnIgnoredConfigKeys(result.ignoredConfigKeys);
    if (!result.message.empty()) {
      std::cout << result.message << "\n";
    }
    if (result.hasSnapshot) {
      std::cout << result.snapshotJson << "\n";
    }

    if (result.requestScriptReload) {
      const auto trigger = result.scriptParameterChanges.empty() ? "reload" : "params";
      const auto error = reloadScript(result.scriptParameterChanges, trigger);
      if (!error.empty()) {
        std::cerr << "lab error: re-evaluation refused: " << error << "\n";
        if (!interactive) {
          return 1;
        }
        continue;
      }
    }

    if (result.requestSimulation && script && options.labWatch) {
      // A watched edit is picked up before the batch. A refused edit is reported once and the
      // batch runs on the previous script, in a command file too: nothing asked for it.
      const auto fingerprint = script->changedSourceFingerprint();
      if (!fingerprint.empty()) {
        const auto error = reloadScript(nlohmann::json::object(), "watch");
        if (!error.empty()) {
          script->refuseWatchedEdit(fingerprint);
          std::cerr << "lab error: watched edit refused, the previous script stays active: "
                    << error << "\n";
        }
      }
    }

    if (result.requestSimulation) {
#ifdef TRECH_HAS_GEANT4
      const auto started = std::chrono::steady_clock::now();
      int code = 0;
      try {
        if (script) script->prepareBatch(geantRunner.batchMetadata());
        code = geantRunner.run(session.config());
        if (script) script->batchCompleted();
      } catch (const std::exception& error) {
        // A refused geometry (geometry.refuseOn) or a restart-required patch
        // fails this batch only: an interactive session (Studio) stays up and
        // later batches on a refused kernel are refused again; a command file
        // stops with exit 1 as before.
        std::cerr << "lab error: " << error.what() << "\n";
        if (!interactive) {
          return 1;
        }
        continue;
      }
      const auto ended = std::chrono::steady_clock::now();
      const double wallSeconds =
          std::chrono::duration<double>(ended - started).count();
      session.observeSimulation(wallSeconds);
      // Machine-readable feedback for Studio: actual precision/throughput and
      // the online timing estimate that will select the next omitted count.
      std::cout << session.roundTelemetryJson() << "\n";
      if (code != 0) {
        return code;
      }
#else
      std::cout << "simulate requested but Geant4 is disabled.\n";
#endif
    }

    if (!result.continueSession) {
      break;
    }
  }

  return 0;
}

} // namespace

int main(int argc, char** argv) {
  trech::RunOptions options = trech::parseRunOptions(argc, argv);
  if (options.showHelp || !options.valid) {
    if (!options.error.empty()) {
      std::cerr << "Error: " << options.error << "\n";
    }
    std::cerr << trech::runUsage();
    return options.valid ? 0 : 2;
  }

  try {
    if (options.command == trech::CliCommand::Lab) {
      return runLabSession(options, argc, argv);
    }
    if (options.command == trech::CliCommand::Budget) {
      const auto& budget = trech::ml::hostComputeBudget();
      const auto capacity = trech::ml::learnerCapacity(
          budget, static_cast<std::size_t>(options.budgetFeatures), static_cast<std::size_t>(options.budgetTargets));
      nlohmann::json out = {{"budget", budget.toJson()},
                            {"features", options.budgetFeatures},
                            {"targets", options.budgetTargets},
                            {"capacity", capacity.toJson()}};
      std::cout << out.dump(2) << "\n";
      return 0;
    }
    if (options.command == trech::CliCommand::Arch) {
      auto job = trech::ml::loadArchitectureJob(options.experimentPath);
      if (!options.archGenerator.empty()) job.generator = options.archGenerator;
      if (!options.archPython.empty()) job.python = options.archPython;
      const auto outcome = trech::ml::ArchitectureGenerator::generate(job, options.outputDir);
      nlohmann::json summary = {{"generator", outcome.generator},
                                {"model", outcome.modelPath},
                                {"reason", outcome.reason},
                                {"outcome", outcome.outcomePath},
                                {"classic", outcome.outcome.at("classic").at("reference")},
                                {"evolvo", outcome.outcome.at("evolvo").value("status", std::string("not attempted"))}};
      std::cout << summary.dump(2) << "\n";
      return outcome.ok ? 0 : 1;
    }

    trech::JsRuntime js;
    js.setScriptParameterOverrides(options.scriptParameterOverrides);
    if (options.refinement > 0.0) js.setPrecisionRefinement(options.refinement);
    const std::string cfgJson = js.evalExperimentAndGetConfigJson(options.experimentPath);
    if (options.command == trech::CliCommand::Inspect) {
      nlohmann::json inspection;
      inspection["config"] = nlohmann::json::parse(cfgJson);
      inspection["parameters"] = nlohmann::json::parse(js.scriptParametersJson());
      inspection["authoring"] = nlohmann::json::parse(js.authoringMetadataJson());
      // Inspect does not require a parseable config; report unknown keys when
      // it is, and the located parse error (config_error) when it is not.
      try {
        const auto parsed = trech::configFromJsonString(cfgJson);
        if (!parsed.unknownKeys.empty()) {
          inspection["config_unknown_keys"] = parsed.unknownKeys;
        }
      } catch (const std::exception& error) {
        if (options.strictConfig) {
          throw;  // strict inspect requires a parseable config
        }
        inspection["config_error"] = error.what();
      }
      if (options.strictConfig && inspection.contains("config_unknown_keys")) {
        trech::requireNoUnknownConfigKeys(
            trech::configFromJsonString(cfgJson));  // throws, naming the keys
      }
      std::cout << inspection.dump() << "\n";
      return 0;
    }
    trech::TrechConfig cfg = trech::configFromJsonString(cfgJson);
    warnUnknownConfigKeys(cfg, options);
    trech::HookRuntimeContext initContext;
    initContext.seed = cfg.run.seed;
    initContext.nEvents = cfg.run.nEvents;
    initContext.determinismMode = cfg.determinism.mode;
    initContext.maxEmitsPerCallback = cfg.hooks.maxEmitsPerCallback;
    initContext.maxEmitPayloadBytes = cfg.hooks.maxEmitPayloadBytes;
    const auto initReport = js.dispatchHook("onInit", initContext, &cfg, true);
    options.hookInitDispatched = true;
    options.hookInitPatchCount = initReport.patchApplied ? 1 : 0;
    options.hookInitIgnoredPatchPaths = initReport.ignoredPatchPaths;
    for (const auto& path : initReport.ignoredPatchPaths) {
      std::cerr << "TRECH hooks: onInit override '" << path
                << "' was not applied (not a patchable field, or wrong type)\n";
    }
    if (options.strictConfig && !initReport.ignoredPatchPaths.empty()) {
      throw std::invalid_argument("--strict-config: onInit override has " +
                                  std::to_string(initReport.ignoredPatchPaths.size()) +
                                  " path(s) that were not applied");
    }
    options.hookInitEmitCount = static_cast<int>(initReport.emitCount);
    options.hookInitEmitDroppedCount =
        static_cast<int>(initReport.emitDroppedCount);
    options.hookInitPredictCount = static_cast<int>(initReport.predictCount);
    options.hookInitOutOfDomainCount =
        static_cast<int>(initReport.outOfDomainCount);
    options.modelsLoaded = js.loadedModelNames();
    trech::applyRunOverrides(cfg, options);
    options.hookRuntime = &js;

#ifdef TRECH_HAS_GEANT4
    return trech::runGeant4(cfg, options, argc, argv);
#else
    std::cout << "Config parsed OK (Geant4 disabled)\n";
    return 0;
#endif
  } catch (const std::exception& ex) {
    std::cerr << "TRECH error: " << ex.what() << "\n";
    return 1;
  }
}
