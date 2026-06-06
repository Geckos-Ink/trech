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
  // Emission origin (mm). Default keeps the historical point source at the
  // world centre.
  double originXMm = 0.0;
  double originYMm = 0.0;
  double originZMm = 0.0;
  // Source variety knobs ("anti-degeneration"). All default to 0 so existing
  // scenarios keep their exact point/monochromatic/collimated behaviour and
  // serialized config hash. When non-zero they spread primaries across a disk,
  // a divergence cone, and an energy band so a run samples a real distribution
  // instead of one repeated photon.
  double spotRadiusMm = 0.0;           // disk radius perpendicular to direction
  double divergenceDeg = 0.0;          // half-angle of the emission cone
  double energySpreadFractional = 0.0; // Gaussian sigma as a fraction of energy
  // Optical-photon polarization. Geant4 emits optical photons with a null
  // polarization by default and then patches in a random vector internally (the
  // "ZeroPolarization" warning) — an uncontrolled fallback. We instead set the
  // polarization explicitly from the seeded engine so the choice is controlled,
  // reproducible, and documented. Only applied when the primary is an optical
  // photon; other particles are untouched.
  //   "" / "unpolarized": sample a random transverse linear polarization per
  //                       event (an unpolarized beam as a linear ensemble — the
  //                       default, which kills the fallback everywhere).
  //   "linear":           fixed linear polarization at polarizationAngleDeg
  //                       about the beam's transverse axis.
  //   "none":             leave polarization unset (legacy Geant4 fallback).
  std::string polarization;            // default "" => unpolarized sampling
  double polarizationAngleDeg = 0.0;   // used when polarization == "linear"
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

struct OpticsValidationReferenceConfig {
  std::string material;
  double energyEv = 0.0;
  double refractiveIndex = 0.0;
  double absorptionLengthMm = 0.0;
  double scatterLengthMm = 0.0;
  std::string source;
};

struct OpticsDeriveConfig {
  bool enable = false;
  std::string mode = "microscale_geant4";
  double energyMinEv = 1.0;
  double energyMaxEv = 6.0;
  int nEnergyBins = 16;
  double kkIntegrationMinEv = 100.0;
  double kkIntegrationMaxEv = 200000.0;
  int kkIntegrationBins = 256;
  // Geant4 atomic photoabsorption tables (Livermore/Penelope) typically run
  // out below ~100 eV.  Queries below this energy are extrapolations, not
  // tabulated data — we treat them as "not constrained" (cross section 0)
  // rather than letting an extrapolation artifact (which grows as ~ 1/E^3.5
  // in the Born approximation) dominate the optical-band attenuation.
  double modelValidMinEv = 100.0;
  // Valence-electron oscillator (f-sum-rule dispersion).  The visible-band
  // refractive index of condensed matter is dominated by valence-electron
  // oscillator strength in the UV (~10-25 eV), which Geant4's free-atom
  // photoabsorption does not resolve below modelValidMinEv — leaving the KK
  // tail to yield n≈1.  When enabled we restore that contribution as a single
  // effective Lorentz oscillator: its strength is fixed by the f-sum rule
  // (valence electron density, exact from the Geant4 material composition) and
  // its resonance sits at valenceResonanceEv.  This is a physics model, not a
  // handbook lookup: one global resonance energy recovers ~100% of water/glass
  // refraction (see docs/viz_refraction.md).  The residual is reported.
  bool valenceOscillator = true;
  double valenceResonanceEv = 22.0;
  // Torch surrogate model path (TorchScript). When mode == "surrogate" and the
  // model loads successfully the surrogate prediction replaces the extractor
  // pass for that material; on miss we fall back to the extractor.  The
  // surrogate must be trained on extractor outputs (see
  // `tools/torch/train_optics_surrogate.py`).
  std::string surrogateModelPath;
  bool writeSpectrum = true;
  bool validateAgainstReferences = false;
  std::vector<OpticsValidationReferenceConfig> validationReferences;
};

struct ChemistryConfig {
  bool enable = false;
  std::string model = "dna_water";
  std::string solver = "stub";
};

struct NuclearReactionParticipantConfig {
  std::string particle;
  int z = 0;
  int a = 0;
};

struct NuclearSpeciesConfig {
  std::string symbol;
  std::string material;
  int z = 0;
  int a = 0;
  std::string phase;
  double densityGcm3 = 0.0;
};

struct NuclearReactionConfig {
  std::string name;
  std::vector<NuclearReactionParticipantConfig> reactants;
  std::vector<NuclearReactionParticipantConfig> products;
  double halfLifeYears = 0.0;
};

struct NuclearCycleConfig {
  std::string name;
  bool enable = true;
  NuclearSpeciesConfig source;
  NuclearSpeciesConfig target;
  NuclearReactionConfig forward;
  NuclearReactionConfig backward;
};

struct NuclearConfig {
  bool enable = false;
  std::vector<NuclearCycleConfig> cycles;
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
  // A component is either another material (NIST `G4_*` name or a previously
  // declared custom mixture) or a single chemical element symbol (e.g. "Na").
  // Element components let scenarios build compounds Geant4's NIST database
  // does not ship (there is no `G4_SODIUM_CHLORIDE`, so salt = Na + Cl). Both
  // are added to the host material by mass `fraction`; element wins if set.
  std::string material;
  std::string element;
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

struct LabConfig {
  bool enable = false;
  std::string mode = "scenario";
  std::string commandSchema = "trech_lab_command_v1";
  std::string commandChannel = "stdin_jsonl";
  int targetHz = 60;
};

struct VizConfig {
  bool enable = false;
  std::string scenePath = "trech_viz_scene.json";
  std::string trajectoriesPath = "trech_viz_trajectories.jsonl";
  int maxTrajectories = 256;
  int sampleEveryNth = 1;
  int maxSegmentsPerTrajectory = 512;
  bool includeNonOptical = false;
  bool recordVertices = true;
};

struct TrechConfig {
  DetectorConfig detector;
  BeamConfig beam;
  std::vector<BeamConfig> beams;
  RunConfig run;
  DeterminismConfig determinism;
  SystemConfig system;
  OpticsConfig optics;
  OpticsDeriveConfig opticsDerive;
  ChemistryConfig chemistry;
  NuclearConfig nuclear;
  MultiscaleConfig multiscale;
  GeometryConfig geometry;
  std::vector<MaterialConfig> materials;
  HooksConfig hooks;
  StratifyConfig stratify;
  LabConfig lab;
  VizConfig viz;
};

TrechConfig configFromJsonString(const std::string& json);
std::string configToJsonString(const TrechConfig& cfg);

} // namespace trech
