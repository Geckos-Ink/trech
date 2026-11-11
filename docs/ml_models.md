# ML model definitions, structure searches and the checkpoint store

TRECH exposes learned-model *definitions* to JavaScript. A definition file states what a model is:
named inputs/outputs, dimension band, network structure and the Geant4 runs it learns from. A search
file states how to choose a structure. The offline `trech-ml` CLI trains both through the existing
Python trainers. It keeps every produced checkpoint in a typed, versioned store. Scenarios
resolve a stored checkpoint into an ordinary `models[]` entry. Studio's **Models** dock edits the
files live and manages the store.

Every checkpoint is a **learned comparison model**. Its predictions are not Geant4 results, and the
store never upgrades a model's trust: carried accuracy is whatever the trainer measured, labelled
with the data it was measured on.

| Piece | Source | Runs in |
| --- | --- | --- |
| Definition/search library, structure IDs, registry resolution | [`js/trech_ml.js`](../js/trech_ml.js) | QuickJS (`TRECH_INCLUDE`) and Node |
| Sandboxed evaluation of definition files | [`tools/ml/lib/load.js`](../tools/ml/lib/load.js) | Node |
| Checkpoint store (`trech_model_registry_v1`, only writer) | [`tools/ml/lib/store.js`](../tools/ml/lib/store.js) | Node |
| Training / search orchestration | [`tools/ml/lib/orchestrate.js`](../tools/ml/lib/orchestrate.js) → `trech_torch.train_surrogate` / `evolve_structure` | Node + Python |
| CLI | [`tools/ml/bin/trech-ml.cjs`](../tools/ml/bin/trech-ml.cjs) | Node ≥ 18 |
| Definitions shipped with the repo | [`ml/`](../ml) | — |
| Studio dock | `studio/trech_studio/{models.py,engine/models.py,ui/models.py}` | PySide6 |

## Fixed-structure definitions

```js
TRECH_ML.defineModel({
  name: "event_step_count",              // store directory + scenario model name
  scale: "nano",                         // atomic | nano | micro | meso | macro
  inputs: ["total_edep_mev", "total_track_length_mm"],
  outputs: ["total_step_count"],
  links: { total_step_count: "identity" },   // identity | exp | sigmoid (v2 output links)
  structure: { family: "mlp", width: 16, depth: 2 },   // or { family: "linear", l2: 1e-3 }
  // per layer: { family: "mlp", widths: [32, 16, 8], activation: "tanh" }
  //        or: { family: "mlp", widths: [12, 6], activations: ["tanh", "relu"] }
  training: {
    source: "event_features",            // scores | event_features | hook_emits (+ tag, expand)
    runs: ["build/ml_demo/train_*"],     // repository-relative; globs allowed
    validationRuns: ["build/ml_demo/valid_*"],
    testRuns: ["build/ml_demo/test_*"],
    epochs: 300, lr: 0.01, seed: 1234, torchscript: false
  }
});
```

Validation is strict. Unknown keys, invalid names, a column that is both an input and an output, or
overlapping train/validation/test run lists all throw with the file line. Training settings map
one-to-one to `trech-train-surrogate` flags (`--hidden/--depth/--activation` for a uniform MLP,
`--widths 32,16,8 --activations tanh,tanh,relu` for a per-layer one). Hidden activations are
`silu` (default), `tanh`, `relu` and `sigmoid`: the ones the torch trainer exports and the C++
`GenericSurrogate` evaluates. A per-layer spelling of a uniform network normalizes to the uniform
form, so it keeps the same `structure_id` and `definition_hash`. Plain training carries the test runs as its holdout when declared. Without test
runs it uses the validation runs. Without either, it uses the trainer's random row split.
`holdout_source` records which one applied.

The result carries `structure_id`, `parameter_count`, the exported layer plan (`signature`) and a
`definition_hash`.

**Structure identity.** `structure_id` = `s` + the first 12 hex digits of FNV-1a-64. The hash
covers the canonical JSON of the exported layer plan (`[in, out, activation]` per dense layer), the
named inputs/outputs, and the output links. It is independent of key order and of training
hyperparameters (a linear `l2` changes the weights, not the structure). Two checkpoints can be
loaded into the same definition **iff** their IDs match.

## Structure searches

