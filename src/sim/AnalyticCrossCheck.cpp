#include "trech/sim/AnalyticCrossCheck.hpp"

#include "trech/core/Config.hpp"

#include "G4EmCalculator.hh"
#include "G4Gamma.hh"
#include "G4Material.hh"
#include "G4NistManager.hh"
#include "G4ParticleDefinition.hh"
#include "G4ParticleTable.hh"
#include "G4SystemOfUnits.hh"

#include <algorithm>
#include <cmath>
#include <sstream>

namespace trech {
namespace sim {
namespace {

// Resolves a material by name, mirroring the optics extractor: try the NIST
// builder first, then fall back to a scan of the live material table (so custom
// mixtures declared in the scenario resolve too).
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

// The active beam's energy: prefer the explicitly-active entry in `beams`, else
// the first entry, else the single `beam`. Used as the default probe energy.
double activeBeamEnergyMeV(const TrechConfig& cfg) {
  for (const auto& beam : cfg.beams) {
    if (beam.active) {
      return beam.energyMeV;
    }
  }
  if (!cfg.beams.empty()) {
    return cfg.beams.front().energyMeV;
  }
  return cfg.beam.energyMeV;
}

const G4ParticleDefinition* resolveParticle(const std::string& name) {
  if (name.empty() || name == "gamma") {
    return G4Gamma::Definition();
  }
  if (auto* table = G4ParticleTable::GetParticleTable()) {
    if (auto* def = table->FindParticle(name)) {
      return def;
    }
  }
  return G4Gamma::Definition();
}

// One Beer-Lambert check: sum the photon linear attenuation coefficient from
// Geant4's own cross sections and predict the uncollided transmission.
AnalyticCheckResult evaluateBeerLambert(const AnalyticCheckConfig& check,
                                        const TrechConfig& cfg,
                                        G4EmCalculator& calc) {
  AnalyticCheckResult result;
  result.type = "beer_lambert";
  result.label = check.label.empty() ? "beer_lambert" : check.label;
  result.particle = check.particle.empty() ? "gamma" : check.particle;
  result.toleranceRel = check.toleranceRel;
  result.formula = "T = exp(-mu*x), mu = phot + compt + Rayl + conv (G4EmCalculator)";
  result.measuredField = "primaries_uncollided_fraction";

  // Resolve probe energy: config override, else the active beam energy.
  result.energyMeV = check.energyMeV > 0.0 ? check.energyMeV : activeBeamEnergyMeV(cfg);

  // Resolve attenuator material: config override, else the medium material, else
  // the world material.
  std::string materialName = check.material;
  if (materialName.empty()) {
    materialName = cfg.detector.mediumBoxMm > 0.0 ? cfg.detector.mediumMaterial
                                                  : cfg.detector.worldMaterial;
  }
  result.material = materialName;

  // Resolve path length: config override, else the medium box side length, else
  // the world side length.
  result.pathLengthMm = check.pathLengthMm;
  if (result.pathLengthMm <= 0.0) {
    result.pathLengthMm =
        cfg.detector.mediumBoxMm > 0.0 ? cfg.detector.mediumBoxMm : cfg.detector.worldSizeMm;
  }

  G4Material* material = findMaterial(materialName);
  if (!material) {
    result.note = "material '" + materialName + "' could not be resolved";
    return result;
  }
  if (result.energyMeV <= 0.0 || result.pathLengthMm <= 0.0) {
    result.note = "non-positive energy or path length";
    return result;
  }

  const double energyG4 = result.energyMeV * MeV;
  const G4ParticleDefinition* particle = resolveParticle(result.particle);
  const auto safeQuery = [&](const G4String& processName) -> double {
    try {
      // Geant4 returns CLHEP "1/length"; convert to 1/mm.
      const double value =
          calc.ComputeCrossSectionPerVolume(energyG4, particle, processName, material);
      return std::max(0.0, value * mm);
    } catch (...) {
      return 0.0;
    }
  };

  result.muPhotoElectricPerMm = safeQuery("phot");
  result.muComptonPerMm = safeQuery("compt");
  result.muRayleighPerMm = safeQuery("Rayl");
  result.muPairPerMm = safeQuery("conv");
  result.muTotalPerMm = result.muPhotoElectricPerMm + result.muComptonPerMm +
                        result.muRayleighPerMm + result.muPairPerMm;
  if (result.muTotalPerMm > 0.0) {
    result.meanFreePathMm = 1.0 / result.muTotalPerMm;
  }
  result.predictedValue = std::exp(-result.muTotalPerMm * result.pathLengthMm);
  result.available = true;

  std::ostringstream note;
  note << "Beer-Lambert uncollided transmission of a " << result.particle << " beam at "
       << result.energyMeV << " MeV through " << result.pathLengthMm << " mm of "
       << materialName << "; mu derived from Geant4 atomic cross sections, compared to the "
       << "Monte-Carlo uncollided primary fraction.";
  result.note = note.str();
  return result;
}

} // namespace

std::vector<AnalyticCheckResult> computeAnalyticChecks(const AnalyticConfig& analytic,
                                                       const TrechConfig& cfg) {
  std::vector<AnalyticCheckResult> results;
  if (!analytic.enable || analytic.checks.empty()) {
    return results;
  }
  G4EmCalculator calc;
  results.reserve(analytic.checks.size());
  for (const auto& check : analytic.checks) {
    if (check.type == "beer_lambert" || check.type.empty()) {
      results.push_back(evaluateBeerLambert(check, cfg, calc));
    } else {
      AnalyticCheckResult unknown;
      unknown.type = check.type;
      unknown.label = check.label.empty() ? check.type : check.label;
      unknown.note = "unknown analytic check type '" + check.type + "'";
      results.push_back(unknown);
    }
  }
  return results;
}

} // namespace sim
} // namespace trech
