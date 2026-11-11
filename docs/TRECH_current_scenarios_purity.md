# TRECH — current scenarios purity report

<!-- GENERATED FILE: do not edit by hand. Regenerate with
     PYTHONPATH=tools/validation python3 -m trech_validation.purity
     schema: trech_scenario_purity_v1 -->

This report shows, for every bundle in [`examples/scenarios/`](../examples/scenarios), how much of its behaviour comes from **TRECH statistical inference over the Geant4 base** and how much is **forced by authored laws, fixed constants and closed-form functions**. It follows the [engine thesis](../AGENTS.md#essential-project-principles): elementary Geant4 truth is lifted scale by scale through learned models, and classical formulas stay comparison/validation references only.

It is regenerated from committed inputs only, so it is reproducible and guarded by CTest (`trech_scenario_purity_report`). Adding, removing or editing a scenario, the law ledger, a referenced model or the committed validation report makes that test fail until the file is regenerated. `scripts/run_validation_suite.sh` also regenerates it after each validation report. **Purity is a static and declared measure. Performance is whatever the last committed validation run recorded.** Neither is proof that a run is correct.

## How to read it

### Purity grade

The reviewed law ledger ([`tools/validation/js_law_audit.json`](../tools/validation/js_law_audit.json)) is authoritative. Bundles outside the ledger fall back to the `physics_status` declared in their `.validation.js` companion. Model provenance then decides between A and B (or A and M).

| Grade | Meaning | Rule |
| --- | --- | --- |
| **A** | Geant4-learned | Normal path runs engine inference whose models were trained on Geant4 Monte Carlo output; no authored material law remains on it. |
| **B** | Learned, not from Geant4 | Normal path runs engine inference with trained models, but they were distilled from an authored teacher law or fitted to external anchors rather than Geant4 output, so the behaviour's origin is not yet the particle base. |
| **C** | Partially operator-backed | Inference supplies part of the normal path; named authored laws remain in the ledger residual. |
| **D** | Authored law, inferred coefficients | The cascade infers coefficients, but an authored forward law integrates the behaviour. |
| **E** | Authored forward law | Behaviour is driven by an authored law with no engine inference on the normal path (labelled comparison physics; a migration target). |
| **M** | Inference mechanism demo | Uses engine inference without a declared material law, but at least one normal-path model is a hand-authored response surface (or none could be resolved). It shows the mechanism, not learned physics. |
| **G** | Geant4 transport / configuration | Pure Geant4 transport or configuration. Nothing is forced, but nothing is lifted up the scale ladder either. |
| **V** | Analytic cross-check | Classical formulas fed from Geant4's own data, used only to validate transport. This is the permitted use of closed-form laws. |
| **R** | Independent comparison reference | An explicitly separate comparison solver, kept outside TRECH's learned path. It must not become training truth. |

Purity order for TRECH's goal: **A > B > C > D > E**. **M** is mechanism-only. **G** forces nothing but lifts nothing. **V** and **R** are validation roles, not lift attempts.

### Static evidence (normal path)

The generator lexes the physics entry point and every non-utility module it `TRECH_INCLUDE`s (`.view.js`, `.ui.js` and `.validation.js` companions are presentation/expectations and are excluded). Code inside functions whose names say *reference/classical/analytic/comparison/teacher/oracle/expected*, inside `if (… "reference" …)` branches, and inside `*_reference.js` modules counts as comparison code, not normal path.

- **Inference sites**: `ctx.predict/cascade/evolve/react/interact` call sites. `ctx.cascade()` with no argument auto-seeds from the Geant4 base.
- **Law-shaped math**: `Math.exp/log/pow/tanh/sinh/cosh…` and `**`, the usual signatures of authored rate, decay or power laws.
- **Inference share** = inference sites ÷ (inference sites + law-shaped math). It reads 100% when no authored law shape remains on the normal path, and — when the bundle has neither.
- **Embedded coefficients**: non-trivial decimal/exponent literals inside function bodies, per 100 code lines. These are forced numbers in behavioural code. Top-level literals (apparatus, inputs) are reported separately and not counted against purity.
- **Geant4 reads**: `ctx.materials/optics/step` and per-event `ctx.event.*` facts consumed by the hooks.
- Geometry/kinematics math (`sqrt`, trig) is listed but not treated as a forced law.

Model provenance comes from each referenced model file's own metadata: `trained_from`, `holdout`, `note.teacher` and `note.geant4_trained`.

Performance source: [`docs/validation_report.json`](validation_report.json), generated 2026-11-11T23:20:22Z at `917adc2` (totals {"error": 0, "fail": 0, "info": 4, "pass": 57, "skip": 0, "total": 61}). Bundles that the suite does not run show *none recorded*. Their dedicated validators (when declared) are listed per section.

## Summary

68 scenario bundles. Grade distribution: **A** 4, **B** 11, **C** 4, **D** 2, **E** 12, **M** 3, **G** 25, **V** 5, **R** 2.

8 bundles carry review flags (see their sections).

| Scenario | Grade | Status | Inference share | Inference / law sites | Coeff. /100 lines | Models (normal path) | Scales | Validation |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| [aerodynamics_reference](#aerodynamics_reference) | **R** | `reference_only` | — | 0 / 0 | 0.0 | — | — | none recorded |
| [analytic_beer_lambert](#analytic_beer_lambert) | **V** | `configuration_or_transport` | — | 0 / 0 | 0.0 | — | — | 4 pass |
| [analytic_compton_transfer](#analytic_compton_transfer) | **V** | `configuration_or_transport` | — | 0 / 0 | 0.0 | — | — | 1 pass |
| [analytic_csda_range](#analytic_csda_range) | **V** | `configuration_or_transport` | — | 0 / 0 | 0.0 | — | — | 1 pass |
| [analytic_pair_production](#analytic_pair_production) | **V** | `configuration_or_transport` | — | 0 / 0 | 0.0 | — | — | 5 pass |
| [analytic_photo_fraction](#analytic_photo_fraction) | **V** | `configuration_or_transport` | — | 0 / 0 | 0.0 | — | — | 2 pass |
| [beaker_water_n_pentane](#beaker_water_n_pentane) | **C** ⚠ | `operator_partial` | 50% | 1 / 1 | 5.0 | 2×hand | nano→macro | 1 pass |
| [beaker_water_n_pentane_studio](#beaker_water_n_pentane_studio) | **M** | `configuration_or_transport` | 50% | 1 / 1 | 5.0 | 2×hand | nano→macro | none recorded |
| [briggs_rauscher_oscillator](#briggs_rauscher_oscillator) | **D** ⚠ | `reference_only` | 33% | 1 / 2 | 10.3 | 2×hand | nano→macro | 1 pass |
| [cascade_multiscale_demo](#cascade_multiscale_demo) | **M** | `no_active_material_law` | 100% | 1 / 0 | 0.0 | 2×hand | nano→meso | none recorded |
| [chemistry_atomic_levels_reference](#chemistry_atomic_levels_reference) | **A** | `configuration_or_transport` | 60% | 3 / 2 | 0.4 | 2×G4 | atomic→nano | none recorded |
| [chemistry_mode](#chemistry_mode) | **A** | `operator_native` | 60% | 3 / 2 | 0.4 | 2×G4 | atomic→nano | none recorded |
| [chemistry_probability_reference](#chemistry_probability_reference) | **A** | `configuration_or_transport` | 60% | 3 / 2 | 0.4 | 2×G4 | atomic→nano | none recorded |
| [cnt_band_structure](#cnt_band_structure) | **E** | `reference_only` | — | 0 / 0 | 4.8 | — | — | 1 pass |
| [cnt_logic_gates](#cnt_logic_gates) | **E** | `reference_only` | 0% | 0 / 20 | 6.7 | — | — | 1 pass |
| [config_chemistry_stub](#config_chemistry_stub) | **G** | `configuration_or_transport` | — | 0 / 0 | 0.0 | — | — | none recorded |
| [config_cnt_optics_stub](#config_cnt_optics_stub) | **G** | `configuration_or_transport` | — | 0 / 0 | 0.0 | — | — | none recorded |
| [config_cnt_stub](#config_cnt_stub) | **G** | `configuration_or_transport` | — | 0 / 0 | 0.0 | — | — | none recorded |
| [config_cnt_world_stub](#config_cnt_world_stub) | **G** | `configuration_or_transport` | — | 0 / 0 | 0.0 | — | — | none recorded |
| [config_flow_language](#config_flow_language) | **G** | `configuration_or_transport` | — | 0 / 0 | 0.0 | — | — | none recorded |
| [config_hook_dispatch](#config_hook_dispatch) | **G** | `no_active_material_law` | — | 0 / 0 | 0.0 | — | — | none recorded |
| [config_multi_beam_units](#config_multi_beam_units) | **G** | `configuration_or_transport` | — | 0 / 0 | 0.0 | — | — | none recorded |
| [config_multiscale_stub](#config_multiscale_stub) | **G** | `configuration_or_transport` | — | 0 / 0 | 0.0 | — | — | none recorded |
| [config_nitrogen_carbon_cycle](#config_nitrogen_carbon_cycle) | **G** | `configuration_or_transport` | — | 0 / 0 | 0.0 | — | — | 2 pass |
| [config_optics](#config_optics) | **G** | `configuration_or_transport` | — | 0 / 0 | 0.0 | — | — | none recorded |
| [config_stratify](#config_stratify) | **G** | `configuration_or_transport` | — | 0 / 0 | 0.0 | — | — | none recorded |
| [config_stratify_ml](#config_stratify_ml) | **G** | `configuration_or_transport` | — | 0 / 0 | 0.0 | — | — | none recorded |
| [elephants_toothpaste](#elephants_toothpaste) | **D** ⚠ | `reference_only` | 25% | 1 / 3 | 3.7 | 2×hand | nano→macro | 1 pass |
| [geometry_procedural_assembly](#geometry_procedural_assembly) | **G** | `no_active_material_law` | — | 0 / 0 | 0.0 | — | — | 1 pass |
| [glass_from_sand](#glass_from_sand) | **B** ⚠ | `operator_backed` | 100% | 5 / 0 | 0.8 | 8×dist 8×hand | nano→micro→meso→macro | 3 pass |
| [glass_of_water_shaken](#glass_of_water_shaken) | **C** ⚠ | `operator_partial` | 25% | 1 / 3 | 7.5 | 3×hand | nano→micro→macro | 1 pass |
| [glass_of_water_spectral](#glass_of_water_spectral) | **G** | `configuration_or_transport` | — | 0 / 0 | 0.0 | — | — | none recorded |
| [glass_of_water_varied](#glass_of_water_varied) | **G** | `configuration_or_transport` | — | 0 / 0 | 0.0 | — | — | 1 pass |
| [h2o_bulk_water](#h2o_bulk_water) | **E** | `reference_only` | 0% | 0 / 3 | 8.2 | — | — | 1 pass |
| [h2o_cluster_fluid](#h2o_cluster_fluid) | **E** | `reference_only` | — | 0 / 0 | 2.3 | — | — | 1 pass |
| [h2o_diffusion_temperature](#h2o_diffusion_temperature) | **E** | `reference_only` | 0% | 0 / 3 | 4.8 | — | — | 1 pass |
| [h2o_fluid](#h2o_fluid) | **G** | `configuration_or_transport` | — | 0 / 0 | 0.0 | — | — | 1 pass |
| [h2o_molecule_stability](#h2o_molecule_stability) | **E** | `reference_only` | — | 0 / 0 | 3.2 | — | — | 1 pass |
| [h2o_optics_beam](#h2o_optics_beam) | **G** | `configuration_or_transport` | — | 0 / 0 | 0.0 | — | — | none recorded |
| [h2o_single_molecule](#h2o_single_molecule) | **G** | `configuration_or_transport` | — | 0 / 0 | 0.0 | — | — | none recorded |
| [hello_world](#hello_world) | **G** | `no_active_material_law` | — | 0 / 0 | 0.0 | — | — | none recorded |
| [lava_lamp](#lava_lamp) | **C** ⚠ | `operator_partial` | 12% | 1 / 7 | 6.7 | 2×hand | nano→macro | 1 pass |
| [molecular_01_ethane](#molecular_01_ethane) | **B** | `configuration_or_transport` | 60% | 3 / 2 | 14.0 | 2×G4 6×dist | atomic→nano | none recorded |
| [molecular_02_ethanol](#molecular_02_ethanol) | **B** | `configuration_or_transport` | 60% | 3 / 2 | 14.0 | 2×G4 6×dist | atomic→nano | none recorded |
| [molecular_03_formamide](#molecular_03_formamide) | **B** | `configuration_or_transport` | 60% | 3 / 2 | 14.0 | 2×G4 6×dist | atomic→nano | none recorded |
| [molecular_04_butane](#molecular_04_butane) | **B** | `configuration_or_transport` | 60% | 3 / 2 | 14.0 | 2×G4 6×dist | atomic→nano | none recorded |
| [molecular_05_dimethyl_ether](#molecular_05_dimethyl_ether) | **B** | `configuration_or_transport` | 60% | 3 / 2 | 14.0 | 2×G4 6×dist | atomic→nano | none recorded |
| [molecular_06_acetamide](#molecular_06_acetamide) | **B** | `configuration_or_transport` | 60% | 3 / 2 | 14.0 | 2×G4 6×dist | atomic→nano | none recorded |
| [molecular_series](#molecular_series) | **B** | `no_active_material_law` | 60% | 3 / 2 | 14.1 | 2×G4 6×dist | atomic→nano | none recorded |
| [nacl_dehydration_reference](#nacl_dehydration_reference) | **R** | `reference_only` | — | 0 / 0 | 0.0 | — | — | none recorded |
| [optics_surrogate_demo](#optics_surrogate_demo) | **G** | `configuration_or_transport` | — | 0 / 0 | 0.0 | 1×anchor | — | 1 pass |
| [optics_training_panel](#optics_training_panel) | **G** | `configuration_or_transport` | — | 0 / 0 | 0.0 | — | — | none recorded |
| [particle_observer_cascade](#particle_observer_cascade) | **A** | `no_active_material_law` | 60% | 3 / 2 | 0.0 | 3×G4 | atomic→nano→meso | none recorded |
| [polyurethane_foam](#polyurethane_foam) | **C** ⚠ | `operator_partial` | 50% | 3 / 3 | 4.9 | 2×dist 2×hand | nano→meso→macro | 2 pass |
| [spectrum_prediction](#spectrum_prediction) | **M** ⚠ | `no_active_material_law` | 100% | 2 / 0 | 0.0 | — | atomic→nano | none recorded |
| [surrogate_generic_demo](#surrogate_generic_demo) | **B** | `no_active_material_law` | 100% | 2 / 0 | 0.0 | 1×anchor | atomic | 1 pass |
| [testscenario_efflux](#testscenario_efflux) | **B** | `operator_backed` | 50% | 2 / 2 | 1.9 | 2×dist | micro | 2 pass |
| [testscenario_h2o_electrolysis_combustion](#testscenario_h2o_electrolysis_combustion) | **B** | `operator_backed` | 25% | 1 / 3 | 5.8 | 1×dist | meso | 2 pass |
| [testscenario_magnetic_resonance](#testscenario_magnetic_resonance) | **E** | `reference_only` | 0% | 0 / 4 | 1.9 | — | — | 1 pass |
| [testscenario_magnetic_resonance_brain](#testscenario_magnetic_resonance_brain) | **E** | `reference_only` | — | 0 / 0 | 0.0 | — | — | 1 pass |
| [testscenario_magnetic_resonance_imaging](#testscenario_magnetic_resonance_imaging) | **E** | `reference_only` | 0% | 0 / 1 | 2.2 | — | — | 1 pass |
| [testscenario_magnetic_resonance_tissues](#testscenario_magnetic_resonance_tissues) | **E** | `reference_only` | — | 0 / 0 | 0.0 | — | — | 1 pass |
| [testscenario_osmotic](#testscenario_osmotic) | **E** | `reference_only` | — | 0 / 0 | 1.7 | — | — | 1 pass |
| [testscenario_pascal](#testscenario_pascal) | **E** | `reference_only` | — | 0 / 0 | 2.9 | — | — | 1 pass |
| [validation_glass_of_water](#validation_glass_of_water) | **G** | `configuration_or_transport` | — | 0 / 0 | 0.0 | — | — | none recorded |
| [viz_refraction_demo](#viz_refraction_demo) | **G** | `configuration_or_transport` | — | 0 / 0 | 0.0 | — | — | 4 info, 11 pass |
| [water_box](#water_box) | **G** | `configuration_or_transport` | — | 0 / 0 | 0.0 | — | — | none recorded |
| [water_salt_recipe](#water_salt_recipe) | **G** | `no_active_material_law` | 0% | 0 / 1 | 1.6 | — | — | none recorded |

## Scenarios

### aerodynamics_reference

**Grade R — Independent comparison reference** · entry [`examples/scenarios/aerodynamics_reference/aerodynamics_reference.js`](../examples/scenarios/aerodynamics_reference/aerodynamics_reference.js)

> Independent Euler comparison for a fixed blunt body; not a Geant4 aero prediction.

**Purity**

- Status: ledger `reference_only`, companion `reference_only`.
- Authored residual still forcing behaviour: Independent ideal-gas Euler comparison only. Exact periodic entropy/shear grid/CFL verification exists; obstacle/shock/acoustic accuracy, external anchors with uncertainty, particle-derived aerodynamic scale lift, thermal coupling and structural failure remain unavailable.
- Ledger note: The reference solver is explicitly separate from Geant4 transport and must not become a synthetic training truth. Future learned behaviour needs its own validated path.
- Inference sites: 0 · law-shaped math: 0 · inference share: —
- Embedded coefficients: 0 in 162 code lines (0.0/100) · top-level literals: 6 · geometry math: 0
- Geant4 fact reads: 1 · seeded RNG draws: 0 · hooks: yes
- Comparison-only (excluded): modules `js/trech_euler3d_reference.js`
- Inherited from modules: `js/trech_euler3d_reference.js` — 0 inference / 0 law-shaped / 0 coefficients
- Utility/data includes (not counted): `js/trech_helpers.js`, `js/trech_math.js`, `js/trech_random.js`, `js/trech_material_facts.js`

**Performance**

- No case in the committed validation report runs this bundle.

### analytic_beer_lambert

**Grade V — Analytic cross-check** · entry [`examples/scenarios/analytic_beer_lambert/analytic_beer_lambert.js`](../examples/scenarios/analytic_beer_lambert/analytic_beer_lambert.js)

> Analytic cross-check scenario: Beer-Lambert photon attenuation.

**Purity**

- Status: ledger `—`, companion `configuration_or_transport`.
- Inference sites: 0 · law-shaped math: 0 · inference share: —
- Embedded coefficients: 0 in 42 code lines (0.0/100) · top-level literals: 6 · geometry math: 0
- Geant4 fact reads: 0 · seeded RNG draws: 0 · hooks: no

**Performance**

- `analytic_beer_lambert_cross_check` — **pass**: 1 check(s), worst rel_err=1.13%, all_within_tolerance=True
- `system_event_edep_shape_consistent` — **pass**: n=20000 min=0 max=0.1 zero=0.4322 (uncollided 8433/20000) skew=2.595410472819898 kurt=9.00789684629253
- `system_event_histogram_consistent` — **pass**: n=20000 edep bins=47 zero=8644 under=0 over=0 fullest [0.02512, 0.03162) MeV x1874; secondaries bins=9 over=0 (species with non-zero bins: electron); track length bins=9 over=0
- `system_event_multiplicity_consistent` — **pass**: n=20000 secondaries mean=0.8718 (electron=0.8718) max=8 zero=0.4341 (uncollided 8433/20000, photoelectric 213) dispersion=1.164 track length mean=190.4 mm

### analytic_compton_transfer

**Grade V — Analytic cross-check** · entry [`examples/scenarios/analytic_compton_transfer/analytic_compton_transfer.js`](../examples/scenarios/analytic_compton_transfer/analytic_compton_transfer.js)

> Analytic cross-check scenario: Klein-Nishina Compton energy transfer and edge.

**Purity**

- Status: ledger `—`, companion `configuration_or_transport`.
- Inference sites: 0 · law-shaped math: 0 · inference share: —
- Embedded coefficients: 0 in 41 code lines (0.0/100) · top-level literals: 6 · geometry math: 0
- Geant4 fact reads: 0 · seeded RNG draws: 0 · hooks: no

**Performance**

- `analytic_compton_transfer_cross_check` — **pass**: 1 check(s), worst rel_err=0.26%, all_ok=True

### analytic_csda_range

**Grade V — Analytic cross-check** · entry [`examples/scenarios/analytic_csda_range/analytic_csda_range.js`](../examples/scenarios/analytic_csda_range/analytic_csda_range.js)

> Analytic cross-check scenario: charged-particle CSDA range.

**Purity**

- Status: ledger `—`, companion `configuration_or_transport`.
- Inference sites: 0 · law-shaped math: 0 · inference share: —
- Embedded coefficients: 0 in 42 code lines (0.0/100) · top-level literals: 6 · geometry math: 0
- Geant4 fact reads: 0 · seeded RNG draws: 0 · hooks: no

**Performance**

- `analytic_csda_range_cross_check` — **pass**: 1 check(s), worst rel_err=0.38%, contained=True, all_within_tolerance=True

### analytic_pair_production

**Grade V — Analytic cross-check** · entry [`examples/scenarios/analytic_pair_production/analytic_pair_production.js`](../examples/scenarios/analytic_pair_production/analytic_pair_production.js)

> Analytic cross-check scenario: pair-production and photonuclear branching fractions, the 2 m_e c^2 threshold and the oxygen giant-dipole resonance.

**Purity**

- Status: ledger `—`, companion `configuration_or_transport`.
- Declared limitations: Self-consistency of Geant4 process selection against its own conversion and photonuclear cross sections (photonuclear absorption is part of mu_total); not an independent XCOM/IAEA comparison.
- Inference sites: 0 · law-shaped math: 0 · inference share: —
- Embedded coefficients: 0 in 51 code lines (0.0/100) · top-level literals: 5 · geometry math: 0
- Geant4 fact reads: 0 · seeded RNG draws: 0 · hooks: no

**Performance**

- `analytic_pair_fraction_cross_check` — **pass**: rel_err=1.12%, z=+0.83, within_tolerance=True
- `analytic_pair_fraction_energy_sweep` — **pass**: 8/8 energies, threshold_zero=True, increasing=True, span=413.1x, all_ok=True
- `analytic_photonuclear_final_state` — **pass**: 3 graded energies, all_ok=True
- `analytic_photonuclear_fraction_giant_dipole` — **pass**: 5/5 energies, zero_points=2, peak=23000 keV (0.0501), all_ok=True
- `analytic_photonuclear_model_comparison` — **pass**: 3 paired energies, all_ok=True

### analytic_photo_fraction

**Grade V — Analytic cross-check** · entry [`examples/scenarios/analytic_photo_fraction/analytic_photo_fraction.js`](../examples/scenarios/analytic_photo_fraction/analytic_photo_fraction.js)

> Analytic cross-check scenario: photoelectric process-branching fraction.

**Purity**

- Status: ledger `—`, companion `configuration_or_transport`.
- Inference sites: 0 · law-shaped math: 0 · inference share: —
- Embedded coefficients: 0 in 41 code lines (0.0/100) · top-level literals: 5 · geometry math: 0
- Geant4 fact reads: 0 · seeded RNG draws: 0 · hooks: no

**Performance**

- `analytic_photo_fraction_cross_check` — **pass**: 1 check(s), worst rel_err=0.59%, all_within_tolerance=True
- `analytic_photo_fraction_energy_sweep` — **pass**: 5/5 energies, decreasing=True, span=57.4x, all_ok=True

### beaker_water_n_pentane

**Grade C — Partially operator-backed** · entry [`examples/scenarios/beaker_water_n_pentane/beaker_water_n_pentane.js`](../examples/scenarios/beaker_water_n_pentane/beaker_water_n_pentane.js)

> Water + n-pentane poured into an open beaker at 30 C, observed for 60 minutes.

**Purity**

- Status: ledger `operator_partial`, companion `operator_partial`.
- Authored residual still forcing behaviour: time-resolved evaporation/dissolution/phase-transfer operator
- Inference sites: 1 (`cascade` 1) · law-shaped math: 1 · inference share: 50%
- Embedded coefficients: 19 in 378 code lines (5.0/100) · top-level literals: 13 · geometry math: 15
- Geant4 fact reads: 6 · seeded RNG draws: 0 · hooks: yes
- Utility/data includes (not counted): `js/trech_helpers.js`, `js/trech_math.js`, `js/trech_random.js`, `js/trech_material_facts.js`
- Scale bands reached by declared models: nano → macro

**Models**

| Normal-path model | Origin | Scale | Held-out R² (min) | n |
| --- | --- | --- | --- | --- |
| [`data/beaker_cascade/macro_beaker_behavior.json`](../data/beaker_cascade/macro_beaker_behavior.json) | hand-authored response surface | macro | — | — |
| [`data/beaker_cascade/nano_pair_descriptors.json`](../data/beaker_cascade/nano_pair_descriptors.json) | hand-authored response surface | nano | — | — |

**Performance**

- `beaker_water_n_pentane_inference` — **pass**: checks=11/11 pentane_top=True evaporated=14.0% (4.38 g/60 min) heldout_Pvap=87.17 kPa

**Review flags**

- ⚠ 2 normal-path model(s) are hand-authored response surfaces, not trained

### beaker_water_n_pentane_studio

**Grade M — Inference mechanism demo** · entry [`examples/scenarios/beaker_water_n_pentane_studio/beaker_water_n_pentane_studio.js`](../examples/scenarios/beaker_water_n_pentane_studio/beaker_water_n_pentane_studio.js)

> Studio reference wrapper for beaker_water_n_pentane.js.

**Purity**

- Status: ledger `—`, companion `configuration_or_transport`.
- Inference sites: 1 (`cascade` 1) · law-shaped math: 1 · inference share: 50%
- Embedded coefficients: 19 in 379 code lines (5.0/100) · top-level literals: 13 · geometry math: 15
- Geant4 fact reads: 6 · seeded RNG draws: 0 · hooks: no
- Inherited from modules: `examples/scenarios/beaker_water_n_pentane/beaker_water_n_pentane.js` — 1 inference / 1 law-shaped / 19 coefficients
- Utility/data includes (not counted): `js/trech_helpers.js`, `js/trech_math.js`, `js/trech_random.js`, `js/trech_material_facts.js`
- Scale bands reached by declared models: nano → macro

**Models**

| Normal-path model | Origin | Scale | Held-out R² (min) | n |
| --- | --- | --- | --- | --- |
| [`data/beaker_cascade/macro_beaker_behavior.json`](../data/beaker_cascade/macro_beaker_behavior.json) | hand-authored response surface | macro | — | — |
| [`data/beaker_cascade/nano_pair_descriptors.json`](../data/beaker_cascade/nano_pair_descriptors.json) | hand-authored response surface | nano | — | — |

**Performance**

- No case in the committed validation report runs this bundle.

### briggs_rauscher_oscillator

**Grade D — Authored law, inferred coefficients** · entry [`examples/scenarios/briggs_rauscher_oscillator/briggs_rauscher_oscillator.js`](../examples/scenarios/briggs_rauscher_oscillator/briggs_rauscher_oscillator.js)

> The Briggs-Rauscher oscillating reaction, observed in an open beaker.

**Purity**

- Status: ledger `reference_only`, companion `reference_only`.
- Authored residual still forcing behaviour: six-state oscillatory reaction evolution
- Inference sites: 1 (`cascade` 1) · law-shaped math: 2 · inference share: 33%
- Embedded coefficients: 43 in 419 code lines (10.3/100) · top-level literals: 39 · geometry math: 3
- Geant4 fact reads: 6 · seeded RNG draws: 0 · hooks: yes
- Utility/data includes (not counted): `js/trech_helpers.js`, `js/trech_math.js`, `js/trech_random.js`, `js/trech_material_facts.js`
- Scale bands reached by declared models: nano → macro

**Models**

| Normal-path model | Origin | Scale | Held-out R² (min) | n |
| --- | --- | --- | --- | --- |
| [`data/briggs_rauscher_cascade/macro_oscillator_response.json`](../data/briggs_rauscher_cascade/macro_oscillator_response.json) | hand-authored response surface | macro | — | — |
| [`data/briggs_rauscher_cascade/nano_reagent_descriptors.json`](../data/briggs_rauscher_cascade/nano_reagent_descriptors.json) | hand-authored response surface | nano | — | — |

**Performance**

- `briggs_rauscher_oscillation` — **pass**: checks=10/10 cycles=8 (colourless->amber->deep-blue) period=10.5s then settles; inferred f=1.05 eps=0.14 sigma=0.12

**Review flags**

- ⚠ 2 normal-path model(s) are hand-authored response surfaces, not trained

### cascade_multiscale_demo

**Grade M — Inference mechanism demo** · entry [`examples/scenarios/cascade_multiscale_demo/cascade_multiscale_demo.js`](../examples/scenarios/cascade_multiscale_demo/cascade_multiscale_demo.js)

> Multi-scale inference cascade demo: ctx.cascade chains scale-tagged models from the Geant4 particle/nano base up to an observer-scale number in ONE deterministic pass, WITHOUT the scenario hand-wiring "call A, feed B".

**Purity**

- Status: ledger `no_active_material_law`, companion `no_active_material_law`.
- Inference sites: 1 (`cascade` 1; 1 auto-seeded `cascade()`) · law-shaped math: 0 · inference share: 100%
- Embedded coefficients: 0 in 40 code lines (0.0/100) · top-level literals: 1 · geometry math: 0
- Geant4 fact reads: 1 · seeded RNG draws: 0 · hooks: yes
- Scale bands reached by declared models: nano → meso

**Models**

| Normal-path model | Origin | Scale | Held-out R² (min) | n |
| --- | --- | --- | --- | --- |
| [`data/cascade_demo/meso_response.json`](../data/cascade_demo/meso_response.json) | hand-authored response surface | meso | — | — |
| [`data/cascade_demo/nano_ionization.json`](../data/cascade_demo/nano_ionization.json) | hand-authored response surface | nano | — | — |

**Performance**

- No case in the committed validation report runs this bundle.

### chemistry_atomic_levels_reference

**Grade A — Geant4-learned** · entry [`examples/scenarios/chemistry_atomic_levels_reference/chemistry_atomic_levels_reference.js`](../examples/scenarios/chemistry_atomic_levels_reference/chemistry_atomic_levels_reference.js)

> Closed-shell atom reference: computed occupied-energy groups, not fixed shell radii.

**Purity**

- Status: ledger `—`, companion `configuration_or_transport`.
- Inference sites: 3 (`cascade` 1, `evolve` 1, `react` 1) · law-shaped math: 2 · inference share: 60%
- Embedded coefficients: 2 in 528 code lines (0.4/100) · top-level literals: 0 · geometry math: 0
- Geant4 fact reads: 7 · seeded RNG draws: 0 · hooks: no
- Inherited from modules: `examples/scenarios/chemistry_mode/chemistry_mode.js`, `js/trech_molecular_particle.js`, `js/trech_chemistry.js`, `js/trech_chemistry_scene.js` — 3 inference / 2 law-shaped / 2 coefficients
- Utility/data includes (not counted): `js/trech_helpers.js`, `js/trech_math.js`, `js/trech_random.js`, `js/trech_material_facts.js`, `data/molecular_series/series.js`, `data/particle_molecule/response.js`
- Runtime-supplied model paths: 1 (chosen by parameters at run time; not graded)
- Scale bands reached by declared models: atomic → nano

**Models**

| Normal-path model | Origin | Scale | Held-out R² (min) | n |
| --- | --- | --- | --- | --- |
| [`data/particle_molecule/atomic_response.json`](../data/particle_molecule/atomic_response.json) | Geant4-trained | atomic | 1.0000 | 96 |
| [`data/particle_molecule/molecular_response.json`](../data/particle_molecule/molecular_response.json) | Geant4-trained | nano | 1.0000 | 144 |

**Performance**

- No case in the committed validation report runs this bundle.

### chemistry_mode

**Grade A — Geant4-learned** · entry [`examples/scenarios/chemistry_mode/chemistry_mode.js`](../examples/scenarios/chemistry_mode/chemistry_mode.js)

> Initial Chemistry workspace: authored molecular graph + live isotope-resolved Geant4 material response + bounded learned response. No imposed stability law.

**Purity**

- Status: ledger `operator_native`, companion `operator_native`.
- Ledger note: Authored structures and optional conserved inventories; supplied hazard models run in the engine. No built-in reaction/stability/valence law; transferable chemistry models and atomistic paths remain roadmap work. Particle response uses the shared Geant4-trained helper.
- Inference sites: 3 (`cascade` 1, `evolve` 1, `react` 1) · law-shaped math: 2 · inference share: 60%
- Embedded coefficients: 2 in 526 code lines (0.4/100) · top-level literals: 0 · geometry math: 0
- Geant4 fact reads: 7 · seeded RNG draws: 0 · hooks: yes
- Inherited from modules: `js/trech_molecular_particle.js`, `js/trech_chemistry.js`, `js/trech_chemistry_scene.js` — 2 inference / 2 law-shaped / 1 coefficients
- Utility/data includes (not counted): `js/trech_helpers.js`, `js/trech_math.js`, `js/trech_random.js`, `js/trech_material_facts.js`, `data/molecular_series/series.js`, `data/particle_molecule/response.js`
- Runtime-supplied model paths: 1 (chosen by parameters at run time; not graded)
- Scale bands reached by declared models: atomic → nano

**Models**

| Normal-path model | Origin | Scale | Held-out R² (min) | n |
| --- | --- | --- | --- | --- |
| [`data/particle_molecule/atomic_response.json`](../data/particle_molecule/atomic_response.json) | Geant4-trained | atomic | 1.0000 | 96 |
| [`data/particle_molecule/molecular_response.json`](../data/particle_molecule/molecular_response.json) | Geant4-trained | nano | 1.0000 | 144 |

**Performance**

- No case in the committed validation report runs this bundle.

### chemistry_probability_reference

**Grade A — Geant4-learned** · entry [`examples/scenarios/chemistry_probability_reference/chemistry_probability_reference.js`](../examples/scenarios/chemistry_probability_reference/chemistry_probability_reference.js)

> Joint electronic comparison and Geant4 nuclear initial-state ensembles. The approach is a declared parameter scan, not inferred dynamics.

**Purity**

- Status: ledger `—`, companion `configuration_or_transport`.
- Inference sites: 3 (`cascade` 1, `evolve` 1, `react` 1) · law-shaped math: 2 · inference share: 60%
- Embedded coefficients: 2 in 529 code lines (0.4/100) · top-level literals: 0 · geometry math: 0
- Geant4 fact reads: 7 · seeded RNG draws: 0 · hooks: no
- Inherited from modules: `examples/scenarios/chemistry_mode/chemistry_mode.js`, `js/trech_molecular_particle.js`, `js/trech_chemistry.js`, `js/trech_chemistry_scene.js` — 3 inference / 2 law-shaped / 2 coefficients
- Utility/data includes (not counted): `js/trech_helpers.js`, `js/trech_math.js`, `js/trech_random.js`, `js/trech_material_facts.js`, `data/molecular_series/series.js`, `data/particle_molecule/response.js`
- Runtime-supplied model paths: 1 (chosen by parameters at run time; not graded)
- Scale bands reached by declared models: atomic → nano

**Models**

| Normal-path model | Origin | Scale | Held-out R² (min) | n |
| --- | --- | --- | --- | --- |
| [`data/particle_molecule/atomic_response.json`](../data/particle_molecule/atomic_response.json) | Geant4-trained | atomic | 1.0000 | 96 |
| [`data/particle_molecule/molecular_response.json`](../data/particle_molecule/molecular_response.json) | Geant4-trained | nano | 1.0000 | 144 |

**Performance**

- No case in the committed validation report runs this bundle.

### cnt_band_structure

**Grade E — Authored forward law** · entry [`examples/scenarios/cnt_band_structure/cnt_band_structure.js`](../examples/scenarios/cnt_band_structure/cnt_band_structure.js)

> Vostok milestone (CNT parallel track): carbon-nanotube ELECTRONIC STRUCTURE.

**Purity**

- Status: ledger `reference_only`, companion `reference_only`.
- Authored residual still forcing behaviour: chirality-to-band-structure forward law
- Inference sites: 0 · law-shaped math: 0 · inference share: —
- Embedded coefficients: 14 in 292 code lines (4.8/100) · top-level literals: 8 · geometry math: 17
- Geant4 fact reads: 0 · seeded RNG draws: 0 · hooks: yes
- Utility/data includes (not counted): `js/trech_helpers.js`, `js/trech_math.js`, `js/trech_random.js`, `js/trech_material_facts.js`

**Performance**

- `cnt_band_structure` — **pass**: ok=True metallicity_rule=True primary_gap~1/d=True curvature~cos3theta/d2=True E_g*d=0.824eV*nm (meas 0.7-0.9) E_curv*d^2=0.050eV*nm^2 anchors<=1% warping=True kataura_margin(tb/meas)=0.067/0.137 12nominal-metal/14semi (gamma0=2.9eV)

### cnt_logic_gates

**Grade E — Authored forward law** · entry [`examples/scenarios/cnt_logic_gates/cnt_logic_gates.js`](../examples/scenarios/cnt_logic_gates/cnt_logic_gates.js)

> Vostok milestone (CNT parallel track): carbon-nanotube LOGIC GATES + CIRCUITS.

**Purity**

- Status: ledger `reference_only`, companion `reference_only`.
- Authored residual still forcing behaviour: CNTFET conductance and Fermi turn-on forward laws
- Inference sites: 0 · law-shaped math: 20 · inference share: 0%
- Embedded coefficients: 68 in 1013 code lines (6.7/100) · top-level literals: 23 · geometry math: 10
- Geant4 fact reads: 3 · seeded RNG draws: 0 · hooks: yes
- Utility/data includes (not counted): `js/trech_helpers.js`, `js/trech_math.js`, `js/trech_random.js`, `js/trech_material_facts.js`

**Performance**

- `cnt_logic_gates` — **pass**: ok=True gates=True half/full/2bit_adders=True/True/True margin_ok=True metallic_breaks=True SS=60.3mV/dec (ideal 59.5) on/off semi=3.33e+05 vs metal=1 g4_drive=True yield_ok=True purity_for_99pct_2bit_adder=0.9998995

### config_chemistry_stub

**Grade G — Geant4 transport / configuration** · entry [`examples/scenarios/config_chemistry_stub/config_chemistry_stub.js`](../examples/scenarios/config_chemistry_stub/config_chemistry_stub.js)

> config_chemistry_stub: configured gamma transport in water. Check completed output and the declared physics/inference scope.

**Purity**

- Status: ledger `—`, companion `configuration_or_transport`.
- Inference sites: 0 · law-shaped math: 0 · inference share: —
- Embedded coefficients: 0 in 30 code lines (0.0/100) · top-level literals: 4 · geometry math: 0
- Geant4 fact reads: 0 · seeded RNG draws: 0 · hooks: no
- Utility/data includes (not counted): `js/trech_helpers.js`, `js/trech_math.js`, `js/trech_random.js`, `js/trech_material_facts.js`

**Performance**

- No case in the committed validation report runs this bundle.

### config_cnt_optics_stub

**Grade G — Geant4 transport / configuration** · entry [`examples/scenarios/config_cnt_optics_stub/config_cnt_optics_stub.js`](../examples/scenarios/config_cnt_optics_stub/config_cnt_optics_stub.js)

> config_cnt_optics_stub: configured e- transport in G4_AIR. Check completed output and the declared physics/inference scope.

**Purity**

- Status: ledger `—`, companion `configuration_or_transport`.
- Inference sites: 0 · law-shaped math: 0 · inference share: —
- Embedded coefficients: 0 in 65 code lines (0.0/100) · top-level literals: 7 · geometry math: 0
- Geant4 fact reads: 0 · seeded RNG draws: 0 · hooks: no
- Utility/data includes (not counted): `js/trech_helpers.js`, `js/trech_math.js`, `js/trech_random.js`, `js/trech_material_facts.js`

**Performance**

- No case in the committed validation report runs this bundle.

### config_cnt_stub

**Grade G — Geant4 transport / configuration** · entry [`examples/scenarios/config_cnt_stub/config_cnt_stub.js`](../examples/scenarios/config_cnt_stub/config_cnt_stub.js)

> config_cnt_stub: configured e- transport in G4_AIR. Check completed output and the declared physics/inference scope.

**Purity**

- Status: ledger `—`, companion `configuration_or_transport`.
- Inference sites: 0 · law-shaped math: 0 · inference share: —
- Embedded coefficients: 0 in 81 code lines (0.0/100) · top-level literals: 7 · geometry math: 0
- Geant4 fact reads: 0 · seeded RNG draws: 0 · hooks: no
- Utility/data includes (not counted): `js/trech_helpers.js`, `js/trech_math.js`, `js/trech_random.js`, `js/trech_material_facts.js`

**Performance**

- No case in the committed validation report runs this bundle.

### config_cnt_world_stub

**Grade G — Geant4 transport / configuration** · entry [`examples/scenarios/config_cnt_world_stub/config_cnt_world_stub.js`](../examples/scenarios/config_cnt_world_stub/config_cnt_world_stub.js)

> config_cnt_world_stub: configured e- transport in G4_AIR. Check completed output and the declared physics/inference scope.

**Purity**

- Status: ledger `—`, companion `configuration_or_transport`.
- Inference sites: 0 · law-shaped math: 0 · inference share: —
- Embedded coefficients: 0 in 61 code lines (0.0/100) · top-level literals: 4 · geometry math: 0
- Geant4 fact reads: 0 · seeded RNG draws: 0 · hooks: no
- Utility/data includes (not counted): `js/trech_helpers.js`, `js/trech_math.js`, `js/trech_random.js`, `js/trech_material_facts.js`

**Performance**

- No case in the committed validation report runs this bundle.

### config_flow_language

**Grade G — Geant4 transport / configuration** · entry [`examples/scenarios/config_flow_language/config_flow_language.js`](../examples/scenarios/config_flow_language/config_flow_language.js)

> config_flow_language: configured e- transport in G4_AIR. Check completed output and the declared physics/inference scope.

**Purity**

- Status: ledger `—`, companion `configuration_or_transport`.
- Inference sites: 0 · law-shaped math: 0 · inference share: —
- Embedded coefficients: 0 in 68 code lines (0.0/100) · top-level literals: 9 · geometry math: 0
- Geant4 fact reads: 0 · seeded RNG draws: 0 · hooks: no
- Utility/data includes (not counted): `js/trech_helpers.js`, `js/trech_math.js`, `js/trech_random.js`, `js/trech_material_facts.js`

**Performance**

- No case in the committed validation report runs this bundle.

### config_hook_dispatch

**Grade G — Geant4 transport / configuration** · entry [`examples/scenarios/config_hook_dispatch/config_hook_dispatch.js`](../examples/scenarios/config_hook_dispatch/config_hook_dispatch.js)

> config_hook_dispatch: configured e- transport in G4_WATER. Check completed output and the declared physics/inference scope.

**Purity**

- Status: ledger `no_active_material_law`, companion `no_active_material_law`.
- Inference sites: 0 · law-shaped math: 0 · inference share: —
- Embedded coefficients: 0 in 51 code lines (0.0/100) · top-level literals: 1 · geometry math: 0
- Geant4 fact reads: 3 · seeded RNG draws: 0 · hooks: yes

**Performance**

- No case in the committed validation report runs this bundle.

### config_multi_beam_units

**Grade G — Geant4 transport / configuration** · entry [`examples/scenarios/config_multi_beam_units/config_multi_beam_units.js`](../examples/scenarios/config_multi_beam_units/config_multi_beam_units.js)

> config_multi_beam_units: configured particle transport in G4_AIR. Check completed output and the declared physics/inference scope.

**Purity**

- Status: ledger `—`, companion `configuration_or_transport`.
- Inference sites: 0 · law-shaped math: 0 · inference share: —
- Embedded coefficients: 0 in 46 code lines (0.0/100) · top-level literals: 7 · geometry math: 0
- Geant4 fact reads: 0 · seeded RNG draws: 0 · hooks: no
- Utility/data includes (not counted): `js/trech_helpers.js`, `js/trech_math.js`, `js/trech_random.js`, `js/trech_material_facts.js`

**Performance**

- No case in the committed validation report runs this bundle.

### config_multiscale_stub

**Grade G — Geant4 transport / configuration** · entry [`examples/scenarios/config_multiscale_stub/config_multiscale_stub.js`](../examples/scenarios/config_multiscale_stub/config_multiscale_stub.js)

> config_multiscale_stub: configured e- transport in G4_WATER. Check completed output and the declared physics/inference scope.

**Purity**

- Status: ledger `—`, companion `configuration_or_transport`.
- Inference sites: 0 · law-shaped math: 0 · inference share: —
- Embedded coefficients: 0 in 11 code lines (0.0/100) · top-level literals: 1 · geometry math: 0
- Geant4 fact reads: 0 · seeded RNG draws: 0 · hooks: no

**Performance**

- No case in the committed validation report runs this bundle.

### config_nitrogen_carbon_cycle

**Grade G — Geant4 transport / configuration** · entry [`examples/scenarios/config_nitrogen_carbon_cycle/config_nitrogen_carbon_cycle.js`](../examples/scenarios/config_nitrogen_carbon_cycle/config_nitrogen_carbon_cycle.js)

> config_nitrogen_carbon_cycle: configured neutron transport in nitrogen_gas. Check completed output and the declared physics/inference scope.

**Purity**

- Status: ledger `—`, companion `configuration_or_transport`.
- Inference sites: 0 · law-shaped math: 0 · inference share: —
- Embedded coefficients: 0 in 95 code lines (0.0/100) · top-level literals: 9 · geometry math: 1
- Geant4 fact reads: 0 · seeded RNG draws: 0 · hooks: no
- Utility/data includes (not counted): `js/trech_helpers.js`, `js/trech_math.js`, `js/trech_random.js`, `js/trech_material_facts.js`

**Performance**

- `nuclear_cycle_conservation` — **pass**: 1 cycles all conserve baryon/charge
- `nuclear_cycle_q_value_closure` — **pass**: worst \|Qf+Qb\| = 0.782 MeV (tolerance 1 MeV)

### config_optics

**Grade G — Geant4 transport / configuration** · entry [`examples/scenarios/config_optics/config_optics.js`](../examples/scenarios/config_optics/config_optics.js)

> config_optics: configured gamma transport in G4_AIR. Check completed output and the declared physics/inference scope.

**Purity**

- Status: ledger `—`, companion `configuration_or_transport`.
- Inference sites: 0 · law-shaped math: 0 · inference share: —
- Embedded coefficients: 0 in 45 code lines (0.0/100) · top-level literals: 14 · geometry math: 0
- Geant4 fact reads: 0 · seeded RNG draws: 0 · hooks: no
- Utility/data includes (not counted): `js/trech_helpers.js`, `js/trech_math.js`, `js/trech_random.js`, `js/trech_material_facts.js`

**Performance**

- No case in the committed validation report runs this bundle.

### config_stratify

**Grade G — Geant4 transport / configuration** · entry [`examples/scenarios/config_stratify/config_stratify.js`](../examples/scenarios/config_stratify/config_stratify.js)

> config_stratify: configured e- transport in G4_WATER. Check completed output and the declared physics/inference scope.

**Purity**

- Status: ledger `—`, companion `configuration_or_transport`.
- Inference sites: 0 · law-shaped math: 0 · inference share: —
- Embedded coefficients: 0 in 18 code lines (0.0/100) · top-level literals: 3 · geometry math: 0
- Geant4 fact reads: 0 · seeded RNG draws: 0 · hooks: no

**Performance**

- No case in the committed validation report runs this bundle.

### config_stratify_ml

**Grade G — Geant4 transport / configuration** · entry [`examples/scenarios/config_stratify_ml/config_stratify_ml.js`](../examples/scenarios/config_stratify_ml/config_stratify_ml.js)

> config_stratify_ml: configured e- transport in G4_WATER. Check completed output and the declared physics/inference scope.

**Purity**

- Status: ledger `—`, companion `configuration_or_transport`.
- Inference sites: 0 · law-shaped math: 0 · inference share: —
- Embedded coefficients: 0 in 25 code lines (0.0/100) · top-level literals: 5 · geometry math: 0
- Geant4 fact reads: 0 · seeded RNG draws: 0 · hooks: no

**Performance**

- No case in the committed validation report runs this bundle.

### elephants_toothpaste

**Grade D — Authored law, inferred coefficients** · entry [`examples/scenarios/elephants_toothpaste/elephants_toothpaste.js`](../examples/scenarios/elephants_toothpaste/elephants_toothpaste.js)

> Elephant's toothpaste ("the soapy lather"), observed in a graduated cylinder.

**Purity**

- Status: ledger `reference_only`, companion `reference_only`.
- Authored residual still forcing behaviour: catalytic reaction, heat, trapping and foam-drainage evolution
- Inference sites: 1 (`cascade` 1) · law-shaped math: 3 · inference share: 25%
- Embedded coefficients: 18 in 488 code lines (3.7/100) · top-level literals: 44 · geometry math: 8
- Geant4 fact reads: 10 · seeded RNG draws: 0 · hooks: yes
- Utility/data includes (not counted): `js/trech_helpers.js`, `js/trech_math.js`, `js/trech_random.js`, `js/trech_material_facts.js`
- Scale bands reached by declared models: nano → macro

**Models**

| Normal-path model | Origin | Scale | Held-out R² (min) | n |
| --- | --- | --- | --- | --- |
| [`data/elephants_toothpaste_cascade/macro_eruption_response.json`](../data/elephants_toothpaste_cascade/macro_eruption_response.json) | hand-authored response surface | macro | — | — |
| [`data/elephants_toothpaste_cascade/nano_reagent_descriptors.json`](../data/elephants_toothpaste_cascade/nano_reagent_descriptors.json) | hand-authored response surface | nano | — | — |

**Performance**

- `elephants_toothpaste_eruption` — **pass**: checks=16/16 acceleration=8.03e+04x t90=9.7067s peak_foam=18.4x peakT=369K (steaming) retention=74% (soft lather, never solid)

**Review flags**

- ⚠ 2 normal-path model(s) are hand-authored response surfaces, not trained

### geometry_procedural_assembly

**Grade G — Geant4 transport / configuration** · entry [`examples/scenarios/geometry_procedural_assembly/geometry_procedural_assembly.js`](../examples/scenarios/geometry_procedural_assembly/geometry_procedural_assembly.js)

> geometry_procedural_assembly: 1.25 MeV gamma transport through a TRECH_GEOMETRY-generated layer stack, dosimeter grid and NaI ring. Checks the generated volumes are built and scored without substitution and the onStep step-detail tally covers every event.

**Purity**

- Status: ledger `no_active_material_law`, companion `configuration_or_transport`.
- Declared limitations: Procedural authoring and Geant4 transport only; the first-interaction tally is bookkeeping of Geant4 steps, not a physics model. Rotated-volume overlap audit is conservative (axis-aligned bounds).
- Ledger note: TRECH_GEOMETRY-generated apparatus; the onStep first-interaction tally is bookkeeping of Geant4 steps, not a material law.
- Inference sites: 0 · law-shaped math: 0 · inference share: —
- Embedded coefficients: 0 in 95 code lines (0.0/100) · top-level literals: 15 · geometry math: 0
- Geant4 fact reads: 1 · seeded RNG draws: 0 · hooks: yes
- Utility/data includes (not counted): `js/trech_geometry.js`

**Performance**

- `system_volume_event_edep_consistent` — **pass**: n=400 volumes=19 hit=9 scored sum=144.756 MeV of total 147.961 MeV; track length 89.7 of 363 mm/event; secondaries 0.835 of 0.8875/event
- Dedicated validator: [`tools/validation/trech_validation/declarative.py`](../tools/validation/trech_validation/declarative.py)

### glass_from_sand

**Grade B — Learned, not from Geant4** · entry [`examples/scenarios/glass_from_sand/glass_from_sand.js`](../examples/scenarios/glass_from_sand/glass_from_sand.js)

> Making glass: a material that does not exist when the run starts.

**Purity**

- Status: ledger `operator_backed`, companion `operator_backed`.
- Ledger note: Material-creation scenario. The default physics_source=operator runs the distilled trained per-material thermal/chemistry family (measured meso hull + independent holdout); the hand-authored illustrative family it was distilled from is reachable only with physics_source=reference and is the harvest/audit teacher. Cell-to-cell conduction deliberately stays in the reference family: its law is exactly linear in the temperature difference.
- Inference sites: 5 (`cascade` 1, `evolve` 2, `react` 1, `interact` 1) · law-shaped math: 0 · inference share: 100%
- Embedded coefficients: 7 in 867 code lines (0.8/100) · top-level literals: 25 · geometry math: 0
- Geant4 fact reads: 2 · seeded RNG draws: 0 · hooks: yes
- Comparison-only (excluded): functions `harvestTeacherRows`
- Utility/data includes (not counted): `js/trech_helpers.js`, `js/trech_math.js`, `js/trech_random.js`, `js/trech_material_facts.js`
- Runtime-supplied model paths: 1 (chosen by parameters at run time; not graded)
- Scale bands reached by declared models: nano → micro → meso → macro

**Models**

| Normal-path model | Origin | Scale | Held-out R² (min) | n |
| --- | --- | --- | --- | --- |
| [`data/glass_furnace_cascade/macro_furnace_response.json`](../data/glass_furnace_cascade/macro_furnace_response.json) | hand-authored response surface | macro | — | — |
| [`data/glass_furnace_cascade/nano_batch_material_response.json`](../data/glass_furnace_cascade/nano_batch_material_response.json) | hand-authored response surface | nano | — | — |
| [`data/glass_furnace_conduction_set/conduction_set_batch_solid.json`](../data/glass_furnace_conduction_set/conduction_set_batch_solid.json) | distilled from authored teacher | meso | 0.9998 | 14717 |
| [`data/glass_furnace_conduction_set/conduction_set_glass.json`](../data/glass_furnace_conduction_set/conduction_set_glass.json) | distilled from authored teacher | meso | 0.9999 | 5226 |
| [`data/glass_furnace_conduction_set/conduction_set_melt.json`](../data/glass_furnace_conduction_set/conduction_set_melt.json) | distilled from authored teacher | meso | 0.9997 | 5707 |
| [`data/glass_furnace_operators/conduction_batch_solid__batch_solid.json`](../data/glass_furnace_operators/conduction_batch_solid__batch_solid.json) | hand-authored response surface | micro | — | — |
| [`data/glass_furnace_operators/conduction_batch_solid__glass.json`](../data/glass_furnace_operators/conduction_batch_solid__glass.json) | hand-authored response surface | micro | — | — |
| [`data/glass_furnace_operators/conduction_batch_solid__melt.json`](../data/glass_furnace_operators/conduction_batch_solid__melt.json) | hand-authored response surface | micro | — | — |
| [`data/glass_furnace_operators/conduction_glass__glass.json`](../data/glass_furnace_operators/conduction_glass__glass.json) | hand-authored response surface | micro | — | — |
| [`data/glass_furnace_operators/conduction_glass__melt.json`](../data/glass_furnace_operators/conduction_glass__melt.json) | hand-authored response surface | micro | — | — |
| [`data/glass_furnace_operators/conduction_melt__melt.json`](../data/glass_furnace_operators/conduction_melt__melt.json) | hand-authored response surface | micro | — | — |
| [`data/glass_furnace_operators_trained/chemistry_batch_solid.json`](../data/glass_furnace_operators_trained/chemistry_batch_solid.json) | distilled from authored teacher | meso | 1.0000 | 2211 |
| [`data/glass_furnace_operators_trained/chemistry_melt.json`](../data/glass_furnace_operators_trained/chemistry_melt.json) | distilled from authored teacher | meso | 1.0000 | 757 |
| [`data/glass_furnace_operators_trained/thermal_batch_solid.json`](../data/glass_furnace_operators_trained/thermal_batch_solid.json) | distilled from authored teacher | meso | 1.0000 | 2211 |
| [`data/glass_furnace_operators_trained/thermal_glass.json`](../data/glass_furnace_operators_trained/thermal_glass.json) | distilled from authored teacher | meso | 1.0000 | 932 |
| [`data/glass_furnace_operators_trained/thermal_melt.json`](../data/glass_furnace_operators_trained/thermal_melt.json) | distilled from authored teacher | meso | 1.0000 | 757 |

Comparison/teacher models off the normal path: 5 (hand-authored response surface) in `data/glass_furnace_operators/`.

**Performance**

- `glass_from_sand_material_creation` — **pass**: checks=21/21 glass=648 units from 0 (first at tick 17, 10 mm) classes=3 pair_materials=5 inferences=551977
- `glass_operator_matches_reference` — **pass**: gap checks=8/8 trust=22/22
- `glass_set_conduction_matches_pair` — **pass**: checks=17/17 glass 648->648 units, mean T gap 0.977 K, net/moved heat 2.94e-03, set evaluations 129600

**Review flags**

- ⚠ 8 normal-path model(s) are hand-authored response surfaces, not trained

### glass_of_water_shaken

**Grade C — Partially operator-backed** · entry [`examples/scenarios/glass_of_water_shaken/glass_of_water_shaken.js`](../examples/scenarios/glass_of_water_shaken/glass_of_water_shaken.js)

> Sputnik / multi-scale-cascade CANONICAL demo: a GLASS OF WATER BEING SHAKEN.

**Purity**

- Status: ledger `operator_partial`, companion `operator_partial`.
- Authored residual still forcing behaviour: PBF neighbour pressure, viscosity and cohesion response
- Inference sites: 1 (`cascade` 1) · law-shaped math: 3 · inference share: 25%
- Embedded coefficients: 63 in 844 code lines (7.5/100) · top-level literals: 28 · geometry math: 34
- Geant4 fact reads: 0 · seeded RNG draws: 0 · hooks: yes
- Inherited from modules: `js/trech_water_md.js` — 0 inference / 3 law-shaped / 17 coefficients
- Utility/data includes (not counted): `js/trech_helpers.js`, `js/trech_math.js`, `js/trech_random.js`, `js/trech_material_facts.js`
- Scale bands reached by declared models: nano → micro → macro

**Models**

| Normal-path model | Origin | Scale | Held-out R² (min) | n |
| --- | --- | --- | --- | --- |
| [`data/glass_cascade/macro_fluid_params.json`](../data/glass_cascade/macro_fluid_params.json) | hand-authored response surface | macro | — | — |
| [`data/glass_cascade/micro_bulk.json`](../data/glass_cascade/micro_bulk.json) | hand-authored response surface | micro | — | — |
| [`data/glass_cascade/nano_coarse_grain.json`](../data/glass_cascade/nano_coarse_grain.json) | hand-authored response surface | nano | — | — |

**Performance**

- `glass_of_water_shaken_waves` — **pass**: ok=True poured=True waves=True splash=True contained=True stable=True particles=4301/4301 (~928g) scales=nano->micro->macro nano(coord=4.86, g(r)peak=2.77A) -> macro(rho=999.2 kg/m3 [0.10% vs 998], surf_tension=0.108, visc=0.054) still_level=7.8cm peak_wave=19.3mm peak_splash=35.5mm

**Review flags**

- ⚠ 3 normal-path model(s) are hand-authored response surfaces, not trained

### glass_of_water_spectral

**Grade G — Geant4 transport / configuration** · entry [`examples/scenarios/glass_of_water_spectral/glass_of_water_spectral.js`](../examples/scenarios/glass_of_water_spectral/glass_of_water_spectral.js)

> Chromatic-dispersion demo: a *white* (blackbody) source through the glass of water. Where glass_of_water_varied.js fires a narrow green band, this scenario fires the full visible spectrum, so each photon's wavelength is sampled across 380-750 nm and refracts at its OWN angle through the derived n(lambda) tables.

**Purity**

- Status: ledger `—`, companion `configuration_or_transport`.
- Inference sites: 0 · law-shaped math: 0 · inference share: —
- Embedded coefficients: 0 in 99 code lines (0.0/100) · top-level literals: 14 · geometry math: 2
- Geant4 fact reads: 0 · seeded RNG draws: 0 · hooks: no
- Utility/data includes (not counted): `js/trech_helpers.js`, `js/trech_math.js`, `js/trech_random.js`, `js/trech_material_facts.js`

**Performance**

- No case in the committed validation report runs this bundle.

### glass_of_water_varied

**Grade G — Geant4 transport / configuration** · entry [`examples/scenarios/glass_of_water_varied/glass_of_water_varied.js`](../examples/scenarios/glass_of_water_varied/glass_of_water_varied.js)

> Anti-degeneration demo scenario: the same glass-of-water optics as validation_glass_of_water.js, but with a *varied* source so the run samples a real distribution of photons instead of one repeated primary.

**Purity**

- Status: ledger `—`, companion `configuration_or_transport`.
- Inference sites: 0 · law-shaped math: 0 · inference share: —
- Embedded coefficients: 0 in 95 code lines (0.0/100) · top-level literals: 13 · geometry math: 2
- Geant4 fact reads: 0 · seeded RNG draws: 0 · hooks: no
- Utility/data includes (not counted): `js/trech_helpers.js`, `js/trech_math.js`, `js/trech_random.js`, `js/trech_material_facts.js`

**Performance**

- `sampling_diversity_non_degenerate` — **pass**: distinct_exit_points=798 incidence_stddev=0.753deg wavelength_stddev=22.73nm (degenerate baseline = 1 / 0 / 0)

### h2o_bulk_water

**Grade E — Authored forward law** · entry [`examples/scenarios/h2o_bulk_water/h2o_bulk_water.js`](../examples/scenarios/h2o_bulk_water/h2o_bulk_water.js)

> Sputnik "H2O fluid behavior", completed toward true BULK: the cluster (h2o_cluster_fluid.js) is a finite droplet with a surface; this is bulk liquid water in a PERIODIC box, so there is no surface and the structure can be compared to the measured liquid. The headline observable is the O-O radial distribution function g(r): real liquid water has a sharp first peak at ~2.8 A (the hydrogen-bond distance) and tetrahedral coordination ~4-4.5.

**Purity**

- Status: ledger `reference_only`, companion `reference_only`.
- Authored residual still forcing behaviour: SPC/E pair forces; SHAKE/RATTLE and integration are numerical prerequisites
- Inference sites: 0 · law-shaped math: 3 · inference share: 0%
- Embedded coefficients: 40 in 485 code lines (8.2/100) · top-level literals: 7 · geometry math: 20
- Geant4 fact reads: 0 · seeded RNG draws: 0 · hooks: yes
- Inherited from modules: `js/trech_water_md.js` — 0 inference / 3 law-shaped / 17 coefficients
- Utility/data includes (not counted): `js/trech_helpers.js`, `js/trech_math.js`, `js/trech_random.js`, `js/trech_material_facts.js`

**Performance**

- `h2o_bulk_water_structure` — **pass**: stable=True g(r)_first_peak=2.736A (exp 2.8) height=3.00 first_min=3.38A g=0.78 (exp ~0.75) second_peak=4.36A (exp ~4.5) coord#(3.4A)=4.73 coord#(own-min)=4.73 (exp ~4.3-4.7) rigid_held=True (maxviol=1.0e-08) D_self=2.57e-9 (Einstein) D_gk=2.79e-9 (Green-Kubo) m2/s (exp 2.3) mean_T=304.9K N=108

### h2o_cluster_fluid

**Grade E — Authored forward law** · entry [`examples/scenarios/h2o_cluster_fluid/h2o_cluster_fluid.js`](../examples/scenarios/h2o_cluster_fluid/h2o_cluster_fluid.js)

> Sputnik item: "Simulate H2O fluid behavior". Next step after the single stable molecule (h2o_molecule_stability.js): a small ENSEMBLE of water molecules that attract each other and settle into a stable, liquid-like hydrogen-bonded droplet at ~300 K -- emergent fluid behavior from molecular interactions, not one isolated molecule.

**Purity**

- Status: ledger `reference_only`, companion `reference_only`.
- Authored residual still forcing behaviour: flexible-water bond, angle and intermolecular force laws
- Inference sites: 0 · law-shaped math: 0 · inference share: —
- Embedded coefficients: 6 in 261 code lines (2.3/100) · top-level literals: 23 · geometry math: 17
- Geant4 fact reads: 0 · seeded RNG draws: 0 · hooks: yes
- Utility/data includes (not counted): `js/trech_helpers.js`, `js/trech_math.js`, `js/trech_random.js`, `js/trech_material_facts.js`

**Performance**

- `h2o_cluster_fluid_stable` — **pass**: stable=True molecules=8 mean_T=313.2K mean_hbonds=10.55 mean_Rg=2.924A max_Rg=3.209A

### h2o_diffusion_temperature

**Grade E — Authored forward law** · entry [`examples/scenarios/h2o_diffusion_temperature/h2o_diffusion_temperature.js`](../examples/scenarios/h2o_diffusion_temperature/h2o_diffusion_temperature.js)

> Sputnik "H2O fluid behavior" -- DYNAMICS, temperature dependence.

**Purity**

- Status: ledger `reference_only`, companion `reference_only`.
- Authored residual still forcing behaviour: shared SPC/E pair-force evolution
- Inference sites: 0 · law-shaped math: 3 · inference share: 0%
- Embedded coefficients: 21 in 442 code lines (4.8/100) · top-level literals: 29 · geometry math: 20
- Geant4 fact reads: 0 · seeded RNG draws: 0 · hooks: yes
- Inherited from modules: `js/trech_water_md.js` — 0 inference / 3 law-shaped / 17 coefficients
- Utility/data includes (not counted): `js/trech_helpers.js`, `js/trech_math.js`, `js/trech_random.js`, `js/trech_material_facts.js`

**Performance**

- `h2o_diffusion_temperature_trend` — **pass**: trend_ok=True monotonic=True D[1e-9 m2/s]@T: 281K:1.24(exp1.43) 297K:2.66(exp2.27) 313K:4.64(exp3.26) D-rise TRECH x3.74 vs exp x2.28

### h2o_fluid

**Grade G — Geant4 transport / configuration** · entry [`examples/scenarios/h2o_fluid/h2o_fluid.js`](../examples/scenarios/h2o_fluid/h2o_fluid.js)

> h2o_fluid: configured gamma transport in G4_AIR. Check completed output and the declared physics/inference scope.

**Purity**

- Status: ledger `—`, companion `configuration_or_transport`.
- Inference sites: 0 · law-shaped math: 0 · inference share: —
- Embedded coefficients: 0 in 81 code lines (0.0/100) · top-level literals: 10 · geometry math: 0
- Geant4 fact reads: 0 · seeded RNG draws: 0 · hooks: no
- Utility/data includes (not counted): `js/trech_helpers.js`, `js/trech_math.js`, `js/trech_random.js`, `js/trech_material_facts.js`

**Performance**

- `h2o_fluid_brine_run_closes` — **pass**: total_edep=12.6608 MeV brine(fluid_bulk)_edep=9.0651 MeV primaries emitted=50 transmitted=50 absorbed=0 (closes=True)

### h2o_molecule_stability

**Grade E — Authored forward law** · entry [`examples/scenarios/h2o_molecule_stability/h2o_molecule_stability.js`](../examples/scenarios/h2o_molecule_stability/h2o_molecule_stability.js)

> Sputnik north-star item: simulate a single H2O molecule and show that its bonds are STABLE OVER TIME -- it oscillates around its equilibrium geometry without "exploding" (atoms flying apart).

**Purity**

- Status: ledger `reference_only`, companion `reference_only`.
- Authored residual still forcing behaviour: flexible-water bond and angle force laws
- Inference sites: 0 · law-shaped math: 0 · inference share: —
- Embedded coefficients: 6 in 187 code lines (3.2/100) · top-level literals: 9 · geometry math: 9
- Geant4 fact reads: 0 · seeded RNG draws: 0 · hooks: yes
- Utility/data includes (not counted): `js/trech_helpers.js`, `js/trech_math.js`, `js/trech_random.js`, `js/trech_material_facts.js`

**Performance**

- `h2o_molecule_bonds_stable` — **pass**: stable=True mean_bond=0.9578A max_bond=1.1572A mean_angle=104.46deg energy_drift=0.459% (r0=0.9572A, theta0=104.52deg)

### h2o_optics_beam

**Grade G — Geant4 transport / configuration** · entry [`examples/scenarios/h2o_optics_beam/h2o_optics_beam.js`](../examples/scenarios/h2o_optics_beam/h2o_optics_beam.js)

> h2o_optics_beam: configured opticalphoton transport in G4_AIR. Check completed output and the declared physics/inference scope.

**Purity**

- Status: ledger `—`, companion `configuration_or_transport`.
- Inference sites: 0 · law-shaped math: 0 · inference share: —
- Embedded coefficients: 0 in 57 code lines (0.0/100) · top-level literals: 13 · geometry math: 0
- Geant4 fact reads: 0 · seeded RNG draws: 0 · hooks: no
- Utility/data includes (not counted): `js/trech_helpers.js`, `js/trech_math.js`, `js/trech_random.js`, `js/trech_material_facts.js`

**Performance**

- No case in the committed validation report runs this bundle.

### h2o_single_molecule

**Grade G — Geant4 transport / configuration** · entry [`examples/scenarios/h2o_single_molecule/h2o_single_molecule.js`](../examples/scenarios/h2o_single_molecule/h2o_single_molecule.js)

> h2o_single_molecule: configured e- transport in G4_AIR. Check completed output and the declared physics/inference scope.

**Purity**

- Status: ledger `—`, companion `configuration_or_transport`.
- Inference sites: 0 · law-shaped math: 0 · inference share: —
- Embedded coefficients: 0 in 74 code lines (0.0/100) · top-level literals: 14 · geometry math: 0
- Geant4 fact reads: 0 · seeded RNG draws: 0 · hooks: no
- Utility/data includes (not counted): `js/trech_helpers.js`, `js/trech_math.js`, `js/trech_random.js`, `js/trech_material_facts.js`

**Performance**

- No case in the committed validation report runs this bundle.

### hello_world

**Grade G — Geant4 transport / configuration** · entry [`examples/scenarios/hello_world/hello_world.js`](../examples/scenarios/hello_world/hello_world.js)

> hello_world: configured e- transport in G4_WATER. Check completed output and the declared physics/inference scope.

**Purity**

- Status: ledger `no_active_material_law`, companion `no_active_material_law`.
- Inference sites: 0 · law-shaped math: 0 · inference share: —
- Embedded coefficients: 0 in 11 code lines (0.0/100) · top-level literals: 0 · geometry math: 0
- Geant4 fact reads: 0 · seeded RNG draws: 0 · hooks: yes

**Performance**

- No case in the committed validation report runs this bundle.

### lava_lamp

**Grade C — Partially operator-backed** · entry [`examples/scenarios/lava_lamp/lava_lamp.js`](../examples/scenarios/lava_lamp/lava_lamp.js)

> A parameterized lava-lamp thermofluid scenario. Duration is an input, not an identity.

**Purity**

- Status: ledger `operator_partial`, companion `operator_partial`.
- Authored residual still forcing behaviour: thermal, phase, pair-interface and buoyancy/drag state evolution
- Inference sites: 1 (`cascade` 1) · law-shaped math: 7 · inference share: 12%
- Embedded coefficients: 63 in 939 code lines (6.7/100) · top-level literals: 40 · geometry math: 23
- Geant4 fact reads: 6 · seeded RNG draws: 0 · hooks: yes
- Utility/data includes (not counted): `js/trech_helpers.js`, `js/trech_math.js`, `js/trech_random.js`, `js/trech_material_facts.js`
- Scale bands reached by declared models: nano → macro

**Models**

| Normal-path model | Origin | Scale | Held-out R² (min) | n |
| --- | --- | --- | --- | --- |
| [`data/lava_lamp_cascade/macro_thermofluid_response.json`](../data/lava_lamp_cascade/macro_thermofluid_response.json) | hand-authored response surface | macro | — | — |
| [`data/lava_lamp_cascade/nano_material_response.json`](../data/lava_lamp_cascade/nano_material_response.json) | hand-authored response surface | nano | — | — |

**Performance**

- `lava_lamp_inferred_thermofluid` — **pass**: checks=23/23 duration=600s travel=159.9mm xy_path=123.0mm parcels=240 frames=121 readme=600s/100 ticks/101 unique

**Review flags**

- ⚠ 2 normal-path model(s) are hand-authored response surfaces, not trained

### molecular_01_ethane

**Grade B — Learned, not from Geant4** · entry [`examples/scenarios/molecular_01_ethane/molecular_01_ethane.js`](../examples/scenarios/molecular_01_ethane/molecular_01_ethane.js)

> Group 1: nonpolar control, C–C torsion.

**Purity**

- Status: ledger `—`, companion `configuration_or_transport`.
- Inference sites: 3 (`predict` 1, `cascade` 1, `evolve` 1) · law-shaped math: 2 · inference share: 60%
- Embedded coefficients: 32 in 229 code lines (14.0/100) · top-level literals: 6 · geometry math: 5
- Geant4 fact reads: 4 · seeded RNG draws: 0 · hooks: no
- Inherited from modules: `examples/scenarios/molecular_series/molecular_series.js`, `js/trech_molecular_particle.js` — 3 inference / 2 law-shaped / 32 coefficients
- Utility/data includes (not counted): `js/trech_helpers.js`, `js/trech_math.js`, `js/trech_random.js`, `js/trech_material_facts.js`, `data/molecular_series/series.js`, `data/particle_molecule/response.js`
- Scale bands reached by declared models: atomic → nano

**Models**

| Normal-path model | Origin | Scale | Held-out R² (min) | n |
| --- | --- | --- | --- | --- |
| [`data/molecular_series/acetamide.json`](../data/molecular_series/acetamide.json) | distilled from authored teacher | atomic | 1.0000 | 24 |
| [`data/molecular_series/butane.json`](../data/molecular_series/butane.json) | distilled from authored teacher | atomic | 1.0000 | 24 |
| [`data/molecular_series/dimethyl_ether.json`](../data/molecular_series/dimethyl_ether.json) | distilled from authored teacher | atomic | 0.9999 | 24 |
| [`data/molecular_series/ethane.json`](../data/molecular_series/ethane.json) | distilled from authored teacher | atomic | 1.0000 | 24 |
| [`data/molecular_series/ethanol.json`](../data/molecular_series/ethanol.json) | distilled from authored teacher | atomic | 1.0000 | 24 |
| [`data/molecular_series/formamide.json`](../data/molecular_series/formamide.json) | distilled from authored teacher | atomic | 1.0000 | 24 |
| [`data/particle_molecule/atomic_response.json`](../data/particle_molecule/atomic_response.json) | Geant4-trained | atomic | 1.0000 | 96 |
| [`data/particle_molecule/molecular_response.json`](../data/particle_molecule/molecular_response.json) | Geant4-trained | nano | 1.0000 | 144 |

**Performance**

- No case in the committed validation report runs this bundle.

### molecular_02_ethanol

**Grade B — Learned, not from Geant4** · entry [`examples/scenarios/molecular_02_ethanol/molecular_02_ethanol.js`](../examples/scenarios/molecular_02_ethanol/molecular_02_ethanol.js)

> Group 2: polar alcohol, C–O torsion and atom-integrated polarization.

**Purity**

- Status: ledger `—`, companion `configuration_or_transport`.
- Inference sites: 3 (`predict` 1, `cascade` 1, `evolve` 1) · law-shaped math: 2 · inference share: 60%
- Embedded coefficients: 32 in 229 code lines (14.0/100) · top-level literals: 6 · geometry math: 5
- Geant4 fact reads: 4 · seeded RNG draws: 0 · hooks: no
- Inherited from modules: `examples/scenarios/molecular_series/molecular_series.js`, `js/trech_molecular_particle.js` — 3 inference / 2 law-shaped / 32 coefficients
- Utility/data includes (not counted): `js/trech_helpers.js`, `js/trech_math.js`, `js/trech_random.js`, `js/trech_material_facts.js`, `data/molecular_series/series.js`, `data/particle_molecule/response.js`
- Scale bands reached by declared models: atomic → nano

**Models**

| Normal-path model | Origin | Scale | Held-out R² (min) | n |
| --- | --- | --- | --- | --- |
| [`data/molecular_series/acetamide.json`](../data/molecular_series/acetamide.json) | distilled from authored teacher | atomic | 1.0000 | 24 |
| [`data/molecular_series/butane.json`](../data/molecular_series/butane.json) | distilled from authored teacher | atomic | 1.0000 | 24 |
| [`data/molecular_series/dimethyl_ether.json`](../data/molecular_series/dimethyl_ether.json) | distilled from authored teacher | atomic | 0.9999 | 24 |
| [`data/molecular_series/ethane.json`](../data/molecular_series/ethane.json) | distilled from authored teacher | atomic | 1.0000 | 24 |
| [`data/molecular_series/ethanol.json`](../data/molecular_series/ethanol.json) | distilled from authored teacher | atomic | 1.0000 | 24 |
| [`data/molecular_series/formamide.json`](../data/molecular_series/formamide.json) | distilled from authored teacher | atomic | 1.0000 | 24 |
| [`data/particle_molecule/atomic_response.json`](../data/particle_molecule/atomic_response.json) | Geant4-trained | atomic | 1.0000 | 96 |
| [`data/particle_molecule/molecular_response.json`](../data/particle_molecule/molecular_response.json) | Geant4-trained | nano | 1.0000 | 144 |

**Performance**

- No case in the committed validation report runs this bundle.

### molecular_03_formamide

**Grade B — Learned, not from Geant4** · entry [`examples/scenarios/molecular_03_formamide/molecular_03_formamide.js`](../examples/scenarios/molecular_03_formamide/molecular_03_formamide.js)

> Group 3: restricted amide C–N torsion and charge redistribution.

**Purity**

- Status: ledger `—`, companion `configuration_or_transport`.
- Inference sites: 3 (`predict` 1, `cascade` 1, `evolve` 1) · law-shaped math: 2 · inference share: 60%
- Embedded coefficients: 32 in 229 code lines (14.0/100) · top-level literals: 6 · geometry math: 5
- Geant4 fact reads: 4 · seeded RNG draws: 0 · hooks: no
- Inherited from modules: `examples/scenarios/molecular_series/molecular_series.js`, `js/trech_molecular_particle.js` — 3 inference / 2 law-shaped / 32 coefficients
- Utility/data includes (not counted): `js/trech_helpers.js`, `js/trech_math.js`, `js/trech_random.js`, `js/trech_material_facts.js`, `data/molecular_series/series.js`, `data/particle_molecule/response.js`
- Scale bands reached by declared models: atomic → nano

**Models**

| Normal-path model | Origin | Scale | Held-out R² (min) | n |
| --- | --- | --- | --- | --- |
| [`data/molecular_series/acetamide.json`](../data/molecular_series/acetamide.json) | distilled from authored teacher | atomic | 1.0000 | 24 |
| [`data/molecular_series/butane.json`](../data/molecular_series/butane.json) | distilled from authored teacher | atomic | 1.0000 | 24 |
| [`data/molecular_series/dimethyl_ether.json`](../data/molecular_series/dimethyl_ether.json) | distilled from authored teacher | atomic | 0.9999 | 24 |
| [`data/molecular_series/ethane.json`](../data/molecular_series/ethane.json) | distilled from authored teacher | atomic | 1.0000 | 24 |
| [`data/molecular_series/ethanol.json`](../data/molecular_series/ethanol.json) | distilled from authored teacher | atomic | 1.0000 | 24 |
| [`data/molecular_series/formamide.json`](../data/molecular_series/formamide.json) | distilled from authored teacher | atomic | 1.0000 | 24 |
| [`data/particle_molecule/atomic_response.json`](../data/particle_molecule/atomic_response.json) | Geant4-trained | atomic | 1.0000 | 96 |
| [`data/particle_molecule/molecular_response.json`](../data/particle_molecule/molecular_response.json) | Geant4-trained | nano | 1.0000 | 144 |

**Performance**

- No case in the committed validation report runs this bundle.

### molecular_04_butane

**Grade B — Learned, not from Geant4** · entry [`examples/scenarios/molecular_04_butane/molecular_04_butane.js`](../examples/scenarios/molecular_04_butane/molecular_04_butane.js)

> Group 4: alkane conformations + shared particle-to-molecule learned response.

**Purity**

- Status: ledger `—`, companion `configuration_or_transport`.
- Inference sites: 3 (`predict` 1, `cascade` 1, `evolve` 1) · law-shaped math: 2 · inference share: 60%
- Embedded coefficients: 32 in 229 code lines (14.0/100) · top-level literals: 6 · geometry math: 5
- Geant4 fact reads: 4 · seeded RNG draws: 0 · hooks: no
- Inherited from modules: `examples/scenarios/molecular_series/molecular_series.js`, `js/trech_molecular_particle.js` — 3 inference / 2 law-shaped / 32 coefficients
- Utility/data includes (not counted): `js/trech_helpers.js`, `js/trech_math.js`, `js/trech_random.js`, `js/trech_material_facts.js`, `data/molecular_series/series.js`, `data/particle_molecule/response.js`
- Scale bands reached by declared models: atomic → nano

**Models**

| Normal-path model | Origin | Scale | Held-out R² (min) | n |
| --- | --- | --- | --- | --- |
| [`data/molecular_series/acetamide.json`](../data/molecular_series/acetamide.json) | distilled from authored teacher | atomic | 1.0000 | 24 |
| [`data/molecular_series/butane.json`](../data/molecular_series/butane.json) | distilled from authored teacher | atomic | 1.0000 | 24 |
| [`data/molecular_series/dimethyl_ether.json`](../data/molecular_series/dimethyl_ether.json) | distilled from authored teacher | atomic | 0.9999 | 24 |
| [`data/molecular_series/ethane.json`](../data/molecular_series/ethane.json) | distilled from authored teacher | atomic | 1.0000 | 24 |
| [`data/molecular_series/ethanol.json`](../data/molecular_series/ethanol.json) | distilled from authored teacher | atomic | 1.0000 | 24 |
| [`data/molecular_series/formamide.json`](../data/molecular_series/formamide.json) | distilled from authored teacher | atomic | 1.0000 | 24 |
| [`data/particle_molecule/atomic_response.json`](../data/particle_molecule/atomic_response.json) | Geant4-trained | atomic | 1.0000 | 96 |
| [`data/particle_molecule/molecular_response.json`](../data/particle_molecule/molecular_response.json) | Geant4-trained | nano | 1.0000 | 144 |

**Performance**

- No case in the committed validation report runs this bundle.

### molecular_05_dimethyl_ether

**Grade B — Learned, not from Geant4** · entry [`examples/scenarios/molecular_05_dimethyl_ether/molecular_05_dimethyl_ether.js`](../examples/scenarios/molecular_05_dimethyl_ether/molecular_05_dimethyl_ether.js)

> Group 5: ether polarization/torsion + shared particle-to-molecule inference.

**Purity**

- Status: ledger `—`, companion `configuration_or_transport`.
- Inference sites: 3 (`predict` 1, `cascade` 1, `evolve` 1) · law-shaped math: 2 · inference share: 60%
- Embedded coefficients: 32 in 229 code lines (14.0/100) · top-level literals: 6 · geometry math: 5
- Geant4 fact reads: 4 · seeded RNG draws: 0 · hooks: no
- Inherited from modules: `examples/scenarios/molecular_series/molecular_series.js`, `js/trech_molecular_particle.js` — 3 inference / 2 law-shaped / 32 coefficients
- Utility/data includes (not counted): `js/trech_helpers.js`, `js/trech_math.js`, `js/trech_random.js`, `js/trech_material_facts.js`, `data/molecular_series/series.js`, `data/particle_molecule/response.js`
- Scale bands reached by declared models: atomic → nano

**Models**

| Normal-path model | Origin | Scale | Held-out R² (min) | n |
| --- | --- | --- | --- | --- |
| [`data/molecular_series/acetamide.json`](../data/molecular_series/acetamide.json) | distilled from authored teacher | atomic | 1.0000 | 24 |
| [`data/molecular_series/butane.json`](../data/molecular_series/butane.json) | distilled from authored teacher | atomic | 1.0000 | 24 |
| [`data/molecular_series/dimethyl_ether.json`](../data/molecular_series/dimethyl_ether.json) | distilled from authored teacher | atomic | 0.9999 | 24 |
| [`data/molecular_series/ethane.json`](../data/molecular_series/ethane.json) | distilled from authored teacher | atomic | 1.0000 | 24 |
| [`data/molecular_series/ethanol.json`](../data/molecular_series/ethanol.json) | distilled from authored teacher | atomic | 1.0000 | 24 |
| [`data/molecular_series/formamide.json`](../data/molecular_series/formamide.json) | distilled from authored teacher | atomic | 1.0000 | 24 |
| [`data/particle_molecule/atomic_response.json`](../data/particle_molecule/atomic_response.json) | Geant4-trained | atomic | 1.0000 | 96 |
| [`data/particle_molecule/molecular_response.json`](../data/particle_molecule/molecular_response.json) | Geant4-trained | nano | 1.0000 | 144 |

**Performance**

- No case in the committed validation report runs this bundle.

### molecular_06_acetamide

**Grade B — Learned, not from Geant4** · entry [`examples/scenarios/molecular_06_acetamide/molecular_06_acetamide.js`](../examples/scenarios/molecular_06_acetamide/molecular_06_acetamide.js)

> Group 6: substituted amide + shared particle-to-molecule inference.

**Purity**

- Status: ledger `—`, companion `configuration_or_transport`.
- Inference sites: 3 (`predict` 1, `cascade` 1, `evolve` 1) · law-shaped math: 2 · inference share: 60%
- Embedded coefficients: 32 in 229 code lines (14.0/100) · top-level literals: 6 · geometry math: 5
- Geant4 fact reads: 4 · seeded RNG draws: 0 · hooks: no
- Inherited from modules: `examples/scenarios/molecular_series/molecular_series.js`, `js/trech_molecular_particle.js` — 3 inference / 2 law-shaped / 32 coefficients
- Utility/data includes (not counted): `js/trech_helpers.js`, `js/trech_math.js`, `js/trech_random.js`, `js/trech_material_facts.js`, `data/molecular_series/series.js`, `data/particle_molecule/response.js`
- Scale bands reached by declared models: atomic → nano

**Models**

| Normal-path model | Origin | Scale | Held-out R² (min) | n |
| --- | --- | --- | --- | --- |
| [`data/molecular_series/acetamide.json`](../data/molecular_series/acetamide.json) | distilled from authored teacher | atomic | 1.0000 | 24 |
| [`data/molecular_series/butane.json`](../data/molecular_series/butane.json) | distilled from authored teacher | atomic | 1.0000 | 24 |
| [`data/molecular_series/dimethyl_ether.json`](../data/molecular_series/dimethyl_ether.json) | distilled from authored teacher | atomic | 0.9999 | 24 |
| [`data/molecular_series/ethane.json`](../data/molecular_series/ethane.json) | distilled from authored teacher | atomic | 1.0000 | 24 |
| [`data/molecular_series/ethanol.json`](../data/molecular_series/ethanol.json) | distilled from authored teacher | atomic | 1.0000 | 24 |
| [`data/molecular_series/formamide.json`](../data/molecular_series/formamide.json) | distilled from authored teacher | atomic | 1.0000 | 24 |
| [`data/particle_molecule/atomic_response.json`](../data/particle_molecule/atomic_response.json) | Geant4-trained | atomic | 1.0000 | 96 |
| [`data/particle_molecule/molecular_response.json`](../data/particle_molecule/molecular_response.json) | Geant4-trained | nano | 1.0000 | 144 |

**Performance**

- No case in the committed validation report runs this bundle.

### molecular_series

**Grade B — Learned, not from Geant4** · entry [`examples/scenarios/molecular_series/molecular_series.js`](../examples/scenarios/molecular_series/molecular_series.js)

> First bounded electronic/torsional prediction group. See docs/molecular_series.md. Geant4 supplies live elemental identity + neutral-electron bookkeeping and actual particle transport. QM-trained surfaces supply charges/energies. Coordinates are imposed rigid scan samples, NOT predicted molecular dynamics.

**Purity**

- Status: ledger `no_active_material_law`, companion `no_active_material_law`.
- Ledger note: Imposed parameter scans, not material dynamics. Separate QM charge/torsion comparison; new group uses shared Geant4-trained atom response via ctx.evolve and nano composition response via ctx.cascade in trech_molecular_particle.js. Purple halos depend on inferred particle response; no authored molecular potential.
- Inference sites: 3 (`predict` 1, `cascade` 1, `evolve` 1) · law-shaped math: 2 · inference share: 60%
- Embedded coefficients: 32 in 227 code lines (14.1/100) · top-level literals: 6 · geometry math: 5
- Geant4 fact reads: 4 · seeded RNG draws: 0 · hooks: yes
- Inherited from modules: `js/trech_molecular_particle.js` — 2 inference / 2 law-shaped / 0 coefficients
- Utility/data includes (not counted): `js/trech_helpers.js`, `js/trech_math.js`, `js/trech_random.js`, `js/trech_material_facts.js`, `data/molecular_series/series.js`, `data/particle_molecule/response.js`
- Scale bands reached by declared models: atomic → nano

**Models**

| Normal-path model | Origin | Scale | Held-out R² (min) | n |
| --- | --- | --- | --- | --- |
| [`data/molecular_series/acetamide.json`](../data/molecular_series/acetamide.json) | distilled from authored teacher | atomic | 1.0000 | 24 |
| [`data/molecular_series/butane.json`](../data/molecular_series/butane.json) | distilled from authored teacher | atomic | 1.0000 | 24 |
| [`data/molecular_series/dimethyl_ether.json`](../data/molecular_series/dimethyl_ether.json) | distilled from authored teacher | atomic | 0.9999 | 24 |
| [`data/molecular_series/ethane.json`](../data/molecular_series/ethane.json) | distilled from authored teacher | atomic | 1.0000 | 24 |
| [`data/molecular_series/ethanol.json`](../data/molecular_series/ethanol.json) | distilled from authored teacher | atomic | 1.0000 | 24 |
| [`data/molecular_series/formamide.json`](../data/molecular_series/formamide.json) | distilled from authored teacher | atomic | 1.0000 | 24 |
| [`data/particle_molecule/atomic_response.json`](../data/particle_molecule/atomic_response.json) | Geant4-trained | atomic | 1.0000 | 96 |
| [`data/particle_molecule/molecular_response.json`](../data/particle_molecule/molecular_response.json) | Geant4-trained | nano | 1.0000 | 144 |

**Performance**

- No case in the committed validation report runs this bundle.

### nacl_dehydration_reference

**Grade R — Independent comparison reference** · entry [`examples/scenarios/nacl_dehydration_reference/nacl_dehydration_reference.js`](../examples/scenarios/nacl_dehydration_reference/nacl_dehydration_reference.js)

> Validation fixture, not a validated crystallization prediction or metal temper model.

**Purity**

- Status: ledger `reference_only`, companion `reference_only`.
- Authored residual still forcing behaviour: Illustrative capacity/attachment lattice comparison only; calibrated solubility/kinetics, nucleation/morphology anchors, particle-derived phase lift and metal heat-treatment response remain unavailable.
- Ledger note: Exact parcel conservation is an implementation check, not experimental validation of NaCl crystallization.
- Inference sites: 0 · law-shaped math: 0 · inference share: —
- Embedded coefficients: 0 in 92 code lines (0.0/100) · top-level literals: 2 · geometry math: 0
- Geant4 fact reads: 2 · seeded RNG draws: 1 · hooks: yes
- Comparison-only (excluded): modules `js/trech_crystallization_reference.js`
- Inherited from modules: `js/trech_crystallization_reference.js` — 0 inference / 0 law-shaped / 0 coefficients
- Utility/data includes (not counted): `js/trech_helpers.js`, `js/trech_math.js`, `js/trech_random.js`, `js/trech_material_facts.js`

**Performance**

- No case in the committed validation report runs this bundle.

### optics_surrogate_demo

**Grade G — Geant4 transport / configuration** · entry [`examples/scenarios/optics_surrogate_demo/optics_surrogate_demo.js`](../examples/scenarios/optics_surrogate_demo/optics_surrogate_demo.js)

> Optics surrogate demo: show the LibTorch-free ridge surrogate correcting a material the pure f-sum physics extractor cannot reach.

**Purity**

- Status: ledger `—`, companion `configuration_or_transport`.
- Inference sites: 0 · law-shaped math: 0 · inference share: —
- Embedded coefficients: 0 in 61 code lines (0.0/100) · top-level literals: 16 · geometry math: 2
- Geant4 fact reads: 0 · seeded RNG draws: 0 · hooks: no
- Utility/data includes (not counted): `js/trech_helpers.js`, `js/trech_math.js`, `js/trech_random.js`, `js/trech_material_facts.js`

**Models**

| Normal-path model | Origin | Scale | Held-out R² (min) | n |
| --- | --- | --- | --- | --- |
| [`data/optics_surrogate_ridge.json`](../data/optics_surrogate_ridge.json) | trained on measured anchors | — | — | — |

**Performance**

- `optics_surrogate_transport_applied` — **pass**: nai mean_n=1.7672 min_sample_n=1.7654 surrogate_note=True (extractor would be ~1.33)

### optics_training_panel

**Grade G — Geant4 transport / configuration** · entry [`examples/scenarios/optics_training_panel/optics_training_panel.js`](../examples/scenarios/optics_training_panel/optics_training_panel.js)

> Optics surrogate training panel.

**Purity**

- Status: ledger `—`, companion `configuration_or_transport`.
- Inference sites: 0 · law-shaped math: 0 · inference share: —
- Embedded coefficients: 0 in 57 code lines (0.0/100) · top-level literals: 23 · geometry math: 0
- Geant4 fact reads: 0 · seeded RNG draws: 0 · hooks: no
- Utility/data includes (not counted): `js/trech_helpers.js`, `js/trech_math.js`, `js/trech_random.js`, `js/trech_material_facts.js`

**Performance**

- No case in the committed validation report runs this bundle.
- [`docs/validation_optics_surrogate.json`](../docs/validation_optics_surrogate.json): `mae_extractor` = 0.1406; `mae_surrogate_loo` = 0.08394; `surrogate_improves_over_extractor` = True

### particle_observer_cascade

**Grade A — Geant4-learned** · entry [`examples/scenarios/particle_observer_cascade/particle_observer_cascade.js`](../examples/scenarios/particle_observer_cascade/particle_observer_cascade.js)

> An experimental Geant4-trained atomic/nano/meso candidate predicts before an independent Monte Carlo run; model acceptance remains gated by independent holdouts.

**Purity**

- Status: ledger `no_active_material_law`, companion `learned_geant4_transport_candidate`.
- Ledger note: Learned atomic/nano/meso transport observables predicted before an independent MC run; no authored material-state evolution. Proxy domains, held-out model accuracy and candidate promotion remain separate inference validation requirements.
- Inference sites: 3 (`cascade` 2, `evolve` 1) · law-shaped math: 2 · inference share: 60%
- Embedded coefficients: 0 in 176 code lines (0.0/100) · top-level literals: 0 · geometry math: 0
- Geant4 fact reads: 3 · seeded RNG draws: 0 · hooks: yes
- Inherited from modules: `js/trech_molecular_particle.js` — 2 inference / 2 law-shaped / 0 coefficients
- Utility/data includes (not counted): `js/trech_helpers.js`, `js/trech_math.js`, `js/trech_random.js`, `js/trech_material_facts.js`, `data/particle_molecule/response.js`
- Scale bands reached by declared models: atomic → nano → meso

**Models**

| Normal-path model | Origin | Scale | Held-out R² (min) | n |
| --- | --- | --- | --- | --- |
| [`data/particle_molecule/atomic_response.json`](../data/particle_molecule/atomic_response.json) | Geant4-trained | atomic | 1.0000 | 96 |
| [`data/particle_molecule/molecular_response.json`](../data/particle_molecule/molecular_response.json) | Geant4-trained | nano | 1.0000 | 144 |
| [`data/particle_observer/observer_response.json`](../data/particle_observer/observer_response.json) | Geant4-trained | meso | 0.9994 | 18 |

**Performance**

- No case in the committed validation report runs this bundle.
- Dedicated validator: [`scripts/validate_particle_observer.py`](../scripts/validate_particle_observer.py)

### polyurethane_foam

**Grade C — Partially operator-backed** · entry [`examples/scenarios/polyurethane_foam/polyurethane_foam.js`](../examples/scenarios/polyurethane_foam/polyurethane_foam.js)

> The polyurethane foam experiment ("the solid sponge"), observed in an open cup.

**Purity**

- Status: ledger `operator_partial`, companion `operator_partial`.
- Authored residual still forcing behaviour: default mechanics coupling (opt-in constitutive candidate has failing observer gates) and persistent bond/contact response
- Inference sites: 3 (`cascade` 1, `evolve` 2) · law-shaped math: 3 · inference share: 50%
- Embedded coefficients: 78 in 1585 code lines (4.9/100) · top-level literals: 52 · geometry math: 20
- Geant4 fact reads: 10 · seeded RNG draws: 0 · hooks: yes
- Comparison-only (excluded): 3 law-shaped sites in comparison code; functions `referenceApplyMechanicsCoupling`, `stepChemistryReference`
- Inherited from modules: `js/trech_foam_solver.js` — 0 inference / 3 law-shaped / 41 coefficients
- Utility/data includes (not counted): `js/trech_helpers.js`, `js/trech_math.js`, `js/trech_random.js`, `js/trech_material_facts.js`
- Scale bands reached by declared models: nano → meso → macro

**Models**

| Normal-path model | Origin | Scale | Held-out R² (min) | n |
| --- | --- | --- | --- | --- |
| [`data/polyurethane_cascade/macro_foam_response.json`](../data/polyurethane_cascade/macro_foam_response.json) | hand-authored response surface | macro | — | — |
| [`data/polyurethane_cascade/meso_mechanics_operator.json`](../data/polyurethane_cascade/meso_mechanics_operator.json) | distilled from authored teacher | meso | 0.9980 | 6006 |
| [`data/polyurethane_cascade/meso_reaction_operator.json`](../data/polyurethane_cascade/meso_reaction_operator.json) | distilled from authored teacher | meso | 0.9929 | 38565 |
| [`data/polyurethane_cascade/nano_reagent_descriptors.json`](../data/polyurethane_cascade/nano_reagent_descriptors.json) | hand-authored response surface | nano | — | — |

**Performance**

- `polyurethane_foam_expansion` — **pass**: checks=26/26 expansion=31.1x exotherm=+66K (core-skin 34K) lean=5.0deg vs 2.6 at zero-g; cracked=29% vs 12%; 5 pieces fell (vs 0); cures rigid
- `polyurethane_operator_matches_reference` — **pass**: gap checks=8/8 trust=22/22

**Review flags**

- ⚠ 2 normal-path model(s) are hand-authored response surfaces, not trained

### spectrum_prediction

**Grade M — Inference mechanism demo** · entry [`examples/scenarios/spectrum_prediction/spectrum_prediction.js`](../examples/scenarios/spectrum_prediction/spectrum_prediction.js)

> Learned atomic line-strength and molecular UV/Vis envelope predictions from measured PubChem/NIST spectra, evaluated by GenericSurrogate through ctx.cascade.

**Purity**

- Status: ledger `no_active_material_law`, companion `no_active_material_law`.
- Declared limitations: Labels are measured spectra represented on fixed grids; models are learned comparisons with small held-out sets, not Geant4 results.
- Inference sites: 2 (`cascade` 2) · law-shaped math: 0 · inference share: 100%
- Embedded coefficients: 0 in 214 code lines (0.0/100) · top-level literals: 1 · geometry math: 1
- Geant4 fact reads: 2 · seeded RNG draws: 0 · hooks: yes
- Inherited from modules: `projects/spectrum_prediction/lib/index.js` — 0 inference / 0 law-shaped / 0 coefficients
- Utility/data includes (not counted): `js/trech_random.js`
- Runtime-supplied model paths: 2 (chosen by parameters at run time; not graded)
- Scale bands reached by declared models: atomic → nano

**Performance**

- No case in the committed validation report runs this bundle.
- Dedicated validator: [`scripts/validate_spectrum_prediction.py`](../scripts/validate_spectrum_prediction.py)

**Review flags**

- ⚠ calls inference but no model file could be resolved statically

### surrogate_generic_demo

**Grade B — Learned, not from Geant4** · entry [`examples/scenarios/surrogate_generic_demo/surrogate_generic_demo.js`](../examples/scenarios/surrogate_generic_demo/surrogate_generic_demo.js)

> Generic Torch-surrogate demo: any scenario can attach a learned model and call it deterministically from a hook via ctx.predict.

**Purity**

- Status: ledger `no_active_material_law`, companion `no_active_material_law`.
- Inference sites: 2 (`predict` 2) · law-shaped math: 0 · inference share: 100%
- Embedded coefficients: 0 in 50 code lines (0.0/100) · top-level literals: 1 · geometry math: 0
- Geant4 fact reads: 3 · seeded RNG draws: 0 · hooks: yes
- Scale bands reached by declared models: atomic

**Models**

| Normal-path model | Origin | Scale | Held-out R² (min) | n |
| --- | --- | --- | --- | --- |
| [`data/optics_surrogate_ridge.json`](../data/optics_surrogate_ridge.json) | trained on measured anchors | — | — | — |

**Performance**

- `generic_surrogate_inference` — **pass**: models_loaded=['optics_n'] hook_predict_count=8 predicted_water_n=1.3301 (n_events=8, stable=True); Geant4 inputs=True/True, ethanol n=1.4295, material response=True

### testscenario_efflux

**Grade B — Learned, not from Geant4** · entry [`examples/scenarios/testscenario_efflux/testscenario_efflux.js`](../examples/scenarios/testscenario_efflux/testscenario_efflux.js)

> Validation scenario: passive membrane efflux (clearance of a lipophilic "waste" molecule from a cell), cross-checked against the classical first-order / Fick's-law clearance kinetics.

**Purity**

- Status: ledger `operator_backed`, companion `operator_backed`.
- Inference sites: 2 (`evolve` 1, `react` 1) · law-shaped math: 2 · inference share: 50%
- Embedded coefficients: 15 in 807 code lines (1.9/100) · top-level literals: 23 · geometry math: 7
- Geant4 fact reads: 0 · seeded RNG draws: 6 · hooks: yes
- Comparison-only (excluded): 2 law-shaped sites in comparison code; functions `eventFactsWithReferenceActivation`, `referenceAdvectionVelocity`, `referenceStepCleared`, `referenceStepInside`, `referenceStepRandomVelocity`
- Utility/data includes (not counted): `js/trech_helpers.js`, `js/trech_math.js`, `js/trech_random.js`, `js/trech_material_facts.js`
- Scale bands reached by declared models: micro

**Models**

| Normal-path model | Origin | Scale | Held-out R² (min) | n |
| --- | --- | --- | --- | --- |
| [`data/discrete_operators/efflux_crossing_operator.json`](../data/discrete_operators/efflux_crossing_operator.json) | distilled from authored teacher | micro | 0.9827 | 6000 |
| [`data/discrete_operators/efflux_transport_operator.json`](../data/discrete_operators/efflux_transport_operator.json) | distilled from authored teacher | micro | 0.9993 | 6000 |

**Performance**

- `efflux_first_order_kinetics` — **pass**: checks=9/9 R2=0.990 half_life=1226t cleared=78/80 retained=30 g4_ratio=1.296 g4_steps=12952
- `efflux_operators_match_reference` — **pass**: gap checks=4/4 trust=22/22

### testscenario_h2o_electrolysis_combustion

**Grade B — Learned, not from Geant4** · entry [`examples/scenarios/testscenario_h2o_electrolysis_combustion/testscenario_h2o_electrolysis_combustion.js`](../examples/scenarios/testscenario_h2o_electrolysis_combustion/testscenario_h2o_electrolysis_combustion.js)

> Validation scenario: water electrolysis on two cathodes followed by inverse combustion (H2 + O2 -> H2O).

**Purity**

- Status: ledger `operator_backed`, companion `operator_backed`.
- Inference sites: 1 (`react` 1) · law-shaped math: 3 · inference share: 25%
- Embedded coefficients: 53 in 914 code lines (5.8/100) · top-level literals: 32 · geometry math: 8
- Geant4 fact reads: 0 · seeded RNG draws: 6 · hooks: yes
- Comparison-only (excluded): functions `referenceCombustionProbability`, `referenceCombustionStep`, `referenceElectrolysisProbability`, `referenceElectrolysisStep`
- Utility/data includes (not counted): `js/trech_helpers.js`, `js/trech_math.js`, `js/trech_random.js`, `js/trech_material_facts.js`
- Scale bands reached by declared models: meso

**Models**

| Normal-path model | Origin | Scale | Held-out R² (min) | n |
| --- | --- | --- | --- | --- |
| [`data/discrete_operators/h2o_cycle_transition_operator.json`](../data/discrete_operators/h2o_cycle_transition_operator.json) | distilled from authored teacher | meso | 0.9973 | 6000 |

**Performance**

- `h2o_cycle_operator_matches_reference` — **pass**: gap checks=4/4 trust=22/22
- `h2o_electrolysis_combustion_cycle` — **pass**: checks=12/12 H2/O2=2 recovered=100.0% cathode_imbalance=0.0667 water=180 g4_edep=24MeV

### testscenario_magnetic_resonance

**Grade E — Authored forward law** · entry [`examples/scenarios/testscenario_magnetic_resonance/testscenario_magnetic_resonance.js`](../examples/scenarios/testscenario_magnetic_resonance/testscenario_magnetic_resonance.js)

> Validation scenario (Stage 1): nuclear magnetic resonance of a water cube.

**Purity**

- Status: ledger `reference_only`, companion `reference_only`.
- Authored residual still forcing behaviour: Bloch pulse, Curie magnetization and FID forward dynamics
- Inference sites: 0 · law-shaped math: 4 · inference share: 0%
- Embedded coefficients: 8 in 424 code lines (1.9/100) · top-level literals: 17 · geometry math: 8
- Geant4 fact reads: 4 · seeded RNG draws: 3 · hooks: yes
- Utility/data includes (not counted): `js/trech_helpers.js`, `js/trech_math.js`, `js/trech_random.js`, `js/trech_material_facts.js`

**Performance**

- `magnetic_resonance_water` — **pass**: checks=7/7 gamma=42.5768 MHz/T (ref 42.5775, 0.00%) protonH=6.686e+22/cm3 (0.01%) T2*fit=7.99ms RFphotons=4.13e+17

### testscenario_magnetic_resonance_brain

**Grade E — Authored forward law** · entry [`examples/scenarios/testscenario_magnetic_resonance_brain/testscenario_magnetic_resonance_brain.js`](../examples/scenarios/testscenario_magnetic_resonance_brain/testscenario_magnetic_resonance_brain.js)

> Validation scenario (Stage 4): virtual-brain MRI proton densities.

**Purity**

- Status: ledger `reference_only`, companion `reference_only`.
- Authored residual still forcing behaviour: shared voxel/isochromat magnetic-resonance forward dynamics
- Inference sites: 0 · law-shaped math: 0 · inference share: —
- Embedded coefficients: 0 in 98 code lines (0.0/100) · top-level literals: 9 · geometry math: 0
- Geant4 fact reads: 3 · seeded RNG draws: 0 · hooks: yes
- Utility/data includes (not counted): `js/trech_helpers.js`, `js/trech_math.js`, `js/trech_random.js`, `js/trech_material_facts.js`

**Performance**

- `magnetic_resonance_brain_image` — **pass**: checks=7/7 intensity↔proton r=0.998 recon r=0.966 grey=0.639 white=0.55 skull=0.129

### testscenario_magnetic_resonance_imaging

**Grade E — Authored forward law** · entry [`examples/scenarios/testscenario_magnetic_resonance_imaging/testscenario_magnetic_resonance_imaging.js`](../examples/scenarios/testscenario_magnetic_resonance_imaging/testscenario_magnetic_resonance_imaging.js)

> Validation scenario (Stage 3): 1D magnetic-resonance IMAGING via frequency encoding -- turning the tissue contrast into an actual image line.

**Purity**

- Status: ledger `reference_only`, companion `reference_only`.
- Authored residual still forcing behaviour: voxel excitation and synthesized readout forward dynamics
- Inference sites: 0 · law-shaped math: 1 · inference share: 0%
- Embedded coefficients: 6 in 270 code lines (2.2/100) · top-level literals: 14 · geometry math: 6
- Geant4 fact reads: 3 · seeded RNG draws: 1 · hooks: yes
- Utility/data includes (not counted): `js/trech_helpers.js`, `js/trech_math.js`, `js/trech_random.js`, `js/trech_material_facts.js`

**Performance**

- `magnetic_resonance_image_line` — **pass**: checks=6/6 max_pos_err=0.001mm amp_corr=1.000 air=0.011 bone=0.588

### testscenario_magnetic_resonance_tissues

**Grade E — Authored forward law** · entry [`examples/scenarios/testscenario_magnetic_resonance_tissues/testscenario_magnetic_resonance_tissues.js`](../examples/scenarios/testscenario_magnetic_resonance_tissues/testscenario_magnetic_resonance_tissues.js)

> Validation scenario (Stage 2): virtual-tissue magnetic-resonance contrast.

**Purity**

- Status: ledger `reference_only`, companion `reference_only`.
- Authored residual still forcing behaviour: shared tissue magnetic-resonance forward dynamics
- Inference sites: 0 · law-shaped math: 0 · inference share: —
- Embedded coefficients: 0 in 162 code lines (0.0/100) · top-level literals: 11 · geometry math: 1
- Geant4 fact reads: 4 · seeded RNG draws: 0 · hooks: yes
- Utility/data includes (not counted): `js/trech_helpers.js`, `js/trech_math.js`, `js/trech_random.js`, `js/trech_material_facts.js`

**Performance**

- `magnetic_resonance_tissue_contrast` — **pass**: checks=5/5 tissues=6 corr(signal,protonH)=1.000 bone=0.589x (protonR 0.583)

### testscenario_osmotic

**Grade E — Authored forward law** · entry [`examples/scenarios/testscenario_osmotic/testscenario_osmotic.js`](../examples/scenarios/testscenario_osmotic/testscenario_osmotic.js)

> Validation scenario: Osmotic Dehydration via Dimensional & Polarity Exclusion. See docs/testscenario_osmotic-todo.md.

**Purity**

- Status: ledger `reference_only`, companion `reference_only`.
- Authored residual still forcing behaviour: 3D particle transport/crossing and pressure-driven area-conserving membrane response
- Inference sites: 0 · law-shaped math: 0 · inference share: —
- Embedded coefficients: 14 in 834 code lines (1.7/100) · top-level literals: 31 · geometry math: 21
- Geant4 fact reads: 0 · seeded RNG draws: 2 · hooks: yes
- Utility/data includes (not counted): `js/trech_helpers.js`, `js/trech_math.js`, `js/trech_random.js`, `js/trech_material_facts.js`

**Performance**

- `osmotic_shift_observed` — **pass**: checks=9/9 net_water_flux_out=74 first_crossing_tick=1 max_ke=1.36/1.22 late_pressure_external/internal=1.04

### testscenario_pascal

**Grade E — Authored forward law** · entry [`examples/scenarios/testscenario_pascal/testscenario_pascal.js`](../examples/scenarios/testscenario_pascal/testscenario_pascal.js)

> Validation scenario: Pascal's Principle & Material Deformation. See docs/testscenario_pascal-todo.md.

**Purity**

- Status: ledger `reference_only`, companion `reference_only`.
- Authored residual still forcing behaviour: 3D particle bath and tensioned sensor-wall patch constitutive response
- Inference sites: 0 · law-shaped math: 0 · inference share: —
- Embedded coefficients: 18 in 617 code lines (2.9/100) · top-level literals: 36 · geometry math: 3
- Geant4 fact reads: 0 · seeded RNG draws: 0 · hooks: yes
- Utility/data includes (not counted): `js/trech_helpers.js`, `js/trech_math.js`, `js/trech_random.js`, `js/trech_material_facts.js`

**Performance**

- `pascal_principle_holds` — **pass**: pascal_holds=True damping=True rigid_disp=1.962e-05 deformable_disp=2.965e+00 (contrast x151103)

### validation_glass_of_water

**Grade G — Geant4 transport / configuration** · entry [`examples/scenarios/validation_glass_of_water/validation_glass_of_water.js`](../examples/scenarios/validation_glass_of_water/validation_glass_of_water.js)

> Validation scenario: a beam of light enters a glass slab containing a water bulk, then exits back into air -- the "glass of water" cross section, modeled with planar (axis-aligned) interfaces so that the surface normal at every refraction is exactly one of +/- x, y, z. Planar normals are what lets the companion validator (scripts/validate_glass_of_water.py) invert the classical optics formulas with no ambiguity.

**Purity**

- Status: ledger `—`, companion `configuration_or_transport`.
- Inference sites: 0 · law-shaped math: 0 · inference share: —
- Embedded coefficients: 0 in 95 code lines (0.0/100) · top-level literals: 13 · geometry math: 2
- Geant4 fact reads: 0 · seeded RNG draws: 0 · hooks: no
- Utility/data includes (not counted): `js/trech_helpers.js`, `js/trech_math.js`, `js/trech_random.js`, `js/trech_material_facts.js`

**Performance**

- No case in the committed validation report runs this bundle.
- [`docs/validation_glass_of_water.json`](../docs/validation_glass_of_water.json): `derived_optics_direct[air].delta` = 9.003e-05; `derived_optics_direct[water].delta` = -0.002261; `derived_optics_direct[glass].delta` = 0.01216; `fresnel[air -> glass].delta` = 0.02111; `fresnel[water -> glass].delta` = -0.03047; `snell[air -> glass].delta` = -0.007281; `snell[air -> glass].rel_error` = 0.004987; `snell[glass -> air].delta` = 0.01107; `snell[glass -> air].rel_error` = 0.01106; `snell[glass -> water].delta` = -0.013; `snell[glass -> water].rel_error` = 0.009752; `snell[water -> glass].delta` = 0.01436; … 1 more

### viz_refraction_demo

**Grade G — Geant4 transport / configuration** · entry [`examples/scenarios/viz_refraction_demo/viz_refraction_demo.js`](../examples/scenarios/viz_refraction_demo/viz_refraction_demo.js)

> 3D refraction demo: a monochromatic optical-photon beam enters a glass slab containing a water cube, then exits back into air. The point of this scenario is to *show* refraction in a 3D viewer where every material's optical response (n, absorption, scatter) was derived by TRECH from Geant4-level particle interaction cross sections, not from hardcoded classical optics.

**Purity**

- Status: ledger `—`, companion `configuration_or_transport`.
- Inference sites: 0 · law-shaped math: 0 · inference share: —
- Embedded coefficients: 0 in 95 code lines (0.0/100) · top-level literals: 8 · geometry math: 2
- Geant4 fact reads: 0 · seeded RNG draws: 0 · hooks: no
- Utility/data includes (not counted): `js/trech_helpers.js`, `js/trech_math.js`, `js/trech_random.js`, `js/trech_material_facts.js`

**Performance**

- `determinism_replay` — **pass**: all numeric fields agree within ~1e-9 relative; integers/strings/booleans exact-match
- `event_feature_mean_consistent_with_system_summary` — **pass**: stats.mean=0.000000e+00 system.mean=0.000000e+00
- `event_feature_stats_torch_backed_flag` — **info**: torch_backed = False
- `material_composition_sums_to_one` — **pass**: all material fractions sum to 1.0
- `optics_index_above_one` — **pass**: all 4 derived n entries >= 1
- `optics_index_ordering` — **pass**: n_glass=1.472173 > n_water=1.330752 > n_air=1.000383
- `optics_kk_integration_window` — **pass**: kkIntegration window 50 -> 200000 eV (ratio 4000)
- `optics_n_air_visible` — **info**: derived n = 1.000383, reference = 1.000293, delta = +0.000090
- `optics_n_glass_visible` — **info**: derived n = 1.472173, reference = 1.460000, delta = +0.012173
- `optics_n_water_visible` — **info**: derived n = 1.330752, reference = 1.333000, delta = -0.002248
- `primaries_accounting_closure` — **pass**: emitted=60 transmitted=60 absorbed=0 (t+a=60)
- `system_volume_density_arithmetic` — **pass**: density=0.000000e+00 total/vol=0.000000e+00
- `viz_scene_schema_v1` — **pass**: schema='trech_viz_scene_v1'
- `viz_trajectories_min_points` — **pass**: 0/60 trajectories below min-points threshold
- `viz_trajectories_point_count` — **pass**: scores.viz_segments=270 jsonl_total_points=270

### water_box

**Grade G — Geant4 transport / configuration** · entry [`examples/scenarios/water_box/water_box.js`](../examples/scenarios/water_box/water_box.js)

> water_box: configured e- transport in G4_AIR. Check completed output and the declared physics/inference scope.

**Purity**

- Status: ledger `—`, companion `configuration_or_transport`.
- Inference sites: 0 · law-shaped math: 0 · inference share: —
- Embedded coefficients: 0 in 49 code lines (0.0/100) · top-level literals: 7 · geometry math: 0
- Geant4 fact reads: 0 · seeded RNG draws: 0 · hooks: no
- Utility/data includes (not counted): `js/trech_helpers.js`, `js/trech_math.js`, `js/trech_random.js`, `js/trech_material_facts.js`

**Performance**

- No case in the committed validation report runs this bundle.

### water_salt_recipe

**Grade G — Geant4 transport / configuration** · entry [`examples/scenarios/water_salt_recipe/water_salt_recipe.js`](../examples/scenarios/water_salt_recipe/water_salt_recipe.js)

> water_salt_recipe: configured gamma transport in G4_WATER. Check completed output and the declared physics/inference scope.

**Purity**

- Status: ledger `no_active_material_law`, companion `no_active_material_law`.
- Ledger note: Calls reusable solution process libraries; no built-in kinetics or models. The supplied recipe blocks on missing operators and emits no invented spatial motion.
- Inference sites: 0 · law-shaped math: 1 · inference share: 0%
- Embedded coefficients: 10 in 611 code lines (1.6/100) · top-level literals: 7 · geometry math: 0
- Geant4 fact reads: 0 · seeded RNG draws: 0 · hooks: yes
- Inherited from modules: `js/trech_solution_processes.js`, `js/trech_process_runtime.js`, `js/trech_process_operators.js` — 0 inference / 1 law-shaped / 10 coefficients

**Performance**

- No case in the committed validation report runs this bundle.
