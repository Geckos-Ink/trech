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
// surrogate for the probed material's n and emits it — proving the general inference path
// end-to-end without any optics-specific C++.
//
// Determinism: ctx.predict is a pure function of the loaded weights and the
// numeric inputs; it is disabled in strict mode (returns null) and enabled in
// predictive mode, so this demo declares predictive.
const material = TRECH_VALUE.choice("material", {
  label: "Transport material", group: "Conditions",
  description: "Geant4 builds and probes this material; its actual composition feeds the learned model.",
  default: "G4_WATER", choices: ["G4_WATER", "G4_ETHYL_ALCOHOL"]
});
const cfg = {
  detector: { worldSizeMm: 120.0, worldMaterial: material },
  beam: { particle: "e-", energyMeV: 1.0, direction: [0, 0, 1] },
  run: { nEvents: 8, seed: 20260702, threads: 1 },
  determinism: { mode: "predictive" },
  materialProbe: { enable: true, materials: [material] },
  models: [
    // name is how the hook looks it up; path is resolved from CWD, then from
    // this experiment's directory. `scale` tags the model's dimension band:
    // composition -> a material optical property lives at the atomic/material
    // scale (a higher-scale transport/observer model would consume its n).
    { name: "optics_n", scale: "atomic", path: "data/optics_surrogate_ridge.json" }
  ]
};

// This list is the committed model's feature vocabulary, not a material law.
// An absent element is explicitly zero only AFTER Geant4 reports the complete
// material composition. Missing material probes never become assumed water.
const COMPOSITION_FEATURES = ["H", "C", "N", "O", "F", "Na", "Mg", "Al", "Si", "P", "S", "Cl", "I", "other"];
function materialFeatures(ctx) {
  const probe = ctx.materials && ctx.materials[material];
  if (!probe || !probe.available || !Array.isArray(probe.elements)) return null;
  const features = { density_gcm3: probe.density_g_per_cm3 };
  for (const symbol of COMPOSITION_FEATURES) features[symbol] = 0.0;
  for (const element of probe.elements) {
    const key = COMPOSITION_FEATURES.indexOf(element.symbol) >= 0 ? element.symbol : "other";
    features[key] += element.mass_fraction;
  }
  return features;
}

globalThis.TRECH_HOOKS = {
  onInit(ctx) {
    // onInit runs before Geant4 constructs its materials. Do not substitute
    // a handbook density/composition just to obtain an early prediction.
    const n = ctx.predict("optics_n");
    ctx.emit("model_probe", {
      model: "optics_n",
      available: n !== null,
      input_source: "geant4_material_probe",
      note: "Material facts are available after Geant4 Initialize.",
      refractive_index: n ? n.refractive_index : null
    });
  },
  onEventEnd(ctx) {
    if (!ctx.event) return;
    const features = materialFeatures(ctx);
    if (!features) throw new Error("Missing Geant4 material probe for " + material);
    const n = ctx.predict("optics_n", features);
    ctx.emit("predicted_optics", {
      event: ctx.event.id,
      material,
      input_source: "geant4_material_probe",
      input_features: features,
      edepMeV: ctx.event.edepMeV,
      // The learned refractive index for the transported medium.
      refractive_index: n ? n.refractive_index : null
    });
  }
};

globalThis.TRECH_CONFIG = cfg;
