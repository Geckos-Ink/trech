#pragma once

#include "trech/core/Config.hpp"
#include "trech/core/Provenance.hpp"
#include "trech/core/RunOptions.hpp"
#include "trech/ml/EventFeatures.hpp"
#include "G4UserRunAction.hh"
#include "G4Accumulable.hh"

#include <memory>
#include <mutex>
#include <string>
#include <unordered_map>
#include <vector>

class G4Run;

namespace trech {
namespace ml {
struct StratifyResult;
class OnlineEventStats;
} // namespace ml

// Final state of one primary photon's FIRST photonuclear absorption, read from
// the step's secondaries (counterpart of the photonuclear final-state checks).
// The target nucleus is inferred from baryon number / charge conservation of
// the products and matched against the isotopes of the step's material.
struct PhotonuclearFinalState {
  G4int neutrons = 0;
  G4int protons = 0;
  G4int alphas = 0;
  G4int gammas = 0;
  G4int others = 0;              // heavier ions, other light fragments, leptons
  bool targetMatched = false;    // inferred (A, Z) is an isotope of the material
  G4double energyClosure = 0.0;  // signed (E + M - sum E_out - edep) / E
  G4double momentumClosure = 0.0;// |p_gamma - sum p_out| / E
  G4double neutronKineticMax = 0.0;      // MeV; 0 when no neutron emitted
  G4int edgeTested = 0;                  // baryonic ejectiles graded on the edge
  G4double edgeExcessMax = -1.0;         // max (T - T_max,2body) / E over them
};

// Per-dispatch evidence. Causes may overlap for a prediction; event routing
// counts the event once while retaining each cause independently.
struct HookInferenceCounts {
  std::size_t outOfDomain = 0;
  std::size_t starved = 0;
  std::size_t scaleMismatched = 0;
};

class TrechRunAction : public G4UserRunAction {
public:
  TrechRunAction(const TrechConfig& cfg, const RunOptions& options);

  void BeginOfRunAction(const G4Run* run) override;
  void EndOfRunAction(const G4Run* run) override;
  void AddEnergyDeposit(G4double edep);
  void AddVolumeEnergyDeposit(const std::string& volumeName, G4double edep);
  void AddOpticalPhotonStep(G4double stepLength);
  void AddOpticalPhotonTrack();
  void AddPrimaryEmitted();
  void AddPrimaryTransmitted();
  void AddPrimaryAbsorbed();
  // A primary that exits the world having undergone no discrete interaction
  // (the uncollided beam). This is the Monte-Carlo statistical counterpart of
  // the Beer-Lambert exp(-mu*x) analytic prediction.
  void AddPrimaryUncollided();
  // Accumulate one step's length onto the running primary-track path length.
  // Summed over all primary (parentID==0) steps, divided by the primary count,
  // this gives the mean primary path length -- the Monte-Carlo counterpart of
  // the analytic CSDA range (a fully-stopping charged particle's track length).
  void AddPrimaryTrackLength(G4double stepLength);
  // Record a primary's FIRST discrete interaction, classified by EM process
  // subtype: increments the count of primaries that interacted at all, the
  // photoelectric subset (Monte-Carlo counterpart of the analytic photo-fraction
  // check, sigma_phot / sigma_total) and, for a Compton scatter, the fraction of
  // the photon energy handed to the electron (counterpart of the Klein-Nishina
  // compton_energy_transfer check) plus its u = T/T_max histogram bin
  // (counterpart of the binned Klein-Nishina spectrum shape; -1 = unbinned).
  // A gamma conversion feeds the pair_fraction check (sigma_conv / sigma_total);
  // photonuclear absorption (fHadronInelastic, selected inside QBBC's
  // G4GammaGeneralProcess) feeds photonuclear_fraction (sigma_pn / sigma_total).
  // For a Compton scatter, cosTheta is the photon's scattering cosine from its
  // pre/post momentum DIRECTION (counterpart of the Klein-Nishina angular
  // distribution) and kinematicResidual is |E'/E - 1/(1+eps(1-cos theta))|, the
  // free-electron energy-angle closure. All Compton arguments are ignored for
  // other subtypes; a non-finite cosTheta leaves the angular tallies untouched.
  void AddPrimaryFirstInteraction(G4int emSubType, G4double transferFraction,
                                  G4int transferBin, G4double cosTheta,
                                  G4double kinematicResidual);
  // Record the final state of a primary's first photonuclear absorption (called
  // in addition to AddPrimaryFirstInteraction for fHadronInelastic).
  void AddPhotonuclearFinalState(const PhotonuclearFinalState& state);
  void RecordEventSummary(G4double eventEdep);
  void RecordEventFeatureVector(const ml::EventFeatures& features);
  void AddStratifyResult(const ml::StratifyResult& result);
  void RecordHookOnEventStart();
  bool RecordHookOnStep();
  void RecordHookOnEventEnd();
  // Return this dispatch's inference trust evidence for event resim policies.
  HookInferenceCounts DispatchHook(const std::string& hookName,
                   int eventId = -1,
                   int stepIndex = -1,
                   double stepEdepMeV = 0.0,
                   double stepLengthMm = 0.0,
                   double eventEdepMeV = 0.0,
                   double eventTotalTrackLengthMm = 0.0,
                   int eventTotalStepCount = 0,
                   int eventTotalTrackCount = 0,
                   int eventOpticalPhotonSteps = 0,
                   int eventOpticalPhotonTracks = 0,
                   double eventOpticalPhotonTrackLengthMm = 0.0);
  // Record an event qualifying for an enabled inference resim policy,
  // distinct from the stratifier's own exceptional tally.
  void AddLowConfidenceEvent();

private:
  void RecordHookOnInit();
  void RecordHookOnRunStart();
  void RecordHookOnRunEnd();

