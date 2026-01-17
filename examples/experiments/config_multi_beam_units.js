// Inline fallback of trech_helpers.js for single-file execution.
const helpers = globalThis.TRECH_HELPERS || (function() {
  function toArray(value) {
    if (value === undefined || value === null) {
      return [];
    }
    return Array.isArray(value) ? value : [value];
  }

  const units = {
    eV: (value) => value * 1e-6,
    keV: (value) => value * 1e-3,
    MeV: (value) => value,
    GeV: (value) => value * 1e3,
    mm: (value) => value,
    cm: (value) => value * 10.0,
    m: (value) => value * 1000.0,
    nm: (value) => value * 1e-6
  };

  function composeBeams(base, variants) {
    return toArray(variants).map((variant) => {
      return Object.assign({}, base, variant);
    });
  }

  function pickBeam(beams, name) {
    const list = toArray(beams);
    if (name) {
      const match = list.find((beam) => beam && beam.name === name);
      if (match) {
        return match;
      }
    }
    const active = list.find((beam) => beam && beam.active);
    return active || list[0];
  }

  return {
    units,
    toArray,
    composeBeams,
    pickBeam
  };
})();

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
    waterBoxMm: units.cm(10.0),
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

globalThis.TRECH_CONFIG = JSON.stringify(cfg);
