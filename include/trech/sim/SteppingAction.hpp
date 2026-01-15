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
};

} // namespace trech
