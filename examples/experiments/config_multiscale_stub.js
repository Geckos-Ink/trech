const cfg = {
  detector: { worldSizeMm: 200.0, worldMaterial: "G4_WATER" },
  beam: { particle: "e-", energyMeV: 1.0, direction: [0, 0, 1] },
  run: { nEvents: 100, seed: 31415 },
  multiscale: {
    enable: true,
    method: "lbm_stub",
    mode: "auto"
  }
};

globalThis.TRECH_CONFIG = JSON.stringify(cfg);
