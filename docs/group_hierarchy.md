# Recursive group lifting (`ctx.lift`, `GroupHierarchy`)

`ctx.cascade` lifts one context vector from band to band. Many questions are about a
**population** instead: atoms make molecules, molecules make clusters, clusters make parcels,
parcels make the glass of water. `ctx.lift` lifts a population scale by scale, with one trained
set model per level, recursively:

```
base elements (Geant4 steps, atoms, parcels …: named features + position + weight 1)
   │ level 0: partition into groups, run the level's set model on each group's members
   ▼
groups  = new elements: features = the model's outputs, position = weight-centroid, weight = Σ
   │ level 1: partition those, run the next model …
   ▼
…  ▼
observer (often one group of everything)
```

Status: **mechanism shipped and tested; trained on synthetic data only.** No scenario uses it yet,
and no Geant4-harvested hierarchy has been trained. The engine contract is in
[`GroupHierarchy.hpp`](../include/trech/ml/GroupHierarchy.hpp); the trainer is
[`trech_torch/hierarchy.py`](../tools/torch/trech_torch/hierarchy.py) (`trech-train-hierarchy`).

## Levels are trained set networks

Each level is a `generic_surrogate_v3` DeepSets or MPNN model ([set networks](ml_models.md#set-networks-deepsets--message-passing))
with a `group_lift` block:

```json
"group_lift": {
  "member_prefix": "m",                         // inputs m<slot>_<feature>, slot-major
  "member_features": ["present", "weight", "rel_x", "rel_y", "rel_z", "cell_energy", "cell_h0"],
  "context_features": ["g"],                    // trailing global inputs
  "cell_size": 2.0,                             // trained lattice edge (lattice levels)
  "length": 2.0,                                // trained rel_* normaliser
  "latent_outputs": ["block_h0", "block_h1"],   // outputs that are learned latents
  "grouping": "cell", "level": "block", "level_index": 1, "levels": 3
}
```

Loading fails closed when a declared block disagrees with the inputs: every slot must repeat the
slot-0 feature names, the set mask must be the member feature `present`, lengths must be
positive, and `latent_outputs` must name outputs. A model without the block is never used as a
level.

Member features are either names the level below produces or facts the engine synthesizes:

| Name | Value |
| --- | --- |
| `present` | 1 for a real member, 0 for an absent slot (the set mask) |
| `weight` | number of base elements the member stands for |
| `rel_x`, `rel_y`, `rel_z` | (member position − group centroid) / level length |

Dividing by the level length makes member geometry dimensionless, so one model can serve several
levels when the behaviour is self-similar.

## Grouping

- `cell_size`: a cubic lattice from `origin` (default 0). Cells are ordered by (ix, iy, iz).
- `groups`: explicit integer ids, one per current element (e.g. molecule membership), ordered
  ascending.
- `all`: one group of everything (the observer).

Members keep ascending element order; centroids accumulate in that order. The trainer replays
the same partition (`hierarchy.partition` / `build_structure`), so group keys (`"ix,iy,iz"`, the
id, or `"all"`) mean the same thing in labels and at run time.

## Honesty rules

- **No truncation, no implicit zeros.** A group with more members than the model has slots is
  blocked (`overflow`). A group containing a blocked member is blocked (`blockedByMembers`).
  Blocked groups publish NaN and `valid:false`. A missing member feature, context input,
  position or length skips the level and every level above it with a named `skipReason`.
- **Trust propagates up.** A group is out of domain (or starved) when its own inputs are or when
  any member's lineage is. `localOutOfDomain`/`localStarved` keep the model's own checks. A level
  run at a band its model was not trained on, or above such a level, reports `scaleMismatch`.
- **Absent slots never trip coverage.** They are filled with the model's input means
  (`present = 0`), so they standardize to zero and take no part in the set arithmetic.
- **Accounting.** Each group evaluation is one inference in `hook_predict_count`; strict mode
  returns `null`.
- **Latents are not quantities.** `latentOutputs` marks levels that pass learned channels upward.
  Only supervised outputs carry held-out metrics.

## In a hook

```js
const r = ctx.lift({
  features:  { q: charges },                  // per base element (sorted by name)
  positions: { x, y, z },                     // lattice grouping and rel_*
  weight:    weights,                         // optional, default 1
  context:   { g: 1.2 },                      // over the ambient Geant4 seed
  levels: [                                   // optional; omit to let the engine plan
    { model: "cell_lift", cell_size: 1.0 },
    { model: "block_lift", cell_size: 2.0 },
    { model: "system_lift", all: true, length: 4.0 }
  ]
});
r.top?.energy;            // the observer, when the last level produced exactly one valid group
r.levels[1].features.block_energy[g];   // any level's per-group outputs
```

Without `levels`, the engine plans the hierarchy itself: every declared model with
`operator_role: "group_lift"` (filtered by `element_kind` when given) in ascending scale order,
grouped by its carried `cell_size` or as one group without one. A level that names neither a
grouping nor carries a `cell_size` is one group of everything.

Each level reports `{model, scale, grouping, cellSize, length, ran, skipReason,
missingMemberFeatures, missingContext, capacity, maxMembers, groups, evaluated, blocked,
overflow, blockedByMembers, outOfDomain, localOutOfDomain, starved, localStarved,
domainMeasured, latentOutputs, scaleMismatch, trainedScale, holdoutR2, holdoutSamples,
outputAccuracy, features, x, y, z, weight, memberCount, parent, keys, valid, inDomain,
groupStarved}`. `parent[i]` maps element i of the level below to its group.

## Training (`trech-train-hierarchy`)

```
PYTHONPATH=tools/torch build/render-venv/bin/python -m trech_torch.hierarchy \
  --plan plan.json --samples train.jsonl --holdout-samples holdout.jsonl \
  [--calibration-samples cal.jsonl] --out-dir models/ --manifest report.json
```

- **Plan** (`trech_group_hierarchy_plan_v1`): base features and levels. Each level has a grouping,
  member features, optional context, supervised `outputs`, `latent` channels (named
  `<level>_h<i>`), a set-network shape and an optional `loss_weight`. The top level must be
  supervised. See the module docstring for an example.
- **Samples** (`trech_group_samples_v1`, JSON lines): one system per line with base `features`,
  `positions`, optional `weight`, `context`, explicit `groups` per level, and `targets` per level
  keyed by group key. Unlabelled groups simply do not enter the loss. `run` names the source run;
  the CLI refuses a run that appears in both training and held-out files.
- **End to end.** All levels train together in torch. Level k consumes level k−1's
  *predictions*, never its labels, so each level learns from what the chain will feed it at run
  time. Latent channels let a level pass information its supervised outputs cannot hold (for a
  pair energy, how charge is spread inside a cell, which decides the cross-cell terms).
- **Trust blocks** come from the exported JSON, evaluated by the NumPy reference `lift_np` with
  the engine's blocking rules. `input_domain` (hull, occupancy, joint reference) is measured on
  the chain's own training inputs. `holdout` on held-out samples is chained
  (`input_source: "chained_predictions"`), so a level's R² includes the errors of every level
  beneath it. Calibration samples set a run-level conformal `prediction_interval`.
  Capacity defaults to the largest training group.

## Synthetic demonstration (architecture only)

[`tests/fixtures/ml_group_hierarchy/regenerate.py --demo`](../tests/fixtures/ml_group_hierarchy/regenerate.py)
trains a three-level hierarchy on synthetic charged-point systems (60–140 points of q = ±1 in a
4×4×4 box). The pair energy is e_ij = q_i q_j exp(−d²/2σ²) with σ = 0.3. Labels exist at three
levels: intra-cell energy (lattice 1), intra-block energy (lattice 2), and g × total energy for
the system. No lower label contains cross-cell or cross-block pairs. The hierarchy has to infer
them from the members' learned latents.

Recorded run (2026-11-17, torch 2.8 CPU, `regenerate.py --demo`): 500 training systems, 100
selection systems (early stopping kept epoch 475 of 1500), 200 held-out systems, 9 calibration
runs of 20 systems. Levels: MPNN cell, MPNN block, DeepSets system. Capacities 10 / 8 / 8; no
held-out group was blocked. Held-out R² through the chain (each level fed the levels below's
predictions):

| Level | Groups | R² | RMSE | Run-level 90% half-width (9 runs, guarantee holds) |
| --- | --- | --- | --- | --- |
| cell (intra-cell energy) | 9,783 | 0.938 | 0.097 | 0.149 |
| block (intra-block energy) | 1,599 | 0.718 | 0.618 | 1.20 |
| system (g × total energy) | 200 | 0.530 | 2.65 | 6.51 |

**Grade the gap: the learned top level is not yet better than addition.** g × Σ of the
hierarchy's own predicted block energies reaches R² 0.620 on the same held-out systems; with the
true block labels it reaches 0.875. The system level's learned cross-block correction therefore
*loses* 0.09 R² against adding up its inputs. The block level (0.72) is the bottleneck. A first
attempt with 800 training systems, DeepSets cells/blocks and no early stopping did worse
(system R² 0.35 vs 0.67 additive; top training loss 0.009, i.e. overfit). These runs show that
the end-to-end chain trains, exports and evaluates consistently. They do **not** show that it
lifts behaviour better than a sum.

These are synthetic systems. They show that the recursive architecture lifts behaviour, not
physics.

## Tests

- CTest `trech_group_hierarchy` ([`test_group_hierarchy.cpp`](../tests/test_group_hierarchy.cpp)):
  C++ parity with the NumPy reference at every level (1e-9) on the committed fixture (DeepSets
  cell, MPNN block, DeepSets system). Also checks invariance to the order of base elements,
  lattice/explicit keys, overflow and blocked-member propagation, missing context/features/positions,
  out-of-domain lineage reaching the observer, the carried length, and loader rejections.
- CTest `trech_group_hierarchy_py` ([`test_group_hierarchy.py`](../tests/test_group_hierarchy.py)):
  plan validation, the engine partition order, fixture keys, and (with NumPy) `lift_np`
  reproducing the committed reference and blocking an over-capacity group.
- CTest `trech_js_runtime`: `ctx.lift` plans the three declared lifts by scale, reproduces the
  observer, flags latents, counts inferences, stops on a missing context and returns `null` in
  strict mode.

## Limits

- Trained on synthetic data only; no Geant4-harvested hierarchy and no scenario user yet.
- No TorchScript twins, store registration (`trech-ml`), JS `defineModel` family or validator
  gates specific to hierarchies. Each level passes the ordinary v3 static gates.
- One cubic lattice per level (no adaptive/octree or neighbour-overlapping groups). Groups do not
  see their neighbours, so cross-group behaviour must travel through latents to the next level.
- Composed uncertainty is the top level's chained holdout/interval, not a propagated per-group
  error.
