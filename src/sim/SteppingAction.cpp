#include "trech/sim/SteppingAction.hpp"

#include "trech/sim/EventAction.hpp"
#include "trech/sim/RunAction.hpp"
#include "trech/sim/VizRecorder.hpp"

#include "G4LogicalVolume.hh"
#include "G4Material.hh"
#include "G4OpticalPhoton.hh"
#include "G4ParticleDefinition.hh"
#include "G4SystemOfUnits.hh"
#include "G4Step.hh"
#include "G4StepPoint.hh"
#include "G4Track.hh"
#include "G4VPhysicalVolume.hh"
#include "G4Event.hh"
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
      const bool shouldDispatchStepHook = runAction->RecordHookOnStep();
      if (shouldDispatchStepHook) {
        int eventId = -1;
        if (const auto* currentEvent = manager->GetCurrentEvent()) {
          eventId = currentEvent->GetEventID();
        }
        runAction->DispatchHook("onStep", eventId, track->GetCurrentStepNumber(),
                                edep / MeV, step->GetStepLength() / mm);
      }
      if (edep > 0) {
        runAction->AddEnergyDeposit(edep);
        const auto* preStep = step->GetPreStepPoint();
        const auto* volume = preStep ? preStep->GetTouchableHandle()->GetVolume() : nullptr;
        if (volume) {
          runAction->AddVolumeEnergyDeposit(volume->GetName(), edep);
        }
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

  auto& vizRecorder = sim::VizRecorder::instance();
  if (vizRecorder.enabled()) {
    const bool isOptical =
        track->GetDefinition() == G4OpticalPhoton::OpticalPhotonDefinition();
    if (isOptical || cfg_.viz.includeNonOptical) {
      int eventId = -1;
      if (auto* manager = G4RunManager::GetRunManager()) {
        if (const auto* currentEvent = manager->GetCurrentEvent()) {
          eventId = currentEvent->GetEventID();
        }
      }
      const auto& pos = track->GetPosition();
      const auto& dir = track->GetMomentumDirection();
      std::string volumeName;
      std::string materialName;
      if (const auto* prePoint = step->GetPreStepPoint()) {
        if (auto* phys = prePoint->GetPhysicalVolume()) {
          volumeName = phys->GetName();
          if (auto* logic = phys->GetLogicalVolume()) {
            if (auto* mat = logic->GetMaterial()) {
              materialName = mat->GetName();
            }
          }
        }
      }
      const char* particleName =
          track->GetDefinition() ? track->GetDefinition()->GetParticleName().c_str() : "";
      // On the very first step record the track's birthplace as well, so the
      // polyline starts from the emission point rather than from the first
      // post-step location.
      if (track->GetCurrentStepNumber() == 1) {
        if (const auto* prePoint = step->GetPreStepPoint()) {
          const auto& birth = prePoint->GetPosition();
          vizRecorder.recordStep(eventId, track->GetTrackID(), particleName,
                                 birth.x() / mm, birth.y() / mm, birth.z() / mm,
                                 dir.x(), dir.y(), dir.z(),
                                 track->GetKineticEnergy() / eV,
                                 prePoint->GetGlobalTime() / ns,
                                 0.0,
                                 volumeName, materialName);
        }
      }
      vizRecorder.recordStep(eventId, track->GetTrackID(), particleName,
                             pos.x() / mm, pos.y() / mm, pos.z() / mm,
                             dir.x(), dir.y(), dir.z(),
                             track->GetKineticEnergy() / eV,
                             track->GetGlobalTime() / ns,
                             step->GetStepLength() / mm,
                             volumeName, materialName);
    }
  }
}

} // namespace trech
