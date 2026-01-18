TRECH_INCLUDE("trech_helpers.js");
const helpers = globalThis.TRECH_HELPERS;
if (!helpers) {
  throw new Error("TRECH_HELPERS not available; include trech_helpers.js");
}

const units = helpers.units;
const geometry = helpers.geometry;

const containerSizeMm = [units.mm(0.02), units.mm(0.02), units.mm(0.02)];
const fluidSizeMm = [units.mm(0.01), units.mm(0.01), units.mm(0.01)];
const fluidVolumeMm3 = fluidSizeMm[0] * fluidSizeMm[1] * fluidSizeMm[2];
const moleculeRadiusMm = units.nm(0.15);

const waterMaterial = helpers.materialRegistry.fromPreset("water", {
  densityGcm3: 0.997
});

const moleculeProxy = {
  name: "h2o_molecule_proxy",
  material: "water",
  shape: { type: "sphere", outerRadiusMm: moleculeRadiusMm },
  placement: {
    parent: "single_fluid",
    positionMm: [0, 0, 0],
    rotationDeg: [0, 0, 0]
  },
  scoreEdep: true,
  tags: ["molecule", "proxy"]
};

const cfg = {
  detector: {
    worldSizeMm: units.mm(0.04),
    worldMaterial: helpers.materialAliases.air,
    temperatureK: 293.15,
    pressureAtm: 1.0
  },
  beam: { particle: "e-", energyMeV: 0.1, direction: [0, 0, 1] },
  run: { nEvents: 200, seed: 424242 },
  system: {
    enable: true,
    mode: "steady_state",
    frame: "point_agnostic",
    ensemble: "h2o_single_proxy",
    volumeMm3: fluidVolumeMm3
  },
  optics: {
    enable: false,
    refractiveIndex: 1.333,
    absorptionLengthMm: 10000.0,
    scatterLengthMm: 10000.0
  },
  chemistry: {
    enable: true,
    model: "dna_water",
    solver: "stub"
  },
  materials: [waterMaterial],
  geometry: {
    volumes: [
      geometry.containerBox({
        name: "single_container",
        sizeMm: containerSizeMm,
        tags: ["container", "micro"]
      }),
      geometry.boxVolume({
        name: "single_fluid",
        material: "water",
        sizeMm: fluidSizeMm,
        parent: "single_container",
        scoreEdep: true,
        tags: ["fluid", "h2o"]
      }),
      moleculeProxy
    ]
  }
};

globalThis.TRECH_CONFIG = cfg;
