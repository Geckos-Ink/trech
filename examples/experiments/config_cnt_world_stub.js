const nm = 1e-6;
const cntDiameterNm = 3.0;
const cntLengthNm = 100.0;
const wallCount = 5;
const wallThicknessNm = 0.34 * wallCount;
const outerRadiusMm = 0.5 * cntDiameterNm * nm;
const innerRadiusMm = Math.max(0.0, outerRadiusMm - wallThicknessNm * nm);
const lengthMm = cntLengthNm * nm;

const cfg = {
  detector: {
    worldSizeMm: 200.0,
    worldMaterial: "G4_AIR",
    mediumBoxMm: 0.0,
    mediumMaterial: "G4_WATER",
    temperatureK: 293.15,
    pressureAtm: 1.0
  },
  beam: { particle: "proton", energyMeV: 0.8, direction: [1, 0, 0] },
  run: { nEvents: 10, seed: 424242 },
  optics: {
    enable: false,
    refractiveIndex: 1.333,
    absorptionLengthMm: 0.0,
    scatterLengthMm: 0.0
  },
  geometry: {
    volumes: [
      {
        name: "cnt_stub",
        material: "G4_C",
        shape: {
          type: "tube",
          innerRadiusMm,
          outerRadiusMm,
          lengthMm
        },
        placement: { parent: "world" },
        scoreEdep: true,
        tags: ["cnt_stub", "carbon_nanotube"]
      }
    ]
  }
};

globalThis.TRECH_CONFIG = cfg;
