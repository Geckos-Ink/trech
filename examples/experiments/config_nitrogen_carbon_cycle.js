TRECH_INCLUDE("trech_helpers.js");
const helpers = globalThis.TRECH_HELPERS;
if (!helpers) {
  throw new Error("TRECH_HELPERS not available; include trech_helpers.js");
}

const units = helpers.units;
const materialRegistry = helpers.materialRegistry;

const nitrogenGas = {
  name: "nitrogen_gas",
  smiles: "N#N",
  densityGcm3: 0.0012506,
  components: [{ material: "G4_N", fraction: 1.0 }]
};
const carbonProxy = materialRegistry.fromPreset("carbon", {
  name: "carbon14_proxy",
  smiles: "[14C]"
});

globalThis.TRECH_CONFIG = {
  detector: {
    worldSizeMm: units.cm(40.0),
    worldMaterial: "nitrogen_gas",
    mediumBoxMm: units.cm(20.0),
    mediumMaterial: "nitrogen_gas",
    temperatureK: 293.15,
    pressureAtm: 1.0
  },
  beam: {
    particle: "neutron",
    energyMeV: units.eV(0.025),
    direction: [0, 0, 1]
  },
  run: {
    nEvents: 50,
    seed: 14014
  },
  system: {
    enable: true,
    mode: "steady_state",
    frame: "point_agnostic",
    ensemble: "nitrogen_carbon14_cycle",
    volumeMm3: Math.pow(units.cm(20.0), 3)
  },
  materials: [nitrogenGas, carbonProxy],
  geometry: {
    volumes: [
      helpers.geometry.boxVolume({
        name: "carbon14_proxy_volume",
        material: "carbon14_proxy",
        sizeMm: [units.cm(2.0), units.cm(2.0), units.cm(2.0)],
        parent: "medium",
        scoreEdep: true,
        tags: ["carbon14_proxy", "transmutation_probe"]
      })
    ]
  },
  nuclear: {
    enable: true,
    cycles: [
      {
        name: "nitrogen_carbon14_cycle",
        source: {
          symbol: "N",
          material: "nitrogen_gas",
          z: 7,
          a: 14,
          phase: "gas",
          densityGcm3: 0.0012506
        },
        target: {
          symbol: "C",
          material: "carbon14_proxy",
          z: 6,
          a: 14,
          phase: "solid",
          densityGcm3: 2.267
        },
        forward: {
          name: "n14_neutron_capture",
          reactants: [{ z: 7, a: 14 }, { particle: "neutron" }],
          products: [{ z: 6, a: 14 }, { particle: "proton" }]
        },
        backward: {
          name: "c14_beta_decay",
          halfLifeYears: 5730.0,
          reactants: [{ z: 6, a: 14 }],
          products: [{ z: 7, a: 14 }, { particle: "e-" }, { particle: "anti_nu_e" }]
        }
      }
    ]
  }
};
