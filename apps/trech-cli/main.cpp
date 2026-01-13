#include "trech/core/Config.hpp"
#include "trech/js/JsRuntime.hpp"

#ifdef TRECH_HAS_GEANT4
#include "trech/sim/GeantRunner.hpp"
#endif

#include <iostream>
#include <string>

int main(int argc, char** argv) {
  if (argc < 3 || std::string(argv[1]) != "run") {
    std::cerr << "Usage: trech run <experiment.js>\n";
    return 2;
  }

  try {
    trech::JsRuntime js;
    const std::string cfgJson = js.evalExperimentAndGetConfigJson(argv[2]);
    trech::TrechConfig cfg = trech::configFromJsonString(cfgJson);

#ifdef TRECH_HAS_GEANT4
    return trech::runGeant4(cfg, argc, argv);
#else
    std::cout << "Config parsed OK (Geant4 disabled)\n";
    return 0;
#endif
  } catch (const std::exception& ex) {
    std::cerr << "TRECH error: " << ex.what() << "\n";
    return 1;
  }
}
