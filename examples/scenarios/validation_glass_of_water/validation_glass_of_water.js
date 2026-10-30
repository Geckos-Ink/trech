// Validation scenario: a beam of light enters a glass slab containing a
// water bulk, then exits back into air -- the "glass of water" cross
// section, modeled with planar (axis-aligned) interfaces so that the
// surface normal at every refraction is exactly one of +/- x, y, z.
// Planar normals are what lets the companion validator
// (scripts/validate_glass_of_water.py) invert the classical optics
// formulas with no ambiguity.
//
// The scenario does *not* hard-code n_air / n_glass / n_water as
// refractiveIndex tables. Instead it declares the three materials by
// chemical composition only and lets `optics.derive` (MolecularOptics)
// extract the dispersion tables from Geant4 photoelectric + Compton +
// Rayleigh cross sections via Beer-Lambert + Kramers-Kronig. Geant4's
// optical photon transport then samples refraction / Fresnel reflection /
// absorption on those derived tables.
//
// The validator reads the resulting trajectories and runs the inverse
// problem: given the *measured* (theta_i, theta_r) at each interface
// and the *measured* transmitted fraction, solve Snell / Fresnel / Beer
// for n2 (or for alpha) and compare those inferred constants to handbook
// references for air, glass and water. The handbook values appear here
// only as `validate.references` (recorded into the run for the report);
// they never feed back into physics.
//
// Run:
//   trech run examples/scenarios/validation_glass_of_water/validation_glass_of_water.js \
//        --events 4000 --output build/dev/out_validation_gow
// Validate:
//   python3 scripts/validate_glass_of_water.py \
//        --run build/dev/out_validation_gow

TRECH_INCLUDE("../../../js/trech_helpers.js");
const helpers = globalThis.TRECH_HELPERS;
if (!helpers) {
  throw new Error("TRECH_HELPERS not available; include trech_helpers.js");
}

const units = helpers.units;
const geometry = helpers.geometry;

// World / volume sizes. The glass slab is the "cup" cross-section; the
// water bulk sits inside it (so a photon traveling +z hits air->glass at
// the top of the slab, glass->water further down, water->glass at the
// bottom of the water bulk, then glass->air at the bottom of the slab).
const worldSizeMm = units.cm(30.0);
const glassSizeMm = [units.cm(10.0), units.cm(10.0), units.cm(6.0)];
const waterSizeMm = [units.cm(8.0),  units.cm(8.0),  units.cm(4.0)];
const emitterSizeMm = [units.cm(2.0), units.cm(2.0), units.cm(0.5)];

// Single oblique incidence: 30 deg from normal in the x-z plane.
// 30 deg makes total-internal-reflection impossible at any of the
// interfaces involved here (n2 > n1*sin(theta_i) is comfortably
// satisfied), so every photon either refracts or Fresnel-reflects --
// the validator can count both.
const incidenceDeg = 30.0;
const theta = incidenceDeg * Math.PI / 180.0;
const sinT = Math.sin(theta);
const cosT = Math.cos(theta);
const beamEnergyEv = 2.25;                    // ~ 550 nm green light
const beamEnergyMeV = beamEnergyEv * 1.0e-6;

// Emission point: in the air above the glass, offset along -x so the oblique
// (+x, +z) beam enters the glass top face near the centre and then crosses
// air -> glass -> water -> glass -> air. The beam fires from here; without an
// explicit origin the gun would fire from the world origin, which sits inside
// the water bulk (no air -> glass entry to measure).
const emitterPosMm = [
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
    originMm: emitterPosMm,
    direction: [sinT, 0.0, cosT]
  },
  run: { nEvents: 4000, seed: 20260525 },
  determinism: { mode: "strict" },
  system: {
    enable: true,
    mode: "steady_state",
    frame: "point_agnostic",
    ensemble: "validation_glass_of_water"
  },
  materials: [airMaterial, glassMaterial, waterMaterial],
  optics: {
    enable: true,
    derive: {
      enable: true,
      mode: "microscale_geant4",
      // Visible band, fairly tight around 550 nm so the derived n at
      // the beam wavelength is well sampled.
      energyMinEv: 1.6,
      energyMaxEv: 3.2,
      nEnergyBins: 16,
      kkIntegrationMinEv: 50.0,
      kkIntegrationMaxEv: 200000.0,
      kkIntegrationBins: 256,
      writeSpectrum: true,
      validate: TRECH_CHECKS["validation_glass_of_water"]["opticsReferences0"](beamEnergyEv)
    }
  },
  viz: TRECH_VIEWS["validation_glass_of_water"]["viz0"](),
  geometry: {
    volumes: [
      // Light source: thin slab placed above and offset along -x so
      // that the oblique beam enters the glass top face near the
      // center. Tagged so the 3D viewer can render it as a forced
      // light (visualization only -- no physics effect).
      geometry.boxVolume({
        name: "emitter",
        material: "air",
        sizeMm: emitterSizeMm,
        positionMm: emitterPosMm,
        tags: TRECH_VIEWS["validation_glass_of_water"]["tags1"]()
      }),
      // Glass slab -- composition only (SiO2). The MolecularOptics
      // derivation reads density + composition and produces n / abs /
      // scat tables from Geant4 cross sections; no hard-coded optics
      // here.
      geometry.boxVolume({
        name: "glass_cup",
        material: "glass",
        sizeMm: glassSizeMm,
        positionMm: [0.0, 0.0, 0.0],
        scoreEdep: true,
        tags: ["dielectric", "glass", "cup"]
      }),
      // Water bulk inside the glass slab.
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
