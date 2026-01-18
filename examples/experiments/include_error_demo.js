// Demonstrates that TRECH_INCLUDE preserves file/line in stack traces.
TRECH_INCLUDE("include_error_helper.js");

const cfg = {
  detector: { worldSizeMm: 100.0, worldMaterial: "G4_WATER" },
  beam: { particle: "e-", energyMeV: 0.5 },
  run: { nEvents: 1, seed: 7 }
};

globalThis.TRECH_CONFIG = cfg;
