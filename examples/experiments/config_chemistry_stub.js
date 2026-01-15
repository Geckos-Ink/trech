const cfg = {
  detector: {
    worldSizeMm: 200.0,
    worldMaterial: "G4_WATER",
    waterBoxMm: 120.0
  },
  beam: { particle: "gamma", energyMeV: 2.0, direction: [0, 0, 1] },
  run: { nEvents: 50, seed: 7 },
  chemistry: {
    enable: true,
    model: "dna_water",
    solver: "stub"
  }
};

globalThis.TRECH_CONFIG = JSON.stringify(cfg);
