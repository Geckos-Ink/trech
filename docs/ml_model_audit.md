# Committed ML model audit

<!-- Generated; do not edit. Regenerate with:
     python3 -m trech_torch.validate_model --scan data projects --audit-json docs/ml_model_audit.json --audit-md docs/ml_model_audit.md (with PYTHONPATH=tools/torch)
     CTest `trech_ml_model_audit` fails when this file is stale. -->

Static validation of every committed `generic_surrogate` model under `data/`, `projects/` by [`validate_model.py`](../tools/torch/trech_torch/validate_model.py) ([contract](ml_models.md#validating-a-model)). It checks that each model loads under the engine's rules, stays finite across its own trained domain, and carries the trust blocks the engine grades predictions with. It does **not** re-measure accuracy: that needs the model's independent test runs (`trech-ml validate`). A complete trust profile is not a validity claim; `measured:false` models are distilled from an authored teacher.

## Totals

| Measure | Count |
| --- | ---: |
| Models scanned | 53 |
| Load under engine rules (`structure`) | 53 |
| Finite on their trained domain | 53 |
| Failing a static gate | 0 |
| Trust profile complete / partial / none | 17 / 8 / 28 |
| Measured hull | 25 |
| Occupancy histogram | 25 |
| Joint reference | 17 |
| Held-out R² | 25 |
| Per-output measured σ (RMSE) | 25 |
| Trained scale bands | 25 |
| Calibrated prediction interval | 5 |
| Own holdout R²min below 0 (worse than the mean on some output) | 2 |
| Labelled `measured:false` (distilled) | 23 |

## Models

| Model | Structure | Params | Hull | Occ. | Joint | R²min (n) | σ | Bands | measured | Trust | Status |
| --- | --- | ---: | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `data/beaker_cascade/macro_beaker_behavior.json` | linear 9→4 | 40 | — | — | — | — | — | — | — | none | warn |
| `data/beaker_cascade/nano_pair_descriptors.json` | linear 6→5 | 35 | — | — | — | — | — | — | — | none | warn |
| `data/briggs_rauscher_cascade/macro_oscillator_response.json` | linear 6→11 | 77 | — | — | — | — | — | — | — | none | warn |
| `data/briggs_rauscher_cascade/nano_reagent_descriptors.json` | linear 9→6 | 60 | — | — | — | — | — | — | — | none | warn |
| `data/cascade_demo/meso_response.json` | linear 1→1 | 2 | — | — | — | — | — | — | — | none | warn |
| `data/cascade_demo/nano_ionization.json` | linear 1→1 | 2 | — | — | — | — | — | — | — | none | warn |
| `data/discrete_operators/efflux_crossing_operator.json` | mlp(32x2,silu) 12→1 | 1505 | yes | yes | — | 0.9827 (6000) | yes | yes | false | partial | warn |
| `data/discrete_operators/efflux_transport_operator.json` | mlp(64x2,silu) 20→6 | 5894 | yes | yes | yes | 0.9993 (6000) | yes | yes | false | complete | pass |
| `data/discrete_operators/h2o_cycle_transition_operator.json` | mlp(32x2,silu) 16→2 | 1666 | yes | yes | — | 0.9973 (6000) | yes | yes | false | partial | warn |
| `data/elephants_toothpaste_cascade/macro_eruption_response.json` | linear 4→10 | 50 | — | — | — | — | — | — | — | none | warn |
| `data/elephants_toothpaste_cascade/nano_reagent_descriptors.json` | linear 10→4 | 44 | — | — | — | — | — | — | — | none | warn |
| `data/glass_cascade/macro_fluid_params.json` | linear 2→3 | 9 | — | — | — | — | — | — | — | none | warn |
| `data/glass_cascade/micro_bulk.json` | linear 2→2 | 6 | — | — | — | — | — | — | — | none | warn |
| `data/glass_cascade/nano_coarse_grain.json` | linear 2→2 | 6 | — | — | — | — | — | — | — | none | warn |
| `data/glass_furnace_cascade/macro_furnace_response.json` | linear 5→4 | 24 | — | — | — | — | — | — | — | none | warn |
| `data/glass_furnace_cascade/nano_batch_material_response.json` | linear 5→4 | 24 | — | — | — | — | — | — | — | none | warn |
| `data/glass_furnace_conduction_set/conduction_set_batch_solid.json` | deepsets(6x5,phi=32-32,sum,rho=16,silu) 30→1 | 1793 | yes | yes | yes | 0.9998 (14717) | yes | yes | false | complete | pass |
| `data/glass_furnace_conduction_set/conduction_set_glass.json` | deepsets(6x5,phi=32-32,sum,rho=16,silu) 30→1 | 1793 | yes | yes | yes | 0.9999 (5226) | yes | yes | false | complete | pass |
| `data/glass_furnace_conduction_set/conduction_set_melt.json` | deepsets(6x5,phi=32-32,sum,rho=16,silu) 30→1 | 1793 | yes | yes | yes | 0.9997 (5707) | yes | yes | false | complete | pass |
| `data/glass_furnace_operators/chemistry_batch_solid.json` | linear 2→2 | 6 | — | — | — | — | — | — | — | none | warn |
| `data/glass_furnace_operators/chemistry_melt.json` | linear 3→3 | 12 | — | — | — | — | — | — | — | none | warn |
| `data/glass_furnace_operators/conduction_batch_solid__batch_solid.json` | linear 2→1 | 3 | — | — | — | — | — | — | — | none | warn |
| `data/glass_furnace_operators/conduction_batch_solid__glass.json` | linear 2→1 | 3 | — | — | — | — | — | — | — | none | warn |
| `data/glass_furnace_operators/conduction_batch_solid__melt.json` | linear 2→1 | 3 | — | — | — | — | — | — | — | none | warn |
| `data/glass_furnace_operators/conduction_glass__glass.json` | linear 2→1 | 3 | — | — | — | — | — | — | — | none | warn |
| `data/glass_furnace_operators/conduction_glass__melt.json` | linear 2→1 | 3 | — | — | — | — | — | — | — | none | warn |
| `data/glass_furnace_operators/conduction_melt__melt.json` | linear 2→1 | 3 | — | — | — | — | — | — | — | none | warn |
| `data/glass_furnace_operators/thermal_batch_solid.json` | linear 3→2 | 8 | — | — | — | — | — | — | — | none | warn |
| `data/glass_furnace_operators/thermal_glass.json` | linear 3→1 | 4 | — | — | — | — | — | — | — | none | warn |
| `data/glass_furnace_operators/thermal_melt.json` | linear 3→2 | 8 | — | — | — | — | — | — | — | none | warn |
| `data/glass_furnace_operators_trained/chemistry_batch_solid.json` | linear 2→2 | 6 | yes | yes | — | 1.0000 (2211) | yes | yes | false | partial | warn |
| `data/glass_furnace_operators_trained/chemistry_melt.json` | linear 3→3 | 12 | yes | yes | — | 1.0000 (757) | yes | yes | false | partial | warn |
| `data/glass_furnace_operators_trained/thermal_batch_solid.json` | linear 3→2 | 8 | yes | yes | — | 1.0000 (2211) | yes | yes | false | partial | warn |
| `data/glass_furnace_operators_trained/thermal_glass.json` | linear 3→1 | 4 | yes | yes | — | 1.0000 (932) | yes | yes | false | partial | warn |
| `data/glass_furnace_operators_trained/thermal_melt.json` | linear 3→2 | 8 | yes | yes | — | 1.0000 (757) | yes | yes | false | partial | warn |
| `data/lava_lamp_cascade/macro_thermofluid_response.json` | linear 6→20 | 140 | — | — | — | — | — | — | — | none | warn |
| `data/lava_lamp_cascade/nano_material_response.json` | linear 5→6 | 36 | — | — | — | — | — | — | — | none | warn |
| `data/molecular_series/acetamide.json` | linear 13→10 | 140 | yes | yes | yes | 1.0000 (24) | yes | yes | false | complete | pass |
| `data/molecular_series/butane.json` | linear 21→15 | 330 | yes | yes | yes | 1.0000 (24) | yes | yes | false | complete | pass |
| `data/molecular_series/dimethyl_ether.json` | linear 13→10 | 140 | yes | yes | yes | 0.9999 (24) | yes | yes | false | complete | pass |
| `data/molecular_series/ethane.json` | linear 13→9 | 126 | yes | yes | yes | 1.0000 (24) | yes | yes | false | complete | pass |
| `data/molecular_series/ethanol.json` | linear 13→10 | 140 | yes | yes | yes | 1.0000 (24) | yes | yes | false | complete | pass |
| `data/molecular_series/formamide.json` | linear 13→7 | 98 | yes | yes | yes | 1.0000 (24) | yes | yes | false | complete | pass |
| `data/particle_molecule/atomic_response.json` | linear 44→3 | 135 | yes | yes | yes | 1.0000 (96) | yes | yes | false | complete | pass |
| `data/particle_molecule/molecular_response.json` | linear 12→3 | 39 | yes | yes | yes | 1.0000 (144) | yes | yes | false | complete | pass |
| `data/particle_observer/attempt1/observer_response.json` | mlp(48x2,silu) 5→2 | 2738 | yes | yes | yes | 0.9246 (12) | yes | yes | false | complete | pass |
| `data/particle_observer/observer_response.json` | mlp(64x2,silu) 5→2 | 4674 | yes | yes | yes | 0.9994 (18) | yes | yes | false | complete | pass |
| `data/polyurethane_cascade/macro_foam_response.json` | linear 6→23 | 161 | — | — | — | — | — | — | — | none | warn |
| `data/polyurethane_cascade/meso_mechanics_operator.json` | mlp(64x2,silu) 6→3 | 4803 | yes | yes | yes | 0.9980 (6006) | yes | yes | false | complete | pass |
| `data/polyurethane_cascade/meso_reaction_operator.json` | mlp(32x2,silu) 27→8 | 2216 | yes | yes | — | 0.9929 (38565) | yes | yes | false | partial | warn |
| `data/polyurethane_cascade/nano_reagent_descriptors.json` | linear 11→6 | 72 | — | — | — | — | — | — | — | none | warn |
| `data/spectrum_prediction/models/spectrum_atomic.json` | mlp(32x2,tanh) 19→40 | 3016 | yes | yes | yes | -7.9680 (6) | yes | yes | — | complete | warn |
| `data/spectrum_prediction/models/spectrum_molecular.json` | mlp(32x1,tanh) 33→32 | 2144 | yes | yes | yes | -0.4816 (33) | yes | yes | — | complete | warn |

## Problems

None: every scanned model passes the static gates.

## Accuracy warnings (from the models' own carried holdout)

- `data/spectrum_prediction/models/spectrum_atomic.json` — its own holdout R2min is -7.968: 22 output(s) predict worse than the holdout mean
- `data/spectrum_prediction/models/spectrum_molecular.json` — its own holdout R2min is -0.4816: 4 output(s) predict worse than the holdout mean
