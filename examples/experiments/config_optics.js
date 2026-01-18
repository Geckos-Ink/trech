TRECH_INCLUDE("trech_helpers.js");
const helpers = globalThis.TRECH_HELPERS;
if (!helpers) {
  throw new Error("TRECH_HELPERS not available; include trech_helpers.js");
}

const units = helpers.units;
const mediumBoxMm = units.cm(10.0);
const worldSizeMm = units.cm(20.0);

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
  beam: { particle: "gamma", energyMeV: 2.0, direction: [0, 0, 1] },
  run: { nEvents: 100, seed: 424242 },
  optics: {
    enable: true,
    refractiveIndex: 1.333,
    absorptionLengthMm: 10000.0,
    scatterLengthMm: 10000.0,
    spectrum: [
      {
        wavelengthNm: 400.0,
        refractiveIndex: 1.34,
        absorptionLengthMm: 8000.0,
        scatterLengthMm: 9000.0
      },
      {
        wavelengthNm: 550.0,
        refractiveIndex: 1.333,
        absorptionLengthMm: 12000.0,
        scatterLengthMm: 11000.0
      }
    ]
  },
  materials: [waterMaterial]
};

globalThis.TRECH_CONFIG = cfg;
