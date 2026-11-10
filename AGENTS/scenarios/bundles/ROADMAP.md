# Scenario bundles and shared helpers — roadmap

[Root principles](../../../AGENTS.md) · [Root roadmap](../../../ROADMAP.md) · [Parent](../ROADMAP.md) · [Handbook](AGENTS.md)

Related owners: [JavaScript host and live lab](../../engine/runtime/ROADMAP.md) · [Scenario and process editing](../../studio/authoring/ROADMAP.md).

Maintain work in its owning branch. Dated results apply to the recorded checkout; they do not validate subsequent changes.

## Scenario bundles

- [x] The experimental `particle_observer_cascade` adds a complete four-file bundle (64 total),
  exposing recorded pre-transport predictions and a labelled static inference diagram. The
  [observer contract](../../../docs/particle_observer.md) owns its scientific scope and open gaps.

- [x] Split all 63 scenario entry points into per-scenario physics/view/validation/UI bundles;
  move shared TRECH JS to `js/`, update CLI/library nested loading, Studio browsing/editor,
  capture registries and validation consumers. Contract: [docs/scenario_bundles.md](../../../docs/scenario_bundles.md).
- [partial: 18 families + 3 multi-run sweeps exported 2026-11-09] Export Python family-validation
  evaluators/tolerances as a common declarative runner schema. **Multi-run sweeps (2026-11-09):**
  `family_sweeps` declare ordered runs with exact `--param` identity (checked against provenance
  `cli_args`), per-run (`run`/`each_run`) checks and cross-run `series_aggregate` reductions
  (monotonicity, span ratios, `argmax`/`argmin`), plus a `binomial_z` derivation. The
  photofraction energy sweep, pair threshold/energy sweep and photonuclear giant-dipole gates now
  take their suite verdict from the analytic bundles (22/22, 44/44, 27/27 on the recorded
  `pn_val` runs, matching the Python verdicts); a corrupted z, mismatched run parameter or
  broken monotonicity flips the case. `validate_scenario.py --sweep` grades one sweep directly.
  Remaining: photonuclear final-state and Bertini model-comparison gates (per-ejectile edge and
  closure lists across runs), operator/reference pair gates and lava/foam/chemistry
  multi-condition gates (sweeps now give them a schema), and regenerating
  `docs/validation_report.*`. **Derived statistics (2026-11-09):** `derive`
  (`abs/difference/ratio/list_sum/list_length/chi2_sf`, nestable, per projected element) exports
  the Klein-Nishina Compton gate (18 checks: availability, tolerance, |z| < 4 for mean transfer
  and `<cos θ>`, edge ratio in [0.98, 1+1e-9], histogram completeness/entry counts, χ² p ≥ 0.001
  for the u and cos θ spectra, closure ≤ 1e-9) and the 10 MeV pair-fraction gate (5 checks).
  Both reproduce the Python verdicts on the recorded `pn_val` runs (18/18, 5/5); a corrupted
  χ², edge, histogram sum, closure residual or dof flips exactly the matching check. Remaining:
  multi-run energy sweeps (photofraction, pair threshold, photonuclear GDR/final state/model
  comparison) need a multi-run selector, plus the operator/reference pair and lava/foam/chemistry
  multi-condition gates. **Aggregates (2026-11-08):** `[*]`/`[?key=value]`
  projections with `count/min/max/max_abs/sum/mean/all/any` now export the Beer-Lambert,
  CSDA-range and photofraction cross-checks (every check available/within tolerance, worst
  relative error ≤ 5/5/6%, primaries contained, classifier fired) and the driver-recorded MR
  tissue contrast (flags + every tissue detected + r ≥ 0.7) and brain image (flags + r ≥ 0.95,
  recon r ≥ 0.9, grey > white, skull < ½ grey, air < 0.12). All 56 suite verdicts are unchanged
  on the recorded Release runs; a corrupted CSDA containment or relative error flips that case.
  Remaining after this pass: Compton χ²/z-score and pair/photonuclear checks (need statistic
  operators or engine-emitted per-check verdict fields), multi-run energy sweeps, operator/reference
  pair gates and lava/foam/chemistry multi-condition gates; earlier note follows. `family_case`/`family_checks` in the validation
  companion now decide the suite verdict for Pascal, osmosis, H2O molecule/cluster/bulk/D(T),
  glass-of-water waves, CNT band/logic and MR water/image line through the shared
  [`declarative.py`](../../../tools/validation/trech_validation/declarative.py) evaluator, also run
  by `validate_scenario.py`. The first eleven reproduce the prior verdicts on the recorded Release runs;
  a corrupted Pascal contrast flips the suite case to fail. Remaining: analytic cross-checks
  (χ²/z-score/sweep statistics need aggregate operators), operator/reference pair gates,
  lava/foam/chemistry multi-condition gates and the Python-driver MR tissue/brain aggregates,
  plus regenerating `docs/validation_report.*` with the new verdict notes.
