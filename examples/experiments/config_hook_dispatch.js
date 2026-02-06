const cfg = {
  detector: {
    worldSizeMm: 120.0,
    worldMaterial: "G4_WATER"
  },
  beam: {
    particle: "e-",
    energyMeV: 1.0,
    direction: [0, 0, 1]
  },
  run: {
    nEvents: 5,
    seed: 424242
  },
  hooks: {
    maxStepCallbacks: 200
  }
};

globalThis.TRECH_HOOKS = {
  onInit(ctx) {
    void ctx;
  },
  onRunStart(ctx) {
    void ctx;
  },
  onEventStart(ctx) {
    void ctx;
  },
  onStep(ctx) {
    void ctx;
  },
  onEventEnd(ctx) {
    void ctx;
  },
  onRunEnd(ctx) {
    void ctx;
  }
};

globalThis.TRECH_CONFIG = cfg;
