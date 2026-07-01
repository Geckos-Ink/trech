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

// Fills the photon linear-attenuation breakdown (1/mm) on `result` from Geant4's
// own atomic cross sections and returns the total. Shared by the Beer-Lambert
// (transmission) and photo-fraction (process branching) checks, which both read
// the SAME per-process mu components -- one predicts exp(-mu*x), the other their
// ratio -- so they must stay in lock-step.
double fillAttenuationBreakdown(AnalyticCheckResult& result, double energyG4,
                                const G4ParticleDefinition* particle,
                                G4Material* material, G4EmCalculator& calc) {
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
  return result.muTotalPerMm;
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
  fillAttenuationBreakdown(result, energyG4, particle, material, calc);
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

// One CSDA-range check: ask Geant4 for the continuous-slowing-down range of a
// charged particle (the path-length integral of dE/(dE/dx) from the start
// energy to rest) and compare it to the run's measured mean primary track
// length. This is the charged-particle companion to Beer-Lambert -- both are
// closed-form predictions evaluated from Geant4's OWN particle-level data, with
// no externally-tuned constant.
AnalyticCheckResult evaluateCsdaRange(const AnalyticCheckConfig& check,
                                      const TrechConfig& cfg,
                                      G4EmCalculator& calc) {
  AnalyticCheckResult result;
  result.type = "csda_range";
  result.label = check.label.empty() ? "csda_range" : check.label;
  result.particle = check.particle.empty() ? "proton" : check.particle;
  result.toleranceRel = check.toleranceRel;
  result.formula = "R_CSDA = integral_0^E dE'/(dE'/dx) (G4EmCalculator stopping power)";
  result.measuredField = "primary_mean_track_length_mm";

  result.energyMeV = check.energyMeV > 0.0 ? check.energyMeV : activeBeamEnergyMeV(cfg);

  std::string materialName = check.material;
  if (materialName.empty()) {
    materialName = cfg.detector.mediumBoxMm > 0.0 ? cfg.detector.mediumMaterial
                                                  : cfg.detector.worldMaterial;
  }
  result.material = materialName;

  G4Material* material = findMaterial(materialName);
  if (!material) {
    result.note = "material '" + materialName + "' could not be resolved";
    return result;
  }
  const G4ParticleDefinition* particle = resolveParticle(result.particle);
  if (!particle || particle == G4Gamma::Definition()) {
    result.note = "csda_range requires a charged particle (e.g. proton, e-, alpha)";
    return result;
  }
  if (result.energyMeV <= 0.0) {
    result.note = "non-positive energy";
    return result;
  }

  const double energyG4 = result.energyMeV * MeV;
  try {
    // GetCSDARange returns CLHEP length (the path-length range integral).
    result.csdaRangeMm = std::max(0.0, calc.GetCSDARange(energyG4, particle, material) / mm);
  } catch (...) {
    result.note = "G4EmCalculator could not provide the CSDA range for this particle/material";
    return result;
  }
  // Initial stopping power is informational only; best-effort so it cannot fail
  // the check.
  try {
    result.stoppingPowerMeVPerMm =
        std::max(0.0, calc.ComputeTotalDEDX(energyG4, particle, material) / (MeV / mm));
  } catch (...) {
    result.stoppingPowerMeVPerMm = 0.0;
  }
  if (result.csdaRangeMm <= 0.0) {
    result.note = "Geant4 returned a non-positive CSDA range (no range table for this particle?)";
    return result;
  }
  result.predictedValue = result.csdaRangeMm;
  result.pathLengthMm = result.csdaRangeMm;  // informational: expected stop depth
  result.available = true;

  std::ostringstream note;
  note << "CSDA range of a " << result.particle << " at " << result.energyMeV
       << " MeV in " << materialName << " from Geant4's stopping power, compared to the "
       << "measured mean primary track length (valid only when primaries stop inside the geometry).";
  result.note = note.str();
  return result;
}

// One photo-fraction check: the probability that a gamma's first discrete
// interaction is photoelectric, f = sigma_phot / (phot + compt + Rayl + conv).
// Both sides come from Geant4: the prediction from the SAME per-process cross
// sections Beer-Lambert sums, and the measurement from the fraction of primaries
// whose first discrete interaction is a photoelectric absorption (tallied in
// SteppingAction). This tests the process BRANCHING RATIO -- a different facet of
// the physics than the total attenuation the other checks probe -- and, unlike
// Beer-Lambert, it is independent of slab thickness: given a primary interacts,
// the odds its first interaction is photoelectric are mu_phot/mu_total whatever
// the depth, so even a thin slab yields an unbiased estimate.
AnalyticCheckResult evaluatePhotoFraction(const AnalyticCheckConfig& check,
                                          const TrechConfig& cfg,
                                          G4EmCalculator& calc) {
  AnalyticCheckResult result;
  result.type = "photo_fraction";
  result.label = check.label.empty() ? "photo_fraction" : check.label;
  result.particle = check.particle.empty() ? "gamma" : check.particle;
  result.toleranceRel = check.toleranceRel;
  result.formula =
      "f_photo = phot / (phot + compt + Rayl + conv) (G4EmCalculator cross sections)";
  result.measuredField = "primaries_photoelectric_first_fraction";

  result.energyMeV = check.energyMeV > 0.0 ? check.energyMeV : activeBeamEnergyMeV(cfg);

  std::string materialName = check.material;
  if (materialName.empty()) {
    materialName = cfg.detector.mediumBoxMm > 0.0 ? cfg.detector.mediumMaterial
                                                  : cfg.detector.worldMaterial;
  }
  result.material = materialName;
  // Path length is informational for this check (the branching ratio does not
  // depend on it); default it to the medium box like the other checks so the
  // emitted entry still records the geometry the run used.
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
  if (result.energyMeV <= 0.0) {
    result.note = "non-positive energy";
    return result;
  }

  const double energyG4 = result.energyMeV * MeV;
  const G4ParticleDefinition* particle = resolveParticle(result.particle);
  const double muTotal = fillAttenuationBreakdown(result, energyG4, particle, material, calc);
  if (muTotal <= 0.0) {
    result.note = "Geant4 returned zero total attenuation (no interaction cross section?)";
    return result;
  }
  result.predictedValue = result.muPhotoElectricPerMm / muTotal;
  result.available = true;

  std::ostringstream note;
  note << "Photoelectric fraction of a " << result.particle << " at " << result.energyMeV
       << " MeV in " << materialName << ": sigma_phot / sigma_total from Geant4 cross "
       << "sections, compared to the measured fraction of primaries whose first discrete "
       << "interaction is photoelectric.";
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
    } else if (check.type == "csda_range") {
      results.push_back(evaluateCsdaRange(check, cfg, calc));
    } else if (check.type == "photo_fraction") {
      results.push_back(evaluatePhotoFraction(check, cfg, calc));
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
