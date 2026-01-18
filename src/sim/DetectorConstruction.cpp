#include "trech/sim/DetectorConstruction.hpp"

#include "G4Box.hh"
#include "G4LogicalVolume.hh"
#include "G4Material.hh"
#include "G4MaterialPropertiesTable.hh"
#include "G4NistManager.hh"
#include "G4PhysicalConstants.hh"
#include "G4PVPlacement.hh"
#include "G4RotationMatrix.hh"
#include "G4Sphere.hh"
#include "G4SystemOfUnits.hh"
#include "G4Tubs.hh"
#include "G4ThreeVector.hh"

#include <algorithm>
#include <cctype>
#include <sstream>
#include <unordered_map>
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

using MaterialMap = std::unordered_map<std::string, G4Material*>;

MaterialMap buildCustomMaterials(G4NistManager* nist,
                                 const std::vector<MaterialConfig>& configs) {
  MaterialMap out;
  if (!nist) {
    return out;
  }
  for (const auto& cfg : configs) {
    if (cfg.name.empty() || cfg.components.empty() || cfg.densityGcm3 <= 0.0) {
      continue;
    }
    const auto key = toLowerCopy(cfg.name);
    if (out.find(key) != out.end()) {
      continue;
    }
    auto* material = new G4Material(cfg.name, cfg.densityGcm3 * g / cm3,
                                    static_cast<int>(cfg.components.size()));
    for (const auto& component : cfg.components) {
      if (component.material.empty() || component.fraction <= 0.0) {
        continue;
      }
      G4Material* compMat = nullptr;
      const auto compKey = toLowerCopy(component.material);
      auto it = out.find(compKey);
      if (it != out.end()) {
        compMat = it->second;
      }
      if (!compMat) {
        compMat = nist->FindOrBuildMaterial(component.material);
      }
      if (compMat) {
        material->AddMaterial(compMat, component.fraction);
      }
    }
    out[key] = material;
  }
  return out;
}

G4Material* resolveMaterial(G4NistManager* nist, const MaterialMap& custom,
                            const std::string& name, const std::string& fallback) {
  if (!nist) {
    return nullptr;
  }
  if (!name.empty()) {
    const auto key = toLowerCopy(name);
    auto it = custom.find(key);
    if (it != custom.end()) {
      return it->second;
    }
    if (auto* material = nist->FindOrBuildMaterial(name)) {
      return material;
    }
  }
  if (!fallback.empty()) {
    if (auto* material = nist->FindOrBuildMaterial(fallback)) {
      return material;
    }
  }
  return nist->FindOrBuildMaterial("G4_AIR");
}

G4LogicalVolume* resolveParentVolume(
    const VolumeConfig& volume, G4LogicalVolume* world, G4LogicalVolume* medium,
    const std::unordered_map<std::string, G4LogicalVolume*>& volumes) {
  if (!world) {
    return nullptr;
  }
  const auto parent = toLowerCopy(volume.placement.parent);
  if (parent.empty()) {
    return medium ? medium : world;
  }
  if (parent == "world") {
    return world;
  }
  if (parent == "medium" || parent == "mediumbox" || parent == "medium_box") {
    return medium ? medium : world;
  }
  auto it = volumes.find(parent);
  if (it != volumes.end()) {
    return it->second;
  }
  return world;
}

G4VSolid* buildSolidForVolume(const VolumeConfig& volume, const std::string& solidName) {
  const auto type = toLowerCopy(volume.shape.type);
  if (type == "box" || type == "cube") {
    if (volume.shape.sizeXmm <= 0.0 || volume.shape.sizeYmm <= 0.0 ||
        volume.shape.sizeZmm <= 0.0) {
      return nullptr;
    }
    const auto hx = 0.5 * volume.shape.sizeXmm * mm;
    const auto hy = 0.5 * volume.shape.sizeYmm * mm;
    const auto hz = 0.5 * volume.shape.sizeZmm * mm;
    return new G4Box(solidName.c_str(), hx, hy, hz);
  }
  if (type == "tube" || type == "cylinder" || type == "cyl") {
    if (volume.shape.outerRadiusMm <= 0.0 || volume.shape.lengthMm <= 0.0) {
      return nullptr;
    }
    const auto outerRadius = volume.shape.outerRadiusMm * mm;
    const auto innerRadius = std::max(0.0, volume.shape.innerRadiusMm) * mm;
    const auto halfLength = 0.5 * volume.shape.lengthMm * mm;
    if (innerRadius >= outerRadius || halfLength <= 0.0) {
      return nullptr;
    }
    return new G4Tubs(solidName.c_str(), innerRadius, outerRadius, halfLength, 0.0,
                      twopi);
  }
  if (type == "sphere") {
    if (volume.shape.outerRadiusMm <= 0.0) {
      return nullptr;
    }
    const auto radius = volume.shape.outerRadiusMm * mm;
    return new G4Sphere(solidName.c_str(), 0.0, radius, 0.0, twopi, 0.0, pi);
  }
  return nullptr;
}

} // namespace