```js
TRECH_ML.defineSearch({
  name: "event_step_count_search",
  inputs: [...], outputs: [...], scale: "nano",
  training: { runs: [...], validationRuns: [...], testRuns: [...] },   // validationRuns required
  strategy: "grid",                    // grid | random (seeded) | custom | evolvo
  space: { families: ["linear", "mlp"], width: [8, 16, 32], depth: { min: 1, max: 3 }, l2: [1e-3],
           activations: ["silu", "tanh"],    // default ["silu"]
           shapes: ["uniform", "taper"],     // taper halves the width per layer (min 2); default uniform
           layouts: [[48, 24, 12]] },        // explicit per-layer widths, crossed with activations
  budget: { maxCandidates: 24, maxParameters: 200000, seconds: 0 },
  objective: "r2_min",                 // r2_min | r2_mean | rmse_mean | nrmse_mean | function(metrics, candidate)
  complexityPenalty: 0,                // added per parameter to the selection loss
  keepCandidates: 3,                   // candidate checkpoints kept after the search
  repeats: 1,                          // seeds per candidate (training.seed, +1, ...); max 32
  selectionRule: "min_loss",           // or "one_standard_error" (needs repeats >= 2)
  activate: false                      // make the winner the model's active checkpoint
  // strategy "custom": generate(space, {random, grid, parameterCount}) returns structures
});
```

- Candidates are enumerated deterministically. Grid order is family → depth → width → shape →
  activation, then explicit layouts × activation; the default space reproduces the original
  family → depth → width order. `random` shuffles that grid with the search seed (mulberry32). A
  one-layer taper equals the uniform net and is skipped as a duplicate. Over-budget and duplicate structures are
  listed as skipped with a reason. Linear candidates that differ only in `l2` are distinct.
- Each candidate is trained on `runs` and scored on the **selection** runs (`validationRuns`). Each
  is registered with role `candidate` under its own `structure_id` directory.
- Ranking is by loss, then fewer parameters, then the structure key.
- **Selection noise.** With `repeats: N`, each candidate is trained under N seeds and its loss is
  the mean, with the sample standard deviation and standard error in the report (`losses`,
  `loss_std`, `loss_stderr`, `metrics_by_seed`). Only the first seed's checkpoint is registered,
  so a re-train of the winner can still be compared byte-for-byte. The report's `selection` block
  says whether the winner is distinguishable from the runner-up (mean gap larger than two
  combined standard errors) and lists the candidates tied with the best. With one seed this is
  `noise_measured: false` and `distinguishable_from_runner_up: null` — a single-seed ordering is
  never presented as settled. `selectionRule: "one_standard_error"` selects the fewest-parameter
  candidate whose mean loss lies within one standard error of the best mean (the classic
  parsimony rule); `min_loss` keeps rank 1. Only seeds vary: the selection runs are fixed, so
  run-to-run sampling noise between whole runs is not measured.
- With `testRuns`, the winner is re-trained with the untouched test runs as its carried holdout and
  registered as `best` with `holdout_source: "test_runs"`. The report records whether the
  re-trained weights equal the selected candidate's (`retrain_identical`). Without test runs, the
  winner is registered as `best` with `holdout_source: "selection_runs"`. That accuracy is
  optimistic: it is the data used to rank.
- `evolvo` delegates to `trech_torch.evolve_structure`, the bounded Evolvo MLP search with
  disjoint training/selection/test runs. It needs `testRuns`, identity links and an MLP-only space.
- Custom objective/generator functions run inside the file's sandbox under a 2 s time limit.
- A JSON report goes to `<store>/searches/<name>/`. It holds every candidate's metrics and loss,
  the skipped structures, the ranking, the best checkpoint and the discarded candidates.

## Validating a model

`trech-ml validate <id|name>` (or `--validate` on `train`/`search`) runs the independent validator
[`tools/torch/trech_torch/validate_model.py`](../tools/torch/trech_torch/validate_model.py)
(`trech-validate-surrogate`) on a stored checkpoint. Test runs default to the definition's
`testRuns`, else its `validationRuns`; `--test-run DIR` overrides, `--min-r2 R` sets the accuracy
threshold (default 0: beat the test mean). The JSON report (`trech_ml_validation_v1`) goes to
`<store>/validations/<name>/`; the checkpoint records the verdict as `validation {status, passed,
failed, warned, skipped, report}`, which `trech-ml show` and Studio's Models dock display. A
failing verdict makes the command exit 1.

Each gate is `pass`, `warn`, `fail` or `skip` with its reason:

