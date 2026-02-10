#include "trech/core/Config.hpp"
#include "trech/core/RunOptions.hpp"
#include "trech/js/JsRuntime.hpp"

#ifdef TRECH_HAS_GEANT4
#include "trech/sim/GeantRunner.hpp"
#endif

#include <iostream>
#include <string>

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
    trech::JsRuntime js;
    const std::string cfgJson = js.evalExperimentAndGetConfigJson(options.experimentPath);
    trech::TrechConfig cfg = trech::configFromJsonString(cfgJson);
    const auto initReport = js.dispatchHook(
        "onInit",
        trech::HookRuntimeContext{
            cfg.run.seed,
            cfg.run.nEvents,
            cfg.determinism.mode,
            -1,
            -1,
            0.0,
            0.0,
            cfg.hooks.maxEmitsPerCallback,
            cfg.hooks.maxEmitPayloadBytes,
        },
        &cfg,
        true);
    options.hookInitPatchCount = initReport.patchApplied ? 1 : 0;
    options.hookInitEmitCount = static_cast<int>(initReport.emitCount);
    options.hookInitEmitDroppedCount =
        static_cast<int>(initReport.emitDroppedCount);
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
