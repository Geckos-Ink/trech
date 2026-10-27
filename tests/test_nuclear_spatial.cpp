#include "trech/sim/NuclearSpatialProbe.hpp"
#include "trech/core/Config.hpp"
#include "Randomize.hh"
#include <nlohmann/json.hpp>
#include <sstream>
#include <cmath>
#include <iostream>
#include <stdexcept>
void require(bool value, const char* message) { if (!value) throw std::runtime_error(message); }
int main() {
  try {
    std::ostringstream before, after;
    G4Random::saveFullState(before);
    auto* engine = G4Random::getTheEngine();
    const auto oxygen = trech::sim::sampleNuclearInitialStates(8, 16, 4, 1234);
    G4Random::saveFullState(after);
    require(engine == G4Random::getTheEngine() && before.str() == after.str(), "diagnostic sampling changed transport RNG");
    require(oxygen == trech::sim::sampleNuclearInitialStates(8, 16, 4, 1234), "nuclear samples must replay exactly");
    require(oxygen != trech::sim::sampleNuclearInitialStates(8, 16, 4, 1235), "nuclear seed must change samples");
    require(oxygen["available"] && oxygen["length_unit"] == "fm" && oxygen["time_kind"] == "ensemble_index", "nuclear source/clock/unit missing");
    for (const auto& sample : oxygen["configurations"]) {
      require(sample["protons"].size() == 8 && sample["neutrons"].size() == 8, "isotope nucleon inventory changed");
      for (const auto* species : {"protons", "neutrons"}) for (const auto& point : sample[species])
        require(point.size() == 3 && std::isfinite(point[0].get<double>()), "invalid Geant4 nuclear coordinate");
    }
    require(!trech::sim::sampleNuclearInitialStates(1, 1, 4, 1)["available"].get<bool>(), "single-proton distribution must not be invented");
    const auto config = trech::configFromJsonString(R"({"materialProbe":{"enable":true,"nuclearSamples":{"configurations":4,"seed":1234}}})");
    require(config.materialProbe.includeIsotopes, "nuclear sampling needs isotope inventory");
    const auto bytes = trech::configToJsonString(config);
    require(bytes == trech::configToJsonString(trech::configFromJsonString(bytes)), "nuclear config must round trip");
    for (auto number : {0, 33}) {
      bool rejected = false;
      try { trech::configFromJsonString(nlohmann::json{{"materialProbe", {{"nuclearSamples", {{"configurations", number}}}}}}.dump()); }
      catch (...) { rejected = true; }
      require(rejected, "unbounded/empty nuclear sampling accepted");
    }
    std::cout << "nuclear ensemble determinism, RNG isolation and isotope counts pass\n";
  } catch (const std::exception& error) { std::cerr << error.what() << '\n'; return 1; }
}
