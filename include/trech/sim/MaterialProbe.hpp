#pragma once

#include "trech/core/Config.hpp"

#include <nlohmann/json_fwd.hpp>

#include <string>
#include <vector>

namespace trech {
namespace sim {

// One element's contribution to a probed material, straight from the constructed
// G4Material. `atomsPerCm3` is this element's number density. Isotope-specific
// observables must use the isotope inventory, not equate all hydrogen with 1H.
struct MaterialIsotopeProbe {
  int z = 0;
  int a = 0;
  double abundance = 0;
  double atomicMassAmu = 0;
};

struct MaterialElementProbe {
  std::string symbol;         // e.g. "H", "O", "C"
  int z = 0;                  // atomic number
  double atomsPerCm3 = 0.0;   // number density of this element
  double massFraction = 0.0;  // by-mass fraction in the material
  double atomicMassAmu = 0.0; // element molar mass (g/mol == amu)
  std::vector<MaterialIsotopeProbe> isotopes; // only with includeIsotopes
  bool naturalIsotopicComposition = false;
  std::string nuclearSamplesJson; // optional diagnostic, only for explicitly chosen isotopes
};

struct MaterialInteractionProbe {
  double energyMeV = 0;
  std::string particle;
  bool available = false;
  std::vector<std::string> processes;
  std::vector<double> crossSectionsPerMm;
  std::string note;
};

// What Geant4 knows about one constructed material. This is descriptive (a probe
// of the material table), not a Monte-Carlo tally -- so it has no measured/predicted
// pairing like AnalyticCheckResult; it is simply reported so scenarios can read
// Geant4-derived composition instead of hard-coding it.
struct MaterialProbeResult {
  std::string name;
  bool available = false;               // false => material could not be resolved
  double densityGcm3 = 0.0;
  double electronDensityPerCm3 = 0.0;
  double meanExcitationEnergyEv = 0.0;  // G4IonisParamMat mean excitation energy I
  double radiationLengthMm = 0.0;
  double totalAtomsPerCm3 = 0.0;
  std::vector<MaterialElementProbe> elements;
  std::vector<MaterialInteractionProbe> interactions;
  std::string note;
};

// Query the material table (post-Initialize; the physics tables/material table
// must exist) for each requested material name. Names that cannot be resolved
// come back with available = false rather than throwing, mirroring the analytic
// cross-check's graceful degradation. Duplicate names are de-duplicated.
std::vector<MaterialProbeResult> computeMaterialProbes(
    const std::vector<std::string>& names, const MaterialProbeConfig& options = {});

// Serialize probes to the shared JSON shape used by both trech_scores.jsonl
// (`material_probes`) and the hook context (`ctx.materials`). The top level is an
// array of per-material objects; each carries a `numberDensityPerCm3` map keyed by
// element symbol (so a hook can read `ctx.materials[name].numberDensityPerCm3.H`).
nlohmann::json materialProbesToJson(const std::vector<MaterialProbeResult>& probes);

} // namespace sim
} // namespace trech
