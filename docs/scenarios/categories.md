# Scenario categories and pruning guide

[Documentation index](../README.md) · [Scenario index](README.md) · [Scenario catalog](catalog.md) · [Purity report](../validation/TRECH_current_scenarios_purity.md)

This page groups the 71 scenario bundles in [`examples/scenarios/`](../../examples/scenarios)
by what they exercise. Within each group it ranks them by how much they help TRECH
development and validation. Use it to decide which bundles can be removed to make room for
new validation scenarios. It is a recommendation for a human decision, not a removal plan:
nothing on this page has been removed.

The [catalog](catalog.md) answers "which scenario shows X?". This page answers "which
scenarios could we lose with the least cost?".

## How the ranking works

Evidence is taken from the checkout of 2026-11-22: the generated
[purity report](../validation/TRECH_current_scenarios_purity.md) (validation results from the
run of 2026-11-18 at `a147530`: 60 pass, 3 info, no failures), the validation suite
([`scripts/run_validation_suite.sh`](../../scripts/run_validation_suite.sh) and its case
registry), the focused tests that name each bundle, the
[gated reference media](../../studio/tests/reference/README.md) and the
[migration ledger](../../AGENTS/scenarios/migrations/ROADMAP.md). Re-check these before
acting; a later change can move a bundle up or down.

A bundle ranks higher when it does more of the following:

1. **Serves the engine thesis.** It lifts Geant4 behaviour up the scale ladder through learned
   models, or it grades the Geant4 base itself. Purity grades A and B, and the V
   cross-checks, rank above authored-law grades D and E.
2. **Carries a validation case.** A graded case in the suite, or a dedicated validator, is
   evidence that something still works. A bundle with no case guards nothing.
3. **Covers something no other bundle covers.** For example, it is the only user of an engine
   operator, a hook contract or a reference.
