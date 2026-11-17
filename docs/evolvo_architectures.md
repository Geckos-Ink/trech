# Evolved torch architectures (Evolvo GFSL-NN, `trech-evolve-arch`)

TRECH's trainers fix a model's structure before training it: an MLP of given widths, a DeepSets
or MPNN set network, a hierarchy plan. `trech-evolve-arch` searches the structure instead. The
architecture is a genome of the Evolvo **GFSL-NN** language
([`thirds/evolvo/papers/GFSL-NN.md`](../thirds/evolvo/papers/GFSL-NN.md), package
`evolvo.nnarch`). The search learns which choices pay while it runs.

Status: **engine command and tooling shipped, tested on synthetic data.** The engine generates
architectures itself with `trech arch`: a native classic reference family, plus Evolvo through
a Python worker. No committed model or scenario uses an evolved architecture yet. Only dense
chains run in the C++ engine without LibTorch. Everything else needs `TRECH_ENABLE_TORCH`.

## In the engine: `trech arch`

```bash
./build/dev/trech arch job.json --output build/arch [--generator auto|evolvo|classic] [--python <exe>]
```

[`ArchitectureGenerator`](../include/trech/ml/ArchitectureGenerator.hpp) (`trech_ml`) handles
one job in two parts, and the engine makes the final choice.

