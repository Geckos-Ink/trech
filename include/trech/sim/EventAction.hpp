#pragma once

#include "trech/core/Config.hpp"
#include "trech/core/RunOptions.hpp"
#include "trech/ml/Stratifier.hpp"

#include "G4UserEventAction.hh"

class G4Event;

namespace trech {

class TrechEventAction : public G4UserEventAction {
public:
  TrechEventAction(const TrechConfig& cfg, const RunOptions& options);

  void BeginOfEventAction(const G4Event* event) override;
  void EndOfEventAction(const G4Event* event) override;

  void AddEnergyDeposit(double edep);
  void AddStep(double stepLength);
  void AddTrack();
  void AddOpticalPhotonStep(double stepLength);
  void AddOpticalPhotonTrack();

private:
  void ResetEvent();

  TrechConfig cfg_;
  RunOptions options_;
  ml::EventStratifier stratifier_;
  std::string eventsPath_;
  std::string featuresPath_;
  std::string resimPath_;
  double eventEdep_;
  int totalStepCount_;
  int totalTrackCount_;
  double totalTrackLength_;
  int opticalPhotonSteps_;
  int opticalPhotonTracks_;
  double opticalPhotonTrackLength_;
};

} // namespace trech
