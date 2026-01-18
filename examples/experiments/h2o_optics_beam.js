const cfg = {
  detector: {
    worldSizeMm: 200.0,
    worldMaterial: "G4_AIR",
    mediumBoxMm: 100.0,
    mediumMaterial: "G4_WATER",
    temperatureK: 293.15,
    pressureAtm: 1.0
  },
  beam: { particle: "opticalphoton", energyMeV: 2.5e-6, direction: [0, 0, 1] },
  run: { nEvents: 500, seed: 424242 },
  system: {
    enable: true,
    mode: "steady_state",
    frame: "point_agnostic",
    ensemble: "h2o_optics_beam"
  },
  optics: {
    enable: true,
    refractiveIndex: 1.333,
    absorptionLengthMm: 10000.0,
    scatterLengthMm: 10000.0,
    spectrum: [
      { energyEv: 2.0, refractiveIndex: 1.333, absorptionLengthMm: 12000.0, scatterLengthMm: 15000.0 },
      { energyEv: 3.0, refractiveIndex: 1.336, absorptionLengthMm: 8000.0, scatterLengthMm: 12000.0 }
    ]
  }
};

globalThis.TRECH_CONFIG = cfg;
