# Evolved torch architectures (Evolvo GFSL-NN, `trech-evolve-arch`)

TRECH's trainers fix a model's structure before training it: an MLP of given widths, a DeepSets
or MPNN set network, a hierarchy plan. `trech-evolve-arch` searches the structure instead. The
architecture is a genome of the Evolvo **GFSL-NN** language
([`thirds/evolvo/papers/GFSL-NN.md`](../../thirds/evolvo/papers/GFSL-NN.md), package
`evolvo.nnarch`). The search learns which choices pay while it runs.

Status: **engine command and tooling shipped, tested on synthetic data.** The engine generates
architectures itself with `trech arch`: a native classic reference family, plus Evolvo through
a Python worker. No committed model or scenario uses an evolved architecture yet. LibTorch and
a torch-capable `TRECH_ML_PYTHON` are required by every build, so any evolved architecture
loads. Dense chains also get a JSON twin, which the engine evaluates with its own deterministic
math. The others run through TorchScript.

## In the engine: `trech arch`

```bash
./build/dev/trech arch job.json --output build/arch [--generator evolvo|classic] [--python <exe>]
```

[`ArchitectureGenerator`](../../include/trech/ml/ArchitectureGenerator.hpp) (`trech_ml`) handles
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
   (`generic_surrogate_v1` with input domain and test holdout). It is the
   **reference** every generated architecture must beat, never a stand-in for a failed search. The arbitrary rules make it a fixed
   point of comparison, not a claim of optimality.
2. **Evolvo (Python worker).** The engine writes `<name>.worker_request.json`
   (`trech_arch_request_v1`). It holds the tables, budgets, the classic family as seed genomes
   and the reference's score. The engine then spawns `python -m trech_torch.arch_worker`
   ([`arch_worker.py`](../../tools/torch/trech_torch/arch_worker.py)), and the worker runs the
   GFSL-NN search over the whole language and exports the best model.
3. **Decision (C++).** The engine accepts the result only after these checks:
   - The result's `request_sha256` must match the request bytes.
   - The engine reloads the exported model with `GenericSurrogate` and checks its names.
   - It **re-scores** the model itself on the selection rows, and records whether the
     worker's reported loss agrees.
   - The evolved model wins only when its score is strictly better than the classic
     reference's. When it loses (`rejected`), the better model, the reference, is kept.

   **There is no fallback.** Every other outcome is an error: `ok: false`, `generator: "none"`,
   no model, and `trech arch` exits 1. The outcome file still records why: interpreter not
   found (`not_started`), `timeout` (process killed), `no_result`, `mismatched_result`,
   `unavailable` (no torch/Evolvo; exit 3), `error`, `no_model` or `unloadable`. The
   `generator` is `evolvo` (default) or `classic`, which trains the reference only and skips
   the search on purpose. `auto` and `require_engine_native` were removed and are refused.

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
`TRECH_ML_PYTHON` (default `build/render-venv/bin/python`; configure fails unless it imports
torch and NumPy). `$TRECH_ROOT` overrides the repository root that holds `tools/torch` and
`thirds/evolvo/src`. The bridge is POSIX-only; on Windows the job fails (`not_started`).

### Job (`trech_arch_job_v1`)

```json
{
  "schema": "trech_arch_job_v1", "name": "uv",
  "inputs": ["a", "b", "c"], "outputs": ["u", "v"],
  "data": {"train": "train.jsonl", "selection": "selection.jsonl", "test": "test.jsonl"},
  "generator": "evolvo", "seed": 7, "size_cost": 0.03, "lr": 0.003,
  "budget": {"max_params": 20000, "max_rows": 6, "max_epochs": 600, "generations": 6,
             "population": 8, "patience": 3, "max_evaluations": 0, "time_budget_s": 0,
             "worker_timeout_s": 3600},
  "ops": ["linear", "act", "mlp"], "knowledge": "knowledge.json",
  "python": "/path/to/python"
}
```

- Tables are JSON-lines files (relative to the job) or inline arrays of row objects. Train,
  selection and test must be different tables.
- `ops`, `knowledge` and `python` are optional.
- `worker: {module, path}` swaps the worker module (the tests use fakes).

### Engine demonstration (synthetic)

The job: u = sin(3a)·b + c², v = a − 0.5c², with 300/100/100 uniform rows in [−1, 1]³ and
default budgets, after the plateau fix below. `trech arch` took about 203 s in the dev (Debug)
build and about 182 s in a Release build (2026-11-18, both with the required LibTorch). The two
builds chose the same architecture with the same losses.

| Architecture | Params | Selection MSE (standardized) | Test R² (u / v) |
| --- | --- | --- | --- |
| classic reference `mlp2` (16×16, SiLU) | 370 | 0.00516 | 0.9940 / 0.9996 |
| Evolvo: `mlp(32, depth 4)` + `concat` with the input (TorchScript) | 3,368 | 0.000252 | 0.9996 / 1.0000 |

