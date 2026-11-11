# Committed ML models re-checked on fresh runs

<!-- Generated; do not edit. Regenerate with:
     PYTHONPATH=tools/torch python3 -m trech_torch.recheck_models --recipes data/ml_recheck_recipes.json --json docs/ml_model_recheck.json --md docs/ml_model_recheck.md (needs NumPy)
     CTest `trech_ml_model_recheck` fails when a model or recipe changed since. -->

Each model below has a reproducible data producer recorded in [`data/ml_recheck_recipes.json`](../data/ml_recheck_recipes.json). [`recheck_models.py`](../tools/torch/trech_torch/recheck_models.py) produced new runs with seeds the model was never trained or held out on and graded the **committed** model on them with the independent validator ([gates](ml_models.md#validating-a-model)). Models without a recipe are only statically audited ([audit](ml_model_audit.md)). A re-check grades what the model learned from its own data source: for `measured:false` operators that source is an authored teacher, so a pass says the distillation generalises to new operating points, not that the teacher is physically right.

| Model | Holdout regenerated | Fresh seeds (operating point); rows | Carried R² → fresh R² | σ check | Status |
| --- | --- | --- | --- | --- | --- |
| `data/discrete_operators/h2o_cycle_transition_operator.json` | reproduces carried RMSE | 2026572612, 2026672614; 12000 rows | hazard_electrolysis 0.997292 → 0.997352; hazard_combustion 0.997344 → 0.997369 | pass | warn |
| `data/discrete_operators/efflux_transport_operator.json` | reproduces carried RMSE | 2026572613, 2026672615; 12000 rows | set_rvx 0.999947 → 0.999947; set_rvy 0.999944 → 0.999945; set_rvz 0.99994 → 0.999938; d_x_dt 0.999344 → 0.999393; d_y_dt 0.999271 → 0.999238; d_z_dt 0.99928 → 0.999378 | pass | pass |
| `data/discrete_operators/efflux_crossing_operator.json` | reproduces carried RMSE | 2026572614, 2026672616; 12000 rows | hazard_cross 0.982737 → 0.980842 | pass | warn |
| `data/glass_furnace_conduction_set/conduction_set_batch_solid.json` | — | 20261141 (furnace_temperature_k=1540.0), 20261142 (ambient_temperature_k=360.0, cells_per_side=7, furnace_temperature_k=1690.0); 27178 rows | d_temperature_k_dt 0.999768 → 0.999731 | warn | warn |
| `data/glass_furnace_conduction_set/conduction_set_melt.json` | — | 20261141 (furnace_temperature_k=1540.0), 20261142 (ambient_temperature_k=360.0, cells_per_side=7, furnace_temperature_k=1690.0); 7791 rows | d_temperature_k_dt 0.999744 → 0.99983 | pass | pass |
| `data/glass_furnace_conduction_set/conduction_set_glass.json` | — | 20261141 (furnace_temperature_k=1540.0), 20261142 (ambient_temperature_k=360.0, cells_per_side=7, furnace_temperature_k=1690.0); 7031 rows | d_temperature_k_dt 0.99992 → 0.999664 | pass | pass |
| `data/glass_furnace_operators_trained/thermal_batch_solid.json` | — | 20261143 (furnace_temperature_k=1640.0), 20261144 (ambient_temperature_k=380.0, furnace_temperature_k=1790.0); 14555 rows | d_temperature_k_dt 1.0 → 1.0; d_melt_fraction_dt 1.0 → 1.0 | pass | warn |
| `data/glass_furnace_operators_trained/thermal_melt.json` | — | 20261143 (furnace_temperature_k=1640.0), 20261144 (ambient_temperature_k=380.0, furnace_temperature_k=1790.0); 6485 rows | d_temperature_k_dt 1.0 → 1.0; d_melt_fraction_dt 1.0 → 1.0 | pass | warn |
| `data/glass_furnace_operators_trained/thermal_glass.json` | — | 20261143 (furnace_temperature_k=1640.0), 20261144 (ambient_temperature_k=380.0, furnace_temperature_k=1790.0); 5360 rows | d_temperature_k_dt 1.0 → 1.0 | pass | warn |
| `data/glass_furnace_operators_trained/chemistry_batch_solid.json` | — | 20261143 (furnace_temperature_k=1640.0), 20261144 (ambient_temperature_k=380.0, furnace_temperature_k=1790.0); 14555 rows | hazard_soda_calcination 1.0 → 1.0; hazard_lime_calcination 1.0 → 1.0 | pass | warn |
| `data/glass_furnace_operators_trained/chemistry_melt.json` | — | 20261143 (furnace_temperature_k=1640.0), 20261144 (ambient_temperature_k=380.0, furnace_temperature_k=1790.0); 6485 rows | hazard_soda_calcination 1.0 → 1.0; hazard_lime_calcination 1.0 → 1.0; hazard_glass_fusion 1.0 → 1.0 | pass | warn |
| `data/polyurethane_cascade/meso_reaction_operator.json` | — | 20261151 (initial_temperature_k=290.0), 20261152 (initial_temperature_k=303.0, max_physics_step_s=0.03); 68115 rows | d_gel_dt 0.999594 → 0.999366; d_blow_dt 0.999753 → 0.999724; d_temperature_k_dt 0.999693 → 0.999618; d_dissolved_co2_dt 0.994257 → 0.994524; d_trapped_gas_dt 0.998581 → 0.998873; d_local_expansion_dt 0.992945 → 0.994424; set_rigidity 0.999744 → 0.99958; set_inverse_relative_viscosity 0.999844 → 0.999768 | pass | warn |

## Warnings and failures

- `data/discrete_operators/h2o_cycle_transition_operator.json` — `trust_profile`: missing joint_reference (engine falls back to heuristic coverage / absent accuracy)
- `data/discrete_operators/efflux_crossing_operator.json` — `trust_profile`: missing joint_reference (engine falls back to heuristic coverage / absent accuracy)
- `data/glass_furnace_conduction_set/conduction_set_batch_solid.json` — `sigma_calibration`: carried uncertainty mis-states the test error for d_temperature_k_dt; independent: the error bar was set on runs disjoint from these test runs
- `data/glass_furnace_operators_trained/thermal_batch_solid.json` — `trust_profile`: missing joint_reference (engine falls back to heuristic coverage / absent accuracy)
- `data/glass_furnace_operators_trained/thermal_melt.json` — `trust_profile`: missing joint_reference (engine falls back to heuristic coverage / absent accuracy)
- `data/glass_furnace_operators_trained/thermal_glass.json` — `trust_profile`: missing joint_reference (engine falls back to heuristic coverage / absent accuracy)
- `data/glass_furnace_operators_trained/chemistry_batch_solid.json` — `trust_profile`: missing joint_reference (engine falls back to heuristic coverage / absent accuracy)
- `data/glass_furnace_operators_trained/chemistry_melt.json` — `trust_profile`: missing joint_reference (engine falls back to heuristic coverage / absent accuracy)
- `data/polyurethane_cascade/meso_reaction_operator.json` — `trust_profile`: missing joint_reference (engine falls back to heuristic coverage / absent accuracy)

## Not re-checked

Every other committed model: the illustrative cascade maps and untrained teachers have no data producer; the particle observer (`tools/torch/build_particle_observer_models.py`, strict serial Geant4 harvests with frozen final cases) and the spectrum models (`projects/spectrum_prediction`) have their own builders and no fresh-run recipe yet (open work in the training roadmap). The glass-furnace and polyurethane operators ARE re-checked above on fresh operating points of the current scenarios, but their ORIGINAL runs (`build/glass_train/*`, `build/dev/operator_harvest/*`) cannot be regenerated: the glass operators were harvested from the 2D revision of glass_from_sand (36e979d, `CELL_COUNT = SIDE*SIDE`, today 3D) with unrecorded holdout knobs, so no holdout reproduction is claimed for them.
