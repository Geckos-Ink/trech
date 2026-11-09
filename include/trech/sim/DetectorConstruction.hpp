#pragma once

#include "trech/core/Config.hpp"
#include "trech/sim/GeometryResolution.hpp"
#include "G4VUserDetectorConstruction.hh"

#include <memory>

class G4VPhysicalVolume;

namespace trech {

class TrechDetectorConstruction : public G4VUserDetectorConstruction {
public:
  TrechDetectorConstruction(const trech::DetectorConfig& cfg,
                            const trech::OpticsConfig& optics,
                            const trech::GeometryConfig& geometry,
                            const std::vector<trech::MaterialConfig>& materials,
                            std::shared_ptr<sim::GeometryResolutionReport> resolution = nullptr)
      : cfg_(cfg), optics_(optics), geometry_(geometry), materials_(materials),
        resolution_(std::move(resolution)) {}
  G4VPhysicalVolume* Construct() override;

private:
  trech::DetectorConfig cfg_;
  trech::OpticsConfig optics_;
  trech::GeometryConfig geometry_;
  std::vector<trech::MaterialConfig> materials_;
  // Shared with RunAction (provenance); refilled on every Construct().
  std::shared_ptr<sim::GeometryResolutionReport> resolution_;
};

} // namespace trech
