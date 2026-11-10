#include "trech/sim/DetectorConstruction.hpp"
#include "trech/sim/OverlapSampling.hpp"

#include "G4Box.hh"
#include "G4Element.hh"
#include "G4Exception.hh"
#include "G4ios.hh"
#include "G4Isotope.hh"
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
#include "G4VSolid.hh"

#include <algorithm>
#include <array>
#include <cctype>
#include <cmath>
#include <sstream>
#include <stdexcept>
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
    // Resolve every component before constructing anything. A component is
    // either another material (NIST or a previously-built custom mixture) or a
    // chemical element symbol (optionally a specified isotope). Resolving up front means an unresolvable name
    // (e.g. the non-existent `G4_SODIUM_CHLORIDE`) is dropped with a warning
    // rather than leaving a G4Material declared with N components but fewer
    // added — that half-built state is what SIGSEGV'd Geant4's cut/table
    // builders after physics construction. Stoichiometric components instead
    // fail closed: silently dropping an atom would change the declared species.
    struct ResolvedComponent {
      G4Material* material = nullptr;
      G4Element* element = nullptr;
      double fraction = 0.0;
      int atoms = 0;
    };
    std::vector<ResolvedComponent> resolved;
    double fractionSum = 0.0;
    for (const auto& component : cfg.components) {
      if (component.fraction <= 0.0 && component.atoms <= 0) {
        continue;
      }
      ResolvedComponent rc;
      rc.fraction = component.fraction;
      rc.atoms = component.atoms;
      if (!component.element.empty()) {
        rc.element = nist->FindOrBuildElement(component.element);
        if (component.massNumber > 0) {
          if (!rc.element) throw std::invalid_argument("unknown isotope element: " + component.element);
          const int z = rc.element->GetZasInt(), a = component.massNumber;
          const int first = nist->GetNistFirstIsotopeN(z);
          if (a < z || a < first || a >= first + nist->GetNumberOfNistIsotopes(z) ||
              nist->GetIsotopeMass(z, a) <= 0)
            throw std::invalid_argument("isotope absent from Geant4 NIST mass table: " + component.element + "-" + std::to_string(a));
          const auto name = "trech_isotope_" + component.element + "_" + std::to_string(a);
          auto* isotopeElement = G4Element::GetElement(name, false);
          if (!isotopeElement) {
            auto* isotope = new G4Isotope(name, z, a); // mass from Geant4, never A*g/mole
            isotopeElement = new G4Element(name, rc.element->GetSymbol(), 1);
            isotopeElement->AddIsotope(isotope, 1.0);
          }
          rc.element = isotopeElement;
        }
      } else if (!component.material.empty()) {
        const auto compKey = toLowerCopy(component.material);
        auto it = out.find(compKey);
        rc.material = (it != out.end())
                          ? it->second
                          : nist->FindOrBuildMaterial(component.material);
      }
      if (!rc.material && !rc.element) {
        if (component.atoms > 0)
          throw std::invalid_argument("unresolved stoichiometric element: " + component.element);
        const std::string what =
            component.element.empty() ? component.material : component.element;
        G4Exception("TrechDetectorConstruction::buildCustomMaterials",
                    "TrechMaterialComponentUnresolved", JustWarning,
                    ("material '" + cfg.name + "' drops unresolvable component '" +
                     what + "' (no NIST/custom material or element by that name)")
                        .c_str());
        continue;
      }
      resolved.push_back(rc);
      fractionSum += rc.atoms > 0 ? rc.atoms : rc.fraction;
    }
    if (resolved.empty() || fractionSum <= 0.0) {
      G4Exception("TrechDetectorConstruction::buildCustomMaterials",
                  "TrechMaterialNoComponents", JustWarning,
                  ("material '" + cfg.name +
                   "' has no resolvable components; skipping (volumes referencing "
                   "it fall back to NIST/air)")
                      .c_str());
      continue;
    }
    // In mass-fraction mode, fractions must sum to 1.0; renormalize over the
    // components that actually resolved (a no-op when all resolve and the
    // input already sums to one). In stoichiometric mode Geant4 converts the
    // declared integer counts using its own element/isotope masses.
    auto* material = new G4Material(cfg.name, cfg.densityGcm3 * g / cm3,
                                    static_cast<int>(resolved.size()));
    for (const auto& rc : resolved) {
      const double massFraction = rc.fraction / fractionSum;
      if (rc.element) {
        if (rc.atoms > 0) material->AddElement(rc.element, rc.atoms);
        else material->AddElement(rc.element, massFraction);
      } else {
        material->AddMaterial(rc.material, massFraction);
      }
    }
    out[key] = material;
  }
  return out;
}