  struct VolumeScore {
    std::string name;
    std::unique_ptr<G4Accumulable<G4double>> edep;
  };

  struct FeatureScore {
    std::string name;
    std::unique_ptr<G4Accumulable<G4double>> sum;
    std::unique_ptr<G4Accumulable<G4double>> sumSq;
    std::unique_ptr<G4Accumulable<G4double>> min;
    std::unique_ptr<G4Accumulable<G4double>> max;
  };

  TrechConfig cfg_;
  RunOptions options_;
  ProvenanceWriter provenance_;
  std::string scoresPath_;
  std::string hookEmitsPath_;
  G4Accumulable<G4double> totalEdep_;
  std::vector<VolumeScore> volumeScores_;
  std::unordered_map<std::string, std::size_t> volumeScoreIndex_;
  G4Accumulable<G4int> opticalPhotonSteps_;
  G4Accumulable<G4int> opticalPhotonTracks_;
  G4Accumulable<G4double> opticalPhotonTrackLength_;
  G4Accumulable<G4int> primariesEmittedCount_;
  G4Accumulable<G4int> primariesTransmittedCount_;
  G4Accumulable<G4int> primariesAbsorbedCount_;
  G4Accumulable<G4int> primariesUncollidedCount_;
  G4Accumulable<G4double> primaryTrackLength_;
  G4Accumulable<G4int> primariesFirstInteractionCount_;
  G4Accumulable<G4int> primariesPhotoelectricFirstCount_;
  G4Accumulable<G4int> primariesComptonFirstCount_;
  G4Accumulable<G4double> comptonFirstTransferSum_;
  G4Accumulable<G4double> comptonFirstTransferSumSq_;
  G4Accumulable<G4double> comptonFirstTransferMax_;
  G4Accumulable<G4int> primariesPairFirstCount_;
  G4Accumulable<G4int> primariesPhotonuclearFirstCount_;
  // First-Compton transfer histogram, klein_nishina::kTransferHistogramBins
  // equal-width bins of u = T / T_max (heap-held: accumulables are not movable).
  std::vector<std::unique_ptr<G4Accumulable<G4int>>> comptonFirstTransferHistogram_;
  // First-Compton scattered-photon direction: cos(theta) moments, the maximum
  // free-electron energy-angle residual, and a klein_nishina::kCosThetaHistogramBins
  // equal-width cos(theta) histogram over [-1, 1].
  G4Accumulable<G4int> comptonFirstAngleCount_;
  G4Accumulable<G4double> comptonFirstCosSum_;
  G4Accumulable<G4double> comptonFirstCosSumSq_;
  G4Accumulable<G4double> comptonFirstKinematicResidualMax_;
  std::vector<std::unique_ptr<G4Accumulable<G4int>>> comptonFirstCosHistogram_;
  // First photonuclear absorptions: final-state counts, conservation residuals
  // (max |.| merges), the two-body ejectile-edge excess and a neutron
  // multiplicity histogram (photonuclear::kNeutronMultiplicityBins bins).
  G4Accumulable<G4int> photonuclearFinalStateCount_;
  G4Accumulable<G4int> photonuclearTargetUnmatchedCount_;
  G4Accumulable<G4int> photonuclearNeutronCount_;
  G4Accumulable<G4int> photonuclearProtonCount_;
  G4Accumulable<G4int> photonuclearAlphaCount_;
  G4Accumulable<G4int> photonuclearGammaCount_;
  G4Accumulable<G4int> photonuclearOtherCount_;
  G4Accumulable<G4double> photonuclearEnergyClosureSum_;
  G4Accumulable<G4double> photonuclearEnergyClosureAbsMax_;
  G4Accumulable<G4double> photonuclearMomentumClosureMax_;
  G4Accumulable<G4double> photonuclearNeutronKineticMax_;
  G4Accumulable<G4int> photonuclearEdgeTestedCount_;
  G4Accumulable<G4double> photonuclearEdgeExcessMax_;
  std::vector<std::unique_ptr<G4Accumulable<G4int>>> photonuclearNeutronMultiplicity_;
  std::unique_ptr<ml::OnlineEventStats> eventStats_;
  mutable std::mutex eventStatsMutex_;
  G4Accumulable<G4int> featureStatsCount_;
  std::vector<FeatureScore> featureScores_;
  G4Accumulable<G4int> stratifyTotalCount_;
  G4Accumulable<G4int> stratifyPredictableCount_;
  G4Accumulable<G4int> stratifyExceptionalCount_;
  // Events routed to resim by the coverage flag (low-confidence inference),
  // separate from the stratifier's feature-based exceptional count.
  G4Accumulable<G4int> stratifyLowConfidenceCount_;
  G4Accumulable<G4int> stratifyUnclassifiedCount_;
  G4Accumulable<G4int> stratifyThresholdCount_;
  G4Accumulable<G4int> stratifyModelCount_;
  G4Accumulable<G4int> stratifySourceUnknownCount_;
  G4Accumulable<G4int> eventSummaryCount_;
  G4Accumulable<G4double> eventEdepSumMeV_;
  G4Accumulable<G4double> eventEdepSqSumMeV2_;
  G4Accumulable<G4double> eventEdepCubeSumMeV3_;
  G4Accumulable<G4double> eventEdepQuartSumMeV4_;
  G4Accumulable<G4int> eventEdepZeroCount_;
  G4Accumulable<G4double> eventEdepMinMeV_;
  G4Accumulable<G4double> eventEdepMaxMeV_;
  bool hooksEnabled_ = false;
  bool hookOnInitEnabled_ = false;
  bool hookOnRunStartEnabled_ = false;
  bool hookOnEventStartEnabled_ = false;
  bool hookOnStepEnabled_ = false;
  bool hookOnEventEndEnabled_ = false;
  bool hookOnRunEndEnabled_ = false;
  int hookUnknownRegisteredCount_ = 0;
  int hookMaxStepCallbacks_ = 0;
  int hookMaxEmitsPerCallback_ = 0;
  int hookMaxEmitPayloadBytes_ = 0;
  // Geant4 material-composition probes serialized once (run-constant) and copied
  // into every hook context as ctx.materials. Empty when the probe is disabled.
  std::string hookMaterialsJson_;
  bool hookMaterialsJsonReady_ = false;
  // Geant4-derived optical results serialized once and exposed as ctx.optics.
  std::string hookOpticsJson_;
  bool hookOpticsJsonReady_ = false;
  int activeNEvents_ = 0;
  std::uint64_t activeSeed_ = 0;
  std::string activeConfigJson_;
  G4Accumulable<G4int> hookOnInitCount_;
  G4Accumulable<G4int> hookOnRunStartCount_;
  G4Accumulable<G4int> hookOnEventStartCount_;
  G4Accumulable<G4int> hookOnStepRawCount_;
  G4Accumulable<G4int> hookOnEventEndCount_;
  G4Accumulable<G4int> hookOnRunEndCount_;
  G4Accumulable<G4int> hookPatchCount_;
  G4Accumulable<G4int> hookEmitCount_;
  G4Accumulable<G4int> hookEmitDroppedCount_;
  G4Accumulable<G4int> hookPredictCount_;
  // Subset of hookPredictCount_ whose inputs fell outside the model's trained
  // domain (low-confidence extrapolations) -- the auditable "acting on the
  // coverage flag" run fact (workstream 3a).
  G4Accumulable<G4int> hookOutOfDomainCount_;
};

} // namespace trech
