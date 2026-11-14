#include "trech/sim/TrackingAction.hpp"

#include "trech/js/JsRuntime.hpp"
#include "trech/sim/RunAction.hpp"

#include "G4Event.hh"
#include "G4RunManager.hh"
#include "G4Step.hh"
#include "G4StepPoint.hh"
#include "G4SystemOfUnits.hh"
#include "G4Track.hh"
#include "G4VPhysicalVolume.hh"
#include "G4VProcess.hh"

#include <cctype>

namespace trech {
namespace {

// Same normalization as RunAction's hook registration: alphanumerics only,
// lower-cased ("on_track_start" and "onTrackStart" both register).
std::string normalized(const std::string& value) {
  std::string out;
  for (unsigned char c : value) {
    if (std::isalnum(c)) {
      out.push_back(static_cast<char>(std::tolower(c)));
    }
  }
  return out;
}

TrechRunAction* currentRunAction() {
  auto* manager = G4RunManager::GetRunManager();
  return manager ? const_cast<TrechRunAction*>(
                       static_cast<const TrechRunAction*>(manager->GetUserRunAction()))
                 : nullptr;
}

// Track identity and the track's current point (its vertex in
// PreUserTrackingAction, its final point in PostUserTrackingAction).
HookRuntimeContext trackDetail(const G4Track* track) {
  HookRuntimeContext detail;
  if (const auto* manager = G4RunManager::GetRunManager()) {
    if (const auto* event = manager->GetCurrentEvent()) {
      detail.eventId = event->GetEventID();
    }
  }
  detail.trackId = track->GetTrackID();
  detail.parentTrackId = track->GetParentID();
  if (const auto* definition = track->GetDefinition()) {
    detail.particleName = definition->GetParticleName();
  }
  const auto& p = track->GetPosition();
  detail.trackPositionMm = {p.x() / mm, p.y() / mm, p.z() / mm};
  detail.trackGlobalTimeNs = track->GetGlobalTime() / ns;
  detail.trackKineticEnergyMeV = track->GetKineticEnergy() / MeV;
  detail.trackLengthMm = track->GetTrackLength() / mm;
  detail.trackStepCount = track->GetCurrentStepNumber();
  return detail;
}

} // namespace

bool registersTrackHook(const TrechConfig& cfg) {
  for (const auto& name : cfg.hooks.registered) {
    const auto key = normalized(name);
    if (key == "ontrackstart" || key == "ontrackend") {
      return true;
    }
  }
  return false;
}

void TrechTrackingAction::PreUserTrackingAction(const G4Track* track) {
  auto* runAction = currentRunAction();
  if (!track || !runAction || !runAction->HookOnTrackStartEnabled() ||
      !runAction->RecordHookOnTrackStart()) {
    return;
  }
  auto detail = trackDetail(track);
  if (const auto* volume = track->GetVolume()) {
    detail.volumeName = volume->GetName();  // the vertex volume
  }
  if (const auto* creator = track->GetCreatorProcess()) {
    detail.processName = creator->GetProcessName();  // "" (null) for a primary
  }
  runAction->DispatchTrackHook("onTrackStart", detail);
}

void TrechTrackingAction::PostUserTrackingAction(const G4Track* track) {
  auto* runAction = currentRunAction();
  if (!track || !runAction || !runAction->HookOnTrackEndEnabled() ||
      !runAction->RecordHookOnTrackEnd()) {
    return;
  }
  auto detail = trackDetail(track);
  // The last step's pre-step volume is where the track ended (a track leaving
  // the world has no current volume), and its defining process ended it.
  if (const auto* step = track->GetStep()) {
    if (const auto* pre = step->GetPreStepPoint()) {
      if (const auto* volume = pre->GetPhysicalVolume()) {
        detail.volumeName = volume->GetName();
      }
    }
    if (const auto* post = step->GetPostStepPoint()) {
      if (const auto* process = post->GetProcessDefinedStep()) {
        detail.processName = process->GetProcessName();
      }
    }
  }
  runAction->DispatchTrackHook("onTrackEnd", detail);
}

} // namespace trech
