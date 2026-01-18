#pragma once

#include "trech/core/Config.hpp"
#include "G4VUserDetectorConstruction.hh"

class G4VPhysicalVolume;

namespace trech {

class TrechDetectorConstruction : public G4VUserDetectorConstruction {
public:
  TrechDetectorConstruction(const trech::DetectorConfig& cfg,
                            const trech::OpticsConfig& optics,
                            const trech::GeometryConfig& geometry,
                            const std::vector<trech::MaterialConfig>& materials)
      : cfg_(cfg), optics_(optics), geometry_(geometry), materials_(materials) {}
  G4VPhysicalVolume* Construct() override;

private:
  trech::DetectorConfig cfg_;
  trech::OpticsConfig optics_;
  trech::GeometryConfig geometry_;
  std::vector<trech::MaterialConfig> materials_;
};

} // namespace trech
