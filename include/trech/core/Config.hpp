#pragma once

#include <cstdint>
#include <string>
#include <vector>

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

struct OpticsSpectrumPoint {
  double energyEv = 0.0;
  double wavelengthNm = 0.0;
  double refractiveIndex = 0.0;
  double absorptionLengthMm = 0.0;
  double scatterLengthMm = 0.0;
};

struct OpticsConfig {
  bool enable = false;
  double refractiveIndex = 1.333;
  double absorptionLengthMm = 0.0;
  double scatterLengthMm = 0.0;
  std::vector<OpticsSpectrumPoint> spectrum;
};

struct ChemistryConfig {
  bool enable = false;
  std::string model = "dna_water";
  std::string solver = "stub";
};

struct MultiscaleConfig {
  bool enable = false;
  std::string method = "stub";
  std::string mode = "auto";
};

struct StratifyConfig {
  bool enable = false;
  double edepMeVThreshold = 0.0;
  double opticalTrackLengthMmThreshold = 0.0;
  double totalTrackLengthMmThreshold = 0.0;
  int totalTrackCountThreshold = 0;
  int totalStepCountThreshold = 0;
  int opticalPhotonTrackThreshold = 0;
  int opticalPhotonStepThreshold = 0;
  std::string labelPredictable = "predictable";
  std::string labelExceptional = "exceptional";
  std::string labelUnclassified = "unclassified";
  std::string modelPath;
  bool dumpFeatures = false;
  bool dumpResimQueue = false;
};

struct TrechConfig {
  DetectorConfig detector;
  BeamConfig beam;
  RunConfig run;
  OpticsConfig optics;
  ChemistryConfig chemistry;
  MultiscaleConfig multiscale;
  StratifyConfig stratify;
};

TrechConfig configFromJsonString(const std::string& json);
std::string configToJsonString(const TrechConfig& cfg);

} // namespace trech
