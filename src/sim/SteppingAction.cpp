#include "trech/sim/SteppingAction.hpp"

#include "trech/sim/EventAction.hpp"
#include "trech/sim/KleinNishina.hpp"
#include "trech/sim/PhotonuclearKinematics.hpp"
#include "trech/sim/RunAction.hpp"
#include "trech/sim/SecondarySpecies.hpp"
#include "trech/sim/VizRecorder.hpp"

#include "G4EmProcessSubType.hh"
#include "G4HadronicProcessType.hh"
#include "G4GammaGeneralProcess.hh"
#include "G4LogicalVolume.hh"
#include "G4Element.hh"
#include "G4Isotope.hh"
#include "G4Material.hh"
#include "G4Neutron.hh"
#include "G4NucleiProperties.hh"
#include "G4Proton.hh"
#include "G4Alpha.hh"
#include "G4Gamma.hh"
#include "G4OpBoundaryProcess.hh"
#include "G4OpticalPhoton.hh"
#include "G4PhysicalConstants.hh"
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

#include <algorithm>
#include <cmath>
#include <limits>

namespace trech {

namespace {

// True when (A, Z) is a defined isotope of an element of `material`.
bool isMaterialIsotope(const G4Material* material, G4int a, G4int z) {
  if (!material) {
    return false;
  }
  for (std::size_t i = 0; i < material->GetNumberOfElements(); ++i) {
    const auto* element = material->GetElement(static_cast<G4int>(i));
    if (!element || static_cast<G4int>(std::lround(element->GetZ())) != z) {
      continue;
    }
    for (std::size_t k = 0; k < element->GetNumberOfIsotopes(); ++k) {
      const auto* isotope = element->GetIsotope(static_cast<G4int>(k));
      if (isotope && isotope->GetN() == a) {
        return true;
      }
    }
  }
  return false;
}

// Ground-state nuclear mass from Geant4's own mass table; NaN when undefined.
double nuclearMass(G4int a, G4int z) {
  if (a < 1 || z < 0 || z > a) {
    return std::numeric_limits<double>::quiet_NaN();
  }
  if (a == 1) {
    return z == 1 ? G4Proton::Definition()->GetPDGMass() : G4Neutron::Definition()->GetPDGMass();
  }
  const double mass = G4NucleiProperties::GetNuclearMass(a, z);
  return mass > 0.0 ? mass : std::numeric_limits<double>::quiet_NaN();
}

// Final state of a photon's photonuclear absorption from the step's secondaries:
// the target (A, Z) is inferred from baryon-number/charge conservation of the
// products, its ground-state mass taken from G4NucleiProperties, and the
// four-momentum closure and the two-body ejectile edge evaluated against it.
PhotonuclearFinalState analysePhotonuclearFinalState(const G4Step* step) {
  PhotonuclearFinalState state;
  const auto* pre = step->GetPreStepPoint();
  const auto* post = step->GetPostStepPoint();
  const double photonEnergy = pre->GetKineticEnergy();
  const G4ThreeVector photonMomentum = pre->GetMomentum();
  G4int baryons = 0;
  G4int charge = 0;
  double outEnergy = 0.0;
  G4ThreeVector outMomentum;
  // A photon that survives the step (it should not after absorption) still
  // carries energy and momentum out of the vertex.
  if (step->GetTrack()->GetTrackStatus() == fAlive && post->GetKineticEnergy() > 0.0) {
    outEnergy += post->GetTotalEnergy();
    outMomentum += post->GetMomentum();
  }
  const auto* secondaries = step->GetSecondaryInCurrentStep();
  if (secondaries) {
    for (const auto* secondary : *secondaries) {
      const auto* definition = secondary->GetDefinition();
      outEnergy += secondary->GetTotalEnergy();
      outMomentum += secondary->GetMomentum();
      const G4int b = definition->GetBaryonNumber();
      if (b > 0) {
        baryons += b;
        charge += static_cast<G4int>(std::lround(definition->GetPDGCharge() / CLHEP::eplus));
      }
      if (definition == G4Neutron::Definition()) {
        state.neutrons += 1;
        state.neutronKineticMax =
            std::max(state.neutronKineticMax, secondary->GetKineticEnergy() / CLHEP::MeV);
      } else if (definition == G4Proton::Definition()) {
        state.protons += 1;
      } else if (definition == G4Alpha::Definition()) {
        state.alphas += 1;
      } else if (definition == G4Gamma::Definition()) {
        state.gammas += 1;
      } else {
        state.others += 1;
      }
    }
  }
  state.targetMatched =
      isMaterialIsotope(pre->GetMaterial(), baryons, charge);
  const double targetMass = nuclearMass(baryons, charge);
  if (!std::isfinite(targetMass) || !(photonEnergy > 0.0)) {
    state.energyClosure = std::numeric_limits<double>::quiet_NaN();
    return state;
  }
  state.energyClosure = sim::photonuclear::energyClosure(
      photonEnergy, targetMass, outEnergy, step->GetTotalEnergyDeposit());
  state.momentumClosure = (photonMomentum - outMomentum).mag() / photonEnergy;
  if (secondaries) {
    for (const auto* secondary : *secondaries) {
      const auto* definition = secondary->GetDefinition();
      const G4int b = definition->GetBaryonNumber();
      if (b <= 0 || b >= baryons) {
        continue;  // only baryonic ejectiles that leave a recoil behind
      }
      const G4int z = static_cast<G4int>(std::lround(definition->GetPDGCharge() / CLHEP::eplus));
      const double ejectileMass = nuclearMass(b, z);
      const double recoilMass = nuclearMass(baryons - b, charge - z);
      const double edge = sim::photonuclear::twoBodyMaxKinetic(photonEnergy, targetMass,
                                                               ejectileMass, recoilMass);
      if (!std::isfinite(edge)) {
        // A closed channel that was nevertheless emitted: maximal violation.
        state.edgeTested += 1;
        state.edgeExcessMax = std::max(state.edgeExcessMax,
                                       secondary->GetKineticEnergy() / photonEnergy);
        continue;
      }
      state.edgeTested += 1;
      state.edgeExcessMax = std::max(
          state.edgeExcessMax, (secondary->GetKineticEnergy() - edge) / photonEnergy);
    }
  }
  return state;
}

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
        HookRuntimeContext detail;
        detail.eventId = eventId;
        detail.stepIndex = track->GetCurrentStepNumber();
        detail.stepEdepMeV = edep / MeV;
        detail.stepLengthMm = step->GetStepLength() / mm;
        detail.trackId = track->GetTrackID();
        detail.parentTrackId = track->GetParentID();
        if (const auto* definition = track->GetDefinition()) {
          detail.particleName = definition->GetParticleName();
        }
        const auto* pre = step->GetPreStepPoint();
        const auto* post = step->GetPostStepPoint();
        if (pre) {
          const auto& p = pre->GetPosition();
          detail.prePositionMm = {p.x() / mm, p.y() / mm, p.z() / mm};
          detail.preGlobalTimeNs = pre->GetGlobalTime() / ns;
          detail.preKineticEnergyMeV = pre->GetKineticEnergy() / MeV;
          if (const auto* volume = pre->GetPhysicalVolume()) {
            detail.volumeName = volume->GetName();
          }
        }
        if (post) {
          const auto& p = post->GetPosition();
          detail.postPositionMm = {p.x() / mm, p.y() / mm, p.z() / mm};
          detail.postGlobalTimeNs = post->GetGlobalTime() / ns;
          detail.postKineticEnergyMeV = post->GetKineticEnergy() / MeV;
          if (const auto* process = post->GetProcessDefinedStep()) {
            detail.processName = process->GetProcessName();
          }
        }
        runAction->DispatchStepHook(detail);
      }
      if (edep > 0) {
        runAction->AddEnergyDeposit(edep);
      }
      if (runAction->HasVolumeScores()) {
        // One cached pointer lookup per step resolves the scored volume. The
        // pre-step volume owns the step: its deposit and length count there,
        // and a secondary's first step starts at its creation vertex, so it
        // counts toward the volume it was born in.
        const auto* preStep = step->GetPreStepPoint();
        const int volumeIndex = runAction->VolumeScoreIndex(
            preStep ? preStep->GetTouchableHandle()->GetVolume() : nullptr);
        if (volumeIndex >= 0) {
          if (edep > 0) {
            runAction->AddVolumeEnergyDeposit(volumeIndex, edep);
          }
          runAction->AddVolumeStep(
              volumeIndex, step->GetStepLength(),
              track->GetCurrentStepNumber() == 1 && track->GetParentID() != 0);
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
              // For a Compton scatter also record the fraction of the photon
              // energy handed to the electron, (E - E')/E, from the primary's
              // own pre/post kinetic energy (the photon survives the scatter).
              // Its mean is compared to the Klein-Nishina sigma_tr/sigma.
              // The u = T/T_max bin (edge from this photon's own energy) feeds
              // the binned Klein-Nishina spectrum-shape comparison.
              // The scattering cosine comes from the photon's pre/post momentum
              // DIRECTION (not its energy), feeding the Klein-Nishina angular
              // distribution; the residual |E'/E - 1/(1+eps(1-cos))| closes the
              // free-electron energy-angle relation between the two readings.
              double transferFraction = 0.0;
              G4int transferBin = -1;
              double cosTheta = std::numeric_limits<double>::quiet_NaN();
              double kinematicResidual = 0.0;
              if (subType == fComptonScattering) {
                const double preKE = step->GetPreStepPoint()->GetKineticEnergy();
                if (preKE > 0.0) {
                  const double epsilon = preKE / CLHEP::electron_mass_c2;
                  const double postKE = postPoint->GetKineticEnergy();
                  const double ratio = postKE / preKE;
                  transferFraction = (preKE - postKE) / preKE;
                  transferBin = sim::klein_nishina::transferHistogramBin(epsilon, transferFraction);
                  const auto preDir = step->GetPreStepPoint()->GetMomentumDirection();
                  const auto postDir = postPoint->GetMomentumDirection();
                  const double norm = preDir.mag() * postDir.mag();
                  if (norm > 0.0) {
                    cosTheta = std::clamp(preDir.dot(postDir) / norm, -1.0, 1.0);
                    kinematicResidual = std::abs(
                        ratio - sim::klein_nishina::scatteredEnergyRatio(epsilon, cosTheta));
                  }
                }
              }
              runAction->AddPrimaryFirstInteraction(subType, transferFraction, transferBin,
                                                    cosTheta, kinematicResidual);
              if (subType == fHadronInelastic &&
                  track->GetDefinition() == G4Gamma::Definition()) {
                runAction->AddPhotonuclearFinalState(analysePhotonuclearFinalState(step));
              }
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
        if (track->GetParentID() != 0) {
          const auto* definition = track->GetDefinition();
          eventAction->AddSecondaryTrack(sim::secondary_species::classify(
              definition ? definition->GetPDGEncoding() : 0,
              definition ? std::string_view(definition->GetParticleName()) : std::string_view()));
        }
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
