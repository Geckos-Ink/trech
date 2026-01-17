const cfg = {
  detector: {
    worldSizeMm: 200.0,
    worldMaterial: "G4_AIR",
    waterBoxMm: 100.0,
    temperatureK: 293.15,
    pressureAtm: 1.0
  },
  beam: { particle: "e-", energyMeV: 1.0, direction: [0, 0, 1] },
  run: { nEvents: 10, seed: 424242 },
  optics: {
    enable: false,
    refractiveIndex: 1.333,
    absorptionLengthMm: 0.0,
    scatterLengthMm: 0.0
  },
  cnt: {
    enable: true,
    chiralityN: 10,
    chiralityM: 10,
    diameterNm: 1.36,
    lengthNm: 100.0,
    wallCount: 1,
    material: "carbon",
    placeInWater: true
  }
};

globalThis.TRECH_CONFIG = JSON.stringify(cfg);
