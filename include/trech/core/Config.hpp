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

// One component of a multi-line / sampled emission spectrum. Each event samples
// one line with probability proportional to `weight`; the chosen energy then
// feeds the same `energySpreadFractional` broadening as a single beam. This
// lets a source emit a real spectrum (named lines, a blackbody SPD, ...) rather
// than one Gaussian band — the JS layer generates the table (keeping the engine
// physics-agnostic). Empty spectrum keeps the historical single-energy beam.
struct BeamSpectralLine {
  double energyMeV = 0.0;
  double weight = 1.0;
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
  // Optional emission spectrum: when non-empty, each event samples a line by
  // weight instead of using the single `energyMeV`. Default empty preserves the
  // single-energy beam and its serialized config hash.
  std::vector<BeamSpectralLine> spectrum;
  bool active = false;
};

struct RunConfig {
  int nEvents = 10;
  std::uint64_t seed = 12345;
  // Worker-thread count. 0 keeps Geant4's default (multithreaded with the
  // hardware count). Set to 1 to force serial event processing, which makes
  // hook-driven scenarios whose state accumulates across events (e.g. the MD
  // baths in testscenario_pascal/osmotic) reproducible — MT distributes events
  // across threads, so their completion order (and thus the accumulation)
  // otherwise varies run to run.
  int threads = 0;
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

// One analytic cross-check: a classical closed-form physics prediction that the
// engine evaluates from Geant4's own particle-level data and then compares to
// the Monte-Carlo statistical result of the same run. This is the
// "complex test scenario with comparison to classical formulas vs the
// GEANT4-statistical prediction" surface: the formula is the expected/truth, the
// run's measured tally is the prediction, and the engine emits both + the gap.
//   type = "beer_lambert": narrow-beam photon attenuation T = exp(-mu*x). The
//     linear attenuation coefficient mu is summed from G4EmCalculator
//     (photoelectric + Compton + Rayleigh + pair) at `energyMeV` in `material`,
//     and the predicted uncollided transmission exp(-mu*pathLengthMm) is checked
//     against the run's measured `primaries_uncollided_fraction`.
struct AnalyticCheckConfig {
  std::string type = "beer_lambert";
  std::string label;          // optional human label (default derived from type)
  std::string particle = "gamma";
  double energyMeV = 0.0;      // 0 => use the active beam energy
  std::string material;       // "" => use the medium material (else world)
  double pathLengthMm = 0.0;   // 0 => use the medium box side length
  double toleranceRel = 0.05;  // relative tolerance for the within_tolerance flag
};

struct AnalyticConfig {
  bool enable = false;
  std::vector<AnalyticCheckConfig> checks;
};

// Opt-in Geant4 material-composition probe. When enabled, the engine queries the
// constructed G4Material for each referenced material (world + medium + geometry
// volumes + declared mixtures, plus any names listed here) AFTER initialization
// and reports what Geant4 knows: mass density, per-element number density
// (atoms/cm^3), electron density, mean excitation energy, and radiation length.
// This is a physics-agnostic surface -- scenarios read it from hooks as
// `ctx.materials` (e.g. an NMR scenario weights signal by the Geant4-supplied
// proton number density instead of hard-coding it) and it is also emitted to
// `trech_scores.jsonl` as `material_probes`. Off by default so existing
// scenarios' outputs stay byte-identical.
struct MaterialProbeConfig {
  bool enable = false;
  std::vector<std::string> materials;  // extra material names beyond the referenced set
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

// A scenario-declared learned-inference model. Physics-agnostic: the engine
// only needs a name (to look it up from `ctx.predict`) and a path to a
// GenericSurrogate-loadable model file (portable `.json`, or `.pt` with Torch).
// What the model predicts is defined by the model file's own named inputs/
// outputs, so no domain switches live in C++.
struct ModelConfig {
  std::string name;
  std::string path;
  // Dimension-scale band for the multi-scale inference cascade
  // (`atomic`/`nano`/`micro`/`meso`/`macro`; empty = unscaled, runs last).
  // Physics-agnostic ordering hint only; what the model predicts lives in its
  // file. Consumed by ScaleCascade via `ctx.cascade`.
  std::string scale;
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
  // When set, an event whose onEventEnd inference (ctx.cascade/ctx.predict) ran
  // OUTSIDE the model's trained domain is routed to the resim queue as a
  // low-confidence candidate -- acting on the coverage flag, not just surfacing
  // it. Requires stratify.enable (owns the resim path) + dumpResimQueue to
  // actually write the queue file.
  bool resimOnLowConfidence = false;
};

struct LabConfig {
  bool enable = false;
  std::string mode = "scenario";
  std::string commandSchema = "trech_lab_command_v1";
  std::string commandChannel = "stdin_jsonl";
  int targetHz = 60;
  // Number of Geant4 events ("rounds") per real-time simulate tick. Zero is
  // adaptive: LabSession measures wall time per event and selects the next
  // count that fits targetHz. A positive value is the persistent scenario
  // override; simulate.events remains the one-command override.
  int roundsPerTick = 0;
  int minRoundsPerTick = 1;
  int maxRoundsPerTick = 100000;
  // EWMA gain for measured seconds/event. Higher reacts faster to scenario
  // edits; lower is steadier. Bounded to (0,1] by the parser.
  double roundLearningRate = 0.35;
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
  AnalyticConfig analytic;
  MaterialProbeConfig materialProbe;
  GeometryConfig geometry;
  std::vector<MaterialConfig> materials;
  std::vector<ModelConfig> models;
  HooksConfig hooks;
  StratifyConfig stratify;
  LabConfig lab;
  VizConfig viz;
};

TrechConfig configFromJsonString(const std::string& json);
std::string configToJsonString(const TrechConfig& cfg);

} // namespace trech
