const cfg = {
  detector: {
    worldSizeMm: 200.0,
    worldMaterial: "G4_AIR",
    waterBoxMm: 100.0,
    temperatureK: 293.15,
    pressureAtm: 1.0
  },
  beam: { particle: "gamma", energyMeV: 2.0, direction: [0, 0, 1] },
  run: { nEvents: 1000, seed: 424242 },
  optics: {
    enable: true,
    refractiveIndex: 1.333,
    absorptionLengthMm: 10000.0,
    scatterLengthMm: 10000.0
  }
};

globalThis.TRECH_CONFIG = JSON.stringify(cfg);
