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

  // Optional emission spectrum: per-line energies and a cumulative-weight table
  // (last entry == total weight) for O(log n) weighted sampling from the seeded
  // engine. Empty => single-energy beam.
  std::vector<double> spectrumEnergiesMeV_;
  std::vector<double> spectrumCdf_;

  // Optical-photon polarization control (see BeamConfig::polarization). Only the
  // optical-photon primary uses this; everything else leaves polarization alone.
  enum class PolarizationMode { kNone, kUnpolarized, kLinearFixed };
  bool isOpticalPhoton_ = false;
  PolarizationMode polarizationMode_ = PolarizationMode::kNone;
  double polarizationAngleRad_ = 0.0;
};

} // namespace trech
