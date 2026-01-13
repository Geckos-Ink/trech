#include "trech/sim/DetectorConstruction.hpp"

#include "G4Box.hh"
#include "G4LogicalVolume.hh"
#include "G4NistManager.hh"
#include "G4PVPlacement.hh"
#include "G4SystemOfUnits.hh"

namespace trech {

G4VPhysicalVolume* TrechDetectorConstruction::Construct() {
  auto* nist = G4NistManager::Instance();
  auto* mat = nist->FindOrBuildMaterial(cfg_.worldMaterial);

  const auto half = 0.5 * cfg_.worldSizeMm * mm;
  auto* solidWorld = new G4Box("World", half, half, half);
  auto* logicWorld = new G4LogicalVolume(solidWorld, mat, "World");
  auto* physWorld = new G4PVPlacement(nullptr, {}, logicWorld, "World", nullptr, false, 0);

  return physWorld;
}

} // namespace trech