The engine accepted the evolved model. It reloaded the TorchScript module through its sidecar and
re-scored it on the selection split itself. A search restricted to `tokenize`/`transformer`/`pool`
produced a TorchScript model that lost to the reference and was rejected, as it should be: the
classic reference was kept with `ok = true`.

**Plateau fix (2026-11-17).** Both trainers used to count an epoch as progress only when it beat
the *latest* best by 0.1 %. A loss falling by less than that per epoch, but steadily, was then
stopped as a "plateau" on its last, best epoch. On this job the classic `mlp2` stopped at epoch
203 with MSE 0.122. The worker trained the same seed genome to 0.0033. A reference that weak let
almost anything beat it. Progress is now measured from the loss at the last counted improvement,
in `trainClassicNative` and in Evolvo's `PlateauStopper`.

## What is general (Evolvo) and what is TRECH (adapter)

| Evolvo `evolvo.nnarch` (general purpose) | TRECH [`evolve_architecture.py`](../../tools/torch/trech_torch/evolve_architecture.py) |
| --- | --- |
| Fixed 7-slot rows, cascading validity, repair | Run harvesting (`--runs`/`--validation-runs`/`--test-runs`, disjoint) |
| Primitives (vec/set, attention, tokens) and macros (`mlp`, `resmlp`, `transformer`, `deepsets`, user macros) | Training-split scalers, held-out metrics on test runs |
| `ContextualStats`: learned groups, shrinkage | `generic_surrogate_v1` export for dense chains |
| `AdaptivePolicy`: learned slot and mutation weights | TorchScript + `.pt.io.json` sidecar for every architecture |
| `EfficiencyModel`: loss/size frontier, size pressure | `trech_evolved_arch_v1` record for non-dense ones |
| `PlateauStopper`: learned patience, equal-effort hopeless stop | Provenance: genome, readable architecture, search summary |
| `ArchitectureSearch` + `Knowledge` (save/load) | `--knowledge` file reused across searches |

General-purpose changes go to Evolvo itself (see the [Evolvo workflow](../../AGENTS/tooling/dependencies/AGENTS.md)).

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

## Search quality on Geant4 runs (2026-11-27)

Does a search strategy find better models than a plain grid? `trech-compare-search`
([`compare_search.py`](../../tools/torch/trech_torch/compare_search.py)) answers that on one table
with everything else held fixed:

- **Same trainer.** Every candidate of every strategy is a GFSL-NN genome trained by Evolvo's
  `TorchTask` (full-batch Adam on training-standardized data, learned plateau stop, best
  selection weights restored, at most 1,500 epochs).
- **Same budget.** Each strategy trains exactly 24 distinct candidates per seed. Proposals the
  space refuses (over the parameter budget) are counted, not trained.
- **Same selection.** The winner has the lowest selection-split MSE (size cost 0). Its test MSE
  is computed once.

