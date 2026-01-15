#pragma once

#include "trech/core/Config.hpp"
#include "trech/core/Provenance.hpp"
#include "trech/core/RunOptions.hpp"
#include "G4UserRunAction.hh"
#include "G4Accumulable.hh"

class G4Run;

namespace trech {

class TrechRunAction : public G4UserRunAction {
public:
  TrechRunAction(const TrechConfig& cfg, const RunOptions& options);

  void BeginOfRunAction(const G4Run* run) override;
  void EndOfRunAction(const G4Run* run) override;
  void AddEnergyDeposit(G4double edep);
  void AddOpticalPhotonStep(G4double stepLength);
  void AddOpticalPhotonTrack();

private:
  TrechConfig cfg_;
  RunOptions options_;
  ProvenanceWriter provenance_;
  std::string scoresPath_;
  G4Accumulable<G4double> totalEdep_;
  G4Accumulable<G4int> opticalPhotonSteps_;
  G4Accumulable<G4int> opticalPhotonTracks_;
  G4Accumulable<G4double> opticalPhotonTrackLength_;
};

} // namespace trech
