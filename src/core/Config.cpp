#include "trech/core/Config.hpp"

#include <nlohmann/json.hpp>

#include <algorithm>
#include <cctype>

namespace trech {
namespace {

void appendStringListFromJson(const nlohmann::json& j, std::vector<std::string>& out) {
  if (j.is_string()) {
    out.push_back(j.get<std::string>());
    return;
  }
  if (!j.is_array()) {
    return;
  }
  for (const auto& entry : j) {
    if (entry.is_string()) {
      out.push_back(entry.get<std::string>());
    }
  }
}

DetectorConfig detectorFromJson(const nlohmann::json& j, const DetectorConfig& defaults) {
  DetectorConfig cfg = defaults;
  if (!j.is_object()) {
    return cfg;
  }
  cfg.worldSizeMm = j.value("worldSizeMm", cfg.worldSizeMm);
  cfg.worldMaterial = j.value("worldMaterial", cfg.worldMaterial);
  cfg.mediumBoxMm = j.value("mediumBoxMm", cfg.mediumBoxMm);
  cfg.mediumMaterial = j.value("mediumMaterial", cfg.mediumMaterial);
  if (j.contains("waterBoxMm")) {
    cfg.mediumBoxMm = j.value("waterBoxMm", cfg.mediumBoxMm);
  }
  if (j.contains("waterMaterial")) {
    cfg.mediumMaterial = j.value("waterMaterial", cfg.mediumMaterial);
  }
  cfg.temperatureK = j.value("temperatureK", cfg.temperatureK);
  cfg.pressureAtm = j.value("pressureAtm", cfg.pressureAtm);
  return cfg;
}

BeamConfig beamFromJson(const nlohmann::json& j, const BeamConfig& defaults) {
  BeamConfig cfg = defaults;
  if (!j.is_object()) {
    return cfg;
  }
  cfg.name = j.value("name", cfg.name);
  cfg.particle = j.value("particle", cfg.particle);
  cfg.energyMeV = j.value("energyMeV", cfg.energyMeV);
  if (j.contains("direction")) {
    const auto& dir = j.at("direction");
    if (dir.is_array() && dir.size() >= 3) {
      cfg.directionX = dir.at(0).get<double>();
      cfg.directionY = dir.at(1).get<double>();
      cfg.directionZ = dir.at(2).get<double>();
    } else if (dir.is_object()) {
      cfg.directionX = dir.value("x", cfg.directionX);
      cfg.directionY = dir.value("y", cfg.directionY);
      cfg.directionZ = dir.value("z", cfg.directionZ);
    }
  }
  if (j.contains("originMm")) {
    const auto& org = j.at("originMm");
    if (org.is_array() && org.size() >= 3) {
      cfg.originXMm = org.at(0).get<double>();
      cfg.originYMm = org.at(1).get<double>();
      cfg.originZMm = org.at(2).get<double>();
    } else if (org.is_object()) {
      cfg.originXMm = org.value("x", cfg.originXMm);
      cfg.originYMm = org.value("y", cfg.originYMm);
      cfg.originZMm = org.value("z", cfg.originZMm);
    }
  }
  // Source variety: accept flat keys or a nested `spread` object (the latter
  // reads naturally in JS scenarios). Flat keys win if both are present.
  if (j.contains("spread") && j.at("spread").is_object()) {
    const auto& s = j.at("spread");
    cfg.spotRadiusMm = s.value("spotRadiusMm", cfg.spotRadiusMm);
    cfg.divergenceDeg = s.value("divergenceDeg", cfg.divergenceDeg);
    cfg.energySpreadFractional =
        s.value("energySpreadFractional", cfg.energySpreadFractional);
  }
  cfg.spotRadiusMm = j.value("spotRadiusMm", cfg.spotRadiusMm);
  cfg.divergenceDeg = j.value("divergenceDeg", cfg.divergenceDeg);
  cfg.energySpreadFractional =
      j.value("energySpreadFractional", cfg.energySpreadFractional);
  // Polarization: accept a bare mode string ("linear") or an object
  // ({mode, angleDeg}); a flat polarizationAngleDeg wins if also present.
  if (j.contains("polarization")) {
    const auto& p = j.at("polarization");
    if (p.is_string()) {
      cfg.polarization = p.get<std::string>();
    } else if (p.is_object()) {
      cfg.polarization = p.value("mode", cfg.polarization);
      cfg.polarizationAngleDeg = p.value("angleDeg", cfg.polarizationAngleDeg);
    }
  }
  cfg.polarizationAngleDeg =
      j.value("polarizationAngleDeg", cfg.polarizationAngleDeg);
  cfg.active = j.value("active", cfg.active);
  return cfg;
}

void appendBeamsFromJson(const nlohmann::json& j, std::vector<BeamConfig>& out) {
  if (j.is_array()) {
    for (const auto& entry : j) {
      if (entry.is_object()) {
        out.push_back(beamFromJson(entry, BeamConfig{}));
      }
    }
  } else if (j.is_object()) {
    out.push_back(beamFromJson(j, BeamConfig{}));
  }
}

BeamConfig selectPrimaryBeam(const std::vector<BeamConfig>& beams,
                             const BeamConfig& fallback) {
  for (const auto& beam : beams) {
    if (beam.active) {
      return beam;
    }
  }
  if (!beams.empty()) {
    return beams.front();
  }
  return fallback;
}

// Serialize the optional origin/variety fields only when they differ from the
// historical defaults. This keeps the canonical config (and its hash) byte
// identical for scenarios that don't use them, so existing provenance and the
// determinism-replay baselines are unaffected.
void writeBeamExtras(nlohmann::json& entry, const BeamConfig& beam) {
  if (beam.originXMm != 0.0 || beam.originYMm != 0.0 || beam.originZMm != 0.0) {
    entry["originMm"] = {beam.originXMm, beam.originYMm, beam.originZMm};
  }
  if (beam.spotRadiusMm != 0.0) {
    entry["spotRadiusMm"] = beam.spotRadiusMm;
  }
  if (beam.divergenceDeg != 0.0) {
    entry["divergenceDeg"] = beam.divergenceDeg;
  }
  if (beam.energySpreadFractional != 0.0) {
    entry["energySpreadFractional"] = beam.energySpreadFractional;
  }
  // Default "" (unpolarized sampling) is left unserialized so optical scenarios
  // that don't set polarization keep their exact config hash even though the
  // engine now samples polarization explicitly.
  if (!beam.polarization.empty()) {
    entry["polarization"] = beam.polarization;
  }
  if (beam.polarizationAngleDeg != 0.0) {
    entry["polarizationAngleDeg"] = beam.polarizationAngleDeg;
  }
}

RunConfig runFromJson(const nlohmann::json& j, const RunConfig& defaults) {
  RunConfig cfg = defaults;
  if (!j.is_object()) {
    return cfg;
  }
  cfg.nEvents = j.value("nEvents", cfg.nEvents);
  cfg.seed = j.value("seed", cfg.seed);
  return cfg;
}

std::string normalizeDeterminismMode(std::string mode) {
  std::transform(mode.begin(), mode.end(), mode.begin(),
                 [](unsigned char ch) { return static_cast<char>(std::tolower(ch)); });
  if (mode == "predictive") {
    return mode;
  }
  return "strict";
}

DeterminismConfig determinismFromJson(const nlohmann::json& j,
                                      const DeterminismConfig& defaults) {
  DeterminismConfig cfg = defaults;
  if (j.is_string()) {
    cfg.mode = normalizeDeterminismMode(j.get<std::string>());
    return cfg;
  }
  if (!j.is_object()) {
    return cfg;
  }
  cfg.mode = normalizeDeterminismMode(j.value("mode", cfg.mode));
  if (j.contains("predictive") && j.at("predictive").is_boolean()) {
    cfg.mode = j.at("predictive").get<bool>() ? "predictive" : "strict";
  }
  return cfg;
}

SystemConfig systemFromJson(const nlohmann::json& j, const SystemConfig& defaults) {
  SystemConfig cfg = defaults;
  if (!j.is_object()) {
    return cfg;
  }
  cfg.enable = j.value("enable", cfg.enable);
  cfg.mode = j.value("mode", cfg.mode);
  cfg.frame = j.value("frame", cfg.frame);
  cfg.ensemble = j.value("ensemble", cfg.ensemble);
  cfg.volumeMm3 = j.value("volumeMm3", cfg.volumeMm3);
  return cfg;
}

OpticsConfig opticsFromJson(const nlohmann::json& j, const OpticsConfig& defaults) {
  OpticsConfig cfg = defaults;
  if (!j.is_object()) {
    return cfg;
  }
  cfg.enable = j.value("enable", cfg.enable);
  cfg.refractiveIndex = j.value("refractiveIndex", cfg.refractiveIndex);
  cfg.absorptionLengthMm = j.value("absorptionLengthMm", cfg.absorptionLengthMm);
  cfg.scatterLengthMm = j.value("scatterLengthMm", cfg.scatterLengthMm);
  if (j.contains("spectrum")) {
    cfg.spectrum.clear();
    const auto appendSpectrumPoint = [&](const nlohmann::json& entry) {
      if (!entry.is_array() && !entry.is_object()) {
        return;
      }
      OpticsSpectrumPoint point;
      if (entry.is_array()) {
        if (!entry.empty()) {
          point.energyEv = entry.at(0).get<double>();
        }
        if (entry.size() > 1) {
          point.refractiveIndex = entry.at(1).get<double>();
        }
        if (entry.size() > 2) {
          point.absorptionLengthMm = entry.at(2).get<double>();
        }
        if (entry.size() > 3) {
          point.scatterLengthMm = entry.at(3).get<double>();
        }
      } else {
        point.energyEv = entry.value("energyEv", point.energyEv);
        point.wavelengthNm = entry.value("wavelengthNm", point.wavelengthNm);
        point.refractiveIndex = entry.value("refractiveIndex", point.refractiveIndex);
        point.absorptionLengthMm =
            entry.value("absorptionLengthMm", point.absorptionLengthMm);
        point.scatterLengthMm = entry.value("scatterLengthMm", point.scatterLengthMm);
      }
      if (point.energyEv > 0.0 || point.wavelengthNm > 0.0) {
        cfg.spectrum.push_back(point);
      }
    };
    const auto& spectrum = j.at("spectrum");
    if (spectrum.is_array()) {
      for (const auto& entry : spectrum) {
        appendSpectrumPoint(entry);
      }
    } else {
      appendSpectrumPoint(spectrum);
    }
  }
  return cfg;
}

OpticsValidationReferenceConfig opticsValidationReferenceFromJson(
    const nlohmann::json& j, const OpticsValidationReferenceConfig& defaults) {
  OpticsValidationReferenceConfig cfg = defaults;
  if (!j.is_object()) {
    return cfg;
  }
  cfg.material = j.value("material", cfg.material);
  cfg.energyEv = j.value("energyEv", cfg.energyEv);
  cfg.refractiveIndex = j.value("refractiveIndex", cfg.refractiveIndex);
  cfg.absorptionLengthMm = j.value("absorptionLengthMm", cfg.absorptionLengthMm);
  cfg.scatterLengthMm = j.value("scatterLengthMm", cfg.scatterLengthMm);
  cfg.source = j.value("source", cfg.source);
  return cfg;
}

OpticsDeriveConfig opticsDeriveFromJson(const nlohmann::json& j,
                                        const OpticsDeriveConfig& defaults) {
  OpticsDeriveConfig cfg = defaults;
  if (j.is_boolean()) {
    cfg.enable = j.get<bool>();
    return cfg;
  }
  if (j.is_string()) {
    cfg.enable = true;
    cfg.mode = j.get<std::string>();
    return cfg;
  }
  if (!j.is_object()) {
    return cfg;
  }
  cfg.enable = j.value("enable", cfg.enable);
  cfg.mode = j.value("mode", cfg.mode);
  cfg.energyMinEv = j.value("energyMinEv", cfg.energyMinEv);
  cfg.energyMaxEv = j.value("energyMaxEv", cfg.energyMaxEv);
  cfg.nEnergyBins = j.value("nEnergyBins", cfg.nEnergyBins);
  cfg.kkIntegrationMinEv = j.value("kkIntegrationMinEv", cfg.kkIntegrationMinEv);
  cfg.kkIntegrationMaxEv = j.value("kkIntegrationMaxEv", cfg.kkIntegrationMaxEv);
  cfg.kkIntegrationBins = j.value("kkIntegrationBins", cfg.kkIntegrationBins);
  cfg.modelValidMinEv = j.value("modelValidMinEv", cfg.modelValidMinEv);
  cfg.valenceOscillator = j.value("valenceOscillator", cfg.valenceOscillator);
  cfg.valenceResonanceEv = j.value("valenceResonanceEv", cfg.valenceResonanceEv);
  cfg.surrogateModelPath = j.value("surrogateModelPath", cfg.surrogateModelPath);
  cfg.writeSpectrum = j.value("writeSpectrum", cfg.writeSpectrum);
  if (j.contains("validate") && j.at("validate").is_object()) {
    const auto& validate = j.at("validate");
    cfg.validateAgainstReferences = validate.value("enable", cfg.validateAgainstReferences);
    if (validate.contains("references")) {
      cfg.validationReferences.clear();
      const auto& refs = validate.at("references");
      const auto appendOne = [&](const nlohmann::json& entry) {
        if (entry.is_object()) {
          cfg.validationReferences.push_back(
              opticsValidationReferenceFromJson(entry, OpticsValidationReferenceConfig{}));
        }
      };
      if (refs.is_array()) {
        for (const auto& entry : refs) {
          appendOne(entry);
        }
      } else {
        appendOne(refs);
      }
    }
  }
  if (cfg.nEnergyBins < 2) {
    cfg.nEnergyBins = 2;
  }
  if (cfg.kkIntegrationBins < 16) {
    cfg.kkIntegrationBins = 16;
  }
  return cfg;
}

VizConfig vizFromJson(const nlohmann::json& j, const VizConfig& defaults) {
  VizConfig cfg = defaults;
  if (j.is_boolean()) {
    cfg.enable = j.get<bool>();
    return cfg;
  }
  if (!j.is_object()) {
    return cfg;
  }
  cfg.enable = j.value("enable", cfg.enable);
  cfg.scenePath = j.value("scenePath", cfg.scenePath);
  cfg.trajectoriesPath = j.value("trajectoriesPath", cfg.trajectoriesPath);
  cfg.maxTrajectories = j.value("maxTrajectories", cfg.maxTrajectories);
  cfg.sampleEveryNth = j.value("sampleEveryNth", cfg.sampleEveryNth);
  cfg.maxSegmentsPerTrajectory =
      j.value("maxSegmentsPerTrajectory", cfg.maxSegmentsPerTrajectory);
  cfg.includeNonOptical = j.value("includeNonOptical", cfg.includeNonOptical);
  cfg.recordVertices = j.value("recordVertices", cfg.recordVertices);
  if (cfg.sampleEveryNth < 1) {
    cfg.sampleEveryNth = 1;
  }
  if (cfg.maxTrajectories < 0) {
    cfg.maxTrajectories = 0;
  }
  if (cfg.maxSegmentsPerTrajectory < 1) {
    cfg.maxSegmentsPerTrajectory = 1;
  }
  return cfg;
}

ChemistryConfig chemistryFromJson(const nlohmann::json& j, const ChemistryConfig& defaults) {
  ChemistryConfig cfg = defaults;
  if (!j.is_object()) {
    return cfg;
  }
  cfg.enable = j.value("enable", cfg.enable);
  cfg.model = j.value("model", cfg.model);
  cfg.solver = j.value("solver", cfg.solver);
  return cfg;
}

NuclearReactionParticipantConfig nuclearReactionParticipantFromJson(
    const nlohmann::json& j, const NuclearReactionParticipantConfig& defaults) {
  NuclearReactionParticipantConfig cfg = defaults;
  if (!j.is_object()) {
    return cfg;
  }
  cfg.particle = j.value("particle", cfg.particle);
  cfg.z = j.value("z", cfg.z);
  cfg.a = j.value("a", cfg.a);
  return cfg;
}

void appendNuclearReactionParticipantsFromJson(
    const nlohmann::json& j, std::vector<NuclearReactionParticipantConfig>& out) {
  if (j.is_array()) {
    for (const auto& entry : j) {
      if (entry.is_object()) {
        out.push_back(
            nuclearReactionParticipantFromJson(entry, NuclearReactionParticipantConfig{}));
      }
    }
    return;
  }
  if (j.is_object()) {
    out.push_back(nuclearReactionParticipantFromJson(j, NuclearReactionParticipantConfig{}));
  }
}

NuclearSpeciesConfig nuclearSpeciesFromJson(const nlohmann::json& j,
                                            const NuclearSpeciesConfig& defaults) {
  NuclearSpeciesConfig cfg = defaults;
  if (!j.is_object()) {
    return cfg;
  }
  cfg.symbol = j.value("symbol", cfg.symbol);
  cfg.material = j.value("material", cfg.material);
  cfg.z = j.value("z", cfg.z);
  cfg.a = j.value("a", cfg.a);
  cfg.phase = j.value("phase", cfg.phase);
  cfg.densityGcm3 = j.value("densityGcm3", cfg.densityGcm3);
  return cfg;
}

NuclearReactionConfig nuclearReactionFromJson(const nlohmann::json& j,
                                              const NuclearReactionConfig& defaults) {
  NuclearReactionConfig cfg = defaults;
  if (!j.is_object()) {
    return cfg;
  }
  cfg.name = j.value("name", cfg.name);
  cfg.halfLifeYears = j.value("halfLifeYears", cfg.halfLifeYears);
  if (j.contains("reactants")) {
    cfg.reactants.clear();
    appendNuclearReactionParticipantsFromJson(j.at("reactants"), cfg.reactants);
  }
  if (j.contains("products")) {
    cfg.products.clear();
    appendNuclearReactionParticipantsFromJson(j.at("products"), cfg.products);
  }
  return cfg;
}

NuclearCycleConfig nuclearCycleFromJson(const nlohmann::json& j,
                                        const NuclearCycleConfig& defaults) {
  NuclearCycleConfig cfg = defaults;
  if (!j.is_object()) {
    return cfg;
  }
  cfg.name = j.value("name", cfg.name);
  cfg.enable = j.value("enable", cfg.enable);
  if (j.contains("source")) {
    cfg.source = nuclearSpeciesFromJson(j.at("source"), cfg.source);
  }
  if (j.contains("target")) {
    cfg.target = nuclearSpeciesFromJson(j.at("target"), cfg.target);
  }
  if (j.contains("forward")) {
    cfg.forward = nuclearReactionFromJson(j.at("forward"), cfg.forward);
  }
  if (j.contains("backward")) {
    cfg.backward = nuclearReactionFromJson(j.at("backward"), cfg.backward);
  }
  return cfg;
}

NuclearConfig nuclearFromJson(const nlohmann::json& j, const NuclearConfig& defaults) {
  NuclearConfig cfg = defaults;
  if (!j.is_object()) {
    return cfg;
  }
  cfg.enable = j.value("enable", cfg.enable);
  if (j.contains("cycles")) {
    cfg.cycles.clear();
    const auto& cycles = j.at("cycles");
    if (cycles.is_array()) {
      for (const auto& entry : cycles) {
        if (entry.is_object()) {
          cfg.cycles.push_back(nuclearCycleFromJson(entry, NuclearCycleConfig{}));
        }
      }
    } else if (cycles.is_object()) {
      cfg.cycles.push_back(nuclearCycleFromJson(cycles, NuclearCycleConfig{}));
    }
  }
  return cfg;
}

MultiscaleConfig multiscaleFromJson(const nlohmann::json& j, const MultiscaleConfig& defaults) {
  MultiscaleConfig cfg = defaults;
  if (!j.is_object()) {
    return cfg;
  }
  cfg.enable = j.value("enable", cfg.enable);
  cfg.method = j.value("method", cfg.method);
  cfg.mode = j.value("mode", cfg.mode);
  return cfg;
}

Vector3Config vector3FromJson(const nlohmann::json& j, const Vector3Config& defaults) {
  Vector3Config cfg = defaults;
  if (j.is_array() && j.size() >= 3) {
    cfg.x = j.at(0).get<double>();
    cfg.y = j.at(1).get<double>();
    cfg.z = j.at(2).get<double>();
  } else if (j.is_object()) {
    cfg.x = j.value("x", cfg.x);
    cfg.y = j.value("y", cfg.y);
    cfg.z = j.value("z", cfg.z);
  }
  return cfg;
}

RotationConfig rotationFromJson(const nlohmann::json& j, const RotationConfig& defaults) {
  RotationConfig cfg = defaults;
  if (j.is_array() && j.size() >= 3) {
    cfg.x = j.at(0).get<double>();
    cfg.y = j.at(1).get<double>();
    cfg.z = j.at(2).get<double>();
  } else if (j.is_object()) {
    cfg.x = j.value("x", cfg.x);
    cfg.y = j.value("y", cfg.y);
    cfg.z = j.value("z", cfg.z);
  }
  return cfg;
}

PlacementConfig placementFromJson(const nlohmann::json& j, const PlacementConfig& defaults) {
  PlacementConfig cfg = defaults;
  if (!j.is_object()) {
    return cfg;
  }
  cfg.parent = j.value("parent", cfg.parent);
  if (j.contains("positionMm")) {
    cfg.positionMm = vector3FromJson(j.at("positionMm"), cfg.positionMm);
  }
  if (j.contains("rotationDeg")) {
    cfg.rotationDeg = rotationFromJson(j.at("rotationDeg"), cfg.rotationDeg);
  }
  return cfg;
}

ShapeConfig shapeFromJson(const nlohmann::json& j, const ShapeConfig& defaults) {
  ShapeConfig cfg = defaults;
  if (!j.is_object()) {
    return cfg;
  }
  cfg.type = j.value("type", cfg.type);
  if (j.contains("sizeMm")) {
    const auto& size = j.at("sizeMm");
    if (size.is_array() && size.size() >= 3) {
      cfg.sizeXmm = size.at(0).get<double>();
      cfg.sizeYmm = size.at(1).get<double>();
      cfg.sizeZmm = size.at(2).get<double>();
    } else if (size.is_object()) {
      cfg.sizeXmm = size.value("x", cfg.sizeXmm);
      cfg.sizeYmm = size.value("y", cfg.sizeYmm);
      cfg.sizeZmm = size.value("z", cfg.sizeZmm);
    }
  }
  if ((cfg.sizeXmm <= 0.0 || cfg.sizeYmm <= 0.0 || cfg.sizeZmm <= 0.0) &&
      j.contains("halfSizeMm")) {
    const auto& half = j.at("halfSizeMm");
    if (half.is_array() && half.size() >= 3) {
      cfg.sizeXmm = 2.0 * half.at(0).get<double>();
      cfg.sizeYmm = 2.0 * half.at(1).get<double>();
      cfg.sizeZmm = 2.0 * half.at(2).get<double>();
    } else if (half.is_object()) {
      cfg.sizeXmm = 2.0 * half.value("x", cfg.sizeXmm * 0.5);
      cfg.sizeYmm = 2.0 * half.value("y", cfg.sizeYmm * 0.5);
      cfg.sizeZmm = 2.0 * half.value("z", cfg.sizeZmm * 0.5);
    }
  }
  cfg.innerRadiusMm = j.value("innerRadiusMm", cfg.innerRadiusMm);
  cfg.outerRadiusMm = j.value("outerRadiusMm", cfg.outerRadiusMm);
  if (cfg.outerRadiusMm <= 0.0) {
    cfg.outerRadiusMm = j.value("radiusMm", cfg.outerRadiusMm);
  }
  if (cfg.outerRadiusMm <= 0.0) {
    const auto diameter = j.value("diameterMm", 0.0);
    if (diameter > 0.0) {
      cfg.outerRadiusMm = 0.5 * diameter;
    }
  }
  cfg.lengthMm = j.value("lengthMm", cfg.lengthMm);
  if (cfg.lengthMm <= 0.0) {
    const auto halfLength = j.value("halfLengthMm", 0.0);
    if (halfLength > 0.0) {
      cfg.lengthMm = 2.0 * halfLength;
    }
  }
  return cfg;
}

VolumeConfig volumeFromJson(const nlohmann::json& j, const VolumeConfig& defaults) {
  VolumeConfig cfg = defaults;
  if (!j.is_object()) {
    return cfg;
  }
  cfg.name = j.value("name", cfg.name);
  cfg.material = j.value("material", cfg.material);
  cfg.scoreEdep = j.value("scoreEdep", cfg.scoreEdep);
  if (j.contains("shape")) {
    cfg.shape = shapeFromJson(j.at("shape"), cfg.shape);
  }
  if (j.contains("placement")) {
    cfg.placement = placementFromJson(j.at("placement"), cfg.placement);
  }
  if (j.contains("tags")) {
    cfg.tags.clear();
    appendStringListFromJson(j.at("tags"), cfg.tags);
  }
  return cfg;
}

GeometryConfig geometryFromJson(const nlohmann::json& j, const GeometryConfig& defaults) {
  GeometryConfig cfg = defaults;
  if (!j.is_object()) {
    return cfg;
  }
  if (j.contains("volumes")) {
    const auto& volumes = j.at("volumes");
    cfg.volumes.clear();
    if (volumes.is_array()) {
      for (const auto& entry : volumes) {
        if (entry.is_object()) {
          cfg.volumes.push_back(volumeFromJson(entry, VolumeConfig{}));
        }
      }
    } else if (volumes.is_object()) {
      cfg.volumes.push_back(volumeFromJson(volumes, VolumeConfig{}));
    }
  }
  return cfg;
}

void appendMaterialComponentsFromJson(const nlohmann::json& j,
                                      std::vector<MaterialComponentConfig>& out) {
  const auto appendOne = [&](const nlohmann::json& entry) {
    if (!entry.is_object()) {
      return;
    }
    MaterialComponentConfig comp;
    comp.material = entry.value("material", comp.material);
    comp.element = entry.value("element", comp.element);
    comp.fraction = entry.value("fraction", comp.fraction);
    if (!comp.material.empty() || !comp.element.empty()) {
      out.push_back(comp);
    }
  };
  if (j.is_array()) {
    for (const auto& entry : j) {
      appendOne(entry);
    }
  } else if (j.is_object()) {
    appendOne(j);
  }
}

MaterialConfig materialFromJson(const nlohmann::json& j, const MaterialConfig& defaults) {
  MaterialConfig cfg = defaults;
  if (!j.is_object()) {
    return cfg;
  }
  cfg.name = j.value("name", cfg.name);
  cfg.smiles = j.value("smiles", cfg.smiles);
  cfg.densityGcm3 = j.value("densityGcm3", cfg.densityGcm3);
  if (j.contains("components")) {
    cfg.components.clear();
    appendMaterialComponentsFromJson(j.at("components"), cfg.components);
  }
  return cfg;
}

HooksConfig hooksFromJson(const nlohmann::json& j, const HooksConfig& defaults) {
  HooksConfig cfg = defaults;
  if (j.is_string()) {
    cfg.registered.clear();
    cfg.registered.push_back(j.get<std::string>());
    return cfg;
  }
  if (j.is_array()) {
    cfg.registered.clear();
    appendStringListFromJson(j, cfg.registered);
    return cfg;
  }
  if (!j.is_object()) {
    return cfg;
  }
  const auto parseList = [&](const nlohmann::json& arr) {
    appendStringListFromJson(arr, cfg.registered);
  };
  cfg.registered.clear();
  if (j.contains("registered") && j.at("registered").is_array()) {
    parseList(j.at("registered"));
  } else if (j.contains("registered") && j.at("registered").is_string()) {
    parseList(j.at("registered"));
  } else if (j.contains("names") && j.at("names").is_array()) {
    parseList(j.at("names"));
  } else if (j.contains("names") && j.at("names").is_string()) {
    parseList(j.at("names"));
  } else {
    for (auto it = j.begin(); it != j.end(); ++it) {
      if (it.value().is_boolean() && it.value().get<bool>()) {
        cfg.registered.push_back(it.key());
      }
    }
  }
  if (j.contains("maxStepCallbacks") && j.at("maxStepCallbacks").is_number_integer()) {
    cfg.maxStepCallbacks = j.at("maxStepCallbacks").get<int>();
  }
  if (j.contains("maxStepRecords") && j.at("maxStepRecords").is_number_integer()) {
    cfg.maxStepCallbacks = j.at("maxStepRecords").get<int>();
  }
  if (j.contains("maxEmitsPerCallback") &&
      j.at("maxEmitsPerCallback").is_number_integer()) {
    cfg.maxEmitsPerCallback = j.at("maxEmitsPerCallback").get<int>();
  }
  if (j.contains("maxEmitsPerCall") && j.at("maxEmitsPerCall").is_number_integer()) {
    cfg.maxEmitsPerCallback = j.at("maxEmitsPerCall").get<int>();
  }
  if (j.contains("maxEmits") && j.at("maxEmits").is_number_integer()) {
    cfg.maxEmitsPerCallback = j.at("maxEmits").get<int>();
  }
  if (j.contains("maxEmitPayloadBytes") &&
      j.at("maxEmitPayloadBytes").is_number_integer()) {
    cfg.maxEmitPayloadBytes = j.at("maxEmitPayloadBytes").get<int>();
  }
  if (j.contains("maxPayloadBytes") && j.at("maxPayloadBytes").is_number_integer()) {
    cfg.maxEmitPayloadBytes = j.at("maxPayloadBytes").get<int>();
  }
  if (cfg.maxStepCallbacks < 0) {
    cfg.maxStepCallbacks = 0;
  }
  if (cfg.maxEmitsPerCallback < 0) {
    cfg.maxEmitsPerCallback = 0;
  }
  if (cfg.maxEmitPayloadBytes < 0) {
    cfg.maxEmitPayloadBytes = 0;
  }
  return cfg;
}

StratifyConfig stratifyFromJson(const nlohmann::json& j, const StratifyConfig& defaults) {
  StratifyConfig cfg = defaults;
  if (!j.is_object()) {
    return cfg;
  }
  cfg.enable = j.value("enable", cfg.enable);
  cfg.edepMeVThreshold = j.value("edepMeVThreshold", cfg.edepMeVThreshold);
  cfg.opticalTrackLengthMmThreshold =
      j.value("opticalTrackLengthMmThreshold", cfg.opticalTrackLengthMmThreshold);
  cfg.totalTrackLengthMmThreshold =
      j.value("totalTrackLengthMmThreshold", cfg.totalTrackLengthMmThreshold);
  cfg.totalTrackCountThreshold =
      j.value("totalTrackCountThreshold", cfg.totalTrackCountThreshold);
  cfg.totalStepCountThreshold =
      j.value("totalStepCountThreshold", cfg.totalStepCountThreshold);
  cfg.opticalPhotonTrackThreshold =
      j.value("opticalPhotonTrackThreshold", cfg.opticalPhotonTrackThreshold);
  cfg.opticalPhotonStepThreshold =
      j.value("opticalPhotonStepThreshold", cfg.opticalPhotonStepThreshold);
  cfg.labelPredictable = j.value("labelPredictable", cfg.labelPredictable);
  cfg.labelExceptional = j.value("labelExceptional", cfg.labelExceptional);
  cfg.labelUnclassified = j.value("labelUnclassified", cfg.labelUnclassified);
  cfg.modelPath = j.value("modelPath", cfg.modelPath);
  cfg.dumpFeatures = j.value("dumpFeatures", cfg.dumpFeatures);
  cfg.dumpResimQueue = j.value("dumpResimQueue", cfg.dumpResimQueue);
  return cfg;
}

LabConfig labFromJson(const nlohmann::json& j, const LabConfig& defaults) {
  LabConfig cfg = defaults;
  if (j.is_boolean()) {
    cfg.enable = j.get<bool>();
    return cfg;
  }
  if (j.is_string()) {
    cfg.mode = j.get<std::string>();
    cfg.enable = cfg.mode != "scenario";
    return cfg;
  }
  if (!j.is_object()) {
    return cfg;
  }
  cfg.enable = j.value("enable", cfg.enable);
  cfg.mode = j.value("mode", cfg.mode);
  cfg.commandSchema = j.value("commandSchema", cfg.commandSchema);
  cfg.commandChannel = j.value("commandChannel", cfg.commandChannel);
  if (j.contains("targetHz") && j.at("targetHz").is_number_integer()) {
    cfg.targetHz = j.at("targetHz").get<int>();
  }
  if (j.contains("tickHz") && j.at("tickHz").is_number_integer()) {
    cfg.targetHz = j.at("tickHz").get<int>();
  }
  if (cfg.targetHz <= 0) {
    cfg.targetHz = defaults.targetHz;
  }
  return cfg;
}

} // namespace

TrechConfig configFromJsonString(const std::string& json) {
  TrechConfig cfg;
  if (json.empty()) {
    return cfg;
  }

  const auto root = nlohmann::json::parse(json);
  const auto applyDetectorAlias = [&](const char* key) {
    if (root.contains(key)) {
      cfg.detector = detectorFromJson(root.at(key), cfg.detector);
    }
  };
  applyDetectorAlias("environment");
  applyDetectorAlias("medium");
  applyDetectorAlias("detector");
  const bool hasBeam = root.contains("beam");
  if (hasBeam) {
    cfg.beam = beamFromJson(root.at("beam"), cfg.beam);
  }
  if (root.contains("beams")) {
    cfg.beams.clear();
    appendBeamsFromJson(root.at("beams"), cfg.beams);
  }
  if (!cfg.beams.empty() && !hasBeam) {
    cfg.beam = selectPrimaryBeam(cfg.beams, cfg.beam);
  } else if (cfg.beams.empty() && hasBeam) {
    cfg.beams.push_back(cfg.beam);
  }
  if (root.contains("run")) {
    cfg.run = runFromJson(root.at("run"), cfg.run);
  }
  if (root.contains("determinism")) {
    cfg.determinism = determinismFromJson(root.at("determinism"), cfg.determinism);
  }
  if (root.contains("system")) {
    cfg.system = systemFromJson(root.at("system"), cfg.system);
  }
  if (root.contains("optics")) {
    cfg.optics = opticsFromJson(root.at("optics"), cfg.optics);
    if (root.at("optics").is_object() && root.at("optics").contains("derive")) {
      cfg.opticsDerive = opticsDeriveFromJson(root.at("optics").at("derive"), cfg.opticsDerive);
    }
  }
  if (root.contains("opticsDerive")) {
    cfg.opticsDerive = opticsDeriveFromJson(root.at("opticsDerive"), cfg.opticsDerive);
  }
  if (root.contains("viz")) {
    cfg.viz = vizFromJson(root.at("viz"), cfg.viz);
  }
  if (root.contains("chemistry")) {
    cfg.chemistry = chemistryFromJson(root.at("chemistry"), cfg.chemistry);
  }
  if (root.contains("nuclear")) {
    cfg.nuclear = nuclearFromJson(root.at("nuclear"), cfg.nuclear);
  }
  if (root.contains("multiscale")) {
    cfg.multiscale = multiscaleFromJson(root.at("multiscale"), cfg.multiscale);
  }
  if (root.contains("geometry")) {
    cfg.geometry = geometryFromJson(root.at("geometry"), cfg.geometry);
  }
  if (root.contains("materials")) {
    const auto& materials = root.at("materials");
    cfg.materials.clear();
    if (materials.is_array()) {
      for (const auto& entry : materials) {
        if (entry.is_object()) {
          cfg.materials.push_back(materialFromJson(entry, MaterialConfig{}));
        }
      }
    } else if (materials.is_object()) {
      cfg.materials.push_back(materialFromJson(materials, MaterialConfig{}));
    }
  }
  if (root.contains("hooks")) {
    cfg.hooks = hooksFromJson(root.at("hooks"), cfg.hooks);
  }
  if (root.contains("stratify")) {
    cfg.stratify = stratifyFromJson(root.at("stratify"), cfg.stratify);
  }
  if (root.contains("lab")) {
    cfg.lab = labFromJson(root.at("lab"), cfg.lab);
  }
  return cfg;
}

std::string configToJsonString(const TrechConfig& cfg) {
  nlohmann::json root;
  root["detector"] = {
    {"worldSizeMm", cfg.detector.worldSizeMm},
    {"worldMaterial", cfg.detector.worldMaterial},
    {"mediumBoxMm", cfg.detector.mediumBoxMm},
    {"mediumMaterial", cfg.detector.mediumMaterial},
    {"temperatureK", cfg.detector.temperatureK},
    {"pressureAtm", cfg.detector.pressureAtm},
  };
  root["beam"] = {
    {"particle", cfg.beam.particle},
    {"energyMeV", cfg.beam.energyMeV},
    {"direction", {cfg.beam.directionX, cfg.beam.directionY, cfg.beam.directionZ}},
  };
  if (!cfg.beam.name.empty()) {
    root["beam"]["name"] = cfg.beam.name;
  }
  writeBeamExtras(root["beam"], cfg.beam);
  if (cfg.beam.active) {
    root["beam"]["active"] = cfg.beam.active;
  }
  bool includeBeams = cfg.beams.size() > 1;
  if (!includeBeams) {
    for (const auto& beam : cfg.beams) {
      if (!beam.name.empty() || beam.active) {
        includeBeams = true;
        break;
      }
    }
  }
  if (includeBeams) {
    auto beams = nlohmann::json::array();
    for (const auto& beam : cfg.beams) {
      nlohmann::json entry;
      if (!beam.name.empty()) {
        entry["name"] = beam.name;
      }
      entry["particle"] = beam.particle;
      entry["energyMeV"] = beam.energyMeV;
      entry["direction"] = {beam.directionX, beam.directionY, beam.directionZ};
      writeBeamExtras(entry, beam);
      if (beam.active) {
        entry["active"] = beam.active;
      }
      beams.push_back(entry);
    }
    root["beams"] = beams;
  }
  root["run"] = {
    {"nEvents", cfg.run.nEvents},
    {"seed", cfg.run.seed},
  };
  root["determinism"] = {
    {"mode", normalizeDeterminismMode(cfg.determinism.mode)},
  };
  root["system"] = {
    {"enable", cfg.system.enable},
    {"mode", cfg.system.mode},
    {"frame", cfg.system.frame},
    {"ensemble", cfg.system.ensemble},
    {"volumeMm3", cfg.system.volumeMm3},
  };
  root["optics"] = {
    {"enable", cfg.optics.enable},
    {"refractiveIndex", cfg.optics.refractiveIndex},
    {"absorptionLengthMm", cfg.optics.absorptionLengthMm},
    {"scatterLengthMm", cfg.optics.scatterLengthMm},
  };
  if (!cfg.optics.spectrum.empty()) {
    auto spectrum = nlohmann::json::array();
    for (const auto& point : cfg.optics.spectrum) {
      nlohmann::json entry;
      if (point.energyEv > 0.0) {
        entry["energyEv"] = point.energyEv;
      }
      if (point.wavelengthNm > 0.0) {
        entry["wavelengthNm"] = point.wavelengthNm;
      }
      if (point.refractiveIndex > 0.0) {
        entry["refractiveIndex"] = point.refractiveIndex;
      }
      if (point.absorptionLengthMm > 0.0) {
        entry["absorptionLengthMm"] = point.absorptionLengthMm;
      }
      if (point.scatterLengthMm > 0.0) {
        entry["scatterLengthMm"] = point.scatterLengthMm;
      }
      if (!entry.empty()) {
        spectrum.push_back(entry);
      }
    }
    if (!spectrum.empty()) {
      root["optics"]["spectrum"] = spectrum;
    }
  }
  if (cfg.opticsDerive.enable || !cfg.opticsDerive.validationReferences.empty()) {
    nlohmann::json derive;
    derive["enable"] = cfg.opticsDerive.enable;
    derive["mode"] = cfg.opticsDerive.mode;
    derive["energyMinEv"] = cfg.opticsDerive.energyMinEv;
    derive["energyMaxEv"] = cfg.opticsDerive.energyMaxEv;
    derive["nEnergyBins"] = cfg.opticsDerive.nEnergyBins;
    derive["kkIntegrationMinEv"] = cfg.opticsDerive.kkIntegrationMinEv;
    derive["kkIntegrationMaxEv"] = cfg.opticsDerive.kkIntegrationMaxEv;
    derive["kkIntegrationBins"] = cfg.opticsDerive.kkIntegrationBins;
    derive["modelValidMinEv"] = cfg.opticsDerive.modelValidMinEv;
    derive["valenceOscillator"] = cfg.opticsDerive.valenceOscillator;
    derive["valenceResonanceEv"] = cfg.opticsDerive.valenceResonanceEv;
    if (!cfg.opticsDerive.surrogateModelPath.empty()) {
      derive["surrogateModelPath"] = cfg.opticsDerive.surrogateModelPath;
    }
    derive["writeSpectrum"] = cfg.opticsDerive.writeSpectrum;
    if (cfg.opticsDerive.validateAgainstReferences ||
        !cfg.opticsDerive.validationReferences.empty()) {
      nlohmann::json validate;
      validate["enable"] = cfg.opticsDerive.validateAgainstReferences;
      if (!cfg.opticsDerive.validationReferences.empty()) {
        auto refs = nlohmann::json::array();
        for (const auto& ref : cfg.opticsDerive.validationReferences) {
          nlohmann::json entry;
          entry["material"] = ref.material;
          entry["energyEv"] = ref.energyEv;
          if (ref.refractiveIndex > 0.0) {
            entry["refractiveIndex"] = ref.refractiveIndex;
          }
          if (ref.absorptionLengthMm > 0.0) {
            entry["absorptionLengthMm"] = ref.absorptionLengthMm;
          }
          if (ref.scatterLengthMm > 0.0) {
            entry["scatterLengthMm"] = ref.scatterLengthMm;
          }
          if (!ref.source.empty()) {
            entry["source"] = ref.source;
          }
          refs.push_back(entry);
        }
        validate["references"] = refs;
      }
      derive["validate"] = validate;
    }
    root["optics"]["derive"] = derive;
  }
  if (cfg.viz.enable) {
    nlohmann::json viz;
    viz["enable"] = cfg.viz.enable;
    viz["scenePath"] = cfg.viz.scenePath;
    viz["trajectoriesPath"] = cfg.viz.trajectoriesPath;
    viz["maxTrajectories"] = cfg.viz.maxTrajectories;
    viz["sampleEveryNth"] = cfg.viz.sampleEveryNth;
    viz["maxSegmentsPerTrajectory"] = cfg.viz.maxSegmentsPerTrajectory;
    viz["includeNonOptical"] = cfg.viz.includeNonOptical;
    viz["recordVertices"] = cfg.viz.recordVertices;
    root["viz"] = viz;
  }
  root["chemistry"] = {
    {"enable", cfg.chemistry.enable},
    {"model", cfg.chemistry.model},
    {"solver", cfg.chemistry.solver},
  };
  if (cfg.nuclear.enable || !cfg.nuclear.cycles.empty()) {
    nlohmann::json nuclear;
    nuclear["enable"] = cfg.nuclear.enable;
    if (!cfg.nuclear.cycles.empty()) {
      auto cycles = nlohmann::json::array();
      for (const auto& cycle : cfg.nuclear.cycles) {
        nlohmann::json entry;
        if (!cycle.name.empty()) {
          entry["name"] = cycle.name;
        }
        entry["enable"] = cycle.enable;
        const auto writeSpecies = [](const NuclearSpeciesConfig& species) {
          nlohmann::json value;
          if (!species.symbol.empty()) {
            value["symbol"] = species.symbol;
          }
          if (!species.material.empty()) {
            value["material"] = species.material;
          }
          if (species.z > 0) {
            value["z"] = species.z;
          }
          if (species.a > 0) {
            value["a"] = species.a;
          }
          if (!species.phase.empty()) {
            value["phase"] = species.phase;
          }
          if (species.densityGcm3 > 0.0) {
            value["densityGcm3"] = species.densityGcm3;
          }
          return value;
        };
        const auto writeReaction = [](const NuclearReactionConfig& reaction) {
          nlohmann::json value;
          if (!reaction.name.empty()) {
            value["name"] = reaction.name;
          }
          if (reaction.halfLifeYears > 0.0) {
            value["halfLifeYears"] = reaction.halfLifeYears;
          }
          const auto writeParticipants =
              [](const std::vector<NuclearReactionParticipantConfig>& participants) {
                auto out = nlohmann::json::array();
                for (const auto& participant : participants) {
                  nlohmann::json p;
                  if (!participant.particle.empty()) {
                    p["particle"] = participant.particle;
                  }
                  if (participant.z > 0) {
                    p["z"] = participant.z;
                  }
                  if (participant.a > 0) {
                    p["a"] = participant.a;
                  }
                  if (!p.empty()) {
                    out.push_back(p);
                  }
                }
                return out;
              };
          if (!reaction.reactants.empty()) {
            value["reactants"] = writeParticipants(reaction.reactants);
          }
          if (!reaction.products.empty()) {
            value["products"] = writeParticipants(reaction.products);
          }
          return value;
        };
        const auto source = writeSpecies(cycle.source);
        if (!source.empty()) {
          entry["source"] = source;
        }
        const auto target = writeSpecies(cycle.target);
        if (!target.empty()) {
          entry["target"] = target;
        }
        const auto forward = writeReaction(cycle.forward);
        if (!forward.empty()) {
          entry["forward"] = forward;
        }
        const auto backward = writeReaction(cycle.backward);
        if (!backward.empty()) {
          entry["backward"] = backward;
        }
        cycles.push_back(entry);
      }
      nuclear["cycles"] = cycles;
    }
    root["nuclear"] = nuclear;
  }
  root["multiscale"] = {
    {"enable", cfg.multiscale.enable},
    {"method", cfg.multiscale.method},
    {"mode", cfg.multiscale.mode},
  };
  if (!cfg.geometry.volumes.empty()) {
    auto volumes = nlohmann::json::array();
    for (const auto& volume : cfg.geometry.volumes) {
      nlohmann::json entry;
      entry["name"] = volume.name;
      if (!volume.material.empty()) {
        entry["material"] = volume.material;
      }
      entry["scoreEdep"] = volume.scoreEdep;
      if (!volume.tags.empty()) {
        entry["tags"] = volume.tags;
      }
      nlohmann::json shape;
      shape["type"] = volume.shape.type;
      if (volume.shape.sizeXmm > 0.0 || volume.shape.sizeYmm > 0.0 ||
          volume.shape.sizeZmm > 0.0) {
        shape["sizeMm"] = {volume.shape.sizeXmm, volume.shape.sizeYmm,
                           volume.shape.sizeZmm};
      }
      if (volume.shape.outerRadiusMm > 0.0 || volume.shape.innerRadiusMm > 0.0) {
        shape["outerRadiusMm"] = volume.shape.outerRadiusMm;
        shape["innerRadiusMm"] = volume.shape.innerRadiusMm;
      }
      if (volume.shape.lengthMm > 0.0) {
        shape["lengthMm"] = volume.shape.lengthMm;
      }
      if (!shape.empty()) {
        entry["shape"] = shape;
      }
      nlohmann::json placement;
      if (!volume.placement.parent.empty()) {
        placement["parent"] = volume.placement.parent;
      }
      placement["positionMm"] = {volume.placement.positionMm.x,
                                 volume.placement.positionMm.y,
                                 volume.placement.positionMm.z};
      placement["rotationDeg"] = {volume.placement.rotationDeg.x,
                                  volume.placement.rotationDeg.y,
                                  volume.placement.rotationDeg.z};
      entry["placement"] = placement;
      volumes.push_back(entry);
    }
    root["geometry"]["volumes"] = volumes;
  }
  if (!cfg.materials.empty()) {
    auto materials = nlohmann::json::array();
    for (const auto& material : cfg.materials) {
      nlohmann::json entry;
      entry["name"] = material.name;
      if (!material.smiles.empty()) {
        entry["smiles"] = material.smiles;
      }
      if (material.densityGcm3 > 0.0) {
        entry["densityGcm3"] = material.densityGcm3;
      }
      if (!material.components.empty()) {
        auto components = nlohmann::json::array();
        for (const auto& component : material.components) {
          nlohmann::json comp;
          // Mirror the input form: an element component serializes as
          // `element`, otherwise as `material`, so round-trips stay stable.
          if (!component.element.empty()) {
            comp["element"] = component.element;
          } else {
            comp["material"] = component.material;
          }
          comp["fraction"] = component.fraction;
          components.push_back(comp);
        }
        entry["components"] = components;
      }
      materials.push_back(entry);
    }
    root["materials"] = materials;
  }
  const HooksConfig defaultHooks;
  if (!cfg.hooks.registered.empty() ||
      cfg.hooks.maxStepCallbacks != defaultHooks.maxStepCallbacks ||
      cfg.hooks.maxEmitsPerCallback != defaultHooks.maxEmitsPerCallback ||
      cfg.hooks.maxEmitPayloadBytes != defaultHooks.maxEmitPayloadBytes) {
    if (!cfg.hooks.registered.empty()) {
      root["hooks"]["registered"] = cfg.hooks.registered;
    }
    root["hooks"]["maxStepCallbacks"] =
        std::max(0, cfg.hooks.maxStepCallbacks);
    root["hooks"]["maxEmitsPerCallback"] =
        std::max(0, cfg.hooks.maxEmitsPerCallback);
    root["hooks"]["maxEmitPayloadBytes"] =
        std::max(0, cfg.hooks.maxEmitPayloadBytes);
  }
  root["stratify"] = {
    {"enable", cfg.stratify.enable},
    {"edepMeVThreshold", cfg.stratify.edepMeVThreshold},
    {"opticalTrackLengthMmThreshold", cfg.stratify.opticalTrackLengthMmThreshold},
    {"totalTrackLengthMmThreshold", cfg.stratify.totalTrackLengthMmThreshold},
    {"totalTrackCountThreshold", cfg.stratify.totalTrackCountThreshold},
    {"totalStepCountThreshold", cfg.stratify.totalStepCountThreshold},
    {"opticalPhotonTrackThreshold", cfg.stratify.opticalPhotonTrackThreshold},
    {"opticalPhotonStepThreshold", cfg.stratify.opticalPhotonStepThreshold},
    {"labelPredictable", cfg.stratify.labelPredictable},
    {"labelExceptional", cfg.stratify.labelExceptional},
    {"labelUnclassified", cfg.stratify.labelUnclassified},
    {"modelPath", cfg.stratify.modelPath},
    {"dumpFeatures", cfg.stratify.dumpFeatures},
    {"dumpResimQueue", cfg.stratify.dumpResimQueue},
  };
  root["lab"] = {
    {"enable", cfg.lab.enable},
    {"mode", cfg.lab.mode},
    {"commandSchema", cfg.lab.commandSchema},
    {"commandChannel", cfg.lab.commandChannel},
    {"targetHz", cfg.lab.targetHz},
  };
  return root.dump();
}

} // namespace trech
