#include "trech/sim/SteppingAction.hpp"

#include "trech/sim/EventAction.hpp"
#include "trech/sim/RunAction.hpp"

#include "G4OpticalPhoton.hh"
#include "G4Step.hh"
#include "G4Track.hh"
#include "G4RunManager.hh"

namespace trech {

void TrechSteppingAction::UserSteppingAction(const G4Step* step) {
  const auto* track = step->GetTrack();
  const auto edep = step->GetTotalEnergyDeposit();
  if (auto* manager = G4RunManager::GetRunManager()) {
    auto* runAction = static_cast<TrechRunAction*>(manager->GetUserRunAction());
    auto* eventAction = static_cast<TrechEventAction*>(manager->GetUserEventAction());
    if (runAction) {
      if (edep > 0) {
        runAction->AddEnergyDeposit(edep);
      }
      if (cfg_.optics.enable &&
          track->GetDefinition() == G4OpticalPhoton::OpticalPhotonDefinition()) {
        if (track->GetCurrentStepNumber() == 1) {
          runAction->AddOpticalPhotonTrack();
        }
        runAction->AddOpticalPhotonStep(step->GetStepLength());
      }
    }
    if (eventAction && edep > 0) {
      eventAction->AddEnergyDeposit(edep);
    }
    if (eventAction && cfg_.optics.enable &&
        track->GetDefinition() == G4OpticalPhoton::OpticalPhotonDefinition()) {
      if (track->GetCurrentStepNumber() == 1) {
        eventAction->AddOpticalPhotonTrack();
      }
      eventAction->AddOpticalPhotonStep(step->GetStepLength());
    }
  }

  const auto& pos = track->GetPosition();
  const auto time = track->GetGlobalTime();
  (void)pos;
  (void)time;

  // TODO: push into a compact injection stream.
}

} // namespace trech
