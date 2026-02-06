TRECH_INCLUDE("trech_helpers.js");

const H = globalThis.TRECH_HELPERS;
const u = H.units;

const flow = TRECH_FLOW({
  environment: {
    worldSizeMm: u.cm(12.0),
    worldMaterial: H.materialAliases.air,
    mediumBoxMm: u.cm(8.0),
    mediumMaterial: "flow_water"
  },
  run: { nEvents: 10, seed: 20260206 },
  beams: [],
  materials: [],
  geometry: { volumes: [] },
  system: {
    enable: true,
    mode: "steady_state",
    frame: "point_agnostic",
    ensemble: "flow_h2o_cluster"
  }
});

flow
  .push("materials", H.materialRegistry.fromPreset("water", { name: "flow_water" }))
  .push(
    "geometry.volumes",
    H.geometry.containerBox({
      name: "flow_container",
      parent: "medium",
      sizeMm: [u.cm(8.0), u.cm(8.0), u.cm(8.0)],
      tags: ["flow"]
    })
  )
  .push("beams", {
    name: "probe_electron",
    particle: "e-",
    energyMeV: u.keV(750.0),
    direction: [0.0, 0.0, 1.0],
    active: true
  })
  .tap((f) => {
    const cfg = f.build();
    return f.set("beam", H.pickBeam(cfg.beams, "probe_electron"));
  })
  .when(true, (f) =>
    f.merge({
      optics: {
        enable: true,
        refractiveIndex: 1.333,
        absorptionLengthMm: u.cm(300.0),
        scatterLengthMm: u.cm(150.0)
      }
    })
  );

globalThis.TRECH_CONFIG = () => flow.build();