| Gate | Needs | Fails / warns when |
| --- | --- | --- |
| `structure` | — | the engine could not load it, or would mis-run it: broken layer chain, wrong scaler length, links on a v1 model, or an activation the C++ loader would silently treat as identity |
| `finite_on_domain` | — | an output is non-finite at the training mean, a feature's trained edge or a joint centre |
| `trust_profile` | — | warn: no measured hull / occupancy / joint reference / holdout R² / per-output RMSE (the engine falls back to heuristics) |
| `carried_accuracy` | — | warn: the model's own holdout R²min is below 0 |
| `torchscript_parity` | torch + `.pt` twin | float32 twin differs from the float64 JSON by more than 1e-4 (relative) |
| `evaluator_parity` | NumPy, test runs | an independent pure-Python forward pass disagrees with the trainer's NumPy path |
| `run_leakage` | training runs | a run is used for training and testing, or a test run replays a training configuration (same provenance `config_hash`, incl. seed) |
| `test_accuracy` | test runs | an output's test R² is below `--min-r2` |
| `holdout_reproduces` | carried holdout on the same runs | recomputed metrics differ from the carried ones |
| `beats_linear_baseline` | training runs, non-linear model | warn: a ridge map fitted on the same training runs has lower test MSE |
| `sigma_calibration` | carried RMSE | warn: test RMSE differs from the carried σ by more than ×1.5, or a prediction interval covers less than nominal − 0.1; `independent:false` when the σ was measured on these runs |
| `test_domain_coverage` | test runs | warn: under half the test rows are inside the trained hull (accuracy is then mostly extrapolation); reports in/out-of-domain accuracy |

A verdict never upgrades trust: a passing model is still a learned comparison model, and a
distilled one is still `measured:false`.

**Committed-model audit.** `PYTHONPATH=tools/torch python3 -m trech_torch.validate_model --scan
data projects --audit-json docs/ml_model_audit.json --audit-md docs/ml_model_audit.md` runs the
static gates over every committed `generic_surrogate` model. [`ml_model_audit.md`](ml_model_audit.md)
is generated; CTest `trech_ml_model_audit` fails when it is stale or a committed model fails a
static gate. It needs no NumPy, so it runs in every CTest environment. It does not re-measure
accuracy; that needs each model's own independent test runs.

## Checkpoint store

Default location: `$TRECH_MODEL_STORE`, else `build/model_store/` (git-ignored). The CLI (`--store`)
and Studio (settings `model_store`) accept another directory.

```
index.json                                  trech_model_registry_v1 (atomic rename per write)
index.lock                                  writer lock {pid, at}; stale after 120 s or a dead pid
checkpoints/<name>/<structure_id>/v<NNNN>/  model.json  [model.pt]  definition.json  [manifest.json]
searches/<name>/<stamp>-<hash>.json         search reports
staging/<pid>-<rand>/                       trainer scratch (removed on success; gc removes dead ones)
```

Each `models.<name>` has `active`, `next_version` (monotonic: versions are never reused, even after
deletion) and `checkpoints[]`. A checkpoint has:

- identity and type: `id` (`<name>@v<N>`), `version`, `role` (`final` | `best` | `candidate` |
  `intermediate`), `format`, `structure_id`, `structure`, `structure_label`, `model_kind`;
- IO and size: `inputs`, `outputs`, `links`, `scale`, `parameter_count`, and `files[]` of
  `{format: generic_surrogate|torchscript, path, sha256, size_bytes}` with their total
  `size_bytes`;
- usage: `created_at`, `last_used_at`, `use_count`, `pinned`;
- provenance: `definition {file, hash, imported}`, `metrics`, `holdout_source`,
  `trained_from`, `search`, `note`.

**Conflict rules.** Registration reads the structure from the JSON weights themselves; a name or a
trainer's claim is not trusted. A file whose structure differs from its definition is refused and
nothing is copied. The common cause is the trainer falling back to a linear model without torch.
A TorchScript file is accepted only as the twin of such a JSON file. Formats must match their
extensions. Identical bytes re-registered under the same role return the existing checkpoint.
A version directory is never overwritten.

**Resolution** (`TRECH_ML.resolve`, `trech-ml resolve`) takes an explicit `version`, else the
model's `active` checkpoint, else the newest `final`/`best`. With a definition (or `structure_id`),
an incompatible active checkpoint is skipped. A version that does not match is a **structure
conflict** error; it is never loaded silently.

**Usage** is counted from what the engine actually loaded. `trech-ml touch --run <dir>` matches the
run's provenance `model_artifacts[].sha256` against stored files and counts each run once. Studio
does this automatically after every successful run. Runs launched elsewhere count only when
touched.

**Disk space.** `trech-ml prune` never deletes pinned or active checkpoints, nor the newest
`--keep-last` (default 3) `final`/`best` versions of each model. Optional filters are `--roles`
(e.g. `candidate,intermediate`) and `--unused-days D` (no use and no creation for D days). With
`--max-bytes 2G`, it deletes least-recently-used checkpoints only until the store fits. Without a
size target, it deletes every eligible checkpoint. `delete` refuses pinned/active checkpoints
without `--force`. Both print a dry-run plan and change nothing without `--yes`. `verify` re-hashes
every stored file. `gc` removes unowned directories and dead staging folders.

