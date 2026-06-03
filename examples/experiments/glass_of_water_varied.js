// Anti-degeneration demo scenario: the same glass-of-water optics as
// validation_glass_of_water.js, but with a *varied* source so the run samples
// a real distribution of photons instead of one repeated primary.
//
// The strict validator scenario (validation_glass_of_water.js) deliberately
// fires a single collimated, monochromatic photon from a point so the inverse
// Snell/Fresnel solver sees a clean single incidence. That made every recorded
// trajectory identical -- a degenerate run. This sibling turns on the beam
// `spread` knobs landed in the engine:
//
//   - originMm                -> fire from the emitter slab outside the cup so
//                               photons cross air -> glass -> water -> glass ->
//                               air (a full, realistic optical path).
//   - spread.spotRadiusMm     -> emit over a disk, not a point.
//   - spread.divergenceDeg    -> small angular fan about the nominal direction.
//   - spread.energySpreadFractional -> a green energy band (~530-575 nm), so
//                               wavelength (and colour) varies photon to photon.
//
// All randomness draws from Geant4's seeded engine, so the run stays
// reproducible under a fixed seed; the spread adds distribution, not noise.
//
// Run:
//   trech run examples/experiments/glass_of_water_varied.js \
//        --events 2000 --output build/dev/out_gow_varied
// Then inspect trajectory diversity (distinct exit points, incidence-angle and
// wavelength spread) or render the comparison demo against this run.

TRECH_INCLUDE("trech_helpers.js");
const helpers = globalThis.TRECH_HELPERS;
if (!helpers) {
  throw new Error("TRECH_HELPERS not available; include trech_helpers.js");
}

const units = helpers.units;
const geometry = helpers.geometry;

const worldSizeMm = units.cm(30.0);
const glassSizeMm = [units.cm(10.0), units.cm(10.0), units.cm(6.0)];
const waterSizeMm = [units.cm(8.0),  units.cm(8.0),  units.cm(4.0)];
const emitterSizeMm = [units.cm(2.0), units.cm(2.0), units.cm(0.5)];

const incidenceDeg = 30.0;
const theta = incidenceDeg * Math.PI / 180.0;
const sinT = Math.sin(theta);
const cosT = Math.cos(theta);
const beamEnergyEv = 2.25;                    // ~550 nm green light
const beamEnergyMeV = beamEnergyEv * 1.0e-6;

// Emitter slab sits outside the cup on the -z side, offset along -x so the
// oblique beam enters the glass near the centre. Fire the gun from here.
const emitterPositionMm = [
  -0.5 * worldSizeMm * sinT,
  0.0,
  -0.5 * worldSizeMm * cosT + units.cm(2.0)
];

const airMaterial = helpers.materialRegistry.fromPreset("air");
const glassMaterial = helpers.materialRegistry.fromPreset("glass");
const waterMaterial = helpers.materialRegistry.fromPreset("water", {
  densityGcm3: 0.997
});

const cfg = {
  detector: {
    worldSizeMm: worldSizeMm,
    worldMaterial: "air",
    temperatureK: 293.15,
    pressureAtm: 1.0
  },
  beam: {
    particle: "opticalphoton",
    energyMeV: beamEnergyMeV,
    direction: [sinT, 0.0, cosT],
    originMm: emitterPositionMm,
    // Anti-degeneration: spread the source across space, angle, and energy.
    spread: {
      spotRadiusMm: units.cm(0.6),          // 6 mm emission disk
      divergenceDeg: 1.5,                    // gentle fan
      energySpreadFractional: 0.04           // ~+/- 9% wavelength band
    }
  },
  run: { nEvents: 2000, seed: 20260603 },
  // Predictive (not strict) so the spread/distribution is the whole point;
  // determinism still holds for a fixed seed.
  determinism: { mode: "predictive" },
  system: {
    enable: true,
    mode: "steady_state",
    frame: "point_agnostic",
    ensemble: "glass_of_water_varied"
  },
  materials: [airMaterial, glassMaterial, waterMaterial],
  optics: {
    enable: true,
    derive: {
      enable: true,
      mode: "microscale_geant4",
      energyMinEv: 1.6,
      energyMaxEv: 3.2,
      nEnergyBins: 16,
      kkIntegrationMinEv: 50.0,
      kkIntegrationMaxEv: 200000.0,
      kkIntegrationBins: 256,
      writeSpectrum: true
    }
  },
  viz: {
    enable: true,
    maxTrajectories: 2000,
    sampleEveryNth: 1,
    maxSegmentsPerTrajectory: 64,
    includeNonOptical: false,
    recordVertices: true
  },
  geometry: {
    volumes: [
      geometry.boxVolume({
        name: "emitter",
        material: "air",
        sizeMm: emitterSizeMm,
        positionMm: emitterPositionMm,
        tags: ["viz_emitter", "viz_forced_white"]
      }),
      geometry.boxVolume({
        name: "glass_cup",
        material: "glass",
        sizeMm: glassSizeMm,
        positionMm: [0.0, 0.0, 0.0],
        scoreEdep: true,
        tags: ["dielectric", "glass", "cup"]
      }),
      geometry.boxVolume({
        name: "water_bulk",
        material: "water",
        sizeMm: waterSizeMm,
        parent: "glass_cup",
        positionMm: [0.0, 0.0, 0.0],
        scoreEdep: true,
        tags: ["fluid", "water"]
      })
    ]
  }
};

globalThis.TRECH_CONFIG = cfg;
