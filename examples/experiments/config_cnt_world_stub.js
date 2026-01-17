const cfg = {
  detector: {
    worldSizeMm: 200.0,
    worldMaterial: "G4_AIR",
    waterBoxMm: 0.0,
    temperatureK: 293.15,
    pressureAtm: 1.0
  },
  beam: { particle: "proton", energyMeV: 0.8, direction: [1, 0, 0] },
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
    diameterNm: 3.0,
    lengthNm: 100.0,
    wallCount: 5,
    material: "carbon"
  }
};

globalThis.TRECH_CONFIG = JSON.stringify(cfg);
