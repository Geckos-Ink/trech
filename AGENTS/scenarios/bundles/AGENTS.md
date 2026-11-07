# Scenario bundles and shared helpers — context and contracts

[Root principles](../../../AGENTS.md) · [Root roadmap](../../../ROADMAP.md) · [Parent](../AGENTS.md) · [Roadmap](ROADMAP.md)

Related owners: [JavaScript host and live lab](../../engine/runtime/AGENTS.md) · [Scenario and process editing](../../studio/authoring/AGENTS.md).

Read the root principles and the parent handbook first; then open only the subcategory relevant to the task. Source paths and shell commands in code spans/blocks are repository-relative unless stated otherwise; Markdown links resolve from this file.

**Scenario bundles:** all 64 scenario entry points live in `examples/scenarios/<name>/` with
`<name>.js` (physics), `.view.js` (presentation), `.validation.js` (expectations), and `.ui.js`
(typed controls/Studio descriptions). Shared TRECH JS lives in `js/`; failure fixtures live in
`tests/fixtures/js/`. The C++ loader loads companions for roots and nested includes; CLI/library
and Studio share parameter validation. Source inventory includes companions. Contract:
[`docs/scenario_bundles.md`](../../../docs/scenario_bundles.md). Historical media identities are retained.

- **Accumulating hook scenarios MUST set `run.threads: 1`.** Hook-layer state that grows across
  events (MD baths, Bloch, reaction ledgers, fluid solvers) is non-reproducible under Geant4 MT
  because worker event-completion order varies. This is the single most common determinism bug.

### JS scenario bundles — [`examples/scenarios/`](../../../examples/scenarios) and [`js/`](../../../js)

