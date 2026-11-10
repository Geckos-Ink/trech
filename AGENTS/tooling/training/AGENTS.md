# Training tools, model data and feature schemas — context and contracts

[Root principles](../../../AGENTS.md) · [Root roadmap](../../../ROADMAP.md) · [Parent](../AGENTS.md) · [Roadmap](ROADMAP.md)

Related owners: [Multi-scale inference](../../engine/inference/AGENTS.md) · [Coverage, uncertainty and trust](../../engine/inference/trust/AGENTS.md) · [Tests and validation ownership](../validation/AGENTS.md).

Read the root principles and the parent handbook first; then open only the subcategory relevant to the task. Source paths and shell commands in code spans/blocks are repository-relative unless stated otherwise; Markdown links resolve from this file.

- **Evolvo is optional offline tooling:** pinned submodule `thirds/evolvo`; adapter/trainer
  `tools/torch/trech_torch/evolve_structure.py` evolves bounded MLP definitions, selects on
  validation runs and reports accuracy on separate test runs. Never import it into C++/Studio or
  present genetic candidates as Geant4 truth. Ordinary surrogate training accepts `--depth N`.

- **Bounded fraction targets:** `trech-train-surrogate --logit-outputs ...` fits finite targets
  strictly inside (0,1), exporting v2 `sigmoid` inverse links after destandardisation. It does
  not silently clip endpoints or add pseudocounts; any MC smoothing is a dataset-builder decision
  recorded alongside unchanged raw labels. Training/holdout metrics are decoded fraction errors.
  Identity/exp/sigmoid may coexist; unlinked models retain v1. C++ and NumPy/Python TorchScript
  tests cover saturation, encoded overflow rejection, mixed links and invalid declarations.

- **Actual MC observer builder:** [`build_particle_observer_models.py`](../../../tools/torch/build_particle_observer_models.py)
  harvests strict serial photon counts/energy moments, consumes the existing lower learned
  response, selects weights on explicit development cases and freezes them before final cases.
  `data/particle_observer/` retains raw labels/hashes, metrics and the failed first attempt.
  [`particle_observer_cache.py`](../../../tools/torch/particle_observer_cache.py) binds future
  cache reuse to script, engine, lower-model and feature-source bytes, verifying them after
  harvesting before publication. Legacy caches miss; no historical identities are invented.
  Rebuilding is explicit offline scientific work, never a normal dependency/build step.

- **Feature/composition schemas stay in lock-step** across C++, the Python trainers, and
  [`tools/torch/trech_torch/dataset.py`](../../../tools/torch/trech_torch/dataset.py): event features
  `FeaturePipeline::kSchemaId` (`trech_event_features_v1`) and optics `kCompositionElements`
  (14 slots incl. `I` + density). `OpticsSurrogate::encodeComposition` renormalises all 14 slots.

- **[`tools/torch/trech_torch/`](../../../tools/torch)** — the harvest→train→plan pipeline.
  [`dataset.py`](../../../tools/torch/trech_torch/dataset.py) schema-locked harvesting + dimension-scale
  bands (keep in lock-step with the C++ schemas); `train_optics_surrogate.py` /
  `train_event_stratifier.py` / `train_surrogate.py` (console scripts `trech-train-*`; `.json`
  paths + planner are numpy-only, `.pt` needs the `[torch]` extra);
  [`distill_discrete_scenario_operators.py`](../../../tools/torch/distill_discrete_scenario_operators.py)
  owns the validation-only H2O/efflux teachers and regenerates their portable models/manifests;
  `plan_experiments.py` (active-learning coverage → `geant4_experiment_plan.json`; `--models`
  reads a trained model's exported domain and names the **operating points to simulate next**
  in raw input units — per-feature empty bins and the joint gaps between the regions training
  actually covered).

### JS model definitions and checkpoint store — [`tools/ml/`](../../../tools/ml) · [`js/trech_ml.js`](../../../js/trech_ml.js) · [`ml/`](../../../ml)

Contract: [`docs/ml_models.md`](../../../docs/ml_models.md). `js/trech_ml.js` is host-neutral
(QuickJS + Node). It provides `defineModel`/`defineSearch` validation, `structure_id` (FNV-1a-64
over the exported layer plan + IO + links), deterministic candidates, objectives/ranking,
`checkpointSignature`, and read-only `resolve`/`modelEntry`. `tools/ml/lib/` is Node-only.
`load.js` evaluates definition files in a `vm` sandbox with a time limit. `store.js` is the
**only writer** of `trech_model_registry_v1`, with a lock and atomic index. `orchestrate.js`
spawns `trech_torch.train_surrogate` / `evolve_structure` and registers their outputs.
`bin/trech-ml.cjs` is the CLI (`--json` for Studio).

- **Pitfalls:** structure is read from the checkpoint's weights, so a torch-less trainer's
  linear fallback is a *conflict*, never a silently mismatched checkpoint. Versions are
  monotonic and never reused. Search candidates rank on selection runs only; the deployed `best`
  carries test-run accuracy, or is labelled `selection_runs` (optimistic). Studio and scenarios
  never write the store. The store (`build/model_store/`) is a working area; committed validated
  models stay in `data/`.
- **Tests:** `node --test tools/ml/test/*.test.js` (CTest `trech_ml_models_js`, fake trainer
  `tools/ml/test/fake_python.cjs`), CTest `trech_ml_registry_quickjs` (QuickJS resolution
  fixture under `tests/fixtures/ml_registry/`), Studio `studio/tests/test_models.py`.

### Committed models & data — [`data/`](../../../data)

Source-of-truth learned models and fixtures (NOT generated build output): the bounded quantum-reference
models/rows and pinned PubChem comparison fixtures under [`data/molecular_series/`](../../../data/molecular_series)
(see `docs/molecular_series.md`), the Geant4-trained shared atom/molecular particle-response
models and pinned labels under [`data/particle_molecule/`](../../../data/particle_molecule)
(see `docs/particle_molecule.md`), and cascade stage models
([`data/cascade_demo/`](../../../data/cascade_demo), [`data/glass_cascade/`](../../../data/glass_cascade),
[`data/beaker_cascade/`](../../../data/beaker_cascade), [`data/lava_lamp_cascade/`](../../../data/lava_lamp_cascade),
[`data/briggs_rauscher_cascade/`](../../../data/briggs_rauscher_cascade),
[`data/polyurethane_cascade/`](../../../data/polyurethane_cascade),
[`data/elephants_toothpaste_cascade/`](../../../data/elephants_toothpaste_cascade)),
[`data/discrete_operators/`](../../../data/discrete_operators) (promoted H2O-cycle and efflux
transport/crossing distilled models + independent-holdout manifests),
[`data/glass_furnace_cascade/`](../../../data/glass_furnace_cascade) +
[`data/glass_furnace_operators/`](../../../data/glass_furnace_operators) (the illustrative teacher family
for `glass_from_sand.js`: property stages, per-material thermal/chemistry operators and the six
per-pair-material conduction maps) +
[`data/glass_furnace_operators_trained/`](../../../data/glass_furnace_operators_trained) (the five
**distilled** per-material operators + manifests — measured meso hull, occupancy, band and
independent held-out metrics; the promoted `physics_source=operator` default),
[`data/optics_surrogate_ridge.json`](../../../data/optics_surrogate_ridge.json),
[`data/optics_handbook_anchors.json`](../../../data/optics_handbook_anchors.json) (logged deltas only —
never feeds the extractor), and the read-only legacy `data/pubchem/` fallback.