- [ ] Full-horizon physics/media regression of the split bundles remains deliberate work;
  migration checks cover config/parameter parity and first-event/end-hook replay. Historical
  media source hashes/paths retain the identity of their actual captures.

## Shared JavaScript scenario libraries (2026-10-30)

- [x] `trech_helpers.js` imports `trech_math.js`, `trech_random.js`, and
  `trech_material_facts.js`, exposing `helpers.math` / `random` / `materialFacts`. Fourteen
  scenarios and the water-MD/foam libraries reuse numerical helpers, seeded sampling, parcel
  noise, recorded-optics readers and comparison-only PubChem identity checks. Uniform
  `observer.linearClock` replaces three duplicated clock mappings while retaining both clocks.
- [x] Dependency imports preserve standalone solver use and share existing instances regardless
  of load order. Importing draws no RNG; Mulberry32's callable API and Gaussian two-draw stream
  remain unchanged. Scenario laws, constants, source labels, optional optics notes and output
  property order remain explicit/preserved; no comparison physics is promoted to Geant4 truth.
- [x] `test_scenario_helpers.cpp` exercises the shared APIs through actual QuickJS: independent
  imports, dependency identity, fixed seeded sequence, RNG method receiver and draw counts,
  finite/clamp/round behavior, frame clocks, source-array immutability, absent optics and
  identity-only PubChem extraction. All 60 saved default scenario inspections match, including
  config/typed parameter declarations; 15 old/new scenario run pairs preserve score/emit/viz
  bytes and provenance except output/CLI paths. Bounded MD/membrane/MR runs cover initialization
  and early evolution; chemistry/thermofluid cases include complete bounded-duration runs.
  Debug and Release CTest pass 28/28 each; the Geant4-free build passes 25/25. The full manual
  all-family physics suite and complete long-duration MD/membrane runs were not rerun.
- [ ] Deeper family-specific duplication (flexible-water force kernels and related membrane
  solver machinery) remains to audit independently. Distinct xorshift streams, geometry/units,
  boundary conditions and piecewise clocks must not be collapsed solely because code looks
  similar. This extraction does not retire the separately tracked authored physics-law residuals.
- [x] Procedural geometry module and neutral environment naming (2026-11-10):
  `js/trech_geometry.js` plus `geometry_procedural_assembly`; 56 scenarios moved from an authored
  `detector` block to `environment` with exact `trech inspect` parity after the key mapping and
  unchanged run config hashes on three sampled scenarios. `scripts/audit_flow_presets.py --all`
  passes 68/68 with the PubChem build cache.
- [ ] Hand-migrate `testscenario_magnetic_resonance` and `testscenario_magnetic_resonance_tissues`
  (they read `detector` fields elsewhere in the script) and adopt `TRECH_GEOMETRY` generators in
  scenarios that hand-place repeated volumes (MRI coil arrays, multi-cell chemistry layouts) only
  with run-byte comparisons.
