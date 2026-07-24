#include "trech/core/Config.hpp"
#include "trech/core/LabSession.hpp"
#include "trech/core/RunOptions.hpp"
#include "trech/js/JsRuntime.hpp"

#ifdef TRECH_HAS_GEANT4
#include "trech/sim/GeantRunner.hpp"
#endif

#include <chrono>
#include <fstream>
#include <iostream>
#include <sstream>
#include <stdexcept>
#include <string>
#include <utility>

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

int runLabSession(const trech::RunOptions& options, int argc, char** argv) {
  trech::TrechConfig cfg;
  if (!options.configPath.empty()) {
    cfg = trech::configFromJsonString(readFileContents(options.configPath));
  }
  cfg.lab.enable = true;
  if (cfg.lab.mode.empty() || cfg.lab.mode == "scenario") {
    cfg.lab.mode = "realtime";
  }
  trech::applyRunOverrides(cfg, options);

  trech::LabSession session(cfg);
#ifdef TRECH_HAS_GEANT4
  trech::RunOptions labRunOptions = options;
  labRunOptions.hookRuntime = nullptr;
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

    if (!result.message.empty()) {
      std::cout << result.message << "\n";
    }
    if (result.hasSnapshot) {
      std::cout << result.snapshotJson << "\n";
    }

    if (result.requestSimulation) {
#ifdef TRECH_HAS_GEANT4
      const auto started = std::chrono::steady_clock::now();
      const int code = geantRunner.run(session.config());
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

    trech::JsRuntime js;
    js.setScriptParameterOverrides(options.scriptParameterOverrides);
    const std::string cfgJson = js.evalExperimentAndGetConfigJson(options.experimentPath);
    if (options.command == trech::CliCommand::Inspect) {
      nlohmann::json inspection;
      inspection["config"] = nlohmann::json::parse(cfgJson);
      inspection["parameters"] = nlohmann::json::parse(js.scriptParametersJson());
      std::cout << inspection.dump() << "\n";
      return 0;
    }
    trech::TrechConfig cfg = trech::configFromJsonString(cfgJson);
    trech::HookRuntimeContext initContext;
    initContext.seed = cfg.run.seed;
    initContext.nEvents = cfg.run.nEvents;
    initContext.determinismMode = cfg.determinism.mode;
    initContext.maxEmitsPerCallback = cfg.hooks.maxEmitsPerCallback;
    initContext.maxEmitPayloadBytes = cfg.hooks.maxEmitPayloadBytes;
    const auto initReport = js.dispatchHook("onInit", initContext, &cfg, true);
    options.hookInitPatchCount = initReport.patchApplied ? 1 : 0;
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
