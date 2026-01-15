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
    auto* runAction =
        const_cast<TrechRunAction*>(static_cast<const TrechRunAction*>(manager->GetUserRunAction()));
    auto* eventAction =
        const_cast<TrechEventAction*>(
            static_cast<const TrechEventAction*>(manager->GetUserEventAction()));
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
    if (eventAction) {
      const auto stepLength = step->GetStepLength();
      eventAction->AddStep(stepLength);
      if (track->GetCurrentStepNumber() == 1) {
        eventAction->AddTrack();
      }
      if (edep > 0) {
        eventAction->AddEnergyDeposit(edep);
      }
      if (cfg_.optics.enable &&
          track->GetDefinition() == G4OpticalPhoton::OpticalPhotonDefinition()) {
        if (track->GetCurrentStepNumber() == 1) {
          eventAction->AddOpticalPhotonTrack();
        }
        eventAction->AddOpticalPhotonStep(stepLength);
      }
    }
  }

  const auto& pos = track->GetPosition();
  const auto time = track->GetGlobalTime();
  (void)pos;
  (void)time;

  // TODO: push into a compact injection stream.
}

} // namespace trech
