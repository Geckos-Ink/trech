TRECH_INCLUDE("trech_helpers.js");
const helpers = globalThis.TRECH_HELPERS;
if (!helpers) {
  throw new Error("TRECH_HELPERS not available; include trech_helpers.js");
}

const units = helpers.units;
const constants = helpers.constants;
const geometry = helpers.geometry;

const cntDiameterNm = 3.0;
const cntLengthNm = 100.0;
const wallCount = 5;
const wallThicknessNm = constants.carbonWallThicknessNm * wallCount;
const nm = units.nm(1.0);
const outerRadiusMm = 0.5 * cntDiameterNm * nm;
const innerRadiusMm = Math.max(0.0, outerRadiusMm - wallThicknessNm * nm);
const lengthMm = cntLengthNm * nm;

const containerSizeMm = [units.mm(2.0), units.mm(2.0), units.mm(2.0)];
const containerVolumeMm3 =
  containerSizeMm[0] * containerSizeMm[1] * containerSizeMm[2];

const cntMaterial = helpers.materialRegistry.fromPreset("carbon", {
  name: "cnt_carbon",
  densityGcm3: 2.2
});

const cfg = {
  detector: {
    worldSizeMm: units.mm(5.0),
    worldMaterial: helpers.materialAliases.air,
    temperatureK: 293.15,
    pressureAtm: 1.0
  },
  beam: { particle: "e-", energyMeV: 0.8, direction: [1, 0, 0] },
  run: { nEvents: 10, seed: 424242 },
  system: {
    enable: true,
    mode: "steady_state",
    frame: "point_agnostic",
    ensemble: "cnt_in_void_container",
    volumeMm3: containerVolumeMm3
  },
  materials: [cntMaterial],
  geometry: {
    volumes: [
      geometry.containerBox({
        name: "cnt_container",
        sizeMm: containerSizeMm,
        tags: ["container", "cnt"]
      }),
      geometry.tubeVolume({
        name: "cnt_stub",
        material: "cnt_carbon",
        innerRadiusMm: innerRadiusMm,
        outerRadiusMm: outerRadiusMm,
        lengthMm: lengthMm,
        parent: "cnt_container",
        scoreEdep: true,
        tags: ["cnt_stub", "carbon_nanotube"]
      })
    ]
  }
};

globalThis.TRECH_CONFIG = cfg;
