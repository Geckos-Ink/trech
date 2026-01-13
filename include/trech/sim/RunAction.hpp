#pragma once

#include "trech/core/Config.hpp"
#include "trech/core/Provenance.hpp"
#include "G4UserRunAction.hh"

class G4Run;

namespace trech {

class TrechRunAction : public G4UserRunAction {
public:
  explicit TrechRunAction(const TrechConfig& cfg);

  void BeginOfRunAction(const G4Run* run) override;
  void EndOfRunAction(const G4Run* run) override;

private:
  TrechConfig cfg_;
  ProvenanceWriter provenance_;
};

} // namespace trech
