#pragma once

#include "trech/core/Config.hpp"
#include "G4VUserDetectorConstruction.hh"

class G4VPhysicalVolume;

namespace trech {

class TrechDetectorConstruction : public G4VUserDetectorConstruction {
public:
  explicit TrechDetectorConstruction(const trech::DetectorConfig& cfg) : cfg_(cfg) {}
  G4VPhysicalVolume* Construct() override;

private:
  trech::DetectorConfig cfg_;
};

} // namespace trech