Strategies: `grid` (uniform MLPs: widths 6, 11, 23, 45 × depth 1–3 × SiLU/tanh), `random_mlp`,
`evolvo_mlp` (the bounded Evolvo width/depth search), `random_gfsl` (random genomes of the whole
language), `gfsl` (the learned search) and `gfsl_reuse` (the learned search started from the
knowledge the previous seed's `gfsl` run saved).

**Data.** The 222 committed Geant4 runs of the particle observer
([`data/particle_observer/rows.json`](../../data/particle_observer/rows.json)): gamma beams
through CHNO molecules, with the uncollided and deposited-energy fractions tallied by Geant4.
Each row is a whole run. There are 192 training runs, 12 development runs used for selection and
18 test runs (three held-out molecules, plus a final campaign). The five inputs are the lower
cascade rungs' cross sections, the areal density and the photon energy. This is a non-optics
family: gamma transport, not optical photons.

**Results** over 20 seeds. MSE is in training-standardized output units, and "vs grid" is the
mean ± standard error of the per-seed difference in ln(test MSE) (negative is better than the grid):

| Strategy | Geo-mean selection MSE | Geo-mean test MSE | Test MSE range | Median test R²min | vs grid | Seeds better than grid | Median params | Mean epochs |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `grid` | 0.00300 | 0.00427 | 0.00093–0.0244 | 0.9927 | — | — | 186 | 5,089 |
| `random_mlp` | 0.00248 | 0.00454 | 0.00029–0.0407 | 0.9876 | +0.06 ± 0.39 | 8/20 | 850 | 3,745 |
| `evolvo_mlp` | 0.00244 | 0.00288 | 0.00034–0.0079 | 0.9938 | −0.40 ± 0.28 | 9/20 | 258 | 4,920 |
| `random_gfsl` | 0.00357 | 0.00789 | 0.00044–0.104 | 0.9803 | +0.61 ± 0.32 | 6/20 | 4,133 | 5,211 |
| `gfsl` | 0.00246 | 0.00524 | 0.00025–0.204 | 0.9876 | +0.20 ± 0.46 | 8/20 | 4,408 | 4,186 |
| `gfsl_reuse` (19 seeds) | 0.00319 | 0.00586 | 0.00042–0.0366 | 0.9838 | +0.28 ± 0.34 | 9/19 | 4,502 | 3,976 |

Linear ridge reaches test MSE 0.26 (R² 0.53/0.56), so every search finds a strongly nonlinear
model. The whole comparison took 11 minutes on CPU (torch 2.8).

What this shows:

- **No strategy is distinguishable from the grid** on held-out runs at 24 candidates. Every
  difference is within about 1.9 standard errors. `evolvo_mlp` has the best mean (−0.40 ± 0.28,
  about a third lower test MSE) and the narrowest spread. Random genomes of the whole language
  are the worst (+0.61 ± 0.32).
- **The learned GFSL-NN search reaches low selection loss but transfers worse.** It ties the best
  geo-mean selection loss and picks models over 20 times larger than the grid's (median parameters), with the
  heaviest test tail (one seed at 0.20). Its 12-run selection split rewards fits that do not
  generalize. Across all chosen models, ln(selection MSE) and ln(test MSE) correlate at 0.90, so
  the tail is the selection split's small size, not a test-split artefact.
- **Knowledge reuse did not help** here: +0.28 ± 0.34 against the grid, no better than the fresh
  search.
- **The hand-built model is still better.** The committed observer model
  (`tools/torch/build_particle_observer_models.py`: decoded-probability loss, 10,900 epochs)
  reaches test R²min 0.9994. That is above every strategy's median (0.980–0.994). The trainer and
  the output transform matter more than the architecture search on this table.

Reproduce:

```bash
PYTHONPATH=tools/torch build/render-venv/bin/python -m trech_torch.compare_search \
  --table data/particle_observer/rows.json --seeds 0,1,2,3,4,5,6,7,8,9,10,11,12,13,14,15,16,17,18,19 \
  --budget 24 --out build/search_compare/particle_observer.json
```

The committed report is
[`docs/validation/search_comparison_particle_observer.json`](../validation/search_comparison_particle_observer.json)
(per-seed winners, summaries, the ridge reference; `--keep-trials` also keeps every candidate).

## Tests

- CTest `trech_architecture_generator`
  ([`test_architecture_generator.cpp`](../../tests/test_architecture_generator.cpp)):
  - the width ladder and classic family rules, and job validation;
  - native-trainer determinism and learning;
  - `GenericSurrogate` reproduces the native export (≤1e-9);
  - classic generation, and a missing interpreter failing the job;
  - stdlib-only fake workers ([`fake_arch_worker.py`](../../tests/fixtures/arch_worker_fake/fake_arch_worker.py)):
    an exact model accepted, a worse model with a lying loss caught and rejected (reference
    kept); a mismatched request hash, unavailability, a crash and a hang killed at the timeout
    each fail the job with no model;
  - the removed `auto` generator and `require_engine_native` are refused.
- CTest `trech_architecture_evolvo_live`: the real worker through `TRECH_ML_PYTHON`, which must
  return a model the engine reloads and re-scores in agreement. An unavailable worker fails.
- CTest `trech_compare_search` ([`tests/test_compare_search.py`](../../tests/test_compare_search.py)):
  every strategy trains exactly the budget of distinct candidates, refused proposals are never
  trained, knowledge reuse loads only an earlier seed's knowledge, overlapping splits are
  refused, and a repeated comparison selects the same candidates.
- CTest `trech_evolvo_arch` ([`tests/test_evolvo_arch.py`](../../tests/test_evolvo_arch.py)):
  - `evolvo.nnarch` imports without NumPy, and 200 random genomes validate.
  - NumPy and torch (required; it runs under `TRECH_ML_PYTHON` and fails without them):
    - dense export reproduces the module in JSON (NumPy) and TorchScript;
    - the sidecar is bound to the module bytes;
    - a transformer search exports TorchScript plus the non-loadable record and runs at a new
      batch size;
    - knowledge accumulates across searches;
    - every worker export has TorchScript + sidecar, dense ones also a JSON twin, and a
      request with the removed `engine_native_only` is refused;
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
- Non-dense architectures run through LibTorch using the sidecar's named layout, coverage
  reference, training scale and held-out residuals.
- `TRECH_ML.defineSearch({strategy: "evolvo"})` still routes to the older bounded MLP search
  (`evolve_structure`), not to `trech arch`. The `trech-ml` store does not register evolved or
  engine-generated models.
- Search quality is measured on one small Geant4 table only (the particle observer, 12 selection
  runs); there the learned search does not beat a 24-point grid. Larger Geant4 tables (fluid
  parcels, CNT devices) and selection splits large enough to rank candidates are not measured.
