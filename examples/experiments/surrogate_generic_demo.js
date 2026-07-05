// Generic Torch-surrogate demo: any scenario can attach a learned model and
// call it deterministically from a hook via ctx.predict.
//
// This is the scenario-agnostic inference path (docs: CHARTS.md "Generic
// surrogate" flow). The engine hardcodes nothing about WHAT is predicted:
//   - `models[]` declares named models pointing at GenericSurrogate-loadable
//     files (portable `.json`, or `.pt` with LibTorch).
//   - the hook calls `ctx.predict(name, features)` and gets named outputs back.
//
// `ctx.predict` is the SINGLE-model (point-predictor) tier. To chain several
// scale-tagged models from the Geant4 base up the dimension ladder in one pass
// (the engine's multi-scale doctrine), use `ctx.cascade` instead — see
// examples/experiments/cascade_multiscale_demo.js. Declaring `scale` here keeps
// even this single-model scenario cascade-ready and consistent with the
// convention that every declared model carries its dimension band.
//
// Here we reuse the committed, validated optics ridge model
// (data/optics_surrogate_ridge.json) as a live example: given a material's
// element mass fractions + density, it predicts the refractive index. The hook
// runs Geant4-driven electron transport each event and, per event, asks the
// surrogate for water's n and emits it — proving the general inference path
// end-to-end without any optics-specific C++.
//
// Determinism: ctx.predict is a pure function of the loaded weights and the
// numeric inputs; it is disabled in strict mode (returns null) and enabled in
// predictive mode, so this demo declares predictive.
const cfg = {
  detector: { worldSizeMm: 120.0, worldMaterial: "G4_WATER" },
  beam: { particle: "e-", energyMeV: 1.0, direction: [0, 0, 1] },
  run: { nEvents: 8, seed: 20260702, threads: 1 },
  determinism: { mode: "predictive" },
  models: [
    // name is how the hook looks it up; path is resolved from CWD, then from
    // this experiment's directory. `scale` tags the model's dimension band:
    // composition -> a material optical property lives at the atomic/material
    // scale (a higher-scale transport/observer model would consume its n).
    { name: "optics_n", scale: "atomic", path: "data/optics_surrogate_ridge.json" }
  ]
};

// Water composition (mass fractions) + density — the optics model's inputs.
const WATER = { H: 0.1119, O: 0.8881, density_gcm3: 1.0 };

globalThis.TRECH_HOOKS = {
  onInit(ctx) {
    // Predict once up front to prove init-path inference is counted too.
    const n = ctx.predict("optics_n", WATER);
    ctx.emit("model_probe", {
      model: "optics_n",
      available: n !== null,
      refractive_index: n ? n.refractive_index : null
    });
  },
  onEventEnd(ctx) {
    if (!ctx.event) return;
    const n = ctx.predict("optics_n", WATER);
    ctx.emit("predicted_optics", {
      event: ctx.event.id,
      edepMeV: ctx.event.edepMeV,
      // The learned refractive index for the transported medium.
      refractive_index: n ? n.refractive_index : null
    });
  }
};

globalThis.TRECH_CONFIG = cfg;
