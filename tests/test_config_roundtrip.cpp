#include "trech/core/Config.hpp"

#include <cmath>
#include <iostream>

namespace {

bool almostEqual(double a, double b, double eps = 1e-9) {
  return std::fabs(a - b) < eps;
}

} // namespace

int main() {
  trech::TrechConfig cfg;
  cfg.detector.worldSizeMm = 42.0;
  cfg.detector.worldMaterial = "G4_AIR";
  cfg.detector.waterBoxMm = 21.0;
  cfg.detector.temperatureK = 285.0;
  cfg.detector.pressureAtm = 0.9;
  cfg.beam.particle = "proton";
  cfg.beam.energyMeV = 7.5;
  cfg.beam.directionX = 0.1;
  cfg.beam.directionY = 0.2;
  cfg.beam.directionZ = 0.3;
  cfg.run.nEvents = 17;
  cfg.run.seed = 98765;
  cfg.optics.enable = true;
  cfg.optics.refractiveIndex = 1.4;
  cfg.optics.absorptionLengthMm = 500.0;
  cfg.optics.scatterLengthMm = 250.0;
  cfg.chemistry.enable = true;
  cfg.chemistry.model = "dna_water_g4";
  cfg.chemistry.solver = "stubs";
  cfg.multiscale.enable = true;
  cfg.multiscale.method = "lbm_stub";
  cfg.multiscale.mode = "auto";
  cfg.stratify.enable = true;
  cfg.stratify.edepMeVThreshold = 1.25;
  cfg.stratify.opticalTrackLengthMmThreshold = 12.5;
  cfg.stratify.totalTrackLengthMmThreshold = 33.0;
  cfg.stratify.totalTrackCountThreshold = 7;
  cfg.stratify.totalStepCountThreshold = 99;
  cfg.stratify.opticalPhotonTrackThreshold = 5;
  cfg.stratify.opticalPhotonStepThreshold = 21;
  cfg.stratify.labelPredictable = "steady";
  cfg.stratify.labelExceptional = "spike";
  cfg.stratify.labelUnclassified = "skip";
  cfg.stratify.modelPath = "models/stratify.pt";
  cfg.stratify.dumpFeatures = true;
  cfg.stratify.dumpResimQueue = true;

  const std::string json = trech::configToJsonString(cfg);
  const trech::TrechConfig parsed = trech::configFromJsonString(json);

  if (!almostEqual(parsed.detector.worldSizeMm, cfg.detector.worldSizeMm)) {
    std::cerr << "Detector worldSizeMm mismatch\n";
    return 1;
  }
  if (parsed.detector.worldMaterial != cfg.detector.worldMaterial) {
    std::cerr << "Detector worldMaterial mismatch\n";
    return 1;
  }
  if (!almostEqual(parsed.detector.waterBoxMm, cfg.detector.waterBoxMm)) {
    std::cerr << "Detector waterBoxMm mismatch\n";
    return 1;
  }
  if (!almostEqual(parsed.detector.temperatureK, cfg.detector.temperatureK)) {
    std::cerr << "Detector temperatureK mismatch\n";
    return 1;
  }
  if (!almostEqual(parsed.detector.pressureAtm, cfg.detector.pressureAtm)) {
    std::cerr << "Detector pressureAtm mismatch\n";
    return 1;
  }
  if (parsed.beam.particle != cfg.beam.particle) {
    std::cerr << "Beam particle mismatch\n";
    return 1;
  }
  if (!almostEqual(parsed.beam.energyMeV, cfg.beam.energyMeV)) {
    std::cerr << "Beam energyMeV mismatch\n";
    return 1;
  }
  if (!almostEqual(parsed.beam.directionX, cfg.beam.directionX) ||
      !almostEqual(parsed.beam.directionY, cfg.beam.directionY) ||
      !almostEqual(parsed.beam.directionZ, cfg.beam.directionZ)) {
    std::cerr << "Beam direction mismatch\n";
    return 1;
  }
  if (parsed.run.nEvents != cfg.run.nEvents) {
    std::cerr << "Run nEvents mismatch\n";
    return 1;
  }
  if (parsed.run.seed != cfg.run.seed) {
    std::cerr << "Run seed mismatch\n";
    return 1;
  }
  if (parsed.optics.enable != cfg.optics.enable) {
    std::cerr << "Optics enable mismatch\n";
    return 1;
  }
  if (!almostEqual(parsed.optics.refractiveIndex, cfg.optics.refractiveIndex)) {
    std::cerr << "Optics refractiveIndex mismatch\n";
    return 1;
  }
  if (!almostEqual(parsed.optics.absorptionLengthMm, cfg.optics.absorptionLengthMm)) {
    std::cerr << "Optics absorptionLengthMm mismatch\n";
    return 1;
  }
  if (!almostEqual(parsed.optics.scatterLengthMm, cfg.optics.scatterLengthMm)) {
    std::cerr << "Optics scatterLengthMm mismatch\n";
    return 1;
  }
  if (parsed.chemistry.enable != cfg.chemistry.enable) {
    std::cerr << "Chemistry enable mismatch\n";
    return 1;
  }
  if (parsed.chemistry.model != cfg.chemistry.model) {
    std::cerr << "Chemistry model mismatch\n";
    return 1;
  }
  if (parsed.chemistry.solver != cfg.chemistry.solver) {
    std::cerr << "Chemistry solver mismatch\n";
    return 1;
  }
  if (parsed.multiscale.enable != cfg.multiscale.enable) {
    std::cerr << "Multiscale enable mismatch\n";
    return 1;
  }
  if (parsed.multiscale.method != cfg.multiscale.method) {
    std::cerr << "Multiscale method mismatch\n";
    return 1;
  }
  if (parsed.multiscale.mode != cfg.multiscale.mode) {
    std::cerr << "Multiscale mode mismatch\n";
    return 1;
  }
  if (parsed.stratify.enable != cfg.stratify.enable) {
    std::cerr << "Stratify enable mismatch\n";
    return 1;
  }
  if (!almostEqual(parsed.stratify.edepMeVThreshold, cfg.stratify.edepMeVThreshold)) {
    std::cerr << "Stratify edepMeVThreshold mismatch\n";
    return 1;
  }
  if (!almostEqual(parsed.stratify.opticalTrackLengthMmThreshold,
                   cfg.stratify.opticalTrackLengthMmThreshold)) {
    std::cerr << "Stratify opticalTrackLengthMmThreshold mismatch\n";
    return 1;
  }
  if (!almostEqual(parsed.stratify.totalTrackLengthMmThreshold,
                   cfg.stratify.totalTrackLengthMmThreshold)) {
    std::cerr << "Stratify totalTrackLengthMmThreshold mismatch\n";
    return 1;
  }
  if (parsed.stratify.totalTrackCountThreshold != cfg.stratify.totalTrackCountThreshold) {
    std::cerr << "Stratify totalTrackCountThreshold mismatch\n";
    return 1;
  }
  if (parsed.stratify.totalStepCountThreshold != cfg.stratify.totalStepCountThreshold) {
    std::cerr << "Stratify totalStepCountThreshold mismatch\n";
    return 1;
  }
  if (parsed.stratify.opticalPhotonTrackThreshold != cfg.stratify.opticalPhotonTrackThreshold) {
    std::cerr << "Stratify opticalPhotonTrackThreshold mismatch\n";
    return 1;
  }
  if (parsed.stratify.opticalPhotonStepThreshold != cfg.stratify.opticalPhotonStepThreshold) {
    std::cerr << "Stratify opticalPhotonStepThreshold mismatch\n";
    return 1;
  }
  if (parsed.stratify.labelPredictable != cfg.stratify.labelPredictable) {
    std::cerr << "Stratify labelPredictable mismatch\n";
    return 1;
  }
  if (parsed.stratify.labelExceptional != cfg.stratify.labelExceptional) {
    std::cerr << "Stratify labelExceptional mismatch\n";
    return 1;
  }
  if (parsed.stratify.labelUnclassified != cfg.stratify.labelUnclassified) {
    std::cerr << "Stratify labelUnclassified mismatch\n";
    return 1;
  }
  if (parsed.stratify.modelPath != cfg.stratify.modelPath) {
    std::cerr << "Stratify modelPath mismatch\n";
    return 1;
  }
  if (parsed.stratify.dumpFeatures != cfg.stratify.dumpFeatures) {
    std::cerr << "Stratify dumpFeatures mismatch\n";
    return 1;
  }
  if (parsed.stratify.dumpResimQueue != cfg.stratify.dumpResimQueue) {
    std::cerr << "Stratify dumpResimQueue mismatch\n";
    return 1;
  }

  return 0;
}
