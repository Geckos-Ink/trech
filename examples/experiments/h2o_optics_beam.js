TRECH_INCLUDE("trech_helpers.js");
const helpers = globalThis.TRECH_HELPERS;
if (!helpers) {
  throw new Error("TRECH_HELPERS not available; include trech_helpers.js");
}

const units = helpers.units;
const mediumBoxMm = units.cm(10.0);
const worldSizeMm = units.cm(20.0);
const mediumVolumeMm3 = mediumBoxMm * mediumBoxMm * mediumBoxMm;

const waterMaterial = helpers.materialRegistry.fromPreset("water", {
  densityGcm3: 0.997
});

const cfg = {
  detector: {
    worldSizeMm: worldSizeMm,
    worldMaterial: helpers.materialAliases.air,
    mediumBoxMm: mediumBoxMm,
    mediumMaterial: "water",
    temperatureK: 293.15,
    pressureAtm: 1.0
  },
  beam: {
    particle: "opticalphoton",
    energyMeV: 2.5e-6,
    direction: [0, 0, 1]
  },
  run: { nEvents: 500, seed: 424242 },
  system: {
    enable: true,
    mode: "steady_state",
    frame: "point_agnostic",
    ensemble: "h2o_optics_beam",
    volumeMm3: mediumVolumeMm3
  },
  optics: {
    enable: true,
    refractiveIndex: 1.333,
    absorptionLengthMm: 10000.0,
    scatterLengthMm: 10000.0,
    spectrum: [
      {
        energyEv: 2.0,
        refractiveIndex: 1.333,
        absorptionLengthMm: 12000.0,
        scatterLengthMm: 15000.0
      },
      {
        energyEv: 3.0,
        refractiveIndex: 1.336,
        absorptionLengthMm: 8000.0,
        scatterLengthMm: 12000.0
      }
    ]
  },
  materials: [waterMaterial]
};

globalThis.TRECH_CONFIG = cfg;
