#include "trech/sim/MaterialProbe.hpp"

#include "G4Element.hh"
#include "G4EmCalculator.hh"
#include "G4IonisParamMat.hh"
#include "G4LossTableManager.hh"
#include "G4Material.hh"
#include "G4NistManager.hh"
#include "G4ParticleTable.hh"
#include "G4SystemOfUnits.hh"
#include "G4VEmProcess.hh"
#include "G4VEnergyLossProcess.hh"

#include <nlohmann/json.hpp>

#include <algorithm>
#include <cmath>
#include <stdexcept>

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

MaterialProbeResult probeOne(const std::string& name, const MaterialProbeConfig& options) {
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
  if (!options.interactionEnergiesMeV.empty()) {
    G4EmCalculator calculator;
    auto* particle = G4ParticleTable::GetParticleTable()->FindParticle(options.interactionParticle);
    for (double energy : options.interactionEnergiesMeV) {
      MaterialInteractionProbe sample;
      sample.energyMeV = energy;
      sample.particle = options.interactionParticle;
      sample.processes = options.interactionProcesses;
      if (!particle || !std::isfinite(energy) || energy <= 0 || sample.processes.empty()) {
        sample.note = "invalid particle/process/energy request";
      } else {
        try {
          for (const auto& process : sample.processes) {
            bool known = false;
            auto* manager = G4LossTableManager::Instance();
            for (auto* candidate : manager->GetEmProcessVector()) {
              if (candidate && candidate->GetProcessName() == process && candidate->IsApplicable(*particle))
                known = true;
            }
            for (auto* candidate : manager->GetEnergyLossProcessVector()) {
              if (candidate && candidate->GetProcessName() == process && candidate->IsApplicable(*particle))
                known = true;
            }
            if (!known) throw std::runtime_error("unavailable electromagnetic process: " + process);
            const double value = calculator.ComputeCrossSectionPerVolume(
                energy * MeV, particle, process, material) * mm;
            if (!std::isfinite(value) || value < 0)
              throw std::runtime_error("invalid Geant4 cross section");
            sample.crossSectionsPerMm.push_back(value);
          }
          sample.available = true;
        } catch (const std::exception& error) {
          sample.crossSectionsPerMm.clear();
          sample.note = error.what();
        }
      }
      result.interactions.push_back(std::move(sample));
    }
  }
  result.available = true;
  return result;
}

} // namespace

std::vector<MaterialProbeResult> computeMaterialProbes(
    const std::vector<std::string>& names, const MaterialProbeConfig& options) {
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
    results.push_back(probeOne(name, options));
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
    if (!p.interactions.empty()) {
      auto samples = nlohmann::json::array();
      for (const auto& sample : p.interactions) {
        nlohmann::json row = {{"energy_mev", sample.energyMeV}, {"particle", sample.particle},
                             {"available", sample.available},
                             {"source", "Geant4 G4EmCalculator; tabulated particle interaction response, not a Monte-Carlo tally"}};
        if (sample.available) {
          auto crossSections = nlohmann::json::object();
          for (std::size_t i = 0; i < sample.processes.size(); ++i)
            crossSections[sample.processes[i]] = sample.crossSectionsPerMm[i];
          row["cross_sections_per_mm"] = crossSections;
        } else {
          row["note"] = sample.note;
        }
        samples.push_back(row);
      }
      entry["interactions"] = samples;
    }
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
