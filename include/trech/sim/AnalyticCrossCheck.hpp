#pragma once

#include <string>
#include <vector>

namespace trech {

struct TrechConfig;
struct AnalyticConfig;

namespace sim {

// Result of one analytic cross-check: the classical-formula prediction plus the
// physics inputs Geant4 supplied to evaluate it. The Monte-Carlo measured value
// (and the gap) are attached later, at run end, where the run tallies live (see
// TrechRunAction::EndOfRunAction) — this struct carries only the half that can
// be computed up front, from Geant4's particle-level data, before BeamOn.
struct AnalyticCheckResult {
  std::string type;            // "beer_lambert" | "csda_range" | "photo_fraction"
  std::string label;           // human label
  std::string particle;        // probe particle
  std::string material;        // resolved attenuator material name
  double energyMeV = 0.0;      // probe energy actually used
  double pathLengthMm = 0.0;   // path actually used
  double toleranceRel = 0.0;   // relative tolerance for the within_tolerance flag
  bool available = false;      // false => inputs could not be resolved
  std::string note;            // diagnostics / formula provenance
  std::string formula;         // human-readable classical formula
  // Which run-end scalar metric this prediction is compared against. RunAction
  // looks the value up by this key so new check types stay data-driven.
  std::string measuredField;
  // The classical-formula expected value (the comparison target).
  double predictedValue = 0.0;

  // Linear attenuation breakdown (1/mm), filled for the photon checks that read
  // Geant4's per-process cross sections: "beer_lambert" (predicts exp(-mu*x))
  // and "photo_fraction" (predicts muPhotoElectric/muTotal). Zero for other
  // check types.
  double muPhotoElectricPerMm = 0.0;
  double muComptonPerMm = 0.0;
  double muRayleighPerMm = 0.0;
  double muPairPerMm = 0.0;
  double muTotalPerMm = 0.0;
  double meanFreePathMm = 0.0;

  // CSDA-range breakdown. Zero for other check types. The predicted range
  // (== predictedValue) is the path-length integral of a charged particle
  // slowing down from energyMeV to rest in `material`, from Geant4's own
  // stopping power; stoppingPowerMeVPerMm is the initial dE/dx.
  double csdaRangeMm = 0.0;
  double stoppingPowerMeVPerMm = 0.0;
};

// Evaluates every configured analytic check against Geant4's particle-level
// data. MUST be called after G4RunManager::Initialize() (it queries
// G4EmCalculator, which needs the physics tables built), like the optics
// extractor. Unresolvable checks come back with available = false rather than
// throwing, so a bad scenario degrades gracefully.
std::vector<AnalyticCheckResult> computeAnalyticChecks(const AnalyticConfig& analytic,
                                                       const TrechConfig& cfg);

} // namespace sim
} // namespace trech
