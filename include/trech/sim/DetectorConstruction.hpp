#pragma once

#include "trech/core/Config.hpp"
#include "G4VUserDetectorConstruction.hh"

class G4VPhysicalVolume;

namespace trech {

class TrechDetectorConstruction : public G4VUserDetectorConstruction {
public:
  TrechDetectorConstruction(const trech::DetectorConfig& cfg, const trech::OpticsConfig& optics)
      : cfg_(cfg), optics_(optics) {}
  G4VPhysicalVolume* Construct() override;

private:
  trech::DetectorConfig cfg_;
  trech::OpticsConfig optics_;
};

} // namespace trech
