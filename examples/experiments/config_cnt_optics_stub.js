const cfg = {
  detector: {
    worldSizeMm: 200.0,
    worldMaterial: "G4_AIR",
    waterBoxMm: 100.0,
    temperatureK: 293.15,
    pressureAtm: 1.0
  },
  beam: { particle: "e-", energyMeV: 1.2, direction: [1, 0, 0] },
  run: { nEvents: 10, seed: 424242 },
  optics: {
    enable: true,
    refractiveIndex: 1.333,
    absorptionLengthMm: 1000.0,
    scatterLengthMm: 500.0
  },
  cnt: {
    enable: true,
    chiralityN: 10,
    chiralityM: 10,
    diameterNm: 3.0,
    lengthNm: 100.0,
    wallCount: 5,
    material: "carbon"
  }
};

globalThis.TRECH_CONFIG = JSON.stringify(cfg);
