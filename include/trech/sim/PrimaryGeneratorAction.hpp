#pragma once

#include "trech/core/Config.hpp"
#include "G4VUserPrimaryGeneratorAction.hh"
#include "G4ThreeVector.hh"

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

  // Precomputed emission frame: w_ is the nominal direction, u_/v_ span the
  // plane perpendicular to it (for disk + cone sampling).
  G4ThreeVector origin_;
  G4ThreeVector w_;
  G4ThreeVector u_;
  G4ThreeVector v_;
  double baseEnergyMeV_ = 1.0;
  bool varyPosition_ = false;
  bool varyDirection_ = false;
  bool varyEnergy_ = false;
};

} // namespace trech
