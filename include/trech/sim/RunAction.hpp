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
  // Record a primary's FIRST discrete interaction: increments the count of
  // primaries that interacted at all, and (when isPhotoelectric) the photoelectric
  // subset. Their ratio is the Monte-Carlo counterpart of the analytic
  // photo-fraction check (sigma_phot / sigma_total).
  void AddPrimaryFirstInteraction(G4bool isPhotoelectric);
  void RecordEventSummary(G4double eventEdep);
  void RecordEventFeatureVector(const ml::EventFeatures& features);
  void AddStratifyResult(const ml::StratifyResult& result);
  void RecordHookOnEventStart();
  bool RecordHookOnStep();
  void RecordHookOnEventEnd();
  void DispatchHook(const std::string& hookName,
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
  std::unique_ptr<ml::OnlineEventStats> eventStats_;
  mutable std::mutex eventStatsMutex_;
  G4Accumulable<G4int> featureStatsCount_;
  std::vector<FeatureScore> featureScores_;
  G4Accumulable<G4int> stratifyTotalCount_;
  G4Accumulable<G4int> stratifyPredictableCount_;
  G4Accumulable<G4int> stratifyExceptionalCount_;
  G4Accumulable<G4int> stratifyUnclassifiedCount_;
  G4Accumulable<G4int> stratifyThresholdCount_;
  G4Accumulable<G4int> stratifyModelCount_;
  G4Accumulable<G4int> stratifySourceUnknownCount_;
  G4Accumulable<G4int> eventSummaryCount_;
  G4Accumulable<G4double> eventEdepSumMeV_;
  G4Accumulable<G4double> eventEdepSqSumMeV2_;
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
};

} // namespace trech
