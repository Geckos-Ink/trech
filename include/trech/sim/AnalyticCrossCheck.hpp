#pragma once

#include <string>
#include <vector>

namespace trech {

struct TrechConfig;
struct AnalyticConfig;

namespace sim {

// One (gamma, n) channel A(gamma, n)(A-1) of an isotope of the check material,
// from Geant4's nuclear mass table.
struct PhotoneutronChannel {
  std::string target;          // e.g. "O16"
  double abundance = 0.0;      // isotope fraction within its element
  double thresholdMeV = 0.0;   // ((m_n + M_{A-1})^2 - M_A^2) / 2 M_A
  bool open = false;           // probe energy above threshold
  double neutronEdgeMeV = 0.0; // two-body T_n,max at the probe energy (0 if closed)
};

// Result of one analytic cross-check: the classical-formula prediction plus the
// physics inputs Geant4 supplied to evaluate it. The Monte-Carlo measured value
// (and the gap) are attached later, at run end, where the run tallies live (see
// TrechRunAction::EndOfRunAction) — this struct carries only the half that can
// be computed up front, from Geant4's particle-level data, before BeamOn.
struct AnalyticCheckResult {
  std::string type;            // "beer_lambert" | "csda_range" | "photo_fraction" |
                               // "compton_energy_transfer" | "pair_fraction" |
                               // "photonuclear_fraction"
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
  // "photo_fraction" (predicts muPhotoElectric/muTotal), "pair_fraction"
  // (predicts muPair/muTotal) and "photonuclear_fraction" (predicts
  // muPhotonuclear/muTotal). Zero for other check types. muPhotonuclearPerMm is
  // the gamma inelastic (photonuclear) cross section of the registered hadronic
  // process (G4HadronicProcessStore) -- the dataset QBBC's G4GammaGeneralProcess
  // samples -- and is exactly zero below every nuclide's photonuclear threshold,
  // so it leaves low-energy totals unchanged.
  double muPhotoElectricPerMm = 0.0;
  double muComptonPerMm = 0.0;
  double muRayleighPerMm = 0.0;
  double muPairPerMm = 0.0;
  double muPhotonuclearPerMm = 0.0;
  double muTotalPerMm = 0.0;
  double meanFreePathMm = 0.0;

  // CSDA-range breakdown. Zero for other check types. The predicted range
  // (== predictedValue) is the path-length integral of a charged particle
  // slowing down from energyMeV to rest in `material`, from Geant4's own
  // stopping power; stoppingPowerMeVPerMm is the initial dE/dx.
  double csdaRangeMm = 0.0;
  double stoppingPowerMeVPerMm = 0.0;

  // Klein-Nishina breakdown for "compton_energy_transfer". Zero for other check
  // types. kleinNishinaMeanTransferFraction (== predictedValue) is the free-
  // electron sigma_tr/sigma; comptonEdgeFraction is T_max/E = 2eps/(1+2eps).
  double kleinNishinaMeanTransferFraction = 0.0;
  double comptonEdgeFraction = 0.0;
  // Binned Klein-Nishina spectrum shape: probability of u = T/T_max falling in
  // each of klein_nishina::kTransferHistogramBins equal-width bins. Empty for
  // other check types. Compared to the run's first-Compton transfer histogram.
  std::vector<double> kleinNishinaTransferBinProbabilities;
  // Angular distribution: KN <cos theta> of the scattered photon and the
  // probability per klein_nishina::kCosThetaHistogramBins equal-width cos(theta)
  // bin over [-1, 1]. Compared to the first-Compton direction histogram.
  double kleinNishinaMeanCosTheta = 0.0;
  std::vector<double> kleinNishinaCosThetaBinProbabilities;

  // Pair-production threshold 2 m_e c^2 (MeV, from CLHEP) for "pair_fraction";
  // below it the predicted (and required measured) branching is exactly zero.
  double pairThresholdMeV = 0.0;
  bool belowPairThreshold = false;

  // Photonuclear final-state references for "photonuclear_fraction", from
  // Geant4's nuclear mass table (G4NucleiProperties) over the material's
  // isotopes: the lowest (gamma, n) threshold, whether the probe is below it
  // (then no photoneutron may appear), and the largest two-body neutron edge
  // T_n,max at the probe energy (0 when every (gamma, n) channel is closed).
  double photoneutronThresholdMeV = 0.0;
  bool belowPhotoneutronThreshold = false;
  double neutronEdgeMeV = 0.0;
  std::vector<PhotoneutronChannel> photoneutronChannels;
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
