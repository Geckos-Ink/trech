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
// decides the ordering and plumbing. Here we call ctx.cascade() with NO
// argument: it auto-seeds from the real Geant4 base (per-event edep + material
// probes) and we read the top-of-ladder prediction — the scenario hand-wires
// nothing (multi-scale doctrine workstream 1: "the bottom of the ladder is
// ALWAYS the real Geant4 base").
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
    // ctx.cascade() with NO argument auto-seeds the bottom of the ladder from
    // the REAL Geant4 base (per-event tallies like edep_mev + material probes) —
    // the scenario copies nothing by hand. The nano stage reads the ambient
    // `edep_mev` seed and the cascade runs nano -> meso automatically, returning
    // the flat, augmented context.
    const c = ctx.cascade();
    if (!c) return;  // strict mode / no models loaded
    ctx.emit("cascade_result", {
      event: ctx.event.id,
      edep_mev: ctx.event.edepMeV,
      // Intermediate (nano) and top-of-ladder (meso/observer) predictions, both
      // available flat on the returned context.
      ionization_density: c.ionization_density,
      bulk_response: c.bulk_response,
      // Provenance of the chain: how many scale bands were bridged this pass and
      // which ambient Geant4 facts seeded the base.
      stages_run: c.__cascade.stagesRun,
      scales: c.__cascade.trace.map((s) => s.scale),
      seed_keys: c.__cascade.seedKeys
    });
  }
};

globalThis.TRECH_CONFIG = cfg;
