const cfg = {
  detector: { worldSizeMm: 100.0, worldMaterial: "G4_WATER" },
  beam: { particle: "e-", energyMeV: 1.0 },
  run: { nEvents: 10, seed: 12345 }
};

globalThis.TRECH_HOOKS = {
  onInit(ctx) {
    void ctx;
  }
};

globalThis.TRECH_CONFIG = cfg;
