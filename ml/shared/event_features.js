// Shared training-data declaration for the ML demo definitions. Run directories are
// repository-relative (the trech-ml CLI resolves them from the repo root); training,
// selection and test runs are disjoint Geant4 runs, never row splits of one run.
globalThis.ML_DEMO_EVENT_RUNS = {
  source: "event_features",
  runs: ["build/ml_demo/train_1", "build/ml_demo/train_2", "build/ml_demo/train_3", "build/ml_demo/train_4"],
  validationRuns: ["build/ml_demo/valid_5", "build/ml_demo/valid_6"],
  testRuns: ["build/ml_demo/test_7", "build/ml_demo/test_8"]
};
// Runs that only set the carried error bar (prediction interval); disjoint from all of the above
// so the validator's error-bar check is independent. Produced like the others with seeds 1009/1010.
globalThis.ML_DEMO_CALIBRATION_RUNS = ["build/ml_demo/cal_9", "build/ml_demo/cal_10"];
