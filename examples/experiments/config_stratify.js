const cfg = {
  detector: { worldSizeMm: 150.0, worldMaterial: "G4_WATER" },
  beam: { particle: "e-", energyMeV: 1.5, direction: [0, 0, 1] },
  run: { nEvents: 200, seed: 12345 },
  stratify: {
    enable: true,
    edepMeVThreshold: 1.0,
    totalTrackLengthMmThreshold: 200.0,
    totalTrackCountThreshold: 20,
    totalStepCountThreshold: 500,
    labelPredictable: "predictable",
    labelExceptional: "exceptional",
    labelUnclassified: "unclassified"
  }
};

globalThis.TRECH_CONFIG = JSON.stringify(cfg);
