TRECH_INCLUDE("trech_helpers.js");
const helpers = globalThis.TRECH_HELPERS;
if (!helpers) {
  throw new Error("TRECH_HELPERS not available; include trech_helpers.js");
}

const units = helpers.units;
const geometry = helpers.geometry;

const containerSizeMm = [units.cm(10.0), units.cm(10.0), units.cm(10.0)];
const waterSizeMm = [units.cm(8.0), units.cm(8.0), units.cm(8.0)];
const waterVolumeMm3 = waterSizeMm[0] * waterSizeMm[1] * waterSizeMm[2];

const waterMaterial = helpers.materialRegistry.fromPreset("water", {
  densityGcm3: 0.997
});

const cfg = {
  detector: {
    worldSizeMm: units.cm(30.0),
    worldMaterial: helpers.materialAliases.air,
    temperatureK: 293.15,
    pressureAtm: 1.0
  },
  beam: { particle: "e-", energyMeV: 5.0, direction: [0, 0, 1] },
  run: { nEvents: 100, seed: 424242 },
  system: {
    enable: true,
    mode: "steady_state",
    frame: "point_agnostic",
    ensemble: "water_box_container",
    volumeMm3: waterVolumeMm3
  },
  materials: [waterMaterial],
  geometry: {
    volumes: [
      geometry.containerBox({
        name: "water_container",
        sizeMm: containerSizeMm,
        tags: ["container", "demo"]
      }),
      geometry.boxVolume({
        name: "water_bulk",
        material: "water",
        sizeMm: waterSizeMm,
        parent: "water_container",
        scoreEdep: true,
        tags: ["fluid", "h2o"]
      })
    ]
  }
};

globalThis.TRECH_CONFIG = cfg;
