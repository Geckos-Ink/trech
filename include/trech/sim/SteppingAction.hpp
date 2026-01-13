#pragma once

#include "G4UserSteppingAction.hh"

class G4Step;

namespace trech {

class TrechSteppingAction : public G4UserSteppingAction {
public:
  TrechSteppingAction() = default;

  void UserSteppingAction(const G4Step* step) override;
};

} // namespace trech
