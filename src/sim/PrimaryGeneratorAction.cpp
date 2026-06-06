#include "trech/sim/PrimaryGeneratorAction.hpp"

#include <algorithm>
#include <cmath>

#include "G4Event.hh"
#include "G4ParticleGun.hh"
#include "G4ParticleTable.hh"
#include "G4SystemOfUnits.hh"
#include "G4ThreeVector.hh"
#include "Randomize.hh"

namespace trech {

namespace {

// Build a unit vector perpendicular to w to seed an orthonormal frame.
G4ThreeVector perpendicularSeed(const G4ThreeVector& w) {
  const G4ThreeVector axis =
      (std::abs(w.x()) < 0.9) ? G4ThreeVector(1.0, 0.0, 0.0)
                              : G4ThreeVector(0.0, 1.0, 0.0);
  G4ThreeVector u = axis - w * (axis.dot(w));
  if (u.mag2() <= 1.0e-12) {
    u = G4ThreeVector(0.0, 0.0, 1.0) - w * w.z();
  }
  return u.unit();
}

} // namespace

TrechPrimaryGeneratorAction::TrechPrimaryGeneratorAction(const trech::BeamConfig& cfg)
    : cfg_(cfg), particleGun_(new G4ParticleGun(1)) {
  auto* table = G4ParticleTable::GetParticleTable();
  auto* particle = table->FindParticle(cfg_.particle);
  if (!particle) {
    particle = table->FindParticle("e-");
  }
  particleGun_->SetParticleDefinition(particle);

  // Resolve optical-photon polarization control. Geant4 otherwise leaves the
  // optical photon's polarization null and patches in a random vector itself
  // (the "ZeroPolarization" warning); we sample it from the seeded engine so
  // the choice is explicit and reproducible. Non-optical particles are left
  // untouched so electron/ion scenarios keep their exact behaviour.
  isOpticalPhoton_ = (particle->GetParticleName() == "opticalphoton");
  if (isOpticalPhoton_) {
    if (cfg_.polarization == "none") {
      polarizationMode_ = PolarizationMode::kNone;
    } else if (cfg_.polarization == "linear") {
      polarizationMode_ = PolarizationMode::kLinearFixed;
    } else {
      // "" or "unpolarized": random transverse linear polarization per event.
      polarizationMode_ = PolarizationMode::kUnpolarized;
    }
    polarizationAngleRad_ = cfg_.polarizationAngleDeg * deg;
  }

  baseEnergyMeV_ = cfg_.energyMeV;
  particleGun_->SetParticleEnergy(baseEnergyMeV_ * MeV);

  G4ThreeVector direction(cfg_.directionX, cfg_.directionY, cfg_.directionZ);
  if (direction.mag2() <= 0.0) {
    direction = G4ThreeVector(0.0, 0.0, 1.0);
  } else {
    direction = direction.unit();
  }
  w_ = direction;
  u_ = perpendicularSeed(w_);
  v_ = w_.cross(u_).unit();

  origin_ = G4ThreeVector(cfg_.originXMm * mm, cfg_.originYMm * mm,
                          cfg_.originZMm * mm);

  varyPosition_ = cfg_.spotRadiusMm > 0.0;
  varyDirection_ = cfg_.divergenceDeg > 0.0;
  varyEnergy_ = cfg_.energySpreadFractional > 0.0;

  // Static defaults; GeneratePrimaries overrides per event when variety is on.
  particleGun_->SetParticleMomentumDirection(w_);
  particleGun_->SetParticlePosition(origin_);
}

TrechPrimaryGeneratorAction::~TrechPrimaryGeneratorAction() {
  delete particleGun_;
}

void TrechPrimaryGeneratorAction::GeneratePrimaries(G4Event* event) {
  // All randomness draws from Geant4's seeded engine (per-thread in MT), so a
  // fixed seed still reproduces the run exactly — variety here adds spread to
  // the sampled distribution, not non-determinism.

  // Emission position: uniform over a disk of radius spotRadiusMm in the plane
  // perpendicular to the nominal direction.
  G4ThreeVector position = origin_;
  if (varyPosition_) {
    const double r = cfg_.spotRadiusMm * mm * std::sqrt(G4UniformRand());
    const double phi = CLHEP::twopi * G4UniformRand();
    position += r * (std::cos(phi) * u_ + std::sin(phi) * v_);
  }
  particleGun_->SetParticlePosition(position);

  // Emission direction: uniform in solid angle within a cone of half-angle
  // divergenceDeg about the nominal direction.
  G4ThreeVector direction = w_;
  if (varyDirection_) {
    const double cosMax = std::cos(cfg_.divergenceDeg * deg);
    const double cosTheta = 1.0 - G4UniformRand() * (1.0 - cosMax);
    const double sinTheta = std::sqrt(std::max(0.0, 1.0 - cosTheta * cosTheta));
    const double phi = CLHEP::twopi * G4UniformRand();
    direction = sinTheta * (std::cos(phi) * u_ + std::sin(phi) * v_) +
                cosTheta * w_;
    direction = direction.unit();
  }
  particleGun_->SetParticleMomentumDirection(direction);

  // Optical-photon polarization: a unit vector in the plane transverse to the
  // (possibly cone-sampled) emission direction. Unpolarized => a random linear
  // state per event from the seeded engine, which over the ensemble reproduces
  // the unpolarized Fresnel reflection the inverse validator expects; linear =>
  // a fixed angle. Setting it explicitly kills Geant4's ZeroPolarization
  // random fallback while staying reproducible under a fixed seed.
  if (isOpticalPhoton_ && polarizationMode_ != PolarizationMode::kNone) {
    const G4ThreeVector e1 = perpendicularSeed(direction);
    const G4ThreeVector e2 = direction.cross(e1).unit();
    const double psi = (polarizationMode_ == PolarizationMode::kLinearFixed)
                           ? polarizationAngleRad_
                           : CLHEP::twopi * G4UniformRand();
    const G4ThreeVector polarization =
        (std::cos(psi) * e1 + std::sin(psi) * e2).unit();
    particleGun_->SetParticlePolarization(polarization);
  }

  // Emission energy: Gaussian band of fractional width energySpreadFractional,
  // clamped to a small positive floor so a wide tail never goes non-physical.
  if (varyEnergy_) {
    const double sigma = cfg_.energySpreadFractional * baseEnergyMeV_;
    double energyMeV = G4RandGauss::shoot(baseEnergyMeV_, sigma);
    const double floorMeV = 1.0e-6 * baseEnergyMeV_;
    if (energyMeV < floorMeV) {
      energyMeV = floorMeV;
    }
    particleGun_->SetParticleEnergy(energyMeV * MeV);
  }

  particleGun_->GeneratePrimaryVertex(event);
}

} // namespace trech
