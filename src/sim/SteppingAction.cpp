#include "trech/sim/SteppingAction.hpp"

#include "trech/sim/RunAction.hpp"

#include "G4Step.hh"
#include "G4Track.hh"
#include "G4RunManager.hh"

namespace trech {

void TrechSteppingAction::UserSteppingAction(const G4Step* step) {
  const auto* track = step->GetTrack();
  const auto edep = step->GetTotalEnergyDeposit();
  if (edep <= 0) {
    return;
  }

  if (auto* manager = G4RunManager::GetRunManager()) {
    auto* runAction = static_cast<TrechRunAction*>(manager->GetUserRunAction());
    if (runAction) {
      runAction->AddEnergyDeposit(edep);
    }
  }

  const auto& pos = track->GetPosition();
  const auto time = track->GetGlobalTime();
  (void)pos;
  (void)time;

  // TODO: push into a compact injection stream.
}

} // namespace trech
