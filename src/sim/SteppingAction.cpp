#include "trech/sim/SteppingAction.hpp"

#include "trech/sim/EventAction.hpp"
#include "trech/sim/RunAction.hpp"
#include "trech/sim/VizRecorder.hpp"

#include "G4EmProcessSubType.hh"
#include "G4GammaGeneralProcess.hh"
#include "G4LogicalVolume.hh"
#include "G4Material.hh"
#include "G4OpBoundaryProcess.hh"
#include "G4OpticalPhoton.hh"
#include "G4ProcessManager.hh"
#include "G4ParticleDefinition.hh"
#include "G4ProcessType.hh"
#include "G4StepStatus.hh"
#include "G4VProcess.hh"
#include "G4SystemOfUnits.hh"
#include "G4Step.hh"
#include "G4StepPoint.hh"
#include "G4Track.hh"
#include "G4TrackStatus.hh"
#include "G4VPhysicalVolume.hh"
#include "G4Event.hh"
#include "G4RunManager.hh"

namespace trech {

namespace {

// The optical boundary process of this worker (nullptr without optical physics).
G4OpBoundaryProcess* opticalBoundaryProcess(const G4Track* track) {
  static G4ThreadLocal G4OpBoundaryProcess* cached = nullptr;
  static G4ThreadLocal bool searched = false;
  if (!searched) {
    searched = true;
    if (const auto* manager = track->GetDefinition()->GetProcessManager()) {
      const auto* processes = manager->GetProcessList();
      for (std::size_t i = 0; processes && i < processes->size(); ++i) {
        if (auto* boundary = dynamic_cast<G4OpBoundaryProcess*>((*processes)[i])) {
          cached = boundary;
          break;
        }
      }
    }
  }
  return cached;
}

// Compact class of what G4OpBoundaryProcess did at this boundary, so a viewer
// can tell a reflected ray from a refracted one without guessing from geometry.
std::string opticalBoundaryClass(const G4Track* track) {
  const auto* boundary = opticalBoundaryProcess(track);
  if (!boundary) {
    return {};
  }
  switch (boundary->GetStatus()) {
    case FresnelRefraction:
    case Transmission:
      return "refraction";
    case FresnelReflection:
    case LambertianReflection:
    case LobeReflection:
    case SpikeReflection:
    case BackScattering:
      return "reflection";
    case TotalInternalReflection:
      return "total_internal_reflection";
    case Absorption:
      return "absorption";
    case Detection:
      return "detection";
    default:
      return {};
  }
}

}  // namespace

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
        // Accumulate the primary's path length (summed over its steps). For a
        // charged primary that fully stops in the geometry, the per-primary
        // mean of this is the Monte-Carlo CSDA range.
        runAction->AddPrimaryTrackLength(step->GetStepLength());
        // Track whether this primary has interacted yet (for the uncollided
        // beam tally). Reset on the primary's first step; a primary's steps are
        // processed contiguously within a thread, so a single flag is enough.
        if (track->GetTrackID() != activePrimaryTrackId_ ||
            track->GetCurrentStepNumber() == 1) {
          activePrimaryTrackId_ = track->GetTrackID();
          activePrimaryCollided_ = false;
        }
        const auto* postPoint = step->GetPostStepPoint();
        // A discrete interaction is any step-defining process that is not
        // pure transport (Compton, photoelectric, Rayleigh, pair, ...). The
        // attenuation coefficient mu in the Beer-Lambert prediction sums these
        // same processes, so the definitions stay consistent.
        if (const auto* proc =
                postPoint ? postPoint->GetProcessDefinedStep() : nullptr) {
          if (proc->GetProcessType() != fTransportation) {
            if (!activePrimaryCollided_) {
              // This primary's first discrete interaction. Classify it as
              // photoelectric for the photo-fraction (branching-ratio) analytic
              // check. QBBC's EM list wraps the gamma processes in
              // G4GammaGeneralProcess, so read the SELECTED sub-process's EM
              // subtype rather than the wrapper's name; fall back to the process
              // subtype directly when the wrapper is not in use.
              G4int subType = proc->GetProcessSubType();
              if (const auto* general =
                      dynamic_cast<const G4GammaGeneralProcess*>(proc)) {
                subType = general->GetSubProcessSubType();
              }
              runAction->AddPrimaryFirstInteraction(subType == fPhotoElectricEffect);
            }
            activePrimaryCollided_ = true;
          }
        }
        const auto status = postPoint ? postPoint->GetStepStatus() : fUndefined;
        if (status == fWorldBoundary) {
          runAction->AddPrimaryTransmitted();
          if (!activePrimaryCollided_) {
            runAction->AddPrimaryUncollided();
          }
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

      // What physically ended this step? A change of direction at a geometry
      // boundary is not scattering. Persist the actual Geant4 process and a
      // compact class so Studio can show air propagation/boundaries/scatters
      // without guessing from the shape of a polyline.
      std::string processName;
      std::string interaction = "transport";
      if (const auto* postPoint = step->GetPostStepPoint()) {
        const auto status = postPoint->GetStepStatus();
        if (status == fWorldBoundary) {
          interaction = "world_boundary";
        } else if (status == fGeomBoundary) {
          interaction = "boundary";
        }
        if (const auto* proc = postPoint->GetProcessDefinedStep()) {
          processName = proc->GetProcessName();
          if (status != fWorldBoundary && status != fGeomBoundary &&
              proc->GetProcessType() != fTransportation) {
            G4int subType = proc->GetProcessSubType();
            if (const auto* general =
                    dynamic_cast<const G4GammaGeneralProcess*>(proc)) {
              subType = general->GetSubProcessSubType();
            }
            interaction = (subType == fRayleigh || subType == fComptonScattering)
                              ? "scatter"
                              : "interaction";
          }
        }
      }

      const char* particleName =
          track->GetDefinition() ? track->GetDefinition()->GetParticleName().c_str() : "";
      // On the very first step record the track's birthplace as well, so the
      // polyline starts from the emission point rather than from the first
      // post-step location.  Its outgoing segment runs through the pre-step
      // (emission) volume.
      if (track->GetCurrentStepNumber() == 1) {
        if (const auto* prePoint = step->GetPreStepPoint()) {
          const auto& birth = prePoint->GetPosition();
          // The birth point's outgoing segment is the emission segment, so it
          // carries the *pre-step* (emission) momentum direction — not `dir`,
          // which is the post-step direction after any boundary process at the
          // end of step 1 (that would mis-record the emission direction for a
          // photon that refracts/reflects on its first step).
          const auto& birthDir = prePoint->GetMomentumDirection();
          vizRecorder.recordStep(eventId, track->GetTrackID(), particleName,
                                 birth.x() / mm, birth.y() / mm, birth.z() / mm,
                                 birthDir.x(), birthDir.y(), birthDir.z(),
                                 // Emission energy: the pre-step kinetic energy (the track's
                                 // current energy is already after step 1's loss).
                                 prePoint->GetKineticEnergy() / eV,
                                 prePoint->GetGlobalTime() / ns,
                                 0.0,
                                 preVolumeName, preMaterialName,
                                 "source", "emission");
        }
      }
      std::string boundaryClass;
      if (interaction == "boundary" &&
          track->GetDefinition() == G4OpticalPhoton::OpticalPhotonDefinition()) {
        boundaryClass = opticalBoundaryClass(track);
      }
      vizRecorder.recordStep(eventId, track->GetTrackID(), particleName,
                             pos.x() / mm, pos.y() / mm, pos.z() / mm,
                             dir.x(), dir.y(), dir.z(),
                             track->GetKineticEnergy() / eV,
                             track->GetGlobalTime() / ns,
                             step->GetStepLength() / mm,
                             postVolumeName, postMaterialName,
                             processName, interaction, boundaryClass);
    }
  }
}

} // namespace trech
