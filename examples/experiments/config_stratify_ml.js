const cfg = {
  detector: { worldSizeMm: 150.0, worldMaterial: "G4_WATER" },
  beam: { particle: "e-", energyMeV: 1.5, direction: [0, 0, 1] },
  run: { nEvents: 200, seed: 12345 },
  optics: {
    enable: true,
    refractiveIndex: 1.333,
    absorptionLengthMm: 5000.0,
    scatterLengthMm: 5000.0
  },
  stratify: {
    enable: true,
    edepMeVThreshold: 1.0,
    opticalTrackLengthMmThreshold: 100.0,
    opticalPhotonTrackThreshold: 5,
    dumpFeatures: true,
    dumpResimQueue: true,
    modelPath: "models/stratify_stub.pt",
    labelPredictable: "predictable",
    labelExceptional: "exceptional",
    labelUnclassified: "unclassified"
  }
};

globalThis.TRECH_CONFIG = cfg;
