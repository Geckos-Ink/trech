#pragma once

#include "trech/core/Config.hpp"
#include "trech/core/Provenance.hpp"
#include "trech/core/RunOptions.hpp"
#include "G4UserRunAction.hh"
#include "G4Accumulable.hh"

#include <memory>
#include <string>
#include <unordered_map>
#include <vector>

class G4Run;

namespace trech {
namespace ml {
struct StratifyResult;
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
  void RecordEventSummary(G4double eventEdep);
  void AddStratifyResult(const ml::StratifyResult& result);
  void RecordHookOnEventStart();
  bool RecordHookOnStep();
  void RecordHookOnEventEnd();
  void DispatchHook(const std::string& hookName,
                    int eventId = -1,
                    int stepIndex = -1,
                    double stepEdepMeV = 0.0,
                    double stepLengthMm = 0.0);

private:
  void RecordHookOnInit();
  void RecordHookOnRunStart();
  void RecordHookOnRunEnd();

  struct VolumeScore {
    std::string name;
    std::unique_ptr<G4Accumulable<G4double>> edep;
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
  G4Accumulable<G4int> hookOnInitCount_;
  G4Accumulable<G4int> hookOnRunStartCount_;
  G4Accumulable<G4int> hookOnEventStartCount_;
  G4Accumulable<G4int> hookOnStepRawCount_;
  G4Accumulable<G4int> hookOnEventEndCount_;
  G4Accumulable<G4int> hookOnRunEndCount_;
  G4Accumulable<G4int> hookPatchCount_;
  G4Accumulable<G4int> hookEmitCount_;
};

} // namespace trech
