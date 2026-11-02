# Training tools, model data and feature schemas — context and contracts

[Root principles](../../../AGENTS.md) · [Root roadmap](../../../ROADMAP.md) · [Parent](../AGENTS.md) · [Roadmap](ROADMAP.md)

Related owners: [Multi-scale inference](../../engine/inference/AGENTS.md) · [Coverage, uncertainty and trust](../../engine/inference/trust/AGENTS.md) · [Tests and validation ownership](../validation/AGENTS.md).

Read the root principles and the parent handbook first; then open only the subcategory relevant to the task. Source paths and shell commands in code spans/blocks are repository-relative unless stated otherwise; Markdown links resolve from this file.

- **Evolvo is optional offline tooling:** pinned submodule `thirds/evolvo`; adapter/trainer
  `tools/torch/trech_torch/evolve_structure.py` evolves bounded MLP definitions, selects on
  validation runs and reports accuracy on separate test runs. Never import it into C++/Studio or
  present genetic candidates as Geant4 truth. Ordinary surrogate training accepts `--depth N`.

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