4. **Is a target of planned work.** It is named by a [roadmap bucket](../../AGENTS.md#the-roadmap-12-implementations-to-do-bucket)
   slot or a migration-ledger row. Removing it would remove the work's acceptance test.

Removal cost is listed separately. It counts what must change with the bundle: tests and
validation cases, gated reference GIFs, previews, documentation and ledger rows.

### Grades used below

The purity report defines the grades in full. In short:

| Grade | Meaning |
| --- | --- |
| **A** | Engine inference with models trained on Geant4 output. |
| **B** | Engine inference with models distilled from an authored teacher or fitted to external data. |
| **C** | Part of the behaviour comes from inference; named authored laws remain. |
| **D** | Inferred coefficients drive an authored forward law. |
| **E** | An authored forward law, with no inference: comparison physics, a migration target. |
| **M** | Inference mechanism demo with hand-authored models. |
| **G** | Pure Geant4 transport or configuration. |
| **V** | Analytic cross-check fed from Geant4's own data. |
| **R** | Independent comparison reference, kept off the learned path. |

### Verdicts

| Verdict | Meaning |
| --- | --- |
| **Core** | Keep. Removing it loses unique validation evidence or a planned acceptance test. |
| **Keep** | Useful; it overlaps partly with a sibling but carries its own case or contract. |
| **Fold** | Merge into a sibling as a parameter or preset. The behaviour stays; the bundle count drops. |
| **Remove** | Candidate for removal: a duplicate, or a bundle with no case and no unique coverage. |

## Summary

| Category | Bundles | Core | Keep | Fold | Remove |
| --- | --- | --- | --- | --- | --- |
| [Geant4 base and analytic cross-checks](#1-geant4-base-and-analytic-cross-checks) | 6 | 5 | 1 | 0 | 0 |
| [Optical transport](#2-optical-transport) | 8 | 3 | 2 | 1 | 2 |
| [Learning and cascade mechanics](#3-learning-and-cascade-mechanics) | 4 | 2 | 2 | 0 | 0 |
| [Molecular and atomic response](#4-molecular-and-atomic-response) | 10 | 2 | 1 | 7 | 0 |
| [Reactions and material processes](#5-reactions-and-material-processes) | 3 | 2 | 1 | 0 | 0 |
| [Authored-law chemistry demos](#6-authored-law-chemistry-demos) | 5 | 1 | 3 | 0 | 1 |
| [Water and fluids](#7-water-and-fluids) | 9 | 4 | 3 | 1 | 1 |
| [Biology and mechanics](#8-biology-and-mechanics) | 3 | 2 | 1 | 0 | 0 |
| [Magnetic resonance](#9-magnetic-resonance) | 4 | 2 | 1 | 0 | 1 |
| [Carbon nanotube electronics](#10-carbon-nanotube-electronics) | 5 | 2 | 0 | 2 | 1 |
| [Independent process references](#11-independent-process-references) | 2 | 1 | 1 | 0 | 0 |
| [Runtime contracts and authoring fixtures](#12-runtime-contracts-and-authoring-fixtures) | 12 | 4 | 3 | 2 | 3 |
| **Total** | **71** | **30** | **19** | **13** | **9** |

Folding and removing together would free 22 bundle slots: 9 removals and 13 folds, of which
the folds keep their behaviour as parameters. See the [shortlist](#removal-shortlist).

## 1. Geant4 base and analytic cross-checks

These grade the particle base that everything else is lifted from. Classical formulas here are
fed from Geant4's own cross sections, the permitted use of closed-form laws. They are cheap,
fast and fully graded. Keep all of them.

| Rank | Scenario | Grade | Evidence | What only it covers | Verdict |
| --- | --- | --- | --- | --- | --- |
| 1 | [`analytic_compton_transfer`](../../examples/scenarios/analytic_compton_transfer/analytic_compton_transfer.js) | V | 1 suite case | The only companion that records a formal-law verdict (Klein–Nishina, four-momentum) in `law_checks`. | Core |
| 2 | [`analytic_beer_lambert`](../../examples/scenarios/analytic_beer_lambert/analytic_beer_lambert.js) | V | 4 suite cases | Exponential attenuation, also a declared formal law; its family gate requires the engine check `attenuation.memoryless` at Geant4's own coefficient. | Core |
| 3 | [`analytic_pair_production`](../../examples/scenarios/analytic_pair_production/analytic_pair_production.js) | V | 5 suite cases | Pair threshold and branching, photonuclear branching and final-state closure. | Core |
| 4 | [`analytic_photo_fraction`](../../examples/scenarios/analytic_photo_fraction/analytic_photo_fraction.js) | V | 2 suite cases | Photoelectric branching across an energy sweep. | Core |
| 5 | [`analytic_csda_range`](../../examples/scenarios/analytic_csda_range/analytic_csda_range.js) | V | 1 suite case | Charged-particle range against integrated stopping power. The only charged-particle cross-check. | Core |
| 6 | [`config_nitrogen_carbon_cycle`](../../examples/scenarios/config_nitrogen_carbon_cycle/config_nitrogen_carbon_cycle.js) | G | 2 suite cases | Nuclear Q-values and conservation from Geant4 isotope masses. | Keep |

## 2. Optical transport

Optical photon transport with optical properties derived from Geant4 cross sections, plus the
learned refractive-index surrogate. The family is over-represented: five bundles run almost the
same water-and-glass setup.

| Rank | Scenario | Grade | Evidence | What only it covers | Verdict |
| --- | --- | --- | --- | --- | --- |
| 1 | [`viz_refraction_demo`](../../examples/scenarios/viz_refraction_demo/viz_refraction_demo.js) | G | 11 pass, 3 info; gated reference GIF | Optics derived from Geant4 photoelectric, Compton and Rayleigh cross sections, then fed to optical transport. | Core |
| 2 | [`validation_glass_of_water`](../../examples/scenarios/validation_glass_of_water/validation_glass_of_water.js) | G | [`validate_glass_of_water.py`](../../scripts/validate_glass_of_water.py); gated reference GIF | Inverse Snell and Fresnel recovery of the properties Geant4 used. | Core |
| 3 | [`optics_training_panel`](../../examples/scenarios/optics_training_panel/optics_training_panel.js) | G | Feeds [`validate_optics_surrogate.py`](../../scripts/validate_optics_surrogate.py) | Generates the composition → optics training data for the surrogate. | Core |
| 4 | [`optics_surrogate_demo`](../../examples/scenarios/optics_surrogate_demo/optics_surrogate_demo.js) | G | 1 suite case; scene-dependency and flow-preset tests | A learned refractive index applied in Geant4 transport. | Keep |
| 5 | [`glass_of_water_varied`](../../examples/scenarios/glass_of_water_varied/glass_of_water_varied.js) | G | 1 suite case | Distributions of source position, direction and wavelength. | Keep |
| 6 | [`glass_of_water_spectral`](../../examples/scenarios/glass_of_water_spectral/glass_of_water_spectral.js) | G | No case | White-light dispersion. Same apparatus as the varied case. | Fold into `glass_of_water_varied` as a spectrum parameter |
| 7 | [`h2o_optics_beam`](../../examples/scenarios/h2o_optics_beam/h2o_optics_beam.js) | G | No case, no test | Single optical-photon water box. Covered by ranks 1–2. | Remove |
| 8 | [`config_optics`](../../examples/scenarios/config_optics/config_optics.js) | G | No case, no test | Near-duplicate of `h2o_optics_beam` with a gamma primary and a fixed optical table. | Remove |

## 3. Learning and cascade mechanics

These show the engine's inference entry points directly. `particle_observer_cascade` is one of
only four A-grade bundles, and the only one that climbs atomic → nano → meso with
independent Monte Carlo error gates.

| Rank | Scenario | Grade | Evidence | What only it covers | Verdict |
| --- | --- | --- | --- | --- | --- |
| 1 | [`particle_observer_cascade`](../../examples/scenarios/particle_observer_cascade/particle_observer_cascade.js) | A | [`validate_particle_observer.py`](../../scripts/validate_particle_observer.py) | The full Geant4-trained ladder to a meso estimate, checked against independent histories. | Core |
| 2 | [`surrogate_generic_demo`](../../examples/scenarios/surrogate_generic_demo/surrogate_generic_demo.js) | B | 1 suite case; JS engine parity | The minimal `ctx.predict` path on live material facts. | Core |
| 3 | [`spectrum_prediction`](../../examples/scenarios/spectrum_prediction/spectrum_prediction.js) | M | [`validate_spectrum_prediction.py`](../../scripts/validate_spectrum_prediction.py); CTest | Entry point of the spectra JS subproject. Since 2026-11-27 the atomic rung reads the Geant4 atomic response (mean excitation energy, photo-absorption) from the run's own material probe; the validator recomputes those inputs from the probe records. Labels stay measured. | Keep |
| 4 | [`cascade_multiscale_demo`](../../examples/scenarios/cascade_multiscale_demo/cascade_multiscale_demo.js) | M | JS engine parity in CTest | Automatic scale ordering in `ctx.cascade`, with hand-authored maps. | Keep |

## 4. Molecular and atomic response

Seven of these ten bundles are three-line wrappers that set a preset and include a shared root.
They cost almost nothing to maintain, but each counts as a bundle, a Studio tree entry and a
purity section.

| Rank | Scenario | Grade | Evidence | What only it covers | Verdict |
| --- | --- | --- | --- | --- | --- |
| 1 | [`molecular_series`](../../examples/scenarios/molecular_series/molecular_series.js) | B | [`run_molecular_series.py`](../../scripts/run_molecular_series.py) (12 runs), [`validate_particle_molecule.py`](../../scripts/validate_particle_molecule.py) (15 runs) | Shared root: quantum torsion and polarization fits next to Geant4-trained photon response. | Core |
| 2 | [`chemistry_mode`](../../examples/scenarios/chemistry_mode/chemistry_mode.js) | A | [`validate_chemistry_mode.py`](../../scripts/validate_chemistry_mode.py); C++ chemistry tests | Studio Chemistry workspace: isotope-resolved Geant4 response, scenes and reactions (bucket slot 4). | Core |
| 3 | [`chemistry_probability_reference`](../../examples/scenarios/chemistry_probability_reference/chemistry_probability_reference.js) | A | [`validate_chemistry_probability.py`](../../scripts/validate_chemistry_probability.py) | Joint electronic and Geant4 nuclear initial-state ensembles for water and deuterium. | Keep |
| 4 | [`chemistry_atomic_levels_reference`](../../examples/scenarios/chemistry_atomic_levels_reference/chemistry_atomic_levels_reference.js) | A | No case, no test | A neon scene file for `chemistry_mode`. | Fold into `chemistry_mode` (`scene_file` parameter) |
| 5–10 | `molecular_01_ethane` … `molecular_06_acetamide` | B | Covered through `molecular_series` | One preset each. | Fold into `molecular_series` (`preset` parameter) |

Folding the six molecular presets touches the [molecular series guide](molecular_series.md),
the six previews and the media script; the validators already loop over presets.

## 5. Reactions and material processes

| Rank | Scenario | Grade | Evidence | What only it covers | Verdict |
| --- | --- | --- | --- | --- | --- |
| 1 | [`glass_from_sand`](../../examples/scenarios/glass_from_sand/glass_from_sand.js) | B | 4 suite cases; cascade-ladder and parity tests | Domain routing, learn–freeze–deploy at held-out temperatures, set conduction, and the field-evolution validation companion. The richest engine exercise in the corpus. | Core |
| 2 | [`testscenario_h2o_electrolysis_combustion`](../../examples/scenarios/testscenario_h2o_electrolysis_combustion/testscenario_h2o_electrolysis_combustion.js) | B | 2 suite cases | The only teacher-graded `ctx.react` user: discrete inventories with atom-count protection. | Core |
| 3 | [`water_salt_recipe`](../../examples/scenarios/water_salt_recipe/water_salt_recipe.js) | G | No case | The only bundle that drives the [solution-process library](solution_processes.md) (bucket slot 12). | Keep, and give it a case |

## 6. Authored-law chemistry demos

Visually rich, but their behaviour still comes mainly from authored laws and hand-authored
response surfaces (every bundle here carries a purity review flag). They are migration targets
(ledger rows 1, 4 and 7), so removing one also deletes the acceptance test of its row.

| Rank | Scenario | Grade | Evidence | What only it covers | Verdict |
| --- | --- | --- | --- | --- | --- |
| 1 | [`polyurethane_foam`](../../examples/scenarios/polyurethane_foam/polyurethane_foam.js) | C | 2 suite cases; [`validate_foam_mechanics.sh`](../../scripts/validate_foam_mechanics.sh) | The learned constitutive candidate and its seven-observable promotion gate; first user of the shared foam solver (ledger row 1, bucket slot 9). | Core |
| 2 | [`beaker_water_n_pentane`](../../examples/scenarios/beaker_water_n_pentane/beaker_water_n_pentane.js) | C | 1 suite case; particle-sampling test | Two-liquid separation and evaporation. | Keep |
| 3 | [`beaker_water_n_pentane_studio`](../../examples/scenarios/beaker_water_n_pentane_studio/beaker_water_n_pentane_studio.js) | M | Source of the gated `beaker_water_pentane` reference GIF | Presentation wrapper only. | Keep while it is the reference-media source |
| 4 | [`elephants_toothpaste`](../../examples/scenarios/elephants_toothpaste/elephants_toothpaste.js) | D | 1 suite case | Second foam-solver user. Ledger row 1 plans to run the foam gate through it. | Keep |
| 5 | [`briggs_rauscher_oscillator`](../../examples/scenarios/briggs_rauscher_oscillator/briggs_rauscher_oscillator.js) | D | 1 suite case; JS engine parity | An oscillating colour from an authored rate law with hand-authored coefficient maps. | Remove, unless ledger row 4 is about to start |

Removing `briggs_rauscher_oscillator` also requires editing ledger row 4 and the JS engine
parity test list.

## 7. Water and fluids

The headline question of the thesis ("what does a stirred glass of water do?") lives here, but
most bundles are E-grade molecular dynamics used as comparison physics. Ledger row 8 names the
four MD bundles and asks to preserve their gates while migrating them, so a removal there must
also rewrite that row.

| Rank | Scenario | Grade | Evidence | What only it covers | Verdict |
| --- | --- | --- | --- | --- | --- |
| 1 | [`lava_lamp`](../../examples/scenarios/lava_lamp/lava_lamp.js) | C | 1 suite case; parity test; gated reference GIF | Field-evolution arbitration: the validation companion grades the engine's field methods per domain. | Core |
| 2 | [`glass_of_water_shaken`](../../examples/scenarios/glass_of_water_shaken/glass_of_water_shaken.js) | C | 1 suite case; cascade-ladder test; gated reference GIF | The thesis's glass-of-water question: nano MD facts drive a cascade into a particle fluid. | Core |
| 3 | [`h2o_bulk_water`](../../examples/scenarios/h2o_bulk_water/h2o_bulk_water.js) | E | 1 suite case | Radial structure and self-diffusion of rigid SPC/E water, the best-graded MD reference. | Core |
| 4 | [`h2o_bulk_freeze_boil`](../../examples/scenarios/h2o_bulk_freeze_boil/h2o_bulk_freeze_boil.js) | E | No suite case | The reference target for bucket slot 3, a Geant4-trained water operator that freezes. | Core, and give it a case |
| 5 | [`h2o_diffusion_temperature`](../../examples/scenarios/h2o_diffusion_temperature/h2o_diffusion_temperature.js) | E | 1 suite case | Diffusion trend against measured water. | Keep |
| 6 | [`h2o_cluster_fluid`](../../examples/scenarios/h2o_cluster_fluid/h2o_cluster_fluid.js) | E | 1 suite case | A small hydrogen-bonded droplet. | Keep (named by ledger row 8) |
| 7 | [`h2o_molecule_stability`](../../examples/scenarios/h2o_molecule_stability/h2o_molecule_stability.js) | E | 1 suite case | A single flexible molecule. | Keep (named by ledger row 8) |
| 8 | [`h2o_fluid`](../../examples/scenarios/h2o_fluid/h2o_fluid.js) | G | 1 suite case; `run_validation.sh` | Transport through a salt-and-brine apparatus. | Fold into `water_salt_recipe` or keep as a transport fixture |
| 9 | [`h2o_single_molecule`](../../examples/scenarios/h2o_single_molecule/h2o_single_molecule.js) | G | No case, no test | A subpixel molecule-shaped geometry fixture. | Remove |

## 8. Biology and mechanics

| Rank | Scenario | Grade | Evidence | What only it covers | Verdict |
| --- | --- | --- | --- | --- | --- |
| 1 | [`testscenario_efflux`](../../examples/scenarios/testscenario_efflux/testscenario_efflux.js) | B | 2 suite cases; [design](testscenario_efflux.md) | A frozen learned operator deployed in closed loop; the promoted row 6 half. | Core |
| 2 | [`testscenario_osmotic`](../../examples/scenarios/testscenario_osmotic/testscenario_osmotic.js) | C | 2 suite cases | Distilled particle velocity and channel-passage operators (2026-11-26); its authored membrane law is bucket slot 5 (ledger row 6 remainder), and this bundle is that migration's acceptance test. | Core |
| 3 | [`testscenario_pascal`](../../examples/scenarios/testscenario_pascal/testscenario_pascal.js) | E | 1 suite case | Pressure transmission in rigid and deformable vessels; last step of ledger row 8. | Keep |

## 9. Magnetic resonance

All four are E-grade: a hook-layer Bloch model, with Geant4 supplying proton density. Ledger
row 3 (priority P1) migrates them together onto one operator.

| Rank | Scenario | Grade | Evidence | What only it covers | Verdict |
| --- | --- | --- | --- | --- | --- |
| 1 | [`testscenario_magnetic_resonance`](../../examples/scenarios/testscenario_magnetic_resonance/testscenario_magnetic_resonance.js) | E | 1 suite case | Free-induction decay of a water phantom; the base of ledger row 3. | Core |
| 2 | [`testscenario_magnetic_resonance_imaging`](../../examples/scenarios/testscenario_magnetic_resonance_imaging/testscenario_magnetic_resonance_imaging.js) | E | 1 suite case | Frequency encoding and Fourier reconstruction of a 1D profile. | Core |
| 3 | [`testscenario_magnetic_resonance_brain`](../../examples/scenarios/testscenario_magnetic_resonance_brain/testscenario_magnetic_resonance_brain.js) | E | Suite case via a dedicated runner | 2D/3D k-space reconstruction of a procedural phantom. | Keep |
| 4 | [`testscenario_magnetic_resonance_tissues`](../../examples/scenarios/testscenario_magnetic_resonance_tissues/testscenario_magnetic_resonance_tissues.js) | E | Suite case via a dedicated runner | Tissue contrast, which the brain phantom also shows through its tissue proton densities. | Remove, or fold into the brain case |

## 10. Carbon nanotube electronics

Ledger row 2 (priority P1) migrates the band-structure → device → circuit chain. The two main
bundles are its acceptance tests; the three `config_cnt_*` stubs are geometry fixtures with no
case.

| Rank | Scenario | Grade | Evidence | What only it covers | Verdict |
| --- | --- | --- | --- | --- | --- |
| 1 | [`cnt_band_structure`](../../examples/scenarios/cnt_band_structure/cnt_band_structure.js) | E | 1 suite case | Chirality-dependent gaps; the bottom rung of ledger row 2. Includes `config_cnt_stub`. | Core |
| 2 | [`cnt_logic_gates`](../../examples/scenarios/cnt_logic_gates/cnt_logic_gates.js) | E | 1 suite case | Device currents and gate truth tables; the top rung of ledger row 2. | Core |
| 3 | [`config_cnt_stub`](../../examples/scenarios/config_cnt_stub/config_cnt_stub.js) | G | Included by `cnt_band_structure` | A parameterized multi-wall shell. | Fold (keep as an include, drop it as a bundle) |
| 4 | [`config_cnt_optics_stub`](../../examples/scenarios/config_cnt_optics_stub/config_cnt_optics_stub.js) | G | No case, no test | Optical steps near a shell. | Fold into `config_cnt_stub` as an optics parameter |
| 5 | [`config_cnt_world_stub`](../../examples/scenarios/config_cnt_world_stub/config_cnt_world_stub.js) | G | No case, no test | A fixed five-wall version of `config_cnt_stub`. | Remove |

## 11. Independent process references

R-grade comparison solvers kept outside the learned path. Each has a gated reference GIF, a C++
test and a validator, so removal is comparatively expensive.

| Rank | Scenario | Grade | Evidence | What only it covers | Verdict |
| --- | --- | --- | --- | --- | --- |
| 1 | [`nacl_dehydration_reference`](../../examples/scenarios/nacl_dehydration_reference/nacl_dehydration_reference.js) | R | C++ test; validator; gated reference GIF | The NaCl interface workflow, the reference closest to the osmosis and solution-process work. | Core |
| 2 | [`aerodynamics_reference`](../../examples/scenarios/aerodynamics_reference/aerodynamics_reference.js) | R | C++ test; validator; gated reference GIF | An ideal-gas Euler field around a blunt body. No particle-derived lift is planned for it. | Keep; first R-grade candidate if space is needed |

## 12. Runtime contracts and authoring fixtures

These test the engine and the JavaScript host, not physics. The graded ones are cheap
regression guards; the ungraded `config_*` stubs mostly serve as authoring examples. The C++
round-trip test already covers the legacy `multiscale` and DNA chemistry config fields without
a scenario.

| Rank | Scenario | Grade | Evidence | What only it covers | Verdict |
| --- | --- | --- | --- | --- | --- |
| 1 | [`hooks_track_ledger`](../../examples/scenarios/hooks_track_ledger/hooks_track_ledger.js) | G | 1 suite case; CTest | The track-hook contract: every started track ends once, step and length identities. | Core |
| 2 | [`geometry_refusal_guard`](../../examples/scenarios/geometry_refusal_guard/geometry_refusal_guard.js) | G | 1 suite case; dedicated test | The engine refuses overlapping or unknown-material geometry. | Core |
| 3 | [`config_hook_dispatch`](../../examples/scenarios/config_hook_dispatch/config_hook_dispatch.js) | G | C++ JS engine parity test | Hook dispatch, emissions and allowed init overrides. | Core |
| 4 | [`geometry_procedural_assembly`](../../examples/scenarios/geometry_procedural_assembly/geometry_procedural_assembly.js) | G | 1 suite case | `TRECH_GEOMETRY` generators and the authoring-time overlap audit. | Core |
| 5 | [`hello_world`](../../examples/scenarios/hello_world/hello_world.js) | G | Smoke script; CTest; [first run](../first_run.md) | The onboarding walkthrough. | Keep |
| 6 | [`water_box`](../../examples/scenarios/water_box/water_box.js) | G | `test_js_runtime.cpp` | The first authoring example. | Keep |
| 7 | [`config_stratify`](../../examples/scenarios/config_stratify/config_stratify.js) | G | No case | Threshold event stratification. | Keep, merged with rank 8 |
| 8 | [`config_stratify_ml`](../../examples/scenarios/config_stratify_ml/config_stratify_ml.js) | G | No case | The same, with a stratification model and optics. | Fold into `config_stratify` (`ml` parameter) |
| 9 | [`config_flow_language`](../../examples/scenarios/config_flow_language/config_flow_language.js) | G | No case | The `TRECH_FLOW` authoring example. | Fold into `water_box` or keep as the only `TRECH_FLOW` example |
| 10 | [`config_multi_beam_units`](../../examples/scenarios/config_multi_beam_units/config_multi_beam_units.js) | G | No case, no test | Beam composition and units. | Remove (move the snippet into the [authoring guide](authoring.md)) |
| 11 | [`config_chemistry_stub`](../../examples/scenarios/config_chemistry_stub/config_chemistry_stub.js) | G | No case, no test | DNA chemistry option wiring, already covered by the round-trip test. | Remove |
| 12 | [`config_multiscale_stub`](../../examples/scenarios/config_multiscale_stub/config_multiscale_stub.js) | G | No case, no test | The legacy `multiscale` bridge scaffold, superseded by the cascade and operators. | Remove |

## Removal shortlist

Ordered from the safest. Tier 1 loses no validation case. Tier 2 keeps the behaviour as a
parameter. Tier 3 loses a graded case or a migration acceptance test, so it needs a decision.

**Tier 1: remove; no case and no unique coverage (7)**

- `config_optics`, `h2o_optics_beam`: optics duplicates of the validated glass-of-water cases.
- `config_cnt_world_stub`: a fixed copy of `config_cnt_stub`.
- `h2o_single_molecule`: a subpixel geometry fixture.
- `config_multiscale_stub`, `config_chemistry_stub`: config fields already round-trip tested.
- `config_multi_beam_units`: an authoring snippet; move it into the authoring guide.

**Tier 2: fold into a sibling (13 bundles become parameters)**

- `molecular_01_ethane` … `molecular_06_acetamide` → `molecular_series` `preset`.
- `chemistry_atomic_levels_reference` → `chemistry_mode` `scene_file`.
- `glass_of_water_spectral` → `glass_of_water_varied`.
- `config_stratify_ml` → `config_stratify`.
- `config_cnt_optics_stub` → `config_cnt_stub`; then `config_cnt_stub` becomes an include of
  `cnt_band_structure` rather than a bundle.
- `h2o_fluid` → `water_salt_recipe`.
- `config_flow_language` → `water_box`.

**Tier 3: remove with a known loss (decide per item)**

- `briggs_rauscher_oscillator`: loses one D-grade case and the subject of ledger row 4.
- `testscenario_magnetic_resonance_tissues`: tissue contrast stays visible in the brain phantom.
- `aerodynamics_reference`: loses an R-grade reference with no planned particle lift; costs a
  gated reference GIF, a C++ test and a validator.

Do not remove the **Core** bundles. Several are the only acceptance test of a bucket slot or a
P1 ledger row: `h2o_bulk_freeze_boil`, `testscenario_osmotic`, `chemistry_mode`,
`polyurethane_foam`, `cnt_band_structure`, `cnt_logic_gates` and the magnetic-resonance base.

## What a removal touches

Removing or folding a bundle is a code change, not only a deletion. In the same change:

1. Delete the bundle folder (`<name>.js` and its `.view.js`, `.validation.js`, `.ui.js`
   companions) and check that no other bundle `TRECH_INCLUDE`s it.
2. Remove its cases from the validation case registry and
   [`scripts/run_validation_suite.sh`](../../scripts/run_validation_suite.sh), and from any focused
   test that names it (search `tests/`, `studio/tests/`, `scripts/` and `tools/validation/`).
3. Remove its entry from the law ledger
   [`tools/validation/js_law_audit.json`](../../tools/validation/js_law_audit.json), then
   regenerate the purity report with
   `PYTHONPATH=tools/validation python3 -m trech_validation.purity`. CTest
   `trech_scenario_purity_report` fails until you do.
4. Remove its previews from `studio/previews/` and the preview manifest. Never delete or
   regenerate a gated reference GIF without following the
   [reference-media rules](../../studio/tests/reference/README.md).
5. Update the [catalog](catalog.md), the [authoring examples](authoring.md#examples-by-feature),
   the [preview gallery](../previews.md) and any family guide that links it.
6. If a migration-ledger row or bucket slot names it, edit that row in the
   [migration roadmap](../../AGENTS/scenarios/migrations/ROADMAP.md) and run
   `python3 scripts/draw_roadmap_bucket.py --check`.
7. Update the bundle count (71 today) in the
   [bundles handbook](../../AGENTS/scenarios/bundles/AGENTS.md) and on this page.

## Where new validation scenarios would help most

The ranking also shows where the corpus is thin. These are the gaps a new validation scenario
would fill best:

- **A-grade coverage outside chemistry.** Only four bundles are A-grade, and all of them are in
  molecular and atomic response. Fluids, magnetic resonance, CNT and biology have no
  Geant4-trained end-to-end case.
- **Charged-particle and neutron base checks.** The analytic family is mostly photons;
  `analytic_csda_range` is the only charged-particle check, and there is no neutron check.
- **Cases for ungraded Core bundles.** `h2o_bulk_freeze_boil` and `water_salt_recipe` have no
  suite case, though planned work depends on them.
