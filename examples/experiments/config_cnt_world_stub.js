const nm = 1e-6;
const cntDiameterNm = 3.0;
const cntLengthNm = 100.0;
const wallCount = 5;
const wallThicknessNm = 0.34 * wallCount;
const outerRadiusMm = 0.5 * cntDiameterNm * nm;
const innerRadiusMm = Math.max(0.0, outerRadiusMm - wallThicknessNm * nm);
const lengthMm = cntLengthNm * nm;
// create a common JS with definition to include instead of repeating certain "fixed chemistry constant" every time

const cfg = {
  detector: { // detector has sense in particles collider contexts, but in generic context the right term should be like "mean" or "ether"
    worldSizeMm: 200.0,
    worldMaterial: "G4_AIR", // where is defined G4_AIR and what molecules containes? Better a JS level "standard" declarations to be clearly visible to devs
    mediumBoxMm: 0.0,
    mediumMaterial: "G4_WATER", // same point of G4_AIR: a well pre-defined (and editable) water system (one ore more H2O molecules) is the best choice
    temperatureK: 293.15,
    pressureAtm: 1.0
  },
  beam: { particle: "proton", energyMeV: 0.8, direction: [1, 0, 0] }, // only one beam is possible? Why not "beams" so if needed it can accept an array?
  // then, in CNT semiconductor experimentation, shouldn't be used electrons to test electrical behaviours?
  run: { nEvents: 10, seed: 424242 },
  optics: { 
    enable: false,
    refractiveIndex: 1.333, // what's the sense of creating a physic-chemistry simulator if you have to force manually physical properties in any case? (obviously, if needed, the simulated one can be overrided)
    absorptionLengthMm: 0.0,
    scatterLengthMm: 0.0
  },
  geometry: {
    volumes: [
      {
        name: "cnt_stub",
        material: "G4_C", // better a "SMILE-like" definition instead of G4-imported enumeration for atoms/molecules structures in many cases (or defined systems)
        shape: { // this is technically fine for simplicity, but it could a big limitation (and confusive) for complex scenarios
          // and by the way, the same tubes should be obtainable executing the real process that creates various kind of nanotubes in real world (long term)
          // this is evident in case of H2O molecule, where it's stability should be proved by simulating various GEANT4 sub atomic particles interactions in the system
          type: "tube", // is it tube structure "meaning" defined inside another JS file?
          innerRadiusMm, // makes sense forcing in this way dimensions that in someway are forced to physical-chemical property limitations?
          outerRadiusMm,
          lengthMm
        },
        placement: { parent: "world" }, // it may be a way, but at this point a structured object would be better ("word": { ..., "objects":[{"geometry": ..}]})
        scoreEdep: true,
        tags: ["cnt_stub", "carbon_nanotube"]
      }
    ]
  }
};

globalThis.TRECH_CONFIG = cfg;
