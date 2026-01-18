TRECH_INCLUDE("trech_helpers.js");
const helpers = globalThis.TRECH_HELPERS;
if (!helpers) {
  throw new Error("TRECH_HELPERS not available; include trech_helpers.js");
}

const units = helpers.units;
const geometry = helpers.geometry;

const containerSizeMm = [units.cm(12.0), units.cm(12.0), units.cm(12.0)];
const fluidSizeMm = [units.cm(10.0), units.cm(10.0), units.cm(10.0)];
const soluteSizeMm = [units.cm(2.0), units.cm(2.0), units.cm(2.0)];
const fluidVolumeMm3 = fluidSizeMm[0] * fluidSizeMm[1] * fluidSizeMm[2];

const waterMaterial = helpers.materialRegistry.fromPreset("water", {
  densityGcm3: 0.997
});
const brineMaterial = helpers.materialPresets.brine(0.03);
brineMaterial.name = "brine";
brineMaterial.densityGcm3 = 1.03;
const saltMaterial = {
  name: "salt",
  smiles: "[Na+].[Cl-]",
  densityGcm3: 2.16,
  components: [{ material: "G4_SODIUM_CHLORIDE", fraction: 1.0 }]
};

const cfg = {
  detector: {
    worldSizeMm: units.cm(30.0),
    worldMaterial: helpers.materialAliases.air,
    temperatureK: 293.15,
    pressureAtm: 1.0
  },
  beam: { particle: "gamma", energyMeV: 2.0, direction: [0, 0, 1] },
  run: { nEvents: 1000, seed: 424242 },
  system: {
    enable: true,
    mode: "steady_state",
    frame: "point_agnostic",
    ensemble: "h2o_brine_container",
    volumeMm3: fluidVolumeMm3
  },
  optics: {
    enable: false,
    refractiveIndex: 1.333,
    absorptionLengthMm: 10000.0,
    scatterLengthMm: 10000.0
  },
  materials: [waterMaterial, brineMaterial, saltMaterial],
  geometry: {
    volumes: [
      geometry.containerBox({
        name: "fluid_container",
        sizeMm: containerSizeMm,
        tags: ["container", "fluid_boundary"]
      }),
      geometry.boxVolume({
        name: "fluid_bulk",
        material: "brine",
        sizeMm: fluidSizeMm,
        parent: "fluid_container",
        scoreEdep: true,
        tags: ["fluid", "brine"]
      }),
      geometry.boxVolume({
        name: "solute_seed",
        material: "salt",
        sizeMm: soluteSizeMm,
        parent: "fluid_bulk",
        scoreEdep: false,
        tags: ["solute", "seed"]
      })
    ]
  }
};

globalThis.TRECH_CONFIG = cfg;
