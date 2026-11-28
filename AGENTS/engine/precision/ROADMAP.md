# Precision profiles and runtime budgets — roadmap

[Root principles](../../../AGENTS.md) · [Root roadmap](../../../ROADMAP.md) · [Parent](../ROADMAP.md) · [Handbook](AGENTS.md)

Related owners: [Panels, run reports and resource controls](../../studio/workspace/ROADMAP.md) · [Scenario bundles and shared helpers](../../scenarios/bundles/ROADMAP.md).

Maintain work in its owning branch. Dated results apply to the recorded checkout; they do not validate subsequent changes.

## Priority queue

Every open item of this branch, highest priority first. The dated records below are delivery
history: the "Residual" and "Next" notes inside them are tracked here, and this queue wins
where they disagree. Keys and route steps: [priority keys](../../ROADMAP.md#priority-keys) ·
[implementation route](../../ROADMAP.md#implementation-route). When an item lands, delete it here, add a
dated record below, and queue its residuals in the same change.

- **P2** · R4 · Soft deadlines cannot interrupt a long event, hook or initialization; confidence/error-driven space/time refinement needs validated scenario error estimates first. ([detail](#adaptive-precision-inference-depth-and-resource-scheduling))
- **P2** · R4 · Shared per-run inference budget: cascade caps are per call and batched `evolve`/`react`/`interact` calls are atomic. ([detail](#adaptive-precision-inference-depth-and-resource-scheduling))
- **P3** · R4 · Precision-target residuals: the stop watches only the total per-event deposit; let a run name another tally (a scored volume's deposit, a transmitted fraction, a declared emit) and grade several at once; a multi-threaded stop that stays reproducible (fixed event blocks merged in order); lab sessions and Studio's live lab. ([detail](#statistical-precision-target-2026-11-28))

## Statistical precision target (2026-11-28)

- [x] `run.precisionTarget {relativeStderr, minEvents}` / `--precision-target <r>`: a batch run stops
  (soft, after the event) once the standard error of the mean per-event deposited energy is at
  most r of the mean, after at least `minEvents` (default 30); `nEvents` stays the limit. This is
  the first engine error estimate that drives work: the Monte Carlo sampling error of the run's
  own tally, not a model-accuracy claim. Serial manager, so strict mode keeps byte replay;
  threads > 1, lab, UI and macro are refused. Scores `precision_target`
  (`trech_precision_target_v1`), `requested_events`, `stop_reason`; provenance target on
  `run_start` and outcome on `run_end`; conditional serialization keeps other config hashes.
  Measured: a 1 MeV photon beam into 200 mm of water with a 5% target stopped at 564 of 4000
  events, achieved 4.9966% = the run's `system_event_edep_stderr_mev / mean` (to 1e-15), and the
  replay was identical. CTest `trech_precision_target` 9/9 (early stop, estimator identity, strict
  replay, provenance, CLI flag equivalence, unreachable target, zero-deposit geantino, threads
  refusal, unchanged shape without a target); `test_adaptive_precision` adds the Welford-vs-direct
  estimator, min events, zero mean, NaN, parse/round-trip and refusals. Studio: the Precision dock's
  **Statistical precision** control and a run-summary section
  ([workspace roadmap](../../studio/workspace/ROADMAP.md#adaptive-precision-and-resources)).

## Adaptive precision, inference depth and resource scheduling

- [x] Continuous scenario refinement (`--refinement`, JS `factor`) within authored axis bounds;
  explicit unsupported-scenario failures and actual-axis reporting.
- [x] C++ `SimulationBudget`: predictive serial runs stop at whole event boundaries using measured
  EWMA event cost; actual/requested counts and stop reason agree across scores/provenance/scene.
  Strict runs reject time-based scheduling; existing no-budget config serialization is unchanged.
- [x] Arbitrary cascade depth, dependency-ready scheduling within bands, deterministic stage caps
  and target-output early exit with skipped-stage traces. Twelve-stage forward/reverse chains tested.
- [x] Studio continuous refinement/time controls and adaptive representation detail/resources.
- [x] Evolvo pinned in `thirds/evolvo`; optional offline GFSL width/depth search and portable model
  export, with disjoint training/selection/test runs. Ordinary trainer supports `--depth`.
- [ ] Residual: soft deadlines cannot interrupt a long event/hook or bound initialization;
  confidence/error-driven spatial/time-step refinement requires validated scenario-specific error
  estimates. No automatic accuracy claim follows from a resource budget.
- [ ] Residual: batched evolve/react/interact calls remain atomic; cascade caps are per property
  call, not a shared per-run inference budget. Model discovery/training/deployment remain explicit.
- [x] Evolutionary search beyond uniform MLP width/depth: the GFSL-NN language (2026-11-17)
  searches DAGs of primitives and macros with per-row activations. Candidate training stays
  atomic under its time budget.
- [x] (2026-11-27) Measured search-quality comparison on Geant4 runs: `trech-compare-search`
  ranks grid, random, Evolvo width/depth, random GFSL-NN, learned GFSL-NN and knowledge reuse with
  one trainer and equal budgets on the 222 particle-observer runs (20 seeds). No strategy beats a
  24-point grid on held-out runs; the learned search transfers worse than its selection loss.
  [Results](../../../docs/inference/evolvo_architectures.md#search-quality-on-geant4-runs-2026-11-27);
  follow-ups are owned by the [training queue](../../tooling/training/ROADMAP.md#priority-queue).
