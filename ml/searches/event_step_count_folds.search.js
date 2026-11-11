// Structure search with WHOLE-RUN fold rotation and calibration-run error bars.
//
//   node tools/ml/bin/trech-ml.cjs search ml/searches/event_step_count_folds.search.js --validate
//
// Seeds alone (event_step_count.search.js) only measure initialization noise: every seed is
// scored on the same two selection runs. Here the six training + selection runs are dealt into
// three whole-run folds; every candidate is trained on two folds and scored on the third, under
// two seeds each, so the reported standard error includes run-to-run sampling noise. Candidates
// are compared paired across the same folds. The winner is refit on all six runs and graded on
// the untouched test runs; its carried error bar (a split-conformal interval) is set on two
// separate calibration runs, so the validator's sigma check is an independent one.
TRECH_INCLUDE("../shared/event_features.js");

TRECH_ML.defineSearch({
  name: "event_step_count_folds",
  description: "Fold-rotated width/depth/activation search for the per-event step-count surrogate.",
  scale: "nano",
  inputs: ["total_edep_mev", "total_track_length_mm"],
  outputs: ["total_step_count"],
  training: Object.assign({}, ML_DEMO_EVENT_RUNS, { calibrationRuns: ML_DEMO_CALIBRATION_RUNS, epochs: 200, seed: 1234 }),
  strategy: "grid",
  space: { families: ["linear", "mlp"], width: [4, 8, 16], depth: [1, 2], activations: ["silu", "tanh"] },
  budget: { maxCandidates: 24, maxParameters: 5000 },
  runFolds: 3,
  repeats: 2,
  selectionRule: "one_standard_error",
  objective: "r2_min",
  complexityPenalty: 1e-6,
  keepCandidates: 2
});
