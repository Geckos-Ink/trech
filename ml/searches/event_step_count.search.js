// Structure search: which network shape best predicts the per-event step count?
//
//   node tools/ml/bin/trech-ml.cjs search ml/searches/event_step_count.search.js --dry-run
//   node tools/ml/bin/trech-ml.cjs search ml/searches/event_step_count.search.js
//
// Candidates are trained on `runs`, ranked on the selection runs (`validationRuns`), and the
// winner is re-trained with the untouched `testRuns` as its carried holdout. Every candidate is
// stored under its own structure_id, so differently-shaped checkpoints never collide.
//
// The space varies activation (silu/tanh) and shape (uniform or tapered per-layer widths). Each
// candidate is trained with three seeds; the report gives each candidate's mean ± standard error
// and whether the winner is distinguishable from the runner-up. The one-standard-error rule then
// picks the smallest net within one standard error of the best mean. Add --validate to run the
// independent validator (test accuracy, linear baseline, leakage, σ calibration) on the winner.
TRECH_INCLUDE("../shared/event_features.js");

TRECH_ML.defineSearch({
  name: "event_step_count_search",
  description: "Width/depth search for the per-event step-count surrogate.",
  scale: "nano",
  inputs: ["total_edep_mev", "total_track_length_mm"],
  outputs: ["total_step_count"],
  training: Object.assign({}, ML_DEMO_EVENT_RUNS, { epochs: 200, seed: 1234 }),
  strategy: "grid",
  space: { families: ["linear", "mlp"], width: [8, 16, 32], depth: [1, 2],
           activations: ["silu", "tanh"], shapes: ["uniform", "taper"] },
  budget: { maxCandidates: 24, maxParameters: 5000 },
  repeats: 3,
  selectionRule: "one_standard_error",
  // Lower is better. Built-ins: "r2_min", "r2_mean", "rmse_mean", "nrmse_mean"; a function
  // receives the selection metrics {output: {r2, mae, rmse}} and the candidate.
  objective: function (metrics, candidate) {
    return 1 - metrics.total_step_count.r2;
  },
  complexityPenalty: 1e-6,
  keepCandidates: 2
});
