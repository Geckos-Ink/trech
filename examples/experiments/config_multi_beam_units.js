TRECH_INCLUDE("trech_helpers.js");
const helpers = globalThis.TRECH_HELPERS;
if (!helpers) {
  throw new Error("TRECH_HELPERS not available; include trech_helpers.js");
}

const units = helpers.units;
const electronBeams = helpers.composeBeams(
  { particle: "e-", direction: [0, 0, 1] },
  [
    { name: "e-500keV", energyMeV: units.keV(500.0), active: true },
    { name: "e-1MeV", energyMeV: units.MeV(1.0) }
  ]
);
const gammaBeams = helpers.composeBeams(
  { particle: "gamma", direction: [1, 0, 0] },
  [
    { name: "g-250keV", energyMeV: units.keV(250.0) },
    { name: "g-2MeV", energyMeV: units.MeV(2.0) }
  ]
);
const beams = electronBeams.concat(gammaBeams);
const activeBeam = helpers.pickBeam(beams, "e-500keV");

const cfg = {
  detector: {
    worldSizeMm: units.cm(20.0),
    worldMaterial: "G4_AIR",
    mediumBoxMm: units.cm(10.0),
    mediumMaterial: "G4_WATER",
    temperatureK: 293.15,
    pressureAtm: 1.0
  },
  beam: activeBeam,
  // "beams" is forward-looking; current engine reads "beam".
  beams: beams,
  run: { nEvents: 50, seed: 4242 },
  system: {
    enable: true,
    mode: "steady_state",
    frame: "point_agnostic",
    ensemble: "multi_beam_demo"
  },
  optics: {
    enable: false,
    refractiveIndex: 1.333,
    absorptionLengthMm: 10000.0,
    scatterLengthMm: 10000.0
  }
};

globalThis.TRECH_CONFIG = cfg;
