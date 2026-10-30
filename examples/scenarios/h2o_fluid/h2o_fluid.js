TRECH_INCLUDE("../../../js/trech_helpers.js");
const helpers = globalThis.TRECH_HELPERS;
if (!helpers) {
  throw new Error("TRECH_HELPERS not available; include trech_helpers.js");
}

const units = helpers.units;
const geometry = helpers.geometry;

const containerSizeCm = TRECH_PARAMETER("container_size_cm");
const fluidLevelCm = TRECH_PARAMETER("fluid_level_cm");
const soluteSizeCm = TRECH_PARAMETER("solute_size_cm");
const temperatureK = TRECH_PARAMETER("temperature_k");
const eventCount = TRECH_PARAMETER("event_count");

const containerSizeMm = [units.cm(containerSizeCm), units.cm(containerSizeCm), units.cm(containerSizeCm)];
const fluidSizeMm = [units.cm(fluidLevelCm), units.cm(fluidLevelCm), units.cm(fluidLevelCm)];
const soluteSizeMm = [units.cm(soluteSizeCm), units.cm(soluteSizeCm), units.cm(soluteSizeCm)];
const fluidVolumeMm3 = fluidSizeMm[0] * fluidSizeMm[1] * fluidSizeMm[2];

const waterMaterial = helpers.materialRegistry.fromPreset("water", {
  densityGcm3: 0.997
});
const brineMaterial = helpers.materialPresets.brine(0.03);
brineMaterial.name = "brine";
brineMaterial.densityGcm3 = 1.03;
// Geant4 ships no G4_SODIUM_CHLORIDE compound, so build solid salt from its
// elements by mass fraction (NaCl: 39.34% Na / 60.66% Cl).
const saltMaterial = {
  name: "salt",
  smiles: "[Na+].[Cl-]",
  densityGcm3: 2.16,
  components: [
    { element: "Na", fraction: 0.3934 },
    { element: "Cl", fraction: 0.6066 }
  ]
};

const cfg = {
  detector: {
    worldSizeMm: units.cm(30.0),
    worldMaterial: helpers.materialAliases.air,
    temperatureK: temperatureK,
    pressureAtm: 1.0
  },
  beam: { particle: "gamma", energyMeV: 2.0, direction: [0, 0, 1] },
  run: { nEvents: eventCount, seed: 424242 },
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