G4Material* resolveMaterial(G4NistManager* nist, const MaterialMap& custom,
                            const std::string& name, const std::string& fallback,
                            sim::GeometryResolutionReport* report, const char* role,
                            const std::string& volumeName) {
  if (!nist) {
    return nullptr;
  }
  auto lookup = [&](const std::string& candidate) -> G4Material* {
    auto it = custom.find(toLowerCopy(candidate));
    if (it != custom.end()) {
      return it->second;
    }
    return nist->FindOrBuildMaterial(candidate);
  };
  const auto choice = sim::chooseMaterial(name, fallback, "G4_AIR", lookup);
  if (choice.fallback) {
    G4cerr << "TRECH geometry: " << role << (volumeName.empty() ? "" : " '")
           << volumeName << (volumeName.empty() ? "" : "'") << " material '" << name
           << "' is neither declared nor a Geant4 NIST material; using '"
           << (choice.value ? choice.name : std::string("<none>")) << "' instead"
           << G4endl;
    if (report) {
      report->add({"material_fallback", role, volumeName, name,
                   choice.value ? choice.name : std::string(), "unknown_material"});
    }
  }
  return choice.value;
}

G4LogicalVolume* resolveParentVolume(
    const VolumeConfig& volume, G4LogicalVolume* world, G4LogicalVolume* medium,
    const std::unordered_map<std::string, G4LogicalVolume*>& volumes,
    const std::unordered_map<std::string, bool>& declaredLater,
    sim::GeometryResolutionReport* report) {
  if (!world) {
    return nullptr;
  }
  auto recordFallback = [&](const char* reason) {
    G4cerr << "TRECH geometry: volume '" << volume.name << "' parent '"
           << volume.placement.parent << "' (" << reason << "); placed in the world"
           << G4endl;
    if (report) {
      report->add({"parent_fallback", "volume", volume.name, volume.placement.parent,
                   "world", reason});
    }
  };
  const auto parent = toLowerCopy(volume.placement.parent);
  if (parent.empty()) {
    return medium ? medium : world;
  }
  if (parent == "world") {
    return world;
  }
  if (parent == "medium" || parent == "mediumbox" || parent == "medium_box") {
    if (!medium) {
      recordFallback("no_medium_box");
    }
    return medium ? medium : world;
  }
  auto it = volumes.find(parent);
  if (it != volumes.end()) {
    return it->second;
  }
  recordFallback(declaredLater.count(parent) ? "parent_not_built_yet" : "unknown_parent");
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

// A placed physical volume plus the Geant4-free surface description the
// overlap check samples from.
struct PlacedForOverlap {
  G4VPhysicalVolume* physical = nullptr;
  G4LogicalVolume* mother = nullptr;
  sim::OverlapShape shape;
  std::string name;
};

bool overlapShapeFor(const VolumeConfig& volume, sim::OverlapShape& out) {
  const auto type = toLowerCopy(volume.shape.type);
  if (type == "box" || type == "cube") {
    out.kind = sim::OverlapShape::Kind::Box;
    out.hx = 0.5 * volume.shape.sizeXmm;
    out.hy = 0.5 * volume.shape.sizeYmm;
    out.hz = 0.5 * volume.shape.sizeZmm;
    return true;
  }
  if (type == "tube" || type == "cylinder" || type == "cyl") {
    out.kind = sim::OverlapShape::Kind::Tube;
    out.rmin = std::max(0.0, volume.shape.innerRadiusMm);
    out.rmax = volume.shape.outerRadiusMm;
    out.hz = 0.5 * volume.shape.lengthMm;
    return true;
  }
  if (type == "sphere") {
    out.kind = sim::OverlapShape::Kind::Sphere;
    out.rmax = volume.shape.outerRadiusMm;
    return true;
  }
  return false;
}

double boundingRadiusMm(const sim::OverlapShape& s) {
  switch (s.kind) {
  case sim::OverlapShape::Kind::Box:
    return std::sqrt(s.hx * s.hx + s.hy * s.hy + s.hz * s.hz);
  case sim::OverlapShape::Kind::Tube:
    return std::sqrt(s.rmax * s.rmax + s.hz * s.hz);
  case sim::OverlapShape::Kind::Sphere:
    return s.rmax;
  }
  return 0.0;
}

// Geant4's own geometry decides every containment question: sampled surface
// points are moved through each placement's real transform and tested with
// G4VSolid::Inside, and penetration depths are the solids' DistanceToIn /
// DistanceToOut safeties (lower bounds, as in G4PVPlacement::CheckOverlaps).
void runOverlapCheck(const std::vector<PlacedForOverlap>& placed,
                     const GeometryOverlapCheckConfig& cfg,
                     sim::GeometryResolutionReport* report) {
  if (!report || !cfg.enable) {
    return;
  }
  auto& summary = report->overlapCheck;
  summary.ran = true;
  summary.samplesPerVolume = cfg.samplesPerVolume;
  summary.toleranceMm = cfg.toleranceMm;
  summary.volumesChecked = static_cast<int>(placed.size());
  summary.pairsChecked = 0;

  // Surface points of every placed volume in its mother's frame.
  std::vector<std::vector<G4ThreeVector>> motherFramePoints(placed.size());
  for (std::size_t i = 0; i < placed.size(); ++i) {
    const auto& p = placed[i];
    const auto rotation = p.physical->GetObjectRotationValue();
    const auto translation = p.physical->GetTranslation();
    const auto local =
        sim::sampleOverlapSurface(p.shape, cfg.samplesPerVolume, sim::overlapSeedFor(p.name));
    auto& out = motherFramePoints[i];
    out.reserve(local.size());
    for (const auto& q : local) {
      out.push_back(rotation * G4ThreeVector(q[0] * mm, q[1] * mm, q[2] * mm) + translation);
    }
  }

  const double tolerance = cfg.toleranceMm * mm;
  for (std::size_t i = 0; i < placed.size(); ++i) {
    auto* motherSolid = placed[i].mother->GetSolid();
    double worst = 0.0;
    for (const auto& point : motherFramePoints[i]) {
      if (motherSolid->Inside(point) == kOutside) {
        worst = std::max(worst, motherSolid->DistanceToIn(point));
      }
    }
    if (worst > tolerance) {
      const auto depthMm = worst / mm;
      G4cerr << "TRECH geometry: volume '" << placed[i].name << "' protrudes from its mother '"
             << placed[i].mother->GetName() << "' by at least " << depthMm
             << " mm (sampled surface points)" << G4endl;
      report->add({"overlap", "volume", placed[i].name, placed[i].mother->GetName(), "",
                   "protrudes_parent", depthMm});
    }
  }

  // Points of `a` (already in the shared mother frame) inside sibling `b`.
  auto depthInside = [&](std::size_t a, std::size_t b) {
    auto* solid = placed[b].physical->GetLogicalVolume()->GetSolid();
    const auto inverse = placed[b].physical->GetObjectRotationValue().inverse();
    const auto translation = placed[b].physical->GetTranslation();
    double worst = 0.0;
    for (const auto& point : motherFramePoints[a]) {
      const auto local = inverse * (point - translation);
      if (solid->Inside(local) == kInside) {
        worst = std::max(worst, solid->DistanceToOut(local));
      }
    }
    return worst;
  };
  for (std::size_t i = 0; i < placed.size(); ++i) {
    for (std::size_t j = i + 1; j < placed.size(); ++j) {
      if (placed[i].mother != placed[j].mother) {
        continue;
      }
      ++summary.pairsChecked;
      const auto separation =
          (placed[i].physical->GetTranslation() - placed[j].physical->GetTranslation()).mag();
      if (separation > (boundingRadiusMm(placed[i].shape) + boundingRadiusMm(placed[j].shape)) * mm) {
        continue; // bounding spheres are disjoint: no overlap is possible
      }
      const double worst = std::max(depthInside(i, j), depthInside(j, i));
      if (worst > tolerance) {
        const auto depthMm = worst / mm;
        G4cerr << "TRECH geometry: volumes '" << placed[i].name << "' and '" << placed[j].name
               << "' overlap by at least " << depthMm << " mm (sampled surface points)"
               << G4endl;
        report->add({"overlap", "volume", placed[i].name, placed[j].name, "",
                     "overlaps_sibling", depthMm});
      }
    }
  }
}

} // namespace

