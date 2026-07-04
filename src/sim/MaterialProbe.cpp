#include "trech/sim/MaterialProbe.hpp"

#include "G4Element.hh"
#include "G4IonisParamMat.hh"
#include "G4Material.hh"
#include "G4NistManager.hh"
#include "G4SystemOfUnits.hh"

#include <nlohmann/json.hpp>

#include <algorithm>

namespace trech {
namespace sim {
namespace {

// Resolve a material by name: NIST builder first, then a scan of the live
// material table so scenario-declared custom mixtures resolve too. Same strategy
// as AnalyticCrossCheck.cpp / MolecularOptics.cpp.
G4Material* findMaterial(const std::string& name) {
  if (name.empty()) {
    return nullptr;
  }
  auto* nist = G4NistManager::Instance();
  if (auto* material = nist->FindOrBuildMaterial(name)) {
    return material;
  }
  for (auto* m : *G4Material::GetMaterialTable()) {
    if (m && m->GetName() == name) {
      return m;
    }
  }
  return nullptr;
}

MaterialProbeResult probeOne(const std::string& name) {
  MaterialProbeResult result;
  result.name = name;
  G4Material* material = findMaterial(name);
  if (!material) {
    result.note = "material '" + name + "' could not be resolved";
    return result;
  }

  // Unit conversions mirror MolecularOptics.cpp: densities come back in Geant4
  // internal units, so divide by the CLHEP unit to land in physical units.
  result.densityGcm3 = material->GetDensity() / (g / cm3);
  result.electronDensityPerCm3 = material->GetElectronDensity() / (1.0 / cm3);
  result.totalAtomsPerCm3 = material->GetTotNbOfAtomsPerVolume() / (1.0 / cm3);
  result.radiationLengthMm = material->GetRadlen() / mm;
  if (material->GetIonisation()) {
    result.meanExcitationEnergyEv =
        material->GetIonisation()->GetMeanExcitationEnergy() / eV;
  }

  const auto* elements = material->GetElementVector();
  const auto* fractions = material->GetFractionVector();
  const G4double* atomsPerVol = material->GetVecNbOfAtomsPerVolume();
  const std::size_t nElements = material->GetNumberOfElements();
  result.elements.reserve(nElements);
  for (std::size_t i = 0; i < nElements; ++i) {
    const G4Element* elem = elements ? (*elements)[i] : nullptr;
    if (!elem) {
      continue;
    }
    MaterialElementProbe e;
    e.symbol = elem->GetSymbol();
    e.z = elem->GetZasInt();
    e.atomsPerCm3 = atomsPerVol ? atomsPerVol[i] / (1.0 / cm3) : 0.0;
    e.massFraction = fractions ? fractions[i] : 0.0;
    // G4Element::GetA() returns the molar mass in Geant4 internal units (g/mole).
    e.atomicMassAmu = elem->GetA() / (g / mole);
    result.elements.push_back(std::move(e));
  }
  result.available = true;
  return result;
}

} // namespace

std::vector<MaterialProbeResult> computeMaterialProbes(
    const std::vector<std::string>& names) {
  std::vector<MaterialProbeResult> results;
  results.reserve(names.size());
  for (const auto& name : names) {
    if (name.empty()) {
      continue;
    }
    // De-duplicate: a material can be both the medium and a geometry volume.
    const bool seen = std::any_of(results.begin(), results.end(),
                                  [&](const MaterialProbeResult& r) {
                                    return r.name == name;
                                  });
    if (seen) {
      continue;
    }
    results.push_back(probeOne(name));
  }
  return results;
}

nlohmann::json materialProbesToJson(const std::vector<MaterialProbeResult>& probes) {
  auto arr = nlohmann::json::array();
  for (const auto& p : probes) {
    nlohmann::json entry;
    entry["name"] = p.name;
    entry["available"] = p.available;
    if (!p.note.empty()) {
      entry["note"] = p.note;
    }
    if (!p.available) {
      arr.push_back(entry);
      continue;
    }
    entry["density_g_per_cm3"] = p.densityGcm3;
    entry["electron_density_per_cm3"] = p.electronDensityPerCm3;
    entry["mean_excitation_energy_ev"] = p.meanExcitationEnergyEv;
    entry["radiation_length_mm"] = p.radiationLengthMm;
    entry["total_atoms_per_cm3"] = p.totalAtomsPerCm3;
    // Symbol-keyed number-density map so hooks can read e.g.
    // ctx.materials[name].numberDensityPerCm3.H without scanning the array.
    nlohmann::json numberDensity = nlohmann::json::object();
    auto elements = nlohmann::json::array();
    for (const auto& e : p.elements) {
      numberDensity[e.symbol] = e.atomsPerCm3;
      nlohmann::json ej;
      ej["symbol"] = e.symbol;
      ej["z"] = e.z;
      ej["atoms_per_cm3"] = e.atomsPerCm3;
      ej["mass_fraction"] = e.massFraction;
      ej["atomic_mass_amu"] = e.atomicMassAmu;
      elements.push_back(ej);
    }
    entry["numberDensityPerCm3"] = numberDensity;
    entry["elements"] = elements;
    arr.push_back(entry);
  }
  return arr;
}

} // namespace sim
} // namespace trech
