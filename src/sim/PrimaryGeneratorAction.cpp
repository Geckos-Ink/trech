#include "trech/sim/PrimaryGeneratorAction.hpp"

#include "G4Event.hh"
#include "G4ParticleGun.hh"
#include "G4ParticleTable.hh"
#include "G4SystemOfUnits.hh"
#include "G4ThreeVector.hh"

namespace trech {

TrechPrimaryGeneratorAction::TrechPrimaryGeneratorAction(const trech::BeamConfig& cfg)
    : cfg_(cfg), particleGun_(new G4ParticleGun(1)) {
  auto* table = G4ParticleTable::GetParticleTable();
  auto* particle = table->FindParticle(cfg_.particle);
  if (!particle) {
    particle = table->FindParticle("e-");
  }
  particleGun_->SetParticleDefinition(particle);
  particleGun_->SetParticleEnergy(cfg_.energyMeV * MeV);
  G4ThreeVector direction(cfg_.directionX, cfg_.directionY, cfg_.directionZ);
  if (direction.mag2() <= 0.0) {
    direction = G4ThreeVector(0.0, 0.0, 1.0);
  } else {
    direction = direction.unit();
  }
  particleGun_->SetParticleMomentumDirection(direction);
  particleGun_->SetParticlePosition(G4ThreeVector(0.0, 0.0, 0.0));
}

TrechPrimaryGeneratorAction::~TrechPrimaryGeneratorAction() {
  delete particleGun_;
}

void TrechPrimaryGeneratorAction::GeneratePrimaries(G4Event* event) {
  particleGun_->GeneratePrimaryVertex(event);
}

} // namespace trech