The physics content: scenarios set `TRECH_CONFIG` (+ optional `TRECH_HOOKS`). The shipped set
doubles as the manual regression corpus and as Studio's test tree. Shared modules:
[`trech_helpers.js`](../../../js/trech_helpers.js) (constants, `spectra`,
`helpers.beamProfiles.spread` presets, `observer.linearClock`, and the common-library entry point),
[`trech_math.js`](../../../js/trech_math.js) (`helpers.math`: numeric bounds/coercion,
interpolation, rounding and finite-output checks),
[`trech_random.js`](../../../js/trech_random.js) (`helpers.random`: Mulberry32,
two-draw Box–Muller and stateless parcel noise), and
[`trech_material_facts.js`](../../../js/trech_material_facts.js) (`helpers.materialFacts`:
recorded optics plus comparison-only PubChem identity/lexical element checks).
Imports consume no RNG; solver modules can load these dependencies independently. Mulberry32
remains callable and supplies `.uniform` for the same Gaussian sampler as `ctx.rng`; engine
methods retain their receiver and no spare Gaussian is cached. `observer.linearClock` retains
physical and playback clocks; piecewise clocks stay scenario-owned. Helper contracts are tested
through QuickJS in `tests/test_scenario_helpers.cpp`. No shared utility is a new material law.
[`trech_water_md.js`](../../../js/trech_water_md.js)
(`TRECH_WATER_MD.create(cfg)` — the shared rigid-SPC/E MD core: force loop, SHAKE/RATTLE,
velocity-Verlet; both bulk water and the D(T) sweep build on it), and
[`trech_foam_solver.js`](../../../js/trech_foam_solver.js) (`TRECH_FOAM.create(cfg)` — a
chemistry-agnostic **growing viscoelastic bonded-parcel network under standard gravity**: the
scenario supplies per-parcel `growthRatePerS`/`relaxRatePerS`/`strengthScale`/`dragPerS` and the
module grows bond rest lengths, creeps stress away, breaks bonds past the failure strain, solves
contact/wall/ground constraints, and lets detached fragments fall ballistically and land — so
leaning, cracking, shedding and where debris lands are consequences, never scheduled. Both foam
scenarios build on it; gravity enters as a labelled physical constant, every material coefficient
is cascade-inferred). Families (see
[Features](../AGENTS.md#features-and-recurring-development-pitfalls) for behavior/status):

| Family | Canonical scenarios | Guard (category) |
| --- | --- | --- |
| Fluids / H₂O MD | `h2o_molecule_stability`, `h2o_cluster_fluid`, `h2o_bulk_water`, `h2o_diffusion_temperature`, `glass_of_water_shaken`, `lava_lamp` | `*_stable`/`*_structure`/`*_trend`/`glass_of_water_shaken_waves`/`lava_lamp_inferred_thermofluid` (`fluid`) |
| Optics | `viz_refraction_demo`, `validation_glass_of_water`, `glass_of_water_varied`, `glass_of_water_spectral`, `optics_surrogate_demo` | glass-of-water + `optics_surrogate_transport_applied` |
| Chemistry cycles | `testscenario_h2o_electrolysis_combustion`, `config_nitrogen_carbon_cycle`, `briggs_rauscher_oscillator`, `polyurethane_foam`, `elephants_toothpaste`, `glass_from_sand` | `h2o_electrolysis_combustion_cycle` + `h2o_cycle_operator_matches_reference`, nuclear cycle checks, `briggs_rauscher_oscillation`, `polyurethane_foam_expansion`, `elephants_toothpaste_eruption`, `glass_from_sand_material_creation` + `glass_operator_matches_reference` |
| Molecular series | `molecular_01_ethane` through `molecular_06_acetamide` (incl. butane/dimethyl ether; shared `molecular_series.js`) | `test_molecular_series.py`, `test_particle_molecule.py`, `scripts/run_molecular_series.py` (12 runs), `scripts/validate_particle_molecule.py` (15 runs incl. 90,000 MC photons) |
| Biology / membranes | `testscenario_efflux`, `testscenario_osmotic`, `testscenario_pascal` | `efflux_first_order_kinetics` + `efflux_operators_match_reference`, `osmotic_shift_observed`, `pascal_principle_holds` |
| CNT electronics | `cnt_band_structure`, `cnt_logic_gates` (+ `config_cnt_*_stub`) | `cnt_band_structure`, `cnt_logic_gates` (`cnt`) |
| Magnetic resonance | `testscenario_magnetic_resonance`(`_tissues`/`_imaging`/`_brain`) | `magnetic_resonance_*` (`resonance`) |
| Analytic cross-checks | `analytic_beer_lambert`, `analytic_csda_range`, `analytic_photo_fraction` (`energy_mev` param), `analytic_compton_transfer`, `analytic_pair_production` (`energy_mev` param) | `analytic_*_cross_check`, `analytic_photo_fraction_energy_sweep`, `analytic_pair_fraction_energy_sweep`, `analytic_photonuclear_fraction_giant_dipole` (`analytic`) |
| Cascade / ML | `cascade_multiscale_demo`, `surrogate_generic_demo`, `beaker_water_n_pentane` | `generic_surrogate_inference`, `beaker_water_n_pentane_inference` |
| Spectrum prediction (experimental) | `spectrum_prediction` (`selection`, `studio_mode`) | `trech_spectrum_prediction_js`, `scripts/validate_spectrum_prediction.py` ([branch](../spectra/AGENTS.md)) |
| Particle → observer (experimental) | `particle_observer_cascade` | `test_particle_observer.py`, `scripts/validate_particle_observer.py`; learned atomic/nano/meso transport, independent MC error gates and visible sparse-coverage warnings |

Lab bootstrap: [`examples/lab/`](../../../examples/lab). By-design failing demo: `include_error_demo.js`.

- **MT nondeterminism in accumulating hooks.** Symptom: a fixed-seed hook scenario gives different
  tallies across runs. Cause: Geant4 MT event order. Fix: `run.threads: 1`. Prevention:
  cross-check reruns are byte-identical.