G4VPhysicalVolume* TrechDetectorConstruction::Construct() {
  auto* nist = G4NistManager::Instance();
  const auto customMaterials = buildCustomMaterials(nist, materials_);
  auto* worldMat = resolveMaterial(nist, customMaterials, cfg_.worldMaterial, "G4_AIR");
  worldMat = cloneMaterialWithEnvironment(worldMat, cfg_, "world");

  const auto half = 0.5 * cfg_.worldSizeMm * mm;
  auto* solidWorld = new G4Box("World", half, half, half);
  auto* logicWorld = new G4LogicalVolume(solidWorld, worldMat, "World");
  auto* physWorld = new G4PVPlacement(nullptr, {}, logicWorld, "World", nullptr, false, 0);

  G4LogicalVolume* logicMedium = nullptr;
  if (cfg_.mediumBoxMm > 0.0) {
    const auto mediumBoxMm = std::min(cfg_.mediumBoxMm, cfg_.worldSizeMm);
    auto* mediumMat =
        resolveMaterial(nist, customMaterials, cfg_.mediumMaterial, cfg_.worldMaterial);
    mediumMat = cloneMaterialWithEnvironment(mediumMat, cfg_, "medium");
    if (optics_.enable) {
      attachOpticalProperties(mediumMat, optics_);
      if (cfg_.worldMaterial != cfg_.mediumMaterial) {
        attachWorldOptics(worldMat);
      }
    }

    const auto halfMedium = 0.5 * mediumBoxMm * mm;
    auto* solidMedium = new G4Box("MediumBox", halfMedium, halfMedium, halfMedium);
    logicMedium = new G4LogicalVolume(solidMedium, mediumMat, "MediumBox");
    new G4PVPlacement(nullptr, {}, logicMedium, "MediumBox", logicWorld, false, 0);
  } else if (optics_.enable && cfg_.worldMaterial == cfg_.mediumMaterial) {
    attachOpticalProperties(worldMat, optics_);
  } else if (optics_.enable) {
    attachWorldOptics(worldMat);
  }

  std::unordered_map<std::string, G4LogicalVolume*> volumes;
  volumes["world"] = logicWorld;
  if (logicMedium) {
    volumes["medium"] = logicMedium;
    volumes["mediumbox"] = logicMedium;
    volumes["medium_box"] = logicMedium;
  }

  for (const auto& volume : geometry_.volumes) {
    if (volume.name.empty()) {
      continue;
    }
    const auto key = toLowerCopy(volume.name);
    if (volumes.find(key) != volumes.end()) {
      continue;
    }
    auto* parent = resolveParentVolume(volume, logicWorld, logicMedium, volumes);
    if (!parent) {
      continue;
    }
    const std::string solidName = volume.name + "_solid";
    auto* solid = buildSolidForVolume(volume, solidName);
    if (!solid) {
      continue;
    }
    const auto fallback =
        (parent == logicMedium && !cfg_.mediumMaterial.empty()) ? cfg_.mediumMaterial
                                                                : cfg_.worldMaterial;
    auto* material = resolveMaterial(nist, customMaterials, volume.material, fallback);
    auto* logic = new G4LogicalVolume(solid, material, volume.name.c_str());

    G4RotationMatrix* rotation = nullptr;
    if (volume.placement.rotationDeg.x != 0.0 || volume.placement.rotationDeg.y != 0.0 ||
        volume.placement.rotationDeg.z != 0.0) {
      rotation = new G4RotationMatrix();
      rotation->rotateX(volume.placement.rotationDeg.x * deg);
      rotation->rotateY(volume.placement.rotationDeg.y * deg);
      rotation->rotateZ(volume.placement.rotationDeg.z * deg);
    }

    const G4ThreeVector position(volume.placement.positionMm.x * mm,
                                 volume.placement.positionMm.y * mm,
                                 volume.placement.positionMm.z * mm);
    new G4PVPlacement(rotation, position, logic, volume.name.c_str(), parent, false, 0);
    volumes[key] = logic;
  }

  return physWorld;
}

} // namespace trech