## Using a stored checkpoint in a scenario

```js
TRECH_INCLUDE("../../../js/trech_ml.js");
TRECH_INCLUDE("../../../ml/definitions/event_step_count.model.js");
const cfg = {
  determinism: { mode: "predictive" },
  models: [TRECH_ML.modelEntry(EVENT_STEP_COUNT, {
    index: "../../../build/model_store/index.json",    // read with TRECH_READ_JSON, relative to this file
    fallbackPath: "data/my_committed_model.json"      // optional; used only if the index/checkpoint is absent
  })]
};
```

`modelEntry` returns `{name, path, scale, registry}`. The `path` is relative to the same base as the
index, so normal model-path resolution applies. `registry` names the checkpoint, its version and
structure, its SHA-256, how it was resolved, and whether the fallback was used. Pass
`withRegistry: false` to omit it. A structure conflict is never replaced by the fallback.

The checkpoint path enters the config, so a different resolved version changes the config hash.
Pin `version` for reproducible studies. Strict mode still disables all inference. Committed,
validated models stay in `data/`; the store is a working area, not a source of truth.

## CLI

```bash
node tools/ml/bin/trech-ml.cjs help
node tools/ml/bin/trech-ml.cjs inspect ml/searches/event_step_count.search.js
node tools/ml/bin/trech-ml.cjs train ml/definitions/event_step_count.model.js [--dry-run] [--activate]
node tools/ml/bin/trech-ml.cjs search ml/searches/event_step_count.search.js [--validate] [--dry-run]
node tools/ml/bin/trech-ml.cjs validate event_step_count_search [--test-run DIR]... [--min-r2 0.5]
node tools/ml/bin/trech-ml.cjs register data/cascade_demo/meso_response.json --name cascade_meso   # import
node tools/ml/bin/trech-ml.cjs list --sort uses|recent|name|size
node tools/ml/bin/trech-ml.cjs prune --roles candidate --unused-days 30 [--yes]
```

`--json` switches every command to JSON lines (events, then a result), which Studio consumes. The
Python interpreter comes from `--python`, `$TRECH_ML_PYTHON`, `$TRECH_PYTHON` or `python3`. It
needs `numpy`, and `torch` for MLPs. `tools/torch` is put on `PYTHONPATH`.

## Tests

- `node --test tools/ml/test/*.test.js` (CTest `trech_ml_models_js`): validation and canonical
  hashing, signatures read from weights, candidate enumeration/budgets, objectives/ranking, sandbox
  errors and time limits, store registration/conflicts/version monotonicity, resolution,
  provenance usage, prune/delete/verify/gc, and orchestration with a fake trainer. That includes
  the torch-missing linear-fallback conflict and an honest search. Also CLI dry-run safety.
- CTest `trech_ml_registry_quickjs`: `trech inspect` of
  [`tests/fixtures/ml_registry/resolve_scenario.js`](../tests/fixtures/ml_registry/resolve_scenario.js).
  The same library runs in QuickJS, resolves the active checkpoint via `TRECH_READ_JSON`, and
  refuses a structure conflict.
- `studio/tests/test_models.py`: registry/inspection parsing, live draft inspection with line
  numbers, pin/activate/prune/delete/usage through the real CLI, and the validation verdict.
- CTest `trech_ml_model_audit` ([`tests/test_ml_model_validation.py`](../tests/test_ml_model_validation.py)):
  audit staleness, static gates on crafted models (unknown activation, broken chain, v1 links,
  exp overflow, negative carried R²). With NumPy: holdout reproduction, leakage by directory and
  by replayed configuration, the accuracy threshold and coverage. With torch: a per-layer
  tanh/relu MLP, its TorchScript twin parity and the linear baseline.

## Limits

- Only `generic_surrogate_v1/v2` JSON (+ TorchScript twin) checkpoints are stored. Stratifier,
  optics-ridge and other loader formats are not registered yet.
- Structures are dense MLPs (per-layer widths; silu/tanh/relu/sigmoid) or linear models, the ones
  the trainer exports. No residual/normalization layers or architecture families such as
  DeepSets/MPNN; the spectrum project's catalogue remains separate.
- Repeated seeds measure initialization noise only. The selection runs are fixed, so
  between-run sampling noise (repeated run splits) is not measured.
- The run-based validator needs the model's training/test run directories; committed models whose
  runs are not retained can only be audited statically.
- Usage is recorded only for runs that are touched (Studio does it automatically); the engine
  itself does not write to the store.
