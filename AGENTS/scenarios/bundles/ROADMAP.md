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
- [partial: 16 families exported 2026-11-08] Export Python family-validation evaluators/tolerances
  as a common declarative runner schema. **Aggregates (2026-11-08):** `[*]`/`[?key=value]`
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
