#include "trech/core/Config.hpp"
#include "trech/core/RunOptions.hpp"
#include "trech/js/JsRuntime.hpp"

#ifdef TRECH_HAS_GEANT4
#include "trech/sim/GeantRunner.hpp"
#endif

#include <iostream>
#include <string>

int main(int argc, char** argv) {
  const trech::RunOptions options = trech::parseRunOptions(argc, argv);
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
    trech::applyRunOverrides(cfg, options);

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
