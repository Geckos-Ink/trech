const cfg = {
  detector: {
    worldSizeMm: 200.0,
    worldMaterial: "G4_AIR",
    mediumBoxMm: 100.0,
    mediumMaterial: "G4_WATER",
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
      { wavelengthNm: 400.0, refractiveIndex: 1.34, absorptionLengthMm: 8000.0, scatterLengthMm: 9000.0 },
      { wavelengthNm: 550.0, refractiveIndex: 1.333, absorptionLengthMm: 12000.0, scatterLengthMm: 11000.0 }
    ]
  }
};

globalThis.TRECH_CONFIG = cfg;
