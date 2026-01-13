#pragma once

#include <cstdint>
#include <string>

namespace trech {

struct DetectorConfig {
  double worldSizeMm = 100.0;
  std::string worldMaterial = "G4_WATER";
};

struct BeamConfig {
  std::string particle = "e-";
  double energyMeV = 1.0;
};

struct RunConfig {
  int nEvents = 10;
  std::uint64_t seed = 12345;
};

struct TrechConfig {
  DetectorConfig detector;
  BeamConfig beam;
  RunConfig run;
};

TrechConfig configFromJsonString(const std::string& json);
std::string configToJsonString(const TrechConfig& cfg);

} // namespace trech
