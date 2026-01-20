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

const mediumBoxMm = units.cm(10.0);
const worldSizeMm = units.cm(20.0);
const mediumVolumeMm3 = mediumBoxMm * mediumBoxMm * mediumBoxMm;

const waterMaterial = helpers.materialRegistry.fromPreset("water", {
  densityGcm3: 0.997
});
const cntMaterial = helpers.materialRegistry.fromPreset("carbon", {
  name: "cnt_carbon",
  densityGcm3: 2.2
});

const cfg = {
  detector: {
    worldSizeMm: worldSizeMm,
    worldMaterial: helpers.materialAliases.air,
    mediumBoxMm: mediumBoxMm,
    mediumMaterial: "water",
    temperatureK: 293.15,
    pressureAtm: 1.0
  },
  beam: { particle: "e-", energyMeV: 1.2, direction: [1, 0, 0] },
  run: { nEvents: 10, seed: 424242 },
  system: {
    enable: true,
    mode: "steady_state",
    frame: "point_agnostic",
    ensemble: "cnt_optics_stub",
    volumeMm3: mediumVolumeMm3
  },
  optics: {
    enable: true,
    refractiveIndex: 1.333,
    absorptionLengthMm: 1000.0,
    scatterLengthMm: 500.0
  },
  materials: [waterMaterial, cntMaterial],
  geometry: {
    volumes: geometry.tubeVolume({
      name: "cnt_stub",
      material: "cnt_carbon",
      innerRadiusMm: innerRadiusMm,
      outerRadiusMm: outerRadiusMm,
      lengthMm: lengthMm,
      parent: "medium",
      scoreEdep: true,
      tags: ["cnt_stub", "carbon_nanotube"]
    })
  }
};

globalThis.TRECH_CONFIG = cfg;
