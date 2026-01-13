const cfg = {
  detector: { worldSizeMm: 200.0, worldMaterial: "G4_WATER" },
  beam: { particle: "gamma", energyMeV: 2.0 },
  run: { nEvents: 1000, seed: 424242 }
};

globalThis.TRECH_CONFIG = JSON.stringify(cfg);
