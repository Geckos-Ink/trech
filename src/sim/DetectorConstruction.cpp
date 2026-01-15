#include "trech/sim/DetectorConstruction.hpp"

#include "G4Box.hh"
#include "G4LogicalVolume.hh"
#include "G4Material.hh"
#include "G4MaterialPropertiesTable.hh"
#include "G4NistManager.hh"
#include "G4PVPlacement.hh"
#include "G4SystemOfUnits.hh"

#include <algorithm>
#include <sstream>
#include <vector>

namespace trech {
namespace {

G4Material* cloneMaterialWithEnvironment(G4Material* material,
                                         const DetectorConfig& cfg,
                                         const char* tag) {
  if (!material) {
    return material;
  }
  const auto currentTemp = material->GetTemperature();
  const auto currentPressure = material->GetPressure();
  const auto temperature = cfg.temperatureK > 0.0 ? cfg.temperatureK * kelvin : currentTemp;
  const auto pressure = cfg.pressureAtm > 0.0 ? cfg.pressureAtm * atmosphere : currentPressure;
  if (temperature == currentTemp && pressure == currentPressure) {
    return material;
  }

  std::ostringstream name;
  name << material->GetName() << "_" << tag << "_T" << (temperature / kelvin)
       << "_P" << (pressure / atmosphere);
  const auto density = material->GetDensity();
  const auto state = material->GetState();
  const auto nElements = material->GetNumberOfElements();
  auto* cloned = new G4Material(name.str(), density, nElements, state, temperature, pressure);

  const auto* elements = material->GetElementVector();
  const auto* fractions = material->GetFractionVector();
  for (std::size_t i = 0; i < nElements; ++i) {
    cloned->AddElement(const_cast<G4Element*>((*elements)[i]), fractions[i]);
  }

  return cloned;
}

void attachOpticalProperties(G4Material* material, const OpticsConfig& optics) {
  if (!material) {
    return;
  }
  std::vector<G4double> photonEnergy = {2.0 * eV, 3.5 * eV};
  auto* mpt = new G4MaterialPropertiesTable();

  std::vector<G4double> rindex = {optics.refractiveIndex, optics.refractiveIndex};
  mpt->AddProperty("RINDEX", photonEnergy, rindex);

  if (optics.absorptionLengthMm > 0.0) {
    std::vector<G4double> absLength = {
      optics.absorptionLengthMm * mm,
      optics.absorptionLengthMm * mm,
    };
    mpt->AddProperty("ABSLENGTH", photonEnergy, absLength);
  }

  if (optics.scatterLengthMm > 0.0) {
    std::vector<G4double> rayleigh = {
      optics.scatterLengthMm * mm,
      optics.scatterLengthMm * mm,
    };
    mpt->AddProperty("RAYLEIGH", photonEnergy, rayleigh);
  }

  material->SetMaterialPropertiesTable(mpt);
}

void attachWorldOptics(G4Material* material) {
  if (!material) {
    return;
  }
  std::vector<G4double> photonEnergy = {2.0 * eV, 3.5 * eV};
  auto* mpt = new G4MaterialPropertiesTable();
  std::vector<G4double> rindex = {1.0, 1.0};
  mpt->AddProperty("RINDEX", photonEnergy, rindex);
  material->SetMaterialPropertiesTable(mpt);
}

} // namespace

G4VPhysicalVolume* TrechDetectorConstruction::Construct() {
  auto* nist = G4NistManager::Instance();
  auto* worldMat = nist->FindOrBuildMaterial(cfg_.worldMaterial);
  worldMat = cloneMaterialWithEnvironment(worldMat, cfg_, "world");

  const auto half = 0.5 * cfg_.worldSizeMm * mm;
  auto* solidWorld = new G4Box("World", half, half, half);
  auto* logicWorld = new G4LogicalVolume(solidWorld, worldMat, "World");
  auto* physWorld = new G4PVPlacement(nullptr, {}, logicWorld, "World", nullptr, false, 0);

  if (cfg_.waterBoxMm > 0.0) {
    const auto waterBoxMm = std::min(cfg_.waterBoxMm, cfg_.worldSizeMm);
    auto* waterMat = nist->FindOrBuildMaterial("G4_WATER");
    waterMat = cloneMaterialWithEnvironment(waterMat, cfg_, "water");
    if (optics_.enable) {
      attachOpticalProperties(waterMat, optics_);
      if (cfg_.worldMaterial != "G4_WATER") {
        attachWorldOptics(worldMat);
      }
    }

    const auto halfWater = 0.5 * waterBoxMm * mm;
    auto* solidWater = new G4Box("WaterBox", halfWater, halfWater, halfWater);
    auto* logicWater = new G4LogicalVolume(solidWater, waterMat, "WaterBox");
    new G4PVPlacement(nullptr, {}, logicWater, "WaterBox", logicWorld, false, 0);
  } else if (optics_.enable && cfg_.worldMaterial == "G4_WATER") {
    attachOpticalProperties(worldMat, optics_);
  } else if (optics_.enable) {
    attachWorldOptics(worldMat);
  }

  return physWorld;
}

} // namespace trech
