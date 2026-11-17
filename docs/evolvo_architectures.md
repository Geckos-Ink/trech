# Evolved torch architectures (Evolvo GFSL-NN, `trech-evolve-arch`)

TRECH's trainers fix a model's structure before training it: an MLP of given widths, a DeepSets
or MPNN set network, a hierarchy plan. `trech-evolve-arch` searches the structure instead. The
architecture is a genome of the Evolvo **GFSL-NN** language
([`thirds/evolvo/papers/GFSL-NN.md`](../thirds/evolvo/papers/GFSL-NN.md), package
`evolvo.arch`). The search learns which choices pay while it runs.

Status: **tooling shipped and tested on synthetic data.** No committed model or scenario uses an
evolved architecture yet. Only dense chains run in the C++ engine without LibTorch. Everything
else needs `TRECH_ENABLE_TORCH`.

## What is general (Evolvo) and what is TRECH (adapter)

| Evolvo `evolvo.arch` (general purpose) | TRECH [`evolve_architecture.py`](../tools/torch/trech_torch/evolve_architecture.py) |
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

`thirds/evolvo/examples/arch_search_flow.py` (2026-11-17, torch 2.8 CPU):

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

- CTest `trech_evolvo_arch` ([`tests/test_evolvo_arch.py`](../tests/test_evolvo_arch.py)):
  - Always: `evolvo.arch` imports without NumPy, and 200 random genomes validate.
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

- Vector inputs only in the adapter. `set` inputs exist in the language but are dense (no
  padding mask), so hierarchy levels (`ctx.lift`) cannot be evolved yet.
- Non-dense architectures run in the engine only through TorchScript (`TRECH_ENABLE_TORCH`).
  The sidecar carries names, units and holdout, but not `input_domain`, so the engine's
  coverage check sees no domain for them.
- `TRECH_ML.defineSearch({strategy: "evolvo"})` still routes to the older bounded MLP search
  (`evolve_structure`). The `trech-ml` store does not register evolved TorchScript-only models.
- Not benchmarked against grid/random search on Geant4-harvested data.
