#pragma once

#include "trech/core/Config.hpp"
#include "G4UserSteppingAction.hh"

class G4Step;

namespace trech {

class TrechSteppingAction : public G4UserSteppingAction {
public:
  explicit TrechSteppingAction(const TrechConfig& cfg) : cfg_(cfg) {}

  void UserSteppingAction(const G4Step* step) override;

private:
  TrechConfig cfg_;
  // Tracks whether the primary currently being transported has undergone any
  // discrete interaction yet (for the uncollided / Beer-Lambert tally). A
  // primary's steps are processed contiguously within a worker thread, so a
  // single current-track flag suffices; it is reset on each primary's first
  // step. -1 means "no primary in flight".
  int activePrimaryTrackId_ = -1;
  bool activePrimaryCollided_ = false;
};

} // namespace trech
