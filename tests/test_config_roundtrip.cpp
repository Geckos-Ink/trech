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
  cfg.beam.particle = "proton";
  cfg.beam.energyMeV = 7.5;
  cfg.run.nEvents = 17;
  cfg.run.seed = 98765;

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
  if (parsed.beam.particle != cfg.beam.particle) {
    std::cerr << "Beam particle mismatch\n";
    return 1;
  }
  if (!almostEqual(parsed.beam.energyMeV, cfg.beam.energyMeV)) {
    std::cerr << "Beam energyMeV mismatch\n";
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

  return 0;
}
