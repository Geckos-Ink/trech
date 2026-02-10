#pragma once

#include <cstdint>
#include <string>
#include <vector>

namespace trech {

struct DetectorConfig {
  double worldSizeMm = 100.0;
  std::string worldMaterial = "G4_WATER";
  double mediumBoxMm = 0.0;
  std::string mediumMaterial = "G4_WATER";
  double temperatureK = 293.15;
  double pressureAtm = 1.0;
};

struct BeamConfig {
  std::string name;
  std::string particle = "e-";
  double energyMeV = 1.0;
  double directionX = 0.0;
  double directionY = 0.0;
  double directionZ = 1.0;
  bool active = false;
};

struct RunConfig {
  int nEvents = 10;
  std::uint64_t seed = 12345;
};

struct DeterminismConfig {
  std::string mode = "strict";
};

struct SystemConfig {
  bool enable = true;
  std::string mode = "steady_state";
  std::string frame = "point_agnostic";
  std::string ensemble;
  double volumeMm3 = 0.0;
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

struct Vector3Config {
  double x = 0.0;
  double y = 0.0;
  double z = 0.0;
};

struct RotationConfig {
  double x = 0.0;
  double y = 0.0;
  double z = 0.0;
};

struct PlacementConfig {
  std::string parent;
  Vector3Config positionMm;
  RotationConfig rotationDeg;
};

struct ShapeConfig {
  std::string type = "box";
  double sizeXmm = 0.0;
  double sizeYmm = 0.0;
  double sizeZmm = 0.0;
  double innerRadiusMm = 0.0;
  double outerRadiusMm = 0.0;
  double lengthMm = 0.0;
};

struct VolumeConfig {
  std::string name;
  std::string material;
  ShapeConfig shape;
  PlacementConfig placement;
  bool scoreEdep = false;
  std::vector<std::string> tags;
};

struct GeometryConfig {
  std::vector<VolumeConfig> volumes;
};

struct MaterialComponentConfig {
  std::string material;
  double fraction = 0.0;
};

struct MaterialConfig {
  std::string name;
  std::string smiles;
  double densityGcm3 = 0.0;
  std::vector<MaterialComponentConfig> components;
};

struct HooksConfig {
  std::vector<std::string> registered;
  int maxStepCallbacks = 100000;
  int maxEmitsPerCallback = 0;
  int maxEmitPayloadBytes = 0;
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
  std::vector<BeamConfig> beams;
  RunConfig run;
  DeterminismConfig determinism;
  SystemConfig system;
  OpticsConfig optics;
  ChemistryConfig chemistry;
  MultiscaleConfig multiscale;
  GeometryConfig geometry;
  std::vector<MaterialConfig> materials;
  HooksConfig hooks;
  StratifyConfig stratify;
};

TrechConfig configFromJsonString(const std::string& json);
std::string configToJsonString(const TrechConfig& cfg);

} // namespace trech
