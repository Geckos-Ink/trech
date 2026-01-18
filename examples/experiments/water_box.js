const cfg = {
  detector: { worldSizeMm: 200.0, worldMaterial: "G4_WATER" },
  beam: { particle: "e-", energyMeV: 5.0 },
  run: { nEvents: 100, seed: 424242 }
};

globalThis.TRECH_CONFIG = cfg;
