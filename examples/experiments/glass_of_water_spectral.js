// Chromatic-dispersion demo: a *white* (blackbody) source through the glass of
// water. Where glass_of_water_varied.js fires a narrow green band, this scenario
// fires the full visible spectrum, so each photon's wavelength is sampled across
// 380-750 nm and refracts at its OWN angle through the derived n(lambda) tables.
//
// Nothing about the dispersion is hard-coded: MolecularOptics derives n(lambda)
// from Geant4 cross sections + the f-sum valence oscillator, which produces real
// (if under-recovered) normal dispersion -- n is higher toward the violet. A
// blackbody source therefore fans into colours through the cup the way a prism
// does, and the per-segment wavelength colouring in the 3D viewer shows it.
//
// The spectrum is built by the JS helper (the engine stays physics-agnostic):
//   helpers.spectra.blackbody(5778)  -> [{wavelengthNm, weight}, ...] weighted
//   by the Planck radiance of ~sunlight. The engine samples one line per event.
//
// Run:
//   trech run examples/experiments/glass_of_water_spectral.js \
//        --events 3000 --output build/dev/out_gow_spectral
// Then inspect wavelength spread / dispersion with
//   scripts/degeneration_metrics.py build/dev/out_gow_spectral
// or render the trajectories with the trech-viz CLI.

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

// A nominal energy is still required (it seeds the gun); the spectrum overrides
// it per event. Use mid-visible green so a spectrum-less fallback stays sane.
const nominalEnergyMeV = 2.25e-6;

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

// ~5778 K (sunlight) blackbody over the visible band, 32 lines.
const sunlightSpectrum = helpers.spectra.blackbody(5778, { bins: 32 });

const cfg = {
  detector: {
    worldSizeMm: worldSizeMm,
    worldMaterial: "air",
    temperatureK: 293.15,
    pressureAtm: 1.0
  },
  beam: {
    particle: "opticalphoton",
    energyMeV: nominalEnergyMeV,
    direction: [sinT, 0.0, cosT],
    originMm: emitterPositionMm,
    // Full-visible emission spectrum (the headline of this demo) plus a gentle
    // spatial/angular spread so the run also samples a real beam profile.
    spectrum: sunlightSpectrum,
    spread: {
      spotRadiusMm: units.cm(0.6),
      divergenceDeg: 1.0
    }
  },
  run: { nEvents: 3000, seed: 20260606 },
  determinism: { mode: "predictive" },
  system: {
    enable: true,
    mode: "steady_state",
    frame: "point_agnostic",
    ensemble: "glass_of_water_spectral"
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
    maxTrajectories: 3000,
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
