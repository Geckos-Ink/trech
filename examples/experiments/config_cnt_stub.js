TRECH_INCLUDE("trech_helpers.js");
const helpers = globalThis.TRECH_HELPERS;
if (!helpers) {
  throw new Error("TRECH_HELPERS not available; include trech_helpers.js");
}

const units = helpers.units;
const constants = helpers.constants;
const geometry = helpers.geometry;

const cntDiameterNm = TRECH_VALUE.number("cnt_diameter_nm", {
  label: "CNT diameter", group: "Nanotube", unit: "nm",
  default: 3.0, min: 1.0, max: 8.0, step: 0.25
});
const cntLengthNm = TRECH_VALUE.number("cnt_length_nm", {
  label: "CNT length", group: "Nanotube", unit: "nm",
  default: 100.0, min: 20.0, max: 500.0, step: 10.0
});
const wallCount = TRECH_VALUE.integer("wall_count", {
  label: "Wall count", group: "Nanotube",
  default: 5, min: 1, max: 12, step: 1
});
const temperatureK = TRECH_VALUE.number("temperature_k", {
  label: "Temperature", group: "Environment", unit: "K",
  default: 293.15, min: 250.0, max: 400.0, step: 1.0
});
const electronEnergyMeV = TRECH_VALUE.number("electron_energy_mev", {
  label: "Electron energy", group: "Source", unit: "MeV",
  default: 0.8, min: 0.05, max: 5.0, step: 0.05
});
const eventCount = TRECH_VALUE.integer("event_count", {
  label: "Sampling level", group: "Run", unit: "events",
  default: 10, min: 1, max: 1000, step: 1
});
const wallThicknessNm = constants.carbonWallThicknessNm * wallCount;
const nm = units.nm(1.0);
const outerRadiusMm = 0.5 * cntDiameterNm * nm;
const innerRadiusMm = Math.max(0.0, outerRadiusMm - wallThicknessNm * nm);
const lengthMm = cntLengthNm * nm;

const containerSizeMm = [units.mm(2.0), units.mm(2.0), units.mm(2.0)];
const fluidSizeMm = [units.mm(1.6), units.mm(1.6), units.mm(1.6)];
const fluidVolumeMm3 = fluidSizeMm[0] * fluidSizeMm[1] * fluidSizeMm[2];

const waterMaterial = helpers.materialRegistry.fromPreset("water", {
  densityGcm3: 0.997
});
const cntMaterial = helpers.materialRegistry.fromPreset("carbon", {
  name: "cnt_carbon",
  densityGcm3: 2.2
});

const cfg = {
  detector: {
    worldSizeMm: units.mm(5.0),
    worldMaterial: helpers.materialAliases.air,
    temperatureK: temperatureK,
    pressureAtm: 1.0
  },
  beam: { particle: "e-", energyMeV: electronEnergyMeV, direction: [1, 0, 0] },
  run: { nEvents: eventCount, seed: 424242 },
  system: {
    enable: true,
    mode: "steady_state",
    frame: "point_agnostic",
    ensemble: "cnt_in_fluid",
    volumeMm3: fluidVolumeMm3
  },
  optics: {
    enable: false,
    refractiveIndex: 1.333,
    absorptionLengthMm: 0.0,
    scatterLengthMm: 0.0
  },
  materials: [waterMaterial, cntMaterial],
  geometry: {
    volumes: [
      geometry.containerBox({
        name: "cnt_container",
        sizeMm: containerSizeMm,
        tags: ["container", "cnt"]
      }),
      geometry.boxVolume({
        name: "cnt_medium",
        material: "water",
        sizeMm: fluidSizeMm,
        parent: "cnt_container",
        scoreEdep: false,
        tags: ["fluid", "h2o"]
      }),
      geometry.tubeVolume({
        name: "cnt_stub",
        material: "cnt_carbon",
        innerRadiusMm: innerRadiusMm,
        outerRadiusMm: outerRadiusMm,
        lengthMm: lengthMm,
        parent: "cnt_medium",
        scoreEdep: true,
        tags: ["cnt_stub", "carbon_nanotube"]
      })
    ]
  }
};

globalThis.TRECH_CONFIG = cfg;
