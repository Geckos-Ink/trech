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
  cfg.waterBoxMm = j.value("waterBoxMm", cfg.waterBoxMm);
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

OpticsConfig opticsFromJson(const nlohmann::json& j, const OpticsConfig& defaults) {
  OpticsConfig cfg = defaults;
  if (!j.is_object()) {
    return cfg;
  }
  cfg.enable = j.value("enable", cfg.enable);
  cfg.refractiveIndex = j.value("refractiveIndex", cfg.refractiveIndex);
  cfg.absorptionLengthMm = j.value("absorptionLengthMm", cfg.absorptionLengthMm);
  cfg.scatterLengthMm = j.value("scatterLengthMm", cfg.scatterLengthMm);
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
  if (root.contains("optics")) {
    cfg.optics = opticsFromJson(root.at("optics"), cfg.optics);
  }
  if (root.contains("chemistry")) {
    cfg.chemistry = chemistryFromJson(root.at("chemistry"), cfg.chemistry);
  }
  if (root.contains("multiscale")) {
    cfg.multiscale = multiscaleFromJson(root.at("multiscale"), cfg.multiscale);
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
    {"waterBoxMm", cfg.detector.waterBoxMm},
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
  root["optics"] = {
    {"enable", cfg.optics.enable},
    {"refractiveIndex", cfg.optics.refractiveIndex},
    {"absorptionLengthMm", cfg.optics.absorptionLengthMm},
    {"scatterLengthMm", cfg.optics.scatterLengthMm},
  };
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
