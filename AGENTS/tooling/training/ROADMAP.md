# Training tools, model data and feature schemas — roadmap

[Root principles](../../../AGENTS.md) · [Root roadmap](../../../ROADMAP.md) · [Parent](../ROADMAP.md) · [Handbook](AGENTS.md)

Related owners: [Multi-scale inference](../../engine/inference/ROADMAP.md) · [Coverage, uncertainty and trust](../../engine/inference/trust/ROADMAP.md) · [Tests and validation ownership](../validation/ROADMAP.md).

Maintain work in its owning branch. Dated results apply to the recorded checkout; they do not validate subsequent changes.

Training-tool work serves the [multi-scale inference plan](../../engine/inference/ROADMAP.md). Domain/holdout export, measured residuals and experiment-planning gaps are tracked in [trust](../../engine/inference/trust/ROADMAP.md); whole-run splits and observer promotion gates follow [validation](../validation/ROADMAP.md). Add new tooling-only gaps here when they do not belong to one of those workstreams.

## Priority queue

Every open item of this branch, highest priority first. The dated records below are delivery
history: the "Residual" and "Next" notes inside them are tracked here, and this queue wins
where they disagree. Keys and route steps: [priority keys](../../ROADMAP.md#priority-keys) ·
[implementation route](../../ROADMAP.md#implementation-route). When an item lands, delete it here, add a
dated record below, and queue its residuals in the same change.

- **P2** · R2 · Fresh-run recheck recipes for the particle observer (strict serial Geant4 harvests) and the spectrum models. ([detail](#ml-model-validation-2026-11-11))
- **P2** · R2 · Register other loader formats in the trech-ml store (logistic stratifier, optics ridge, operator manifests). ([detail](#js-model-definitions-and-checkpoint-store-2026-11-10))
- **P2** · R3 · Migrate scenarios that hand-write `models[]` paths onto definitions + `modelEntry` with committed fallbacks. ([detail](#js-model-definitions-and-checkpoint-store-2026-11-10))
- **P2** · R3 · Next set-network users: efflux/foam parcel operators, an MPNN where neighbour-of-neighbour structure matters, a conservative set operator through `ctx.interact`. ([detail](#js-model-definitions-and-checkpoint-store-2026-11-10))
- **P2** · R2 · Engine-side checkpoint usage recording (outside Studio) and an automatic age/size budget after searches. ([detail](#js-model-definitions-and-checkpoint-store-2026-11-10))
- **P2** · R2 · Particle-observer coverage holes and physical uncertainty calibration. (owned by the [engine/inference queue](../../engine/inference/ROADMAP.md#priority-queue))
- **P2** · R2 · Make the synthetic hierarchy demo beat its additive baseline before trusting the trainer on Geant4 data: more systems, minibatching, block-level capacity/latent sweeps, and a structure search over levels. Today the system level loses 0.09 R² to adding up its own block predictions. ([detail](#recursive-group-hierarchies-2026-11-17))
- **P2** · R2 · Hierarchy tooling parity with single models: TorchScript twins per level, `trech-ml` store registration and a JS `defineModel` hierarchy family, validator gates for chained-holdout reproduction and capacity coverage, and integrate the particle-hierarchy replay recipe into the recheck registry. ([detail](#recursive-group-hierarchies-2026-11-17))
- **P2** · R2 · First `trech-evolve-arch` search on Geant4-harvested runs of a non-optics family (CNT device metrics or fluid parcels), graded against grid/random `defineSearch` on the same splits. Record test-run R², evaluations and epochs, with and without reused knowledge. ([detail](#evolved-architectures-gfsl-nn-2026-11-17))
- **P2** · R2 · Route `TRECH_ML.defineSearch({strategy: "evolvo"})` and the `trech-ml` store to GFSL-NN (preferably through the engine's `trech arch`, which already applies the classic reference bar): genome and knowledge in the checkpoint, `format: "torchscript"` registration for non-dense winners, and validator gates for evolved models (TorchScript parity, sidecar binding, retrain reproduction). ([detail](#evolved-architectures-gfsl-nn-2026-11-17))
- **P2** · R2 · Evolve set networks and hierarchy levels: masked/padded `set` inputs in GFSL-NN, a lowering of DeepSets/MPNN-shaped genomes to `generic_surrogate_v3`, then per-level search in `trech-train-hierarchy`. ([detail](#evolved-architectures-gfsl-nn-2026-11-17))
- **P3** · R2 · Extend specialist training to density-connected regimes with measured assignment stability and add typed store registration for standalone specialist modules. ([study](../../../docs/inference/multiscale_domain_study.md))
- **P3** · R7 · Native deterministic (`trech_dmath`) evaluation of residual/normalization/attention primitives (so evolved non-dense architectures get byte-reproducible evaluation like dense JSON chains; LibTorch is required and already runs them), cutoff-neighbourhood graphs, and C++ evaluator parity inside the validator. Torch-side residual/norm/attention layers now exist through GFSL-NN. ([detail](#evolved-architectures-gfsl-nn-2026-11-17))

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
  - [x] (2026-11-11) Whole-run fold rotation: `defineSearch({runFolds: K})` deals runs +
    validationRuns into K folds by whole run; the loss SE is taken across folds and runner-up
    comparisons are paired per fold; the winner is refit on all fold runs and validated against
    them. Executed with torch 2.8 on the 6 `config_stratify` train/selection runs (3 folds × 2
    seeds, 13 structures, `ml/searches/event_step_count_folds.search.js`): between-fold loss std
    averaged 0.060 vs 0.028 within-fold seed std, i.e. run-to-run sampling noise is about twice the
    initialization noise the seed-only search measured. Lowest mean loss `mlp(8×2,silu)`
    0.282 ± 0.029; the one-SE rule picked `mlp(4×2,silu)` (37 parameters), not distinguishable
    from the runner-up (paired gap 0.003 < band 0.024). Refit on 6 runs: test R² 0.617, beats
    ridge (skill 0.07), all 11 applicable gates pass. Not a validated observer model.
  - [x] (2026-11-11) Runs that replay one configuration (same provenance `config_hash`) are
    dealt as one fold unit (`runFolds(runs, k, seed, groups)`; the orchestrator reads each run's
    provenance, reports `run_fold_groups` and says when a run had no hash). Node tests cover a
    grouped deal, the unchanged ungrouped deal and too few units after merging.
- [x] (2026-11-11) Per-layer widths and silu/tanh/relu/sigmoid activations end to end: trainer
  `--widths/--activation(s)`, canonical JS structures (uniform spellings keep their old
  `structure_id`), search `space.activations/shapes/layouts`, Studio/store labels. The C++
  `GenericSurrogate` already evaluated these activations; a searched per-layer tanh checkpoint
  resolved through `modelEntry` gives engine predictions identical to the Python evaluator.
  - [x] (2026-11-11) DeepSets/MPNN set networks: portable `generic_surrogate_v3`, C++
    `GenericSurrogate` evaluator (1e-9 parity with NumPy on committed fixtures, permutation
    invariance, mask, fail-closed layouts), torch trainer `--network`, TorchScript twins, JS
    `family: "deepsets"|"mpnn"` structures/search spaces, validator gates. On a synthetic
    4-point pair-interaction target (gain × Σ pairwise Gaussian proximity, mask, 1 context input;
    3000 train / 800 selection / 800 test / 800 calibration rows) a store search ranked MPNN
    2 rounds (selection loss 0.025, test R² 0.983) > MPNN 1 round (0.028) > DeepSets (0.097) >
    MLP 32×2 (0.129); retrain identical, all 12 gates incl. TorchScript parity pass. Synthetic
    data: this exercises the architecture, not physics.
  - [ ] Residual/normalization layers, attention, and graphs other than the complete graph over
    present elements (e.g. cutoff neighbourhoods) are not implemented.
  - [x] (2026-11-11) First scenario on a set network: `glass_from_sand`
    `conduction_source=set_network` runs one DeepSets model per cell material through
    `ctx.evolve` over the cell's six face neighbours (present / temperature offset / one-hot
    material; mask = present), distilled from the pair conduction operator by
    `tools/torch/build_glass_conduction_set_models.py` (every run + command recorded in
    `data/glass_furnace_conduction_set/build_record.json`; 6 train / 2 selection / 9 calibration /
    2 test operating points). Test-run R² 0.9997 / 0.9999 / 0.9998 (batch / melt / glass), all
    validator gates pass, run-level 90% intervals cover 98.7 / 98.5 / 99.6% of test rows. In the
    scenario (default conditions, same seed) it reproduces the pair run's 648 glass units, 72
    glass cells and first-glass tick; mean T +0.98 K; the learned conduction's net heat is 0.29% of
    the heat it moves (reported, since a per-cell model is not equal-and-opposite). Validation
    case `glass_set_conduction_matches_pair` 17/17 (suite run `out_glass_from_sand_set_conduction`).
    Distilled from an illustrative linear teacher: it proves the set-network operator path, not
    glass physics. The default stays `pair`.
  - [ ] Next set-network users: the efflux / foam parcel operators that flatten fixed neighbour
    slots, and an MPNN where neighbour-of-neighbour structure matters (the glass teacher is
    pairwise-additive, so DeepSets suffices there). A conservative set operator (antisymmetric
    per-pair messages through `ctx.interact`) would remove the net-heat error.
- [ ] Engine-side usage recording (runs outside Studio need `trech-ml touch --run`); an
  optional age/size budget enforced automatically after searches.
- [ ] Migrate scenarios that hand-write `models[]` paths onto definitions + `modelEntry` with
  committed fallbacks, so retraining a stage is a definition edit rather than a path edit.

## Evolved architectures (GFSL-NN) (2026-11-17)

- [x] Evolvo `evolvo.nnarch` (Evolvo `main`): a fixed 7-slot genetic language for torch
  architectures.
  - Language: vec/set tensors, linear/act/norm/dropout/add/mul/concat/attend/pool/context/
    tokenize, and `mlp`/`resmlp`/`transformer`/`deepsets` macros with integer arguments plus
    user macros. Cascading, budget-masked options; repair after every edit.
  - Learning: discovered-context `ContextualStats`, `AdaptivePolicy` slot and mutation weights,
    an `EfficiencyModel` size frontier, `PlateauStopper` (learned patience, equal-effort hopeless
    stop), a converging search, and `Knowledge` persistence.
  - Packaging: the Evolvo package init became lazy, so `evolvo.nnarch` imports without NumPy.
- [x] TRECH adapter `trech_torch.evolve_architecture` (`trech-evolve-arch`).
  - Disjoint run splits.
  - Native JSON for dense chains, TorchScript + sidecar + `trech_evolved_arch_v1` otherwise.
  - Retrain-for-export when the size-penalized winner differs.
  - Contract in [`docs/inference/evolvo_architectures.md`](../../../docs/inference/evolvo_architectures.md).
- Verification:
  - Evolvo `tests/test_arch.py`: 13/13 with torch, 12 + 1 skip on the NumPy-less CTest Python.
  - CTest `trech_evolvo_arch`.
  - Synthetic demo: held-out R² ≈ 0.996 after 38 evaluations. A rerun with saved knowledge
    took 28 evaluations and 7,389 epochs (fresh: 17,103) and reached a lower validation loss
    (one seed, one synthetic task).
- Residual (queued above): no Geant4-harvested search and no baseline comparison, no
  `defineSearch`/store/validator routing, no set inputs or hierarchy levels, no domain in the
  sidecar, no native C++ evaluation of non-dense primitives. Macro mining and FLOP/latency costs
  are Evolvo roadmap items.

## Recursive group hierarchies (2026-11-17)

- [x] `trech_torch/hierarchy.py` (`trech-train-hierarchy`) trains the levels `ctx.lift`
  evaluates ([contract](../../../docs/inference/group_hierarchy.md)). It handles plan/sample formats,
  engine-identical partition replay, and end-to-end torch training through every level on
  chained predictions. Levels can mix supervised outputs and named latents. Whole-run selection
  samples drive early stopping, with optional AdamW weight decay. The CLI refuses a run shared
  between roles. Domain, chained holdout and run-level intervals are measured on the exported
  JSON through `lift_np`.
- [x] Committed parity fixture `tests/fixtures/ml_group_hierarchy/` (`regenerate.py`, torch venv;
  regenerates byte-identically here) and `tests/test_group_hierarchy.py` (CTest
  `trech_group_hierarchy_py`; it now runs under `TRECH_ML_PYTHON` and fails without NumPy).
- Demo record: synthetic 500 train / 100 selection / 200 held-out systems, chained held-out R² cell 0.938 / block 0.718 /
  system 0.530, run-level 90% intervals with the guarantee (9 runs). The learned system level is
  **worse** than g × Σ of its own predicted block energies (R² 0.620; 0.875 with true block
  labels). The cross-scale correction does not yet pay for itself, and the block level is the
  bottleneck. A first 800-system DeepSets run without early stopping overfit (system 0.35). See
  [the demo record](../../../docs/inference/group_hierarchy.md#synthetic-demonstration-architecture-only).
- [ ] TorchScript twins, store/`defineModel` integration, hierarchy-specific validator gates and
  recheck recipes (queued above). The trainer is full-batch; very large populations would need
  minibatching over systems.

## ML model validation (2026-11-11)

- [x] Independent validator `trech_torch.validate_model` (`trech-validate-surrogate`,
  `trech-ml validate`, `--validate` on train/search) with named gates; verdicts are recorded on
  store checkpoints and shown by `trech-ml show` and Studio's Models dock. Contract:
  [`docs/inference/ml_models.md`](../../../docs/inference/ml_models.md#validating-a-model).
- [x] Committed-model audit [`docs/validation/ml_model_audit.md`](../../../docs/validation/ml_model_audit.md) + CTest
  `trech_ml_model_audit` (staleness + crafted-model gates). Executed on this checkout: 50 committed
  models all load under the engine's rules and stay finite on their trained domain; trust profile
  complete 14 / partial 8 / none 28 (the illustrative hand-authored cascade maps and the untrained
  glass-furnace teachers); 14 carry a joint reference. Both spectrum-prediction models' own
  holdout R²min is negative (−7.97 atomic, −0.48 molecular), consistent with
  [`docs/research/spectrum_prediction.md`](../../../docs/research/spectrum_prediction.md): flagged as warnings.
- [x] Executed with torch 2.8 (`build/render-venv`) on the 8 `config_stratify` demo runs
  (4 train / 2 selection / 2 test): the fixed 16×2 SiLU definition passes all 11 applicable gates
  (test R² 0.661, beats the ridge baseline, 96% of test rows covered). The demo search (19
  structures × 3 seeds, activations × uniform/taper) selects `mlp(8→4,tanh)` at selection loss
  0.389 ± 0.013 but reports it **not distinguishable** from the runner-up (gap 0.024 < band 0.029);
  its test R² is 0.643, i.e. not better than the fixed definition — selection noise, as reported.
  All gates pass incl. TorchScript twin parity (1.1e-6). Not a validated observer model.
- [x] (2026-11-11) Error-bar check on separate runs: `--calibration-runs` /
  `training.calibrationRuns` set a split-conformal `prediction_interval` (+ RMSE) on runs disjoint
  from training, holdout and test; `sigma_calibration` uses it and reports `independent`. On the
  `config_stratify` demo (2 new Geant4 calibration runs, seeds 1009/1010) the fold-search winner's
  calibration σ is within ×1.10 of the test RMSE and its 90% interval covers 93.5% of test rows
  (independent). On the synthetic set data DeepSets/MPNN intervals also pass independently.
- [x] (2026-11-11) Run-level (grouped) conformal error bars: `--calibration-runs` now carries
  `run_grouped_conformal_abs_residual` — each run's own conformal quantile q_r, then the
  ceil((R+1)c)-th smallest q_r — with `run_level_guarantee` (needs R ≥ c/(1−c), 9 at 0.9),
  `per_run_half_width` and the old row-pooled `pooled_half_width`. Quantiles are exact order
  statistics (the old `np.quantile(..., "higher")` indexed by (n−1)q). On the glass set models
  two calibration runs gave per-run 90% widths 0.0044 vs 0.0097 K/s and a pooled interval that
  covered only 79% of test rows; with nine runs the guaranteed interval covers ≥ 98.5%.
  Committed models trained before this keep their pooled blocks until retrained.
- [x] (2026-11-11) Fresh-run re-checks of committed models: `trech_torch.recheck_models` +
  `data/ml_recheck_recipes.json` + generated `docs/validation/ml_model_recheck.md` (CTest
  `trech_ml_model_recheck`). The three discrete operators were re-graded on 2 × 6000 fresh teacher
  rows each (seeds never used in training/holdout): regenerated original holdouts reproduce the
  carried RMSE exactly (no producer drift), fresh R² equals carried R² to ≤0.002 (h2o 0.9973,
  efflux transport ≥0.9992, crossing 0.9808 vs 0.9827), independent σ checks pass. They remain
  `measured:false` teacher distillations.
- [x] (2026-11-11) Engine recipes carry per-seed operating points (`seed_params`), an `env`
  block and regenerable training runs (`training.seeds`); fresh runs must differ in conditions.
  Recorded recipes for the three glass set-network models, the five glass-furnace operators and
  the polyurethane reaction operator (results in `docs/validation/ml_model_recheck.md`, 12 models, 0 fail).
  Fresh R² hold the carried ones: set models 0.9997 / 0.9998 / 0.9997, glass-furnace operators
  1.0 on the 3D scenario, polyurethane ≥ 0.9944 per output. The set batch_solid model warns
  because its run-level interval is conservative (98.8% fresh coverage vs 90% nominal; fresh RMSE
  0.65× the carried σ), the price of the run-level guarantee. The other warnings are the
  pre-existing missing `joint_reference` on older models.
  - Glass-furnace originals are NOT reproducible and no holdout reproduction is claimed: they
    were harvested from the 2D scenario revision 36e979d (`CELL_COUNT = SIDE*SIDE`, today 3D).
    That revision still runs on today's engine, but a grid over the unrecorded holdout knobs
    (1560 K cells 4/5 ± sub-steps, 1820 K ambient 320–500 K) got within ~2% of the carried row
    counts (2,211 / 757 / 932) without matching them, and Geant4 has changed since. Their recipe
    grades them on fresh 1640 K / 1790 K runs of the current 3D scenario.
  - Polyurethane originals used sampler variants (`boundary`, `fullpop_raw`) no longer in the
    scenario; fresh 290 K / 303 K runs grade the committed operator (needs the PubChem cache).
- [x] (2026-11-26) Portable model metadata. The five glass-furnace operators recorded
  `trained_from.runs`/`validation_runs` as `/Users/<author>/…/build/glass_train/…`; they now
  read `build/glass_train/…` (weights unchanged). New static gate `portable_metadata`: an
  absolute metadata path (`/…`, `~/…`, drive letters, UNC) fails the committed audit and warns
  for ad-hoc validation (models trained on temporary runs). Audit 53 models, 0 failing. The
  changed digests were re-checked on fresh engine runs (`recheck_models --only`, which now
  merges into the committed report instead of dropping the other entries): every gate keeps its
  verdict and fresh R² stays 1.0; the fresh runs differ slightly from 2026-11-18 (the scenario
  changed since), moving σ ratios within the ×1.5 gate (thermal_glass test/carried RMSE 0.80 →
  1.17, 1σ coverage 0.66 → 0.34). Validation report writers also record run directories
  repository-relative (`portable_path`), and the committed validation reports lost their
  `/Users/<author>` prefixes.
- [ ] Recipes for the particle observer (`build_particle_observer_models.py`: strict serial
  Geant4 harvests with frozen final cases) and the spectrum models (`projects/spectrum_prediction`).
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
  density/source/geometry against independent references. See the [observer limits](../../../docs/inference/particle_observer.md).
