TRECH_INCLUDE("trech_helpers.js");
const helpers = globalThis.TRECH_HELPERS;
if (!helpers) {
  throw new Error("TRECH_HELPERS not available; include trech_helpers.js");
}

const units = helpers.units;
const worldSizeMm = units.cm(20.0);
const mediumBoxMm = units.cm(12.0);

const waterMaterial = helpers.materialRegistry.fromPreset("water", {
  densityGcm3: 0.997
});

const cfg = {
  detector: {
    worldSizeMm: worldSizeMm,
    worldMaterial: "water",
    mediumBoxMm: mediumBoxMm,
    mediumMaterial: "water",
    temperatureK: 293.15,
    pressureAtm: 1.0
  },
  beam: { particle: "gamma", energyMeV: 2.0, direction: [0, 0, 1] },
  run: { nEvents: 50, seed: 7 },
  chemistry: {
    enable: true,
    model: "dna_water",
    solver: "stub"
  },
  materials: waterMaterial
};

globalThis.TRECH_CONFIG = cfg;