1. **Classic reference (C++, always).** A fixed, documented family:
   - the linear map;
   - SiLU MLPs of depth 1 and 2.

   The width is the GFSL-NN ladder rung nearest 4 × max(inputs, outputs, 4), shrunk down the
   ladder until the network has at most 8 parameters per training target and fits the budget.
   A deterministic native trainer fits them:
   - full-batch Adam on training-standardized data;
   - plateau stopping on the selection table (patience 25, or 10 % of the epochs run so far),
     with progress measured from the loss at the last counted 0.1 % improvement, so slow
     steady gains add up instead of being stopped (Evolvo's `PlateauStopper` uses the same rule);
   - best-epoch weights restored;
   - portable `trech_dmath` math, no FMA contraction, splitmix64 initialization.

   The best by `ln(loss) + size_cost · ln(params)` becomes `<name>.classic.json`
   (`generic_surrogate_v1` with input domain and test holdout). It is the **fallback** and the
   **reference** every generated architecture must beat. The arbitrary rules make it a fixed
   point of comparison, not a claim of optimality.
2. **Evolvo (Python worker).** The engine writes `<name>.worker_request.json`
   (`trech_arch_request_v1`). It holds the tables, budgets, the classic family as seed genomes
   and the reference's score. The engine then spawns `python -m trech_torch.arch_worker`
   ([`arch_worker.py`](../tools/torch/trech_torch/arch_worker.py)), and the worker runs the
   GFSL-NN search and exports the best model. When the engine build has no LibTorch, the
   request sets `engine_native_only`: the worker searches only `linear`/`act`/`dropout`/`mlp`
   with the C++-supported activations, and exports the best-scoring dense chain it trained.
3. **Decision (C++).** The engine accepts the result only after these checks:
   - The result's `request_sha256` must match the request bytes.
   - The engine reloads the exported model with `GenericSurrogate` and checks its names.
   - It **re-scores** the model itself on the selection rows, and records whether the
     worker's reported loss agrees.
   - The evolved model wins only when its score is strictly better than the classic
     reference's. Otherwise, and for every failure, the classic model is used, with the reason
     recorded.

   Failures are named: interpreter not found (`not_started`), `timeout` (process killed),
   `no_result`, `mismatched_result`, `unavailable` (no torch/Evolvo; exit 3), `no_model`,
   `unloadable`, `rejected`. A TorchScript winner is used only if this build loads it, or if
   the job sets `require_engine_native: false` (then it is worker-scored and labelled so).

Outputs in `--output`:

- `<name>.outcome.json` (`trech_arch_outcome_v1`): the classic candidates and reference, the
  Evolvo status, re-scored loss and holdout, the overall best, and the decision with its reason;
- `<name>.classic.json`;
- `<name>_evolvo.*` (`.json` or `.pt` + `.pt.io.json` + `.arch.json`, `.search.json`);
- the worker request, result and log.

**Why a subprocess and not embedded Python.**
- The engine builds and links without libpython: no ABI coupling, and the venv is chosen at run
  time.
- Torch threads, memory and crashes stay out of the Geant4 process.
- The boundary is a versioned JSON contract, like JS → JSON → C++.
- Strict simulation runs never touch it.
- It follows the `trech-atomic` launcher pattern: shell-free `posix_spawn`, a wall-clock
  timeout, and the log captured.

Process startup (~1 s for torch) is negligible next to training. The interpreter resolves in
this order: the job's `python`, then `--python`, then `$TRECH_PYTHON`, then the CMake cache
`TRECH_ARCH_PYTHON` (default `build/render-venv/bin/python` when present). `$TRECH_ROOT`
overrides the repository root that holds `tools/torch` and `thirds/evolvo/src`. The bridge is
POSIX-only; on Windows the classic fallback is used.

### Job (`trech_arch_job_v1`)

```json
{
  "schema": "trech_arch_job_v1", "name": "uv",
  "inputs": ["a", "b", "c"], "outputs": ["u", "v"],
  "data": {"train": "train.jsonl", "selection": "selection.jsonl", "test": "test.jsonl"},
  "generator": "auto", "seed": 7, "size_cost": 0.03, "lr": 0.003,
  "budget": {"max_params": 20000, "max_rows": 6, "max_epochs": 600, "generations": 6,
             "population": 8, "patience": 3, "max_evaluations": 0, "time_budget_s": 0,
             "worker_timeout_s": 3600},
  "ops": ["linear", "act", "mlp"], "knowledge": "knowledge.json",
  "python": "/path/to/python", "require_engine_native": true
}
```

- Tables are JSON-lines files (relative to the job) or inline arrays of row objects. Train,
  selection and test must be different tables.
- `ops`, `knowledge`, `python` and `require_engine_native` are optional.
- `worker: {module, path}` swaps the worker module (the tests use fakes).

### Engine demonstration (synthetic)

The job: u = sin(3a)·b + c², v = a − 0.5c², with 300/100/100 uniform rows in [−1, 1]³ and
default budgets (2026-11-17, after the plateau fix below). `trech arch` took about 63 s in the
dev (Debug) build without LibTorch and about 182 s in a Release build with LibTorch, where the
search may use the whole language.

| Architecture | Params | Selection MSE (standardized) | Test R² (u / v) |
| --- | --- | --- | --- |
| classic reference `mlp2` (16×16, SiLU) | 370 | 0.00516 | 0.9940 / 0.9996 |
| Evolvo, engine-native (no LibTorch): `mlp(23, depth 5, silu)` | 2,348 | 0.000454 | 0.9994 / 0.9999 |
| Evolvo, LibTorch build: `mlp(32, depth 4)` + `concat` with the input (TorchScript) | 3,368 | 0.000252 | 0.9996 / 1.0000 |

The engine accepted the evolved model in both builds. In the LibTorch build it reloaded the
TorchScript module through its sidecar and re-scored it itself. In both builds the re-score agreed
with the worker's to about 1e-6 relative. A search restricted to `tokenize`/`transformer`/`pool`
produced a TorchScript model that lost to the reference and was rejected, as it should be.

**Plateau fix (2026-11-17).** Both trainers used to count an epoch as progress only when it beat
the *latest* best by 0.1 %. A loss falling by less than that per epoch, but steadily, was then
stopped as a "plateau" on its last, best epoch. On this job the classic `mlp2` stopped at epoch
203 with MSE 0.122. The worker trained the same seed genome to 0.0033. A reference that weak let
almost anything beat it. Progress is now measured from the loss at the last counted improvement,
in `trainClassicNative` and in Evolvo's `PlateauStopper`.

## What is general (Evolvo) and what is TRECH (adapter)

| Evolvo `evolvo.nnarch` (general purpose) | TRECH [`evolve_architecture.py`](../tools/torch/trech_torch/evolve_architecture.py) |
| --- | --- |
| Fixed 7-slot rows, cascading validity, repair | Run harvesting (`--runs`/`--validation-runs`/`--test-runs`, disjoint) |
| Primitives (vec/set, attention, tokens) and macros (`mlp`, `resmlp`, `transformer`, `deepsets`, user macros) | Training-split scalers, held-out metrics on test runs |
| `ContextualStats`: learned groups, shrinkage | `generic_surrogate_v1` export for dense chains |
| `AdaptivePolicy`: learned slot and mutation weights | TorchScript + `.pt.io.json` sidecar for every architecture |
| `EfficiencyModel`: loss/size frontier, size pressure | `trech_evolved_arch_v1` record for non-dense ones |
| `PlateauStopper`: learned patience, equal-effort hopeless stop | Provenance: genome, readable architecture, search summary |
| `ArchitectureSearch` + `Knowledge` (save/load) | `--knowledge` file reused across searches |

General-purpose changes go to Evolvo itself (see the [Evolvo workflow](../AGENTS/tooling/dependencies/AGENTS.md)).

## The language in one example

```text
v0 = input vec[4]
v1 = tokenize(v0, dim=16) -> set[16]@n4          # one learned token per input feature
v2 = transformer(v1, depth=2, heads=4, ff=2)      # macro: 2 pre-norm encoder blocks
v3 = pool(v2, mode=mean) -> vec[16]
out = linear(v3 -> 1)                             # fixed head
```

Each row is `[target, op, src_a, src_b, arg0, arg1, arg2]`. Arguments are indices into
enumerated option lists. Each list is filtered by the shapes and by the remaining parameter
budget (heads must divide the width; a width that would break the budget is not offered). So
every sampled, mutated or crossed genome builds. The `depth` of a macro is one integer gene.

## What is learned, not set

- **Choice weights.** Every slot (op, source distance, width, depth, heads, activation, genome
  length) and every mutation operator is sampled by the reward its choices earned: the fitness
  quantile among all evaluations. The rewards are stored per *context*. Which context features
  form groups (slot, op, width bucket, position, remaining budget, task signature, …) is
  discovered from the data by adjusted variance gain, with shrinkage toward broader groups.
- **Sizes.** Selection minimizes `ln(loss) + size_cost · ln(params)`. A learned power-law
  frontier `L(P) = L∞ + B·P^−α` gives the size where another doubling stops paying, and a
  pressure that tilts size choices up or down. The width ladder's active window widens only
  where elite genomes press its edge.
- **Epochs.** Each candidate trains until a plateau whose patience is learned from how similar
  candidates (same size bucket, row count, task) improved. A candidate is also stopped when it
  is behind the incumbent *at equal effort* and its fitted learning curve cannot catch up. The
  hard `--max-epochs` is only a budget guard. The best-validation weights are restored.
- **Search length.** The search stops when the best score has not improved for `--patience`
  generations (`converged`), or on generation/evaluation/time budgets.
- **Across searches.** `--knowledge k.json` loads these tendencies and saves them updated.

## Usage

```bash
PYTHONPATH=tools/torch build/render-venv/bin/python -m trech_torch.evolve_architecture \
  --runs build/dev/harvest/train_* --validation-runs build/dev/harvest/valid_* \
  --test-runs build/dev/harvest/test_* --source hook_emits --tag sample \
  --inputs a,b,c --outputs u,v --max-params 50000 --knowledge build/evolvo_knowledge.json \
  --out build/models/u_v --report build/models/u_v.search.json
# optional: --ops linear,act,mlp,resmlp   (restrict the language, e.g. to engine-native chains)
#           --size-cost 0.03 --generations 12 --population 10 --patience 4 --time-budget 600
```

Outputs:

- dense chain: `<out>.json` (`generic_surrogate_v1`, C++-native, with `input_domain`, test-run
  `holdout`, genome in `trained_from`) and `<out>.pt` + `<out>.pt.io.json`;
- other architectures: `<out>.pt` + `<out>.pt.io.json` and `<out>.arch.json`
  (`trech_evolved_arch_v1`: names, domain, holdout, genome). The record has no `model` key, so
  no surrogate loader can mistake it for a runnable JSON model.

When the size-penalized winner is not the lowest-loss module trained, the winner is retrained
with its own seed for export (`retrained_for_export`, `retrain_loss` in the report).

## Synthetic demonstration (architecture search only)

`thirds/evolvo/examples/nnarch_search_flow.py` (2026-11-17, torch 2.8 CPU):

- **Task.** y = sin(3x₀)·x₁ + x₂² − 0.5x₃ on 400 training, 150 selection and 150 held-out
  points; 30k-parameter budget.
- **Result.** The search converged after 38 evaluations (32 unique architectures). Held-out
  MSE is 0.00112 against a target variance of 0.288 (R² ≈ 0.996).
- **Pareto front.** (params, val loss): (5, 0.244), (25, 0.232), (79, 0.0092), (193, 0.0025),
  (1249, 0.00097), (5377, 0.00088).
- **Learned groups.** The epoch statistics chose model size, then row count, as their grouping
  features; the task-signature features gained nothing on a single task.

**Reusing knowledge (same seed, same task).** A second search started from the first's saved
knowledge:

| Search | Evaluations | Training epochs | Best validation loss |
| --- | --- | --- | --- |
| Fresh | 38 | 17,103 | 0.00088 |
| With saved knowledge | 28 | 7,389 | 0.00016 |

**Grade the gap.** This is one seed on one synthetic function. It shows that the mechanisms
run and interact, not that they beat grid/random search or the hand-set trainers. No Geant4 run
has been searched yet.

## Tests

- CTest `trech_architecture_generator`
  ([`test_architecture_generator.cpp`](../tests/test_architecture_generator.cpp)):
  - the width ladder and classic family rules, and job validation;
  - native-trainer determinism and learning;
  - `GenericSurrogate` reproduces the native export (≤1e-9);
  - classic generation and the missing-interpreter fallback;
  - stdlib-only fake workers ([`fake_arch_worker.py`](../tests/fixtures/arch_worker_fake/fake_arch_worker.py)):
    an exact model accepted, a worse model with a lying loss caught and rejected, a mismatched
    request hash, unavailability, a crash, and a hang killed at the timeout.
- CTest `trech_architecture_evolvo_live`: the real worker through `TRECH_ARCH_PYTHON`, which
  must return an engine-native model that the engine re-scores in agreement. Exits 77
  (skipped) without torch.
- CTest `trech_evolvo_arch` ([`tests/test_evolvo_arch.py`](../tests/test_evolvo_arch.py)):
  - Always: `evolvo.nnarch` imports without NumPy, and 200 random genomes validate.
  - With NumPy and torch:
    - dense export reproduces the module in JSON (NumPy) and TorchScript;
    - the sidecar is bound to the module bytes;
    - a transformer search exports TorchScript plus the non-loadable record and runs at a new
      batch size;
    - knowledge accumulates across searches;
    - the CLI refuses overlapping splits and carries test-run holdout and genome.
- Evolvo's own suite: `PYTHONPATH=thirds/evolvo/src python -m unittest discover -s thirds/evolvo/tests`
  covers statistics, cascading validity, macros, repair, the efficiency fit, stopping, search
  determinism, and build/trace parity.

## Limits

- The classic native family is dense only, has no `joint` density reference in its domain, and
  uses fixed (not learned) stopping. Its width rules are arbitrary by design.
- Jobs take tables, not run directories. Harvesting Geant4 runs into job tables from the engine
  is not implemented. Scenarios cannot request a generation (no JS API); jobs are run by hand.
- Vector inputs only in the adapter. `set` inputs exist in the language but are dense (no
  padding mask), so hierarchy levels (`ctx.lift`) cannot be evolved yet.
- Non-dense architectures run in the engine only through TorchScript (`TRECH_ENABLE_TORCH`).
  The sidecar carries names, units and holdout, but not `input_domain`, so the engine's
  coverage check sees no domain for them.
- `TRECH_ML.defineSearch({strategy: "evolvo"})` still routes to the older bounded MLP search
  (`evolve_structure`), not to `trech arch`. The `trech-ml` store does not register evolved or
  engine-generated models.
- Not benchmarked against grid/random search on Geant4-harvested data.
