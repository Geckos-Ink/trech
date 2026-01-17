const cfg = {
  detector: {
    worldSizeMm: 0.02,
    worldMaterial: "G4_AIR",
    waterBoxMm: 0.01,
    temperatureK: 293.15,
    pressureAtm: 1.0
  },
  beam: { particle: "e-", energyMeV: 0.1, direction: [0, 0, 1] },
  run: { nEvents: 200, seed: 424242 },
  optics: {
    enable: false,
    refractiveIndex: 1.333,
    absorptionLengthMm: 10000.0,
    scatterLengthMm: 10000.0
  },
  chemistry: {
    enable: true,
    model: "dna_water",
    solver: "stub"
  }
};

globalThis.TRECH_CONFIG = JSON.stringify(cfg);
