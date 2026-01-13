#pragma once

#include "G4UserEventAction.hh"

class G4Event;

namespace trech {

class TrechEventAction : public G4UserEventAction {
public:
  TrechEventAction() = default;

  void BeginOfEventAction(const G4Event* event) override;
  void EndOfEventAction(const G4Event* event) override;
};

} // namespace trech
