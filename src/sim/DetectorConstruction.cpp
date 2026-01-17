#include "trech/sim/DetectorConstruction.hpp"

#include "G4Box.hh"
#include "G4LogicalVolume.hh"
#include "G4Material.hh"
#include "G4MaterialPropertiesTable.hh"
#include "G4NistManager.hh"
#include "G4PhysicalConstants.hh"
#include "G4PVPlacement.hh"
#include "G4SystemOfUnits.hh"
#include "G4Tubs.hh"

#include <algorithm>
#include <cctype>
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
  struct OpticsSample {
    G4double energy;
    G4double rindex;
    G4double absLength;
    G4double rayleigh;
  };

  const auto fallbackRindex = optics.refractiveIndex > 0.0 ? optics.refractiveIndex : 1.0;
  const auto fallbackAbs =
      optics.absorptionLengthMm > 0.0 ? optics.absorptionLengthMm : 0.0;
  const auto fallbackScatter = optics.scatterLengthMm > 0.0 ? optics.scatterLengthMm : 0.0;
  std::vector<OpticsSample> samples;
  if (!optics.spectrum.empty()) {
    samples.reserve(optics.spectrum.size());
    for (const auto& point : optics.spectrum) {
      G4double energy = 0.0;
      if (point.energyEv > 0.0) {
        energy = point.energyEv * eV;
      } else if (point.wavelengthNm > 0.0) {
        energy = (h_Planck * c_light) / (point.wavelengthNm * nm);
      }
      if (energy <= 0.0) {
        continue;
      }
      const auto rindex =
          point.refractiveIndex > 0.0 ? point.refractiveIndex : fallbackRindex;
      const auto absLength =
          (point.absorptionLengthMm > 0.0 ? point.absorptionLengthMm : fallbackAbs) * mm;
      const auto rayleigh =
          (point.scatterLengthMm > 0.0 ? point.scatterLengthMm : fallbackScatter) * mm;
      samples.push_back({energy, rindex, absLength, rayleigh});
    }
  }

  if (samples.size() == 1) {
    const auto sample = samples.front();
    samples.clear();
    samples.push_back({2.0 * eV, sample.rindex, sample.absLength, sample.rayleigh});
    samples.push_back({3.5 * eV, sample.rindex, sample.absLength, sample.rayleigh});
  } else if (samples.empty()) {
    samples.push_back({2.0 * eV, fallbackRindex, fallbackAbs * mm, fallbackScatter * mm});
    samples.push_back({3.5 * eV, fallbackRindex, fallbackAbs * mm, fallbackScatter * mm});
  }

  std::sort(samples.begin(), samples.end(),
            [](const OpticsSample& left, const OpticsSample& right) {
              return left.energy < right.energy;
            });

  std::vector<G4double> photonEnergy;
  std::vector<G4double> rindex;
  std::vector<G4double> absLength;
  std::vector<G4double> rayleigh;
  photonEnergy.reserve(samples.size());
  rindex.reserve(samples.size());
  absLength.reserve(samples.size());
  rayleigh.reserve(samples.size());
  bool hasAbs = false;
  bool hasRayleigh = false;

  for (const auto& sample : samples) {
    photonEnergy.push_back(sample.energy);
    rindex.push_back(sample.rindex);
    absLength.push_back(sample.absLength);
    rayleigh.push_back(sample.rayleigh);
    if (sample.absLength > 0.0) {
      hasAbs = true;
    }
    if (sample.rayleigh > 0.0) {
      hasRayleigh = true;
    }
  }

  auto* mpt = new G4MaterialPropertiesTable();
  mpt->AddProperty("RINDEX", photonEnergy, rindex);

  if (hasAbs) {
    mpt->AddProperty("ABSLENGTH", photonEnergy, absLength);
  }

  if (hasRayleigh) {
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

std::string toLowerCopy(const std::string& input) {
  std::string output = input;
  std::transform(output.begin(), output.end(), output.begin(), [](unsigned char ch) {
    return static_cast<char>(std::tolower(ch));
  });
  return output;
}

G4Material* resolveCntMaterial(G4NistManager* nist, const std::string& name) {
  if (!nist) {
    return nullptr;
  }
  if (name.empty()) {
    return nist->FindOrBuildMaterial("G4_C");
  }
  const auto lower = toLowerCopy(name);
  if (lower == "carbon" || lower == "graphite" || lower == "c") {
    return nist->FindOrBuildMaterial("G4_C");
  }
  auto* material = nist->FindOrBuildMaterial(name);
  if (!material) {
    material = nist->FindOrBuildMaterial("G4_C");
  }
  return material;
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

  G4LogicalVolume* logicWater = nullptr;
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
    logicWater = new G4LogicalVolume(solidWater, waterMat, "WaterBox");
    new G4PVPlacement(nullptr, {}, logicWater, "WaterBox", logicWorld, false, 0);
  } else if (optics_.enable && cfg_.worldMaterial == "G4_WATER") {
    attachOpticalProperties(worldMat, optics_);
  } else if (optics_.enable) {
    attachWorldOptics(worldMat);
  }

  if (cnt_.enable) {
    const auto diameter = cnt_.diameterNm * nm;
    const auto length = cnt_.lengthNm * nm;
    const auto wallCount = std::max(1, cnt_.wallCount);
    const auto wallThickness = 0.34 * nm * wallCount;
    if (diameter > 0.0 && length > 0.0) {
      const auto outerRadius = 0.5 * diameter;
      const auto innerRadius = std::max(0.0, outerRadius - wallThickness);
      const auto halfLength = 0.5 * length;
      if (outerRadius > 0.0 && halfLength > 0.0) {
        auto* cntMat = resolveCntMaterial(nist, cnt_.material);
        auto* solidCnt = new G4Tubs("CNT", innerRadius, outerRadius, halfLength, 0.0, twopi);
        auto* logicCnt = new G4LogicalVolume(solidCnt, cntMat, "CNT");
        auto* parent = logicWorld;
        if (logicWater && cnt_.placeInWater) {
          parent = logicWater;
        }
        new G4PVPlacement(nullptr, {}, logicCnt, "CNT", parent, false, 0);
      }
    }
  }

  return physWorld;
}

} // namespace trech
