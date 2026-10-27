#include "trech/core/Config.hpp"
#include "trech/sim/DetectorConstruction.hpp"
#include "trech/sim/MaterialProbe.hpp"
#include <cmath>
#include <iostream>
#include <stdexcept>
#include <nlohmann/json.hpp>

void require(bool ok, const char* message) { if (!ok) throw std::runtime_error(message); }
int main() {
  try {
    auto cfg = trech::configFromJsonString(R"({"detector":{"worldMaterial":"HD","worldSizeMm":1},"materials":[{"name":"HD","densityGcm3":1,"components":[{"element":"H","atoms":1,"massNumber":1},{"element":"H","atoms":1,"massNumber":2}]}]})");
    trech::TrechDetectorConstruction detector(cfg.detector, cfg.optics, cfg.geometry, cfg.materials);
    require(detector.Construct() != nullptr, "isotope material construction failed");
    trech::MaterialProbeConfig options; options.includeIsotopes = true;
    const auto probes = trech::sim::computeMaterialProbes({"HD"}, options);
    require(probes.size() == 1 && probes[0].available, "isotope probe missing");
    const auto& p = probes[0];
    require(p.elements.size() == 2, "split isotope elements must be retained");
    require(std::abs(p.elements[0].atomsPerCm3 / p.elements[1].atomsPerCm3 - 1) < 1e-12,
            "stoichiometric atoms must have equal counts, not equal mass fractions");
    require(p.elements[1].atomicMassAmu > 2 && p.elements[1].atomicMassAmu < 2.02,
            "isotope mass must come from Geant4, not the integer mass number");
    const auto encoded = trech::sim::materialProbesToJson(probes)[0];
    require(encoded["elements"][1]["isotopes"][0]["neutrons"] == 1, "D neutron count incorrect");
    require(encoded["elements"][1]["natural_isotopic_composition"] == false, "explicit isotope must be identified");
    const auto natural = trech::sim::materialProbesToJson(trech::sim::computeMaterialProbes({"G4_H"}, options))[0];
    require(natural["elements"][0]["natural_isotopic_composition"] == true, "natural composition must be identified");
    require(std::abs(encoded["numberDensityPerCm3"]["H"].get<double>() / p.totalAtomsPerCm3 - 1) < 1e-12,
            "symbol density must sum all isotope components");
    const auto historical = trech::sim::materialProbesToJson(trech::sim::computeMaterialProbes({"HD"}))[0];
    require(!historical["elements"][0].contains("isotopes"), "isotope metadata must be opt-in");
    cfg.materials[0].name = "invalid_isotope"; cfg.materials[0].components[0].massNumber = 999;
    bool rejected = false;
    try {
      trech::TrechDetectorConstruction bad(cfg.detector, cfg.optics, cfg.geometry, cfg.materials);
      bad.Construct();
    } catch (const std::invalid_argument&) { rejected = true; }
    require(rejected, "unknown isotope must fail closed before Geant4 constructs it");
    std::cout << "Geant4 isotope/stoichiometry probe contracts pass\n";
  } catch (const std::exception& e) { std::cerr << e.what() << '\n'; return 1; }
}
