#pragma once

#include <nlohmann/json_fwd.hpp>

#include <string>
#include <vector>

namespace trech {
namespace sim {

// One element's contribution to a probed material, straight from the constructed
// G4Material. `atomsPerCm3` is this element's number density -- for hydrogen it is
// the proton (1H) number density an NMR/MRI signal is proportional to.
struct MaterialElementProbe {
  std::string symbol;         // e.g. "H", "O", "C"
  int z = 0;                  // atomic number
  double atomsPerCm3 = 0.0;   // number density of this element
  double massFraction = 0.0;  // by-mass fraction in the material
  double atomicMassAmu = 0.0; // element molar mass (g/mol == amu)
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
  std::string note;
};

// Query the material table (post-Initialize; the physics tables/material table
// must exist) for each requested material name. Names that cannot be resolved
// come back with available = false rather than throwing, mirroring the analytic
// cross-check's graceful degradation. Duplicate names are de-duplicated.
std::vector<MaterialProbeResult> computeMaterialProbes(
    const std::vector<std::string>& names);

// Serialize probes to the shared JSON shape used by both trech_scores.jsonl
// (`material_probes`) and the hook context (`ctx.materials`). The top level is an
// array of per-material objects; each carries a `numberDensityPerCm3` map keyed by
// element symbol (so a hook can read `ctx.materials[i].numberDensityPerCm3.H`).
nlohmann::json materialProbesToJson(const std::vector<MaterialProbeResult>& probes);

} // namespace sim
} // namespace trech
