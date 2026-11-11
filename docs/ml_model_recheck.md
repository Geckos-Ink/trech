# Committed ML models re-checked on fresh runs

<!-- Generated; do not edit. Regenerate with:
     PYTHONPATH=tools/torch python3 -m trech_torch.recheck_models --recipes data/ml_recheck_recipes.json --json docs/ml_model_recheck.json --md docs/ml_model_recheck.md (needs NumPy)
     CTest `trech_ml_model_recheck` fails when a model or recipe changed since. -->

Each model below has a reproducible data producer recorded in [`data/ml_recheck_recipes.json`](../data/ml_recheck_recipes.json). [`recheck_models.py`](../tools/torch/trech_torch/recheck_models.py) produced new runs with seeds the model was never trained or held out on and graded the **committed** model on them with the independent validator ([gates](ml_models.md#validating-a-model)). Models without a recipe are only statically audited ([audit](ml_model_audit.md)). A re-check grades what the model learned from its own data source: for `measured:false` operators that source is an authored teacher, so a pass says the distillation generalises to new operating points, not that the teacher is physically right.

| Model | Holdout regenerated | Fresh seeds (rows) | Carried R² → fresh R² | σ check | Status |
| --- | --- | --- | --- | --- | --- |
| `data/discrete_operators/h2o_cycle_transition_operator.json` | reproduces carried RMSE | 2026572612, 2026672614 (12000) | hazard_electrolysis 0.997292 → 0.997352; hazard_combustion 0.997344 → 0.997369 | pass | warn |
| `data/discrete_operators/efflux_transport_operator.json` | reproduces carried RMSE | 2026572613, 2026672615 (12000) | set_rvx 0.999947 → 0.999947; set_rvy 0.999944 → 0.999945; set_rvz 0.99994 → 0.999938; d_x_dt 0.999344 → 0.999393; d_y_dt 0.999271 → 0.999238; d_z_dt 0.99928 → 0.999378 | pass | pass |
| `data/discrete_operators/efflux_crossing_operator.json` | reproduces carried RMSE | 2026572614, 2026672616 (12000) | hazard_cross 0.982737 → 0.980842 | pass | warn |

## Warnings and failures

- `data/discrete_operators/h2o_cycle_transition_operator.json` — `trust_profile`: missing joint_reference (engine falls back to heuristic coverage / absent accuracy)
- `data/discrete_operators/efflux_crossing_operator.json` — `trust_profile`: missing joint_reference (engine falls back to heuristic coverage / absent accuracy)

## Not re-checked

Every other committed model: the illustrative cascade maps and untrained teachers have no data producer; the glass-furnace and polyurethane operators were harvested from engine runs (`build/glass_train/*`, `build/dev/operator_harvest/*`) whose exact commands were not recorded; the particle observer and spectrum models have their own builders. Recording an engine recipe (scenario, params, seeds) for each is open work in the training roadmap.
