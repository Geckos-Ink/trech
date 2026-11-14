#pragma once

#include "trech/core/Config.hpp"
#include "G4UserTrackingAction.hh"

class G4Track;

namespace trech {

// Dispatches the onTrackStart / onTrackEnd scenario hooks with Geant4 track
// detail (ctx.track). Registered only when one of them is in hooks.registered,
// so runs without track hooks keep Geant4's default (no tracking action).
// Bookkeeping of Geant4's own transport for the hook layer, never physics.
class TrechTrackingAction : public G4UserTrackingAction {
public:
  explicit TrechTrackingAction(const TrechConfig& cfg) : cfg_(cfg) {}

  void PreUserTrackingAction(const G4Track* track) override;
  void PostUserTrackingAction(const G4Track* track) override;

private:
  TrechConfig cfg_;
};

// Whether a config registers a track hook (normalized like RunAction).
bool registersTrackHook(const TrechConfig& cfg);

} // namespace trech
