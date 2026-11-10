// Fixed-structure model definition: per-event Geant4 step count from deposited energy and
// charged track length (event features dumped by stratify.dumpFeatures).
//
// Train:   node tools/ml/bin/trech-ml.cjs train ml/definitions/event_step_count.model.js
// Use it from a scenario (QuickJS):
//   TRECH_INCLUDE("../../../js/trech_ml.js");
//   TRECH_INCLUDE("../../../ml/definitions/event_step_count.model.js");
//   cfg.models = [TRECH_ML.modelEntry(EVENT_STEP_COUNT, {index: "../../../build/model_store/index.json"})];
//
// The demo runs are config_stratify with different seeds (see ml/README.md). A checkpoint is a
// learned comparison model of Geant4 event tallies, never a Geant4 tally itself.
TRECH_INCLUDE("../shared/event_features.js");

globalThis.EVENT_STEP_COUNT = TRECH_ML.defineModel({
  name: "event_step_count",
  description: "Per-event step count from deposited energy and charged track length.",
  scale: "nano",
  inputs: ["total_edep_mev", "total_track_length_mm"],
  outputs: ["total_step_count"],
  structure: { family: "mlp", width: 16, depth: 2 },
  training: Object.assign({}, ML_DEMO_EVENT_RUNS, { epochs: 300, seed: 1234 }),
  tags: ["demo", "event_features"]
});
