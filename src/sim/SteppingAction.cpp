#include "trech/sim/SteppingAction.hpp"

#include "trech/sim/EventAction.hpp"
#include "trech/sim/RunAction.hpp"
#include "trech/sim/VizRecorder.hpp"

#include "G4LogicalVolume.hh"
#include "G4Material.hh"
#include "G4OpticalPhoton.hh"
#include "G4ParticleDefinition.hh"
#include "G4StepStatus.hh"
#include "G4SystemOfUnits.hh"
#include "G4Step.hh"
#include "G4StepPoint.hh"
#include "G4Track.hh"
#include "G4TrackStatus.hh"
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

      // Primary fate accounting: classify each primary track once when it
      // leaves the world (transmitted) or is otherwise killed (absorbed).
      if (track->GetParentID() == 0) {
        const auto* postPoint = step->GetPostStepPoint();
        const auto status = postPoint ? postPoint->GetStepStatus() : fUndefined;
        if (status == fWorldBoundary) {
          runAction->AddPrimaryTransmitted();
        } else if (track->GetTrackStatus() == fStopAndKill &&
                   status != fWorldBoundary) {
          runAction->AddPrimaryAbsorbed();
        }
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
      // Each recorded point carries the position + momentum direction of the
      // post-step point (i.e. after any boundary process, so `dir` is the
      // *refracted* direction leaving this vertex).  We tag the point with the
      // *post-step* volume/material — the medium of the outgoing segment — so
      // material, direction and position all describe the same segment.  The
      // birth point below is the exception: its outgoing segment is traversed
      // in the pre-step (emission) volume.
      const auto materialAt = [](const G4StepPoint* point,
                                 std::string& volumeName,
                                 std::string& materialName) {
        if (!point) {
          return;
        }
        if (auto* phys = point->GetPhysicalVolume()) {
          volumeName = phys->GetName();
          if (auto* logic = phys->GetLogicalVolume()) {
            if (auto* mat = logic->GetMaterial()) {
              materialName = mat->GetName();
            }
          }
        }
      };
      std::string preVolumeName;
      std::string preMaterialName;
      materialAt(step->GetPreStepPoint(), preVolumeName, preMaterialName);
      // Post-step touchable is the volume being entered; fall back to the
      // pre-step medium at the world exit where there is no next volume.
      std::string postVolumeName = preVolumeName;
      std::string postMaterialName = preMaterialName;
      materialAt(step->GetPostStepPoint(), postVolumeName, postMaterialName);

      const char* particleName =
          track->GetDefinition() ? track->GetDefinition()->GetParticleName().c_str() : "";
      // On the very first step record the track's birthplace as well, so the
      // polyline starts from the emission point rather than from the first
      // post-step location.  Its outgoing segment runs through the pre-step
      // (emission) volume.
      if (track->GetCurrentStepNumber() == 1) {
        if (const auto* prePoint = step->GetPreStepPoint()) {
          const auto& birth = prePoint->GetPosition();
          vizRecorder.recordStep(eventId, track->GetTrackID(), particleName,
                                 birth.x() / mm, birth.y() / mm, birth.z() / mm,
                                 dir.x(), dir.y(), dir.z(),
                                 track->GetKineticEnergy() / eV,
                                 prePoint->GetGlobalTime() / ns,
                                 0.0,
                                 preVolumeName, preMaterialName);
        }
      }
      vizRecorder.recordStep(eventId, track->GetTrackID(), particleName,
                             pos.x() / mm, pos.y() / mm, pos.z() / mm,
                             dir.x(), dir.y(), dir.z(),
                             track->GetKineticEnergy() / eV,
                             track->GetGlobalTime() / ns,
                             step->GetStepLength() / mm,
                             postVolumeName, postMaterialName);
    }
  }
}

} // namespace trech