G4VPhysicalVolume* TrechDetectorConstruction::Construct() {
  auto* nist = G4NistManager::Instance();
  const auto customMaterials = buildCustomMaterials(nist, materials_);
  sim::GeometryResolutionReport* report = resolution_.get();
  if (report) {
    report->issues.clear();
    report->overlapCheck = {};
  }
  auto* worldMat = resolveMaterial(nist, customMaterials, cfg_.worldMaterial, "G4_AIR",
                                   report, "world", "");
  worldMat = cloneMaterialWithEnvironment(worldMat, cfg_, "world");

  const auto half = 0.5 * cfg_.worldSizeMm * mm;
  auto* solidWorld = new G4Box("World", half, half, half);
  auto* logicWorld = new G4LogicalVolume(solidWorld, worldMat, "World");
  auto* physWorld = new G4PVPlacement(nullptr, {}, logicWorld, "World", nullptr, false, 0);
  std::vector<PlacedForOverlap> placedForOverlap;

  G4LogicalVolume* logicMedium = nullptr;
  if (cfg_.mediumBoxMm > 0.0) {
    const auto mediumBoxMm = std::min(cfg_.mediumBoxMm, cfg_.worldSizeMm);
    auto* mediumMat =
        resolveMaterial(nist, customMaterials, cfg_.mediumMaterial, cfg_.worldMaterial,
                        report, "medium", "");
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
    auto* physMedium =
        new G4PVPlacement(nullptr, {}, logicMedium, "MediumBox", logicWorld, false, 0);
    sim::OverlapShape mediumShape;
    mediumShape.hx = mediumShape.hy = mediumShape.hz = halfMedium / mm;
    placedForOverlap.push_back({physMedium, logicWorld, mediumShape, "MediumBox"});
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

  auto recordSkip = [&](const VolumeConfig& volume, const char* reason) {
    G4cerr << "TRECH geometry: volume '" << volume.name << "' not built (" << reason << ")"
           << G4endl;
    if (report) {
      report->add({"volume_skipped", "volume", volume.name, volume.shape.type, "", reason});
    }
  };
  // Names still to be built, so a forward parent reference is reported as an
  // ordering problem rather than an unknown name.
  std::unordered_map<std::string, bool> declaredLater;
  for (const auto& volume : geometry_.volumes) {
    if (!volume.name.empty()) {
      declaredLater[toLowerCopy(volume.name)] = true;
    }
  }
  for (const auto& volume : geometry_.volumes) {
    if (volume.name.empty()) {
      continue;
    }
    const auto key = toLowerCopy(volume.name);
    if (volumes.find(key) != volumes.end()) {
      recordSkip(volume, "duplicate_name");
      continue;
    }
    declaredLater.erase(key);
    auto* parent =
        resolveParentVolume(volume, logicWorld, logicMedium, volumes, declaredLater, report);
    if (!parent) {
      continue;
    }
    const std::string solidName = volume.name + "_solid";
    auto* solid = buildSolidForVolume(volume, solidName);
    if (!solid) {
      recordSkip(volume, "invalid_shape");
      continue;
    }
    const auto fallback =
        (parent == logicMedium && !cfg_.mediumMaterial.empty()) ? cfg_.mediumMaterial
                                                                : cfg_.worldMaterial;
    auto* material = resolveMaterial(nist, customMaterials, volume.material, fallback, report,
                                     "volume", volume.name);
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
    auto* physical =
        new G4PVPlacement(rotation, position, logic, volume.name.c_str(), parent, false, 0);
    volumes[key] = logic;
    sim::OverlapShape shape;
    if (overlapShapeFor(volume, shape)) {
      placedForOverlap.push_back({physical, parent, shape, volume.name});
    }
  }

  runOverlapCheck(placedForOverlap, geometry_.overlapCheck, report);
  return physWorld;
}

} // namespace trech
