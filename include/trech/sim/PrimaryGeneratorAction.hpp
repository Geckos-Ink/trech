#pragma once

#include "trech/core/Config.hpp"
#include "G4VUserPrimaryGeneratorAction.hh"

class G4Event;
class G4ParticleGun;

namespace trech {

class TrechPrimaryGeneratorAction : public G4VUserPrimaryGeneratorAction {
public:
  explicit TrechPrimaryGeneratorAction(const trech::BeamConfig& cfg);
  ~TrechPrimaryGeneratorAction() override;

  void GeneratePrimaries(G4Event* event) override;

private:
  trech::BeamConfig cfg_;
  G4ParticleGun* particleGun_ = nullptr;
};

} // namespace trech
