#pragma once

#include <cstdint>
#include <string>

namespace trech {

struct DetectorConfig {
  double worldSizeMm = 100.0;
  std::string worldMaterial = "G4_WATER";
  double waterBoxMm = 0.0;
  double temperatureK = 293.15;
  double pressureAtm = 1.0;
};

struct BeamConfig {
  std::string particle = "e-";
  double energyMeV = 1.0;
  double directionX = 0.0;
  double directionY = 0.0;
  double directionZ = 1.0;
};

struct RunConfig {
  int nEvents = 10;
  std::uint64_t seed = 12345;
};

struct OpticsConfig {
  bool enable = false;
  double refractiveIndex = 1.333;
  double absorptionLengthMm = 0.0;
  double scatterLengthMm = 0.0;
};

struct TrechConfig {
  DetectorConfig detector;
  BeamConfig beam;
  RunConfig run;
  OpticsConfig optics;
};

TrechConfig configFromJsonString(const std::string& json);
std::string configToJsonString(const TrechConfig& cfg);

} // namespace trech
