# Training tools, model data and feature schemas — roadmap

[Root principles](../../../AGENTS.md) · [Root roadmap](../../../ROADMAP.md) · [Parent](../ROADMAP.md) · [Handbook](AGENTS.md)

Related owners: [Multi-scale inference](../../engine/inference/ROADMAP.md) · [Coverage, uncertainty and trust](../../engine/inference/trust/ROADMAP.md) · [Tests and validation ownership](../validation/ROADMAP.md).

Maintain work in its owning branch. Dated results apply to the recorded checkout; they do not validate subsequent changes.

Training-tool work serves the [multi-scale inference plan](../../engine/inference/ROADMAP.md). Domain/holdout export, measured residuals and experiment-planning gaps are tracked in [trust](../../engine/inference/trust/ROADMAP.md); whole-run splits and observer promotion gates follow [validation](../validation/ROADMAP.md). Add new tooling-only gaps here when they do not belong to one of those workstreams.

## JS model definitions and checkpoint store (2026-11-10)

- [x] `TRECH_ML.defineModel` / `defineSearch` (grid, seeded random, custom generator, Evolvo).
  The `trech-ml` CLI trains/searches through the existing Python trainers. The typed, versioned
  checkpoint store refuses structure conflicts and records usage from provenance SHA-256. It
  supports pin/activate/delete/prune/verify/gc. Scenarios resolve checkpoints with
  `TRECH_ML.modelEntry`; Studio has a Models dock. Verification: `node --test` 12/12, CTest
  `trech_ml_models_js` + `trech_ml_registry_quickjs`, Studio `test_models.py` 7/7. A real
  torch run on 8 `config_stratify` runs took 7 candidates to an 8×2 MLP: test-run R² 0.63,
  retrain identical.
- [ ] Register other loader formats (logistic stratifier, optics ridge, operator manifests).
  Today only `generic_surrogate_v1/v2` JSON + TorchScript twins are accepted.
- [x] (2026-11-11) Repeated-seed candidate scoring: `defineSearch({repeats, selectionRule})`
  trains each candidate under N seeds, ranks on the mean loss and reports standard errors, a
  tie band (two combined standard errors) and whether the winner is distinguishable from the
  runner-up; `one_standard_error` picks the smallest net within one SE. Only seed 0 is stored.
  - [ ] Repeated **run** splits (rotate which whole runs select) so between-run sampling noise
    is measured too; seeds only measure initialization noise today.
- [x] (2026-11-11) Per-layer widths and silu/tanh/relu/sigmoid activations end to end: trainer
  `--widths/--activation(s)`, canonical JS structures (uniform spellings keep their old
  `structure_id`), search `space.activations/shapes/layouts`, Studio/store labels. The C++
  `GenericSurrogate` already evaluated these activations; a searched per-layer tanh checkpoint
  resolved through `modelEntry` gives engine predictions identical to the Python evaluator.
  - [ ] DeepSets/MPNN and residual/normalization layers from the spectrum catalogue need a
    portable format + C++ evaluator first; not started.
- [ ] Engine-side usage recording (runs outside Studio need `trech-ml touch --run`); an
  optional age/size budget enforced automatically after searches.
- [ ] Migrate scenarios that hand-write `models[]` paths onto definitions + `modelEntry` with
  committed fallbacks, so retraining a stage is a definition edit rather than a path edit.

## ML model validation (2026-11-11)

- [x] Independent validator `trech_torch.validate_model` (`trech-validate-surrogate`,
  `trech-ml validate`, `--validate` on train/search) with named gates; verdicts are recorded on
  store checkpoints and shown by `trech-ml show` and Studio's Models dock. Contract:
  [`docs/ml_models.md`](../../../docs/ml_models.md#validating-a-model).
- [x] Committed-model audit [`docs/ml_model_audit.md`](../../../docs/ml_model_audit.md) + CTest
  `trech_ml_model_audit` (staleness + crafted-model gates). Executed on this checkout: 50 committed
  models all load under the engine's rules and stay finite on their trained domain; trust profile
  complete 14 / partial 8 / none 28 (the illustrative hand-authored cascade maps and the untrained
  glass-furnace teachers); 14 carry a joint reference. Both spectrum-prediction models' own
  holdout R²min is negative (−7.97 atomic, −0.48 molecular), consistent with
  [`docs/spectrum_prediction.md`](../../../docs/spectrum_prediction.md): flagged as warnings.
- [x] Executed with torch 2.8 (`build/render-venv`) on the 8 `config_stratify` demo runs
  (4 train / 2 selection / 2 test): the fixed 16×2 SiLU definition passes all 11 applicable gates
  (test R² 0.661, beats the ridge baseline, 96% of test rows covered). The demo search (19
  structures × 3 seeds, activations × uniform/taper) selects `mlp(8→4,tanh)` at selection loss
  0.389 ± 0.013 but reports it **not distinguishable** from the runner-up (gap 0.024 < band 0.029);
  its test R² is 0.643, i.e. not better than the fixed definition — selection noise, as reported.
  All gates pass incl. TorchScript twin parity (1.1e-6). Not a validated observer model.
- [ ] `sigma_calibration` is only independent when the carried σ comes from different runs than
  the test; trainer-side separation of calibration runs from test runs is open.
- [ ] Run-based validation of committed `data/` models: most do not retain their training/test
  runs; add a per-model test-run pointer (or manifest field) so `trech-ml validate` can re-measure
  them, starting with the particle observer and discrete operators.
- [ ] C++-side evaluator parity inside the validator (today: Python pure/NumPy/TorchScript; C++
  parity is covered by `test_generic_surrogate` and was checked by hand on the demo).

## Trainer outputs and observer models

- [x] Explicit logit targets export portable v2 sigmoid links without implicit clipping or
  pseudocounts. Mixed-link NumPy/trainer/optional Python TorchScript tests pass, including natural-unit
  metrics, invalid train/holdout targets, saturation and non-finite encoded failures.
- [ ] Bounded outputs do not establish calibrated uncertainty or good generalization. Preserve
  independent physics/observer promotion gates and record any finite-MC label smoothing explicitly.

- [x] A real MC-trained meso observer extends the shared atomic/nano CHNO models, retaining
  222 raw-label rows, frozen model evidence, independent final conditions and a failed-attempt
  archive. Runtime and offline C++/Python decoder results agree within 2.78e-16 in reviewed emits.
  Future cache reuse checks engine/model/feature-source identity; no legacy cache is silently trusted.
- [ ] Resolve measured per-feature/joint coverage holes with additional training and new final
  holdouts before broader promotion; calibrate physical uncertainty and validate varied
  density/source/geometry against independent references. See the [observer limits](../../../docs/particle_observer.md).
