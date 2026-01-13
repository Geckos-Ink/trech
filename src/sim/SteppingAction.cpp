#include "trech/sim/SteppingAction.hpp"

#include "G4Step.hh"
#include "G4Track.hh"

namespace trech {

void TrechSteppingAction::UserSteppingAction(const G4Step* step) {
  const auto* track = step->GetTrack();
  const auto edep = step->GetTotalEnergyDeposit();
  if (edep <= 0) {
    return;
  }

  const auto& pos = track->GetPosition();
  const auto time = track->GetGlobalTime();
  (void)pos;
  (void)time;

  // TODO: push into a compact injection stream.
}

} // namespace trech
