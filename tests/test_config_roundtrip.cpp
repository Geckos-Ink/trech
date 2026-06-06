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
  cfg.detector.mediumBoxMm = 21.0;
  cfg.detector.mediumMaterial = "G4_WATER";
  cfg.detector.temperatureK = 285.0;
  cfg.detector.pressureAtm = 0.9;
  cfg.beam.particle = "proton";
  cfg.beam.energyMeV = 7.5;
  cfg.beam.directionX = 0.1;
  cfg.beam.directionY = 0.2;
  cfg.beam.directionZ = 0.3;
  cfg.beam.name = "primary";
  cfg.beam.originXMm = 1.5;
  cfg.beam.originYMm = -2.5;
  cfg.beam.originZMm = 3.5;
  cfg.beam.spotRadiusMm = 4.0;
  cfg.beam.divergenceDeg = 2.5;
  cfg.beam.energySpreadFractional = 0.05;
  cfg.beam.polarization = "linear";
  cfg.beam.polarizationAngleDeg = 35.0;
  cfg.beam.spectrum.push_back({2.0e-6, 0.7});
  cfg.beam.spectrum.push_back({2.5e-6, 0.3});
  cfg.beam.active = true;
  trech::BeamConfig altBeam;
  altBeam.name = "alt";
  altBeam.particle = "gamma";
  altBeam.energyMeV = 2.5;
  altBeam.directionX = -0.1;
  altBeam.directionY = 0.0;
  altBeam.directionZ = 1.0;
  altBeam.originXMm = -3.0;
  altBeam.spotRadiusMm = 0.5;
  altBeam.divergenceDeg = 0.25;
  altBeam.energySpreadFractional = 0.01;
  altBeam.polarization = "unpolarized";
  altBeam.active = false;
  cfg.beams.push_back(cfg.beam);
  cfg.beams.push_back(altBeam);
  cfg.run.nEvents = 17;
  cfg.run.seed = 98765;
  cfg.run.threads = 1;
  cfg.determinism.mode = "predictive";
  cfg.system.enable = true;
  cfg.system.mode = "equilibrium";
  cfg.system.frame = "point_agnostic";
  cfg.system.ensemble = "h2o_cluster";
  cfg.system.volumeMm3 = 1337.0;
  cfg.optics.enable = true;
  cfg.optics.refractiveIndex = 1.4;
  cfg.optics.absorptionLengthMm = 500.0;
  cfg.optics.scatterLengthMm = 250.0;
  trech::OpticsSpectrumPoint spectrumA;
  spectrumA.energyEv = 2.1;
  spectrumA.refractiveIndex = 1.35;
  spectrumA.absorptionLengthMm = 1200.0;
  spectrumA.scatterLengthMm = 800.0;
  cfg.optics.spectrum.push_back(spectrumA);
  trech::OpticsSpectrumPoint spectrumB;
  spectrumB.wavelengthNm = 480.0;
  spectrumB.refractiveIndex = 1.32;
  cfg.optics.spectrum.push_back(spectrumB);
  cfg.chemistry.enable = true;
  cfg.chemistry.model = "dna_water_g4";
  cfg.chemistry.solver = "stubs";
  cfg.nuclear.enable = true;
  trech::NuclearCycleConfig cycle;
  cycle.name = "nitrogen_carbon14_cycle";
  cycle.enable = true;
  cycle.source.symbol = "N";
  cycle.source.material = "G4_N";
  cycle.source.z = 7;
  cycle.source.a = 14;
  cycle.source.phase = "gas";
  cycle.source.densityGcm3 = 0.0012506;
  cycle.target.symbol = "C";
  cycle.target.material = "G4_C";
  cycle.target.z = 6;
  cycle.target.a = 14;
  cycle.target.phase = "solid";
  cycle.target.densityGcm3 = 2.267;
  cycle.forward.name = "n14_neutron_capture";
  cycle.forward.reactants = {{"", 7, 14}, {"neutron", 0, 0}};
  cycle.forward.products = {{"", 6, 14}, {"proton", 0, 0}};
  cycle.backward.name = "c14_beta_decay";
  cycle.backward.halfLifeYears = 5730.0;
  cycle.backward.reactants = {{"", 6, 14}};
  cycle.backward.products = {{"", 7, 14}, {"e-", 0, 0}, {"anti_nu_e", 0, 0}};
  cfg.nuclear.cycles.push_back(cycle);
  cfg.multiscale.enable = true;
  cfg.multiscale.method = "lbm_stub";
  cfg.multiscale.mode = "auto";
  trech::VolumeConfig volume;
  volume.name = "test_tube";
  volume.material = "G4_C";
  volume.shape.type = "tube";
  volume.shape.innerRadiusMm = 0.1;
  volume.shape.outerRadiusMm = 0.5;
  volume.shape.lengthMm = 2.0;
  volume.placement.parent = "medium";
  volume.placement.positionMm.x = 1.0;
  volume.placement.positionMm.y = 2.0;
  volume.placement.positionMm.z = 3.0;
  volume.placement.rotationDeg.x = 10.0;
  volume.placement.rotationDeg.y = 20.0;
  volume.placement.rotationDeg.z = 30.0;
  volume.scoreEdep = true;
  volume.tags = {"probe", "carbon"};
  cfg.geometry.volumes.push_back(volume);
  trech::MaterialConfig brine;
  brine.name = "brine";
  brine.smiles = "Cl[Na]";
  brine.densityGcm3 = 1.02;
  trech::MaterialComponentConfig brineWater;
  brineWater.material = "G4_WATER";
  brineWater.fraction = 0.98;
  brine.components.push_back(brineWater);
  // Element component (no NIST G4_SODIUM_CHLORIDE exists): exercise the
  // element form of MaterialComponentConfig through the round-trip.
  trech::MaterialComponentConfig brineSodium;
  brineSodium.element = "Na";
  brineSodium.fraction = 0.02;
  brine.components.push_back(brineSodium);
  cfg.materials.push_back(brine);
  cfg.hooks.registered = {"onInit", "onRunStart"};
  cfg.hooks.maxStepCallbacks = 4321;
  cfg.hooks.maxEmitsPerCallback = 12;
  cfg.hooks.maxEmitPayloadBytes = 2048;
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
  cfg.lab.enable = true;
  cfg.lab.mode = "realtime";
  cfg.lab.commandSchema = "trech_lab_command_v1";
  cfg.lab.commandChannel = "stdin_jsonl";
  cfg.lab.targetHz = 120;

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
  if (!almostEqual(parsed.detector.mediumBoxMm, cfg.detector.mediumBoxMm)) {
    std::cerr << "Detector mediumBoxMm mismatch\n";
    return 1;
  }
  if (parsed.detector.mediumMaterial != cfg.detector.mediumMaterial) {
    std::cerr << "Detector mediumMaterial mismatch\n";
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
  if (parsed.beam.name != cfg.beam.name) {
    std::cerr << "Beam name mismatch\n";
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
  if (parsed.beam.active != cfg.beam.active) {
    std::cerr << "Beam active mismatch\n";
    return 1;
  }
  if (!almostEqual(parsed.beam.originXMm, cfg.beam.originXMm) ||
      !almostEqual(parsed.beam.originYMm, cfg.beam.originYMm) ||
      !almostEqual(parsed.beam.originZMm, cfg.beam.originZMm)) {
    std::cerr << "Beam origin mismatch\n";
    return 1;
  }
  if (!almostEqual(parsed.beam.spotRadiusMm, cfg.beam.spotRadiusMm) ||
      !almostEqual(parsed.beam.divergenceDeg, cfg.beam.divergenceDeg) ||
      !almostEqual(parsed.beam.energySpreadFractional,
                   cfg.beam.energySpreadFractional)) {
    std::cerr << "Beam spread mismatch\n";
    return 1;
  }
  if (parsed.beam.polarization != cfg.beam.polarization ||
      !almostEqual(parsed.beam.polarizationAngleDeg,
                   cfg.beam.polarizationAngleDeg)) {
    std::cerr << "Beam polarization mismatch\n";
    return 1;
  }
  if (parsed.beam.spectrum.size() != cfg.beam.spectrum.size()) {
    std::cerr << "Beam spectrum size mismatch\n";
    return 1;
  }
  for (std::size_t si = 0; si < cfg.beam.spectrum.size(); ++si) {
    if (!almostEqual(parsed.beam.spectrum[si].energyMeV,
                     cfg.beam.spectrum[si].energyMeV) ||
        !almostEqual(parsed.beam.spectrum[si].weight,
                     cfg.beam.spectrum[si].weight)) {
      std::cerr << "Beam spectrum mismatch at index " << si << "\n";
      return 1;
    }
  }
  if (parsed.beams.size() != cfg.beams.size()) {
    std::cerr << "Beams size mismatch\n";
    return 1;
  }
  for (std::size_t idx = 0; idx < cfg.beams.size(); ++idx) {
    const auto& expected = cfg.beams[idx];
    const auto& actual = parsed.beams[idx];
    if (actual.name != expected.name) {
      std::cerr << "Beams name mismatch\n";
      return 1;
    }
    if (actual.particle != expected.particle) {
      std::cerr << "Beams particle mismatch\n";
      return 1;
    }
    if (!almostEqual(actual.energyMeV, expected.energyMeV)) {
      std::cerr << "Beams energyMeV mismatch\n";
      return 1;
    }
    if (!almostEqual(actual.directionX, expected.directionX) ||
        !almostEqual(actual.directionY, expected.directionY) ||
        !almostEqual(actual.directionZ, expected.directionZ)) {
      std::cerr << "Beams direction mismatch\n";
      return 1;
    }
    if (actual.active != expected.active) {
      std::cerr << "Beams active mismatch\n";
      return 1;
    }
    if (!almostEqual(actual.originXMm, expected.originXMm) ||
        !almostEqual(actual.originYMm, expected.originYMm) ||
        !almostEqual(actual.originZMm, expected.originZMm)) {
      std::cerr << "Beams origin mismatch\n";
      return 1;
    }
    if (!almostEqual(actual.spotRadiusMm, expected.spotRadiusMm) ||
        !almostEqual(actual.divergenceDeg, expected.divergenceDeg) ||
        !almostEqual(actual.energySpreadFractional,
                     expected.energySpreadFractional)) {
      std::cerr << "Beams spread mismatch\n";
      return 1;
    }
    if (actual.polarization != expected.polarization ||
        !almostEqual(actual.polarizationAngleDeg,
                     expected.polarizationAngleDeg)) {
      std::cerr << "Beams polarization mismatch\n";
      return 1;
    }
  }
  if (parsed.run.nEvents != cfg.run.nEvents) {
    std::cerr << "Run nEvents mismatch\n";
    return 1;
  }
  if (parsed.run.threads != cfg.run.threads) {
    std::cerr << "Run threads mismatch\n";
    return 1;
  }
  if (parsed.run.seed != cfg.run.seed) {
    std::cerr << "Run seed mismatch\n";
    return 1;
  }
  if (parsed.determinism.mode != cfg.determinism.mode) {
    std::cerr << "Determinism mode mismatch\n";
    return 1;
  }
  if (parsed.system.enable != cfg.system.enable) {
    std::cerr << "System enable mismatch\n";
    return 1;
  }
  if (parsed.system.mode != cfg.system.mode) {
    std::cerr << "System mode mismatch\n";
    return 1;
  }
  if (parsed.system.frame != cfg.system.frame) {
    std::cerr << "System frame mismatch\n";
    return 1;
  }
  if (parsed.system.ensemble != cfg.system.ensemble) {
    std::cerr << "System ensemble mismatch\n";
    return 1;
  }
  if (!almostEqual(parsed.system.volumeMm3, cfg.system.volumeMm3)) {
    std::cerr << "System volumeMm3 mismatch\n";
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
  if (parsed.optics.spectrum.size() != cfg.optics.spectrum.size()) {
    std::cerr << "Optics spectrum size mismatch\n";
    return 1;
  }
  for (std::size_t idx = 0; idx < cfg.optics.spectrum.size(); ++idx) {
    const auto& expected = cfg.optics.spectrum[idx];
    const auto& actual = parsed.optics.spectrum[idx];
    if (!almostEqual(actual.energyEv, expected.energyEv)) {
      std::cerr << "Optics spectrum energyEv mismatch\n";
      return 1;
    }
    if (!almostEqual(actual.wavelengthNm, expected.wavelengthNm)) {
      std::cerr << "Optics spectrum wavelengthNm mismatch\n";
      return 1;
    }
    if (!almostEqual(actual.refractiveIndex, expected.refractiveIndex)) {
      std::cerr << "Optics spectrum refractiveIndex mismatch\n";
      return 1;
    }
    if (!almostEqual(actual.absorptionLengthMm, expected.absorptionLengthMm)) {
      std::cerr << "Optics spectrum absorptionLengthMm mismatch\n";
      return 1;
    }
    if (!almostEqual(actual.scatterLengthMm, expected.scatterLengthMm)) {
      std::cerr << "Optics spectrum scatterLengthMm mismatch\n";
      return 1;
    }
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
  if (parsed.nuclear.enable != cfg.nuclear.enable) {
    std::cerr << "Nuclear enable mismatch\n";
    return 1;
  }
  if (parsed.nuclear.cycles.size() != cfg.nuclear.cycles.size()) {
    std::cerr << "Nuclear cycles size mismatch\n";
    return 1;
  }
  if (!parsed.nuclear.cycles.empty()) {
    const auto& expected = cfg.nuclear.cycles.front();
    const auto& actual = parsed.nuclear.cycles.front();
    if (actual.name != expected.name || actual.enable != expected.enable) {
      std::cerr << "Nuclear cycle metadata mismatch\n";
      return 1;
    }
    if (actual.source.symbol != expected.source.symbol ||
        actual.source.material != expected.source.material ||
        actual.source.z != expected.source.z || actual.source.a != expected.source.a ||
        actual.source.phase != expected.source.phase ||
        !almostEqual(actual.source.densityGcm3, expected.source.densityGcm3)) {
      std::cerr << "Nuclear cycle source mismatch\n";
      return 1;
    }
    if (actual.target.symbol != expected.target.symbol ||
        actual.target.material != expected.target.material ||
        actual.target.z != expected.target.z || actual.target.a != expected.target.a ||
        actual.target.phase != expected.target.phase ||
        !almostEqual(actual.target.densityGcm3, expected.target.densityGcm3)) {
      std::cerr << "Nuclear cycle target mismatch\n";
      return 1;
    }
    if (actual.forward.name != expected.forward.name ||
        actual.forward.reactants.size() != expected.forward.reactants.size() ||
        actual.forward.products.size() != expected.forward.products.size()) {
      std::cerr << "Nuclear cycle forward mismatch\n";
      return 1;
    }
    if (actual.backward.name != expected.backward.name ||
        !almostEqual(actual.backward.halfLifeYears, expected.backward.halfLifeYears) ||
        actual.backward.reactants.size() != expected.backward.reactants.size() ||
        actual.backward.products.size() != expected.backward.products.size()) {
      std::cerr << "Nuclear cycle backward mismatch\n";
      return 1;
    }
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
  if (parsed.geometry.volumes.size() != cfg.geometry.volumes.size()) {
    std::cerr << "Geometry volume count mismatch\n";
    return 1;
  }
  if (!parsed.geometry.volumes.empty()) {
    const auto& expected = cfg.geometry.volumes.front();
    const auto& actual = parsed.geometry.volumes.front();
    if (actual.name != expected.name) {
      std::cerr << "Geometry volume name mismatch\n";
      return 1;
    }
    if (actual.material != expected.material) {
      std::cerr << "Geometry volume material mismatch\n";
      return 1;
    }
    if (actual.shape.type != expected.shape.type) {
      std::cerr << "Geometry volume shape type mismatch\n";
      return 1;
    }
    if (!almostEqual(actual.shape.innerRadiusMm, expected.shape.innerRadiusMm) ||
        !almostEqual(actual.shape.outerRadiusMm, expected.shape.outerRadiusMm) ||
        !almostEqual(actual.shape.lengthMm, expected.shape.lengthMm)) {
      std::cerr << "Geometry volume shape mismatch\n";
      return 1;
    }
    if (actual.placement.parent != expected.placement.parent) {
      std::cerr << "Geometry volume parent mismatch\n";
      return 1;
    }
    if (!almostEqual(actual.placement.positionMm.x, expected.placement.positionMm.x) ||
        !almostEqual(actual.placement.positionMm.y, expected.placement.positionMm.y) ||
        !almostEqual(actual.placement.positionMm.z, expected.placement.positionMm.z)) {
      std::cerr << "Geometry volume position mismatch\n";
      return 1;
    }
    if (!almostEqual(actual.placement.rotationDeg.x, expected.placement.rotationDeg.x) ||
        !almostEqual(actual.placement.rotationDeg.y, expected.placement.rotationDeg.y) ||
        !almostEqual(actual.placement.rotationDeg.z, expected.placement.rotationDeg.z)) {
      std::cerr << "Geometry volume rotation mismatch\n";
      return 1;
    }
    if (actual.scoreEdep != expected.scoreEdep) {
      std::cerr << "Geometry volume scoreEdep mismatch\n";
      return 1;
    }
    if (actual.tags != expected.tags) {
      std::cerr << "Geometry volume tags mismatch\n";
      return 1;
    }
  }
  if (parsed.materials.size() != cfg.materials.size()) {
    std::cerr << "Materials size mismatch\n";
    return 1;
  }
  if (!parsed.materials.empty()) {
    const auto& expected = cfg.materials.front();
    const auto& actual = parsed.materials.front();
    if (actual.name != expected.name) {
      std::cerr << "Material name mismatch\n";
      return 1;
    }
    if (actual.smiles != expected.smiles) {
      std::cerr << "Material smiles mismatch\n";
      return 1;
    }
    if (!almostEqual(actual.densityGcm3, expected.densityGcm3)) {
      std::cerr << "Material density mismatch\n";
      return 1;
    }
    if (actual.components.size() != expected.components.size()) {
      std::cerr << "Material components size mismatch\n";
      return 1;
    }
    for (std::size_t ci = 0; ci < actual.components.size(); ++ci) {
      if (actual.components[ci].material != expected.components[ci].material ||
          actual.components[ci].element != expected.components[ci].element ||
          !almostEqual(actual.components[ci].fraction,
                       expected.components[ci].fraction)) {
        std::cerr << "Material components mismatch at index " << ci << "\n";
        return 1;
      }
    }
  }
  if (parsed.hooks.registered != cfg.hooks.registered) {
    std::cerr << "Hooks registered mismatch\n";
    return 1;
  }
  if (parsed.hooks.maxStepCallbacks != cfg.hooks.maxStepCallbacks) {
    std::cerr << "Hooks maxStepCallbacks mismatch\n";
    return 1;
  }
  if (parsed.hooks.maxEmitsPerCallback != cfg.hooks.maxEmitsPerCallback) {
    std::cerr << "Hooks maxEmitsPerCallback mismatch\n";
    return 1;
  }
  if (parsed.hooks.maxEmitPayloadBytes != cfg.hooks.maxEmitPayloadBytes) {
    std::cerr << "Hooks maxEmitPayloadBytes mismatch\n";
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
  if (parsed.lab.enable != cfg.lab.enable) {
    std::cerr << "Lab enable mismatch\n";
    return 1;
  }
  if (parsed.lab.mode != cfg.lab.mode) {
    std::cerr << "Lab mode mismatch\n";
    return 1;
  }
  if (parsed.lab.commandSchema != cfg.lab.commandSchema) {
    std::cerr << "Lab commandSchema mismatch\n";
    return 1;
  }
  if (parsed.lab.commandChannel != cfg.lab.commandChannel) {
    std::cerr << "Lab commandChannel mismatch\n";
    return 1;
  }
  if (parsed.lab.targetHz != cfg.lab.targetHz) {
    std::cerr << "Lab targetHz mismatch\n";
    return 1;
  }

  const std::string compactJson = R"({
    "materials": {
      "name": "water",
      "densityGcm3": 1.0,
      "components": { "material": "G4_WATER", "fraction": 1.0 }
    },
    "geometry": {
      "volumes": {
        "name": "solo_box",
        "material": "water",
        "scoreEdep": true,
        "tags": "sample",
        "shape": { "type": "box", "sizeMm": [1.0, 2.0, 3.0] },
        "placement": {
          "parent": "world",
          "positionMm": [0.0, 0.0, 0.0],
          "rotationDeg": [0.0, 0.0, 0.0]
        }
      }
    },
    "determinism": { "predictive": false },
    "optics": { "spectrum": { "wavelengthNm": 450.0, "refractiveIndex": 1.33 } },
    "hooks": {
      "registered": "onInit",
      "maxStepCallbacks": 12,
      "maxEmitsPerCallback": 3,
      "maxEmitPayloadBytes": 64
    },
    "lab": {
      "enable": true,
      "mode": "realtime",
      "commandSchema": "trech_lab_command_v1",
      "commandChannel": "stdin_jsonl",
      "targetHz": 30
    },
    "nuclear": {
      "enable": true,
      "cycles": {
        "name": "compact_cycle",
        "source": { "symbol": "N", "z": 7, "a": 14 },
        "target": { "symbol": "C", "z": 6, "a": 14 },
        "forward": {
          "reactants": { "z": 7, "a": 14 },
          "products": { "z": 6, "a": 14 }
        }
      }
    }
  })";

  const trech::TrechConfig compact = trech::configFromJsonString(compactJson);
  if (compact.materials.size() != 1) {
    std::cerr << "Compact materials size mismatch\n";
    return 1;
  }
  if (compact.materials.front().components.size() != 1) {
    std::cerr << "Compact material components size mismatch\n";
    return 1;
  }
  if (compact.geometry.volumes.size() != 1) {
    std::cerr << "Compact geometry volumes size mismatch\n";
    return 1;
  }
  if (compact.geometry.volumes.front().tags.size() != 1 ||
      compact.geometry.volumes.front().tags.front() != "sample") {
    std::cerr << "Compact geometry tags mismatch\n";
    return 1;
  }
  if (compact.optics.spectrum.size() != 1) {
    std::cerr << "Compact optics spectrum size mismatch\n";
    return 1;
  }
  if (compact.determinism.mode != "strict") {
    std::cerr << "Compact determinism mode mismatch\n";
    return 1;
  }
  if (compact.hooks.registered.size() != 1 || compact.hooks.registered.front() != "onInit") {
    std::cerr << "Compact hooks registered mismatch\n";
    return 1;
  }
  if (compact.hooks.maxStepCallbacks != 12) {
    std::cerr << "Compact hooks maxStepCallbacks mismatch\n";
    return 1;
  }
  if (compact.hooks.maxEmitsPerCallback != 3) {
    std::cerr << "Compact hooks maxEmitsPerCallback mismatch\n";
    return 1;
  }
  if (compact.hooks.maxEmitPayloadBytes != 64) {
    std::cerr << "Compact hooks maxEmitPayloadBytes mismatch\n";
    return 1;
  }
  if (!compact.lab.enable || compact.lab.mode != "realtime" ||
      compact.lab.commandSchema != "trech_lab_command_v1" ||
      compact.lab.commandChannel != "stdin_jsonl" || compact.lab.targetHz != 30) {
    std::cerr << "Compact lab config mismatch\n";
    return 1;
  }
  if (!compact.nuclear.enable) {
    std::cerr << "Compact nuclear enable mismatch\n";
    return 1;
  }
  if (compact.nuclear.cycles.size() != 1) {
    std::cerr << "Compact nuclear cycles size mismatch\n";
    return 1;
  }
  if (compact.nuclear.cycles.front().forward.reactants.size() != 1 ||
      compact.nuclear.cycles.front().forward.products.size() != 1) {
    std::cerr << "Compact nuclear participant normalization mismatch\n";
    return 1;
  }

  // Beam source variety accepts a nested `spread` object; flat keys override.
  const std::string beamSpreadJson = R"({
    "beam": {
      "particle": "opticalphoton",
      "energyMeV": 2.25e-6,
      "direction": [0.5, 0.0, 0.8660254],
      "originMm": [-75.0, 0.0, -110.0],
      "spread": {
        "spotRadiusMm": 6.0,
        "divergenceDeg": 1.5,
        "energySpreadFractional": 0.04
      },
      "divergenceDeg": 2.0
    }
  })";
  const trech::TrechConfig beamSpread = trech::configFromJsonString(beamSpreadJson);
  if (!almostEqual(beamSpread.beam.originXMm, -75.0) ||
      !almostEqual(beamSpread.beam.originZMm, -110.0)) {
    std::cerr << "Beam spread originMm parse mismatch\n";
    return 1;
  }
  if (!almostEqual(beamSpread.beam.spotRadiusMm, 6.0) ||
      !almostEqual(beamSpread.beam.energySpreadFractional, 0.04)) {
    std::cerr << "Beam spread nested-object parse mismatch\n";
    return 1;
  }
  if (!almostEqual(beamSpread.beam.divergenceDeg, 2.0)) {
    std::cerr << "Beam spread flat-key precedence mismatch\n";
    return 1;
  }

  const std::string environmentAliasJson = R"({
    "environment": {
      "worldSizeMm": 250.0,
      "worldMaterial": "G4_AIR",
      "mediumBoxMm": 125.0,
      "mediumMaterial": "G4_WATER",
      "temperatureK": 300.0,
      "pressureAtm": 1.2
    }
  })";
  const trech::TrechConfig environmentAlias =
      trech::configFromJsonString(environmentAliasJson);
  if (!almostEqual(environmentAlias.detector.worldSizeMm, 250.0) ||
      environmentAlias.detector.worldMaterial != "G4_AIR" ||
      !almostEqual(environmentAlias.detector.mediumBoxMm, 125.0) ||
      environmentAlias.detector.mediumMaterial != "G4_WATER" ||
      !almostEqual(environmentAlias.detector.temperatureK, 300.0) ||
      !almostEqual(environmentAlias.detector.pressureAtm, 1.2)) {
    std::cerr << "Environment alias detector parse mismatch\n";
    return 1;
  }

  const std::string mediumAliasJson = R"({
    "medium": {
      "worldSizeMm": 180.0,
      "worldMaterial": "G4_Galactic",
      "mediumBoxMm": 90.0,
      "mediumMaterial": "G4_WATER"
    }
  })";
  const trech::TrechConfig mediumAlias = trech::configFromJsonString(mediumAliasJson);
  if (!almostEqual(mediumAlias.detector.worldSizeMm, 180.0) ||
      mediumAlias.detector.worldMaterial != "G4_Galactic" ||
      !almostEqual(mediumAlias.detector.mediumBoxMm, 90.0) ||
      mediumAlias.detector.mediumMaterial != "G4_WATER") {
    std::cerr << "Medium alias detector parse mismatch\n";
    return 1;
  }

  const std::string detectorPrecedenceJson = R"({
    "environment": {
      "worldSizeMm": 100.0,
      "worldMaterial": "G4_AIR",
      "mediumBoxMm": 50.0,
      "mediumMaterial": "G4_WATER"
    },
    "detector": {
      "worldSizeMm": 75.0,
      "worldMaterial": "G4_Galactic",
      "mediumBoxMm": 25.0,
      "mediumMaterial": "G4_POLYSTYRENE"
    }
  })";
  const trech::TrechConfig detectorPrecedence =
      trech::configFromJsonString(detectorPrecedenceJson);
  if (!almostEqual(detectorPrecedence.detector.worldSizeMm, 75.0) ||
      detectorPrecedence.detector.worldMaterial != "G4_Galactic" ||
      !almostEqual(detectorPrecedence.detector.mediumBoxMm, 25.0) ||
      detectorPrecedence.detector.mediumMaterial != "G4_POLYSTYRENE") {
    std::cerr << "Detector precedence mismatch\n";
    return 1;
  }

  return 0;
}
