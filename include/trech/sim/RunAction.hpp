#pragma once

#include "trech/core/Config.hpp"
#include "trech/core/Provenance.hpp"
#include "trech/core/RunOptions.hpp"
#include "trech/js/JsRuntime.hpp"
#include "trech/ml/EventFeatures.hpp"
#include "trech/sim/SecondarySpecies.hpp"
#include "G4UserRunAction.hh"
#include "G4Accumulable.hh"

#include <array>
#include <memory>
#include <mutex>
#include <string>
#include <unordered_map>
#include <vector>

class G4Run;
class G4VPhysicalVolume;
class G4AccumulableManager;

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
  // stepSpecies: the sim::secondary_species class of the particle taking the
  // step (primaries included); the deposit's per-class split uses it.
  void AddVolumeEnergyDeposit(const std::string& volumeName, G4double edep, int stepSpecies);
  // One Geant4 step attributed to its pre-step volume (the same rule as the
  // per-volume deposit): adds the step length to that volume's event track
  // length and, when the step is a secondary track's first step (its creation
  // vertex), one secondary to that volume's event multiplicity. No-op for
  // volumes without `scoreEdep`.
  // stepSpecies: the class of the stepping particle (the track-length split);
  // createdSpecies: the sim::secondary_species class of the secondary whose
  // first step this is, or -1 when the step creates no secondary record.
  void AddVolumeStep(const std::string& volumeName, G4double stepLength, int stepSpecies,
                     int createdSpecies);
  bool HasVolumeScores() const { return !volumeScores_.empty(); }
  // Index of the scored volume a placed Geant4 volume belongs to (by name), or
  // -1 when it is not scored. Cached per physical volume on this thread so the
  // stepping path hashes a pointer, not the volume name; the cache is cleared
  // at every run start because a rebuilt geometry may reuse addresses.
  int VolumeScoreIndex(const G4VPhysicalVolume* volume);
  // Index-based forms of AddVolumeEnergyDeposit / AddVolumeStep (index from
  // VolumeScoreIndex; negative or out-of-range indices are ignored).
  void AddVolumeEnergyDeposit(int volumeIndex, G4double edep, int stepSpecies);
  void AddVolumeStep(int volumeIndex, G4double stepLength, int stepSpecies, int createdSpecies);
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
  // Per-event multiplicity/length shape: secondary tracks created in the
  // event (all stepped tracks minus the event's primaries) and the summed
  // step length of every track, in mm.
  void RecordEventMultiplicity(G4double secondaryCount, G4double trackLengthMm);
  // Same events' secondaries split into species classes (sums to the total
  // secondaries of tracks whose parent ID is non-zero). Call once per event,
  // after RecordEventMultiplicity, so both share eventMultiplicityCount_.
  void RecordEventSecondarySpecies(
      const std::array<int, sim::secondary_species::kCount>& counts);
  // Same events' whole deposit (MeV) and summed step length (mm) split by the
  // stepping particle's class (primaries included). Call once per event after
  // RecordEventMultiplicity, so both share eventMultiplicityCount_.
  void RecordEventClassSplit(const std::array<double, sim::secondary_species::kCount>& edepMeV,
                             const std::array<double, sim::secondary_species::kCount>& lengthMm);
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
  // onStep dispatch with Geant4 step detail (track identity, pre/post points,
  // global time, kinetic energies) for ctx.step. Same counters and trust
  // evidence as DispatchHook; the detail never enters the hook RNG seed.
  HookInferenceCounts DispatchStepHook(const HookRuntimeContext& stepDetail);
  // Record an event qualifying for an enabled inference resim policy,
  // distinct from the stratifier's own exceptional tally.
  void AddLowConfidenceEvent();

