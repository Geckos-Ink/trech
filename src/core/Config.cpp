#include "trech/core/Config.hpp"

#include <nlohmann/json.hpp>

namespace trech {
namespace {

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
  return cfg;
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
  if (j.contains("spectrum") && j.at("spectrum").is_array()) {
    cfg.spectrum.clear();
    for (const auto& entry : j.at("spectrum")) {
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
      } else if (entry.is_object()) {
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
    }
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
  if (j.contains("tags") && j.at("tags").is_array()) {
    cfg.tags.clear();
    for (const auto& tag : j.at("tags")) {
      if (tag.is_string()) {
        cfg.tags.push_back(tag.get<std::string>());
      }
    }
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
        cfg.volumes.push_back(volumeFromJson(entry, VolumeConfig{}));
      }
    } else if (volumes.is_object()) {
      cfg.volumes.push_back(volumeFromJson(volumes, VolumeConfig{}));
    }
  }
  return cfg;
}

MaterialConfig materialFromJson(const nlohmann::json& j, const MaterialConfig& defaults) {
  MaterialConfig cfg = defaults;
  if (!j.is_object()) {
    return cfg;
  }
  cfg.name = j.value("name", cfg.name);
  cfg.densityGcm3 = j.value("densityGcm3", cfg.densityGcm3);
  if (j.contains("components") && j.at("components").is_array()) {
    cfg.components.clear();
    for (const auto& entry : j.at("components")) {
      if (!entry.is_object()) {
        continue;
      }
      MaterialComponentConfig comp;
      comp.material = entry.value("material", comp.material);
      comp.fraction = entry.value("fraction", comp.fraction);
      if (!comp.material.empty()) {
        cfg.components.push_back(comp);
      }
    }
  }
  return cfg;
}

HooksConfig hooksFromJson(const nlohmann::json& j, const HooksConfig& defaults) {
  HooksConfig cfg = defaults;
  if (j.is_array()) {
    cfg.registered.clear();
    for (const auto& entry : j) {
      if (entry.is_string()) {
        cfg.registered.push_back(entry.get<std::string>());
      }
    }
    return cfg;
  }
  if (!j.is_object()) {
    return cfg;
  }
  const auto parseList = [&](const nlohmann::json& arr) {
    for (const auto& entry : arr) {
      if (entry.is_string()) {
        cfg.registered.push_back(entry.get<std::string>());
      }
    }
  };
  cfg.registered.clear();
  if (j.contains("registered") && j.at("registered").is_array()) {
    parseList(j.at("registered"));
  } else if (j.contains("names") && j.at("names").is_array()) {
    parseList(j.at("names"));
  } else {
    for (auto it = j.begin(); it != j.end(); ++it) {
      if (it.value().is_boolean() && it.value().get<bool>()) {
        cfg.registered.push_back(it.key());
      }
    }
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

} // namespace

TrechConfig configFromJsonString(const std::string& json) {
  TrechConfig cfg;
  if (json.empty()) {
    return cfg;
  }

  const auto root = nlohmann::json::parse(json);
  if (root.contains("detector")) {
    cfg.detector = detectorFromJson(root.at("detector"), cfg.detector);
  }
  if (root.contains("beam")) {
    cfg.beam = beamFromJson(root.at("beam"), cfg.beam);
  }
  if (root.contains("run")) {
    cfg.run = runFromJson(root.at("run"), cfg.run);
  }
  if (root.contains("system")) {
    cfg.system = systemFromJson(root.at("system"), cfg.system);
  }
  if (root.contains("optics")) {
    cfg.optics = opticsFromJson(root.at("optics"), cfg.optics);
  }
  if (root.contains("chemistry")) {
    cfg.chemistry = chemistryFromJson(root.at("chemistry"), cfg.chemistry);
  }
  if (root.contains("multiscale")) {
    cfg.multiscale = multiscaleFromJson(root.at("multiscale"), cfg.multiscale);
  }
  if (root.contains("geometry")) {
    cfg.geometry = geometryFromJson(root.at("geometry"), cfg.geometry);
  }
  if (root.contains("materials") && root.at("materials").is_array()) {
    cfg.materials.clear();
    for (const auto& entry : root.at("materials")) {
      cfg.materials.push_back(materialFromJson(entry, MaterialConfig{}));
    }
  }
  if (root.contains("hooks")) {
    cfg.hooks = hooksFromJson(root.at("hooks"), cfg.hooks);
  }
  if (root.contains("stratify")) {
    cfg.stratify = stratifyFromJson(root.at("stratify"), cfg.stratify);
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
  root["run"] = {
    {"nEvents", cfg.run.nEvents},
    {"seed", cfg.run.seed},
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
  root["chemistry"] = {
    {"enable", cfg.chemistry.enable},
    {"model", cfg.chemistry.model},
    {"solver", cfg.chemistry.solver},
  };
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
      if (material.densityGcm3 > 0.0) {
        entry["densityGcm3"] = material.densityGcm3;
      }
      if (!material.components.empty()) {
        auto components = nlohmann::json::array();
        for (const auto& component : material.components) {
          nlohmann::json comp;
          comp["material"] = component.material;
          comp["fraction"] = component.fraction;
          components.push_back(comp);
        }
        entry["components"] = components;
      }
      materials.push_back(entry);
    }
    root["materials"] = materials;
  }
  if (!cfg.hooks.registered.empty()) {
    root["hooks"]["registered"] = cfg.hooks.registered;
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
  return root.dump();
}

} // namespace trech
