// Multi-scale inference cascade demo: ctx.cascade chains scale-tagged models
// from the Geant4 particle/nano base up to an observer-scale number in ONE
// deterministic pass, WITHOUT the scenario hand-wiring "call A, feed B".
//
// This is the general-purpose realization of the engine's core doctrine (see
// AGENTS.md "Multi-scale statistical inference"): Geant4 gives ground truth at
// the particle scale; scale-tagged surrogates lift it band by band
// (atomic -> nano -> micro -> meso -> macro) to the scale the user observes.
//
//   Geant4 event edep  --(nano stage)-->  ionization_density  --(meso stage)-->  bulk_response
//
// The scenario declares WHICH models exist and at WHAT scale; the engine
// decides the ordering and plumbing. Here we seed the cascade with a real
// Geant4 per-event fact (edepMeV) and read the top-of-ladder prediction.
//
// HONEST SCOPE: the two stage models are hand-authored ILLUSTRATIVE linear maps
// (data/cascade_demo/*.json), not trained physics — they demonstrate the
// cascade *mechanism*. Real stages are trained per band via
// `trech-train-surrogate` and validated held-out (see the ROADMAP standing
// objective "Multi-scale statistical inference").
//
// Determinism: ctx.cascade is a pure function of loaded weights + numeric seed;
// disabled in strict mode (returns null), so this demo declares predictive.
const cfg = {
  detector: { worldSizeMm: 120.0, worldMaterial: "G4_WATER" },
  beam: { particle: "e-", energyMeV: 1.0, direction: [0, 0, 1] },
  run: { nEvents: 8, seed: 20260705, threads: 1 },
  determinism: { mode: "predictive" },
  models: [
    // Declared meso-first on purpose: the engine chains by `scale`, not by the
    // order the scenario happens to list them.
    { name: "meso_response",  scale: "meso", path: "data/cascade_demo/meso_response.json" },
    { name: "nano_ionization", scale: "nano", path: "data/cascade_demo/nano_ionization.json" }
  ]
};

globalThis.TRECH_HOOKS = {
  onEventEnd(ctx) {
    if (!ctx.event) return;
    // Seed the bottom of the ladder with a REAL Geant4 fact; the cascade runs
    // nano -> meso automatically and returns the flat, augmented context.
    const c = ctx.cascade({ edep_mev: ctx.event.edepMeV });
    if (!c) return;  // strict mode / no models loaded
    ctx.emit("cascade_result", {
      event: ctx.event.id,
      edep_mev: ctx.event.edepMeV,
      // Intermediate (nano) and top-of-ladder (meso/observer) predictions, both
      // available flat on the returned context.
      ionization_density: c.ionization_density,
      bulk_response: c.bulk_response,
      // Provenance of the chain: how many scale bands were bridged this pass.
      stages_run: c.__cascade.stagesRun,
      scales: c.__cascade.trace.map((s) => s.scale)
    });
  }
};

globalThis.TRECH_CONFIG = cfg;