private:
  void RecordHookOnInit();
  void RecordHookOnRunStart();
  void RecordHookOnRunEnd();

  // Power sums of one per-event scalar (count shared with eventSummaryCount_).
  struct EventScalarAccumulables {
    EventScalarAccumulables();
    void Add(G4double value);
    void Register(G4AccumulableManager* manager);
    G4Accumulable<G4double> sum1;
    G4Accumulable<G4double> sum2;
    G4Accumulable<G4double> sum3;
    G4Accumulable<G4double> sum4;
    G4Accumulable<G4int> zeroCount;
    G4Accumulable<G4double> minimum;
    G4Accumulable<G4double> maximum;
  };
  struct VolumeScore {
    std::string name;
    std::unique_ptr<G4Accumulable<G4double>> edep;
    // Per-event deposit in this volume (MeV), one entry per recorded event
    // (count shared with eventSummaryCount_). Heap-held: not movable.
    std::unique_ptr<EventScalarAccumulables> eventEdepMeV;
    // The same per-event deposit counted into the fixed log10 grid
    // (sim::event_histogram::kLogSlots integer slots).
    std::vector<std::unique_ptr<G4Accumulable<G4int>>> eventEdepHistogram;
    // Per-event summed step length in this volume (mm) and secondaries created
    // in it, each with its fixed-binning histogram (log10 mm / multiplicity).
    std::unique_ptr<EventScalarAccumulables> eventTrackLengthMm;
    std::vector<std::unique_ptr<G4Accumulable<G4int>>> eventTrackLengthHistogram;
    std::unique_ptr<EventScalarAccumulables> eventSecondaries;
    std::vector<std::unique_ptr<G4Accumulable<G4int>>> eventSecondaryHistogram;
    // The same created secondaries split by species class (power sums only).
    std::array<std::unique_ptr<EventScalarAccumulables>, sim::secondary_species::kCount>
        eventSecondarySpecies;
    // Per-event deposit (MeV) and step length (mm) in this volume split by the
    // class of the stepping particle (power sums only; the classes sum to the
    // volume's eventEdepMeV / eventTrackLengthMm in every event).
    std::array<std::unique_ptr<EventScalarAccumulables>, sim::secondary_species::kCount>
        eventEdepSpecies;
    std::array<std::unique_ptr<EventScalarAccumulables>, sim::secondary_species::kCount>
        eventTrackLengthSpecies;
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
  std::unordered_map<const G4VPhysicalVolume*, int> volumeIndexByPlacement_;
  // This thread's deposit per scored volume in the current event (MeV),
  // flushed into VolumeScore::eventEdepMeV by RecordEventSummary.
  std::vector<G4double> volumeEventEdepMeV_;
  // Same per-event buffers for step length (mm) and created secondaries.
  std::vector<G4double> volumeEventTrackLengthMm_;
  std::vector<G4double> volumeEventSecondaries_;
  std::vector<std::array<G4double, sim::secondary_species::kCount>> volumeEventSecondarySpecies_;
  std::vector<std::array<G4double, sim::secondary_species::kCount>> volumeEventEdepSpecies_;
  std::vector<std::array<G4double, sim::secondary_species::kCount>> volumeEventTrackLengthSpecies_;
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
  G4Accumulable<G4int> eventMultiplicityCount_;
  EventScalarAccumulables eventSecondaryCount_;
  EventScalarAccumulables eventTrackLengthMm_;
  std::array<EventScalarAccumulables, sim::secondary_species::kCount> eventSecondarySpecies_;
  // Whole-event deposit (MeV) and step length (mm) by stepping-particle class.
  std::array<EventScalarAccumulables, sim::secondary_species::kCount> eventEdepByClass_;
  std::array<EventScalarAccumulables, sim::secondary_species::kCount> eventTrackLengthByClass_;
  // Fixed-binning per-event histograms (sim::event_histogram slot layouts).
  // Integer counts merge by addition, so the merged histogram does not depend
  // on worker count or merge order.
  std::vector<std::unique_ptr<G4Accumulable<G4int>>> eventEdepHistogram_;
  std::vector<std::unique_ptr<G4Accumulable<G4int>>> eventSecondaryHistogram_;
  std::vector<std::unique_ptr<G4Accumulable<G4int>>> eventTrackLengthHistogram_;
  // Per-species secondary multiplicity on the same integer-then-log2 layout
  // as eventSecondaryHistogram_ (one slot vector per species class).
  std::array<std::vector<std::unique_ptr<G4Accumulable<G4int>>>, sim::secondary_species::kCount>
      eventSecondarySpeciesHistogram_;
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
  int activeRunId_ = -1;
  HookInferenceCounts dispatchHookContext(const std::string& hookName,
                                          HookRuntimeContext& context);
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
