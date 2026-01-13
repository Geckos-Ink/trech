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
  return cfg;
}

BeamConfig beamFromJson(const nlohmann::json& j, const BeamConfig& defaults) {
  BeamConfig cfg = defaults;
  if (!j.is_object()) {
    return cfg;
  }
  cfg.particle = j.value("particle", cfg.particle);
  cfg.energyMeV = j.value("energyMeV", cfg.energyMeV);
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
  return cfg;
}

std::string configToJsonString(const TrechConfig& cfg) {
  nlohmann::json root;
  root["detector"] = {
    {"worldSizeMm", cfg.detector.worldSizeMm},
    {"worldMaterial", cfg.detector.worldMaterial},
  };
  root["beam"] = {
    {"particle", cfg.beam.particle},
    {"energyMeV", cfg.beam.energyMeV},
  };
  root["run"] = {
    {"nEvents", cfg.run.nEvents},
    {"seed", cfg.run.seed},
  };
  return root.dump();
}

} // namespace trech
