# Tests and validation ownership — roadmap

[Root principles](../../../AGENTS.md) · [Root roadmap](../../../ROADMAP.md) · [Parent](../ROADMAP.md) · [Handbook](AGENTS.md)

## Choose a subcategory

| Scope | Context | Work remaining |
| --- | --- | --- |
| Recorded validation snapshots | [AGENTS.md](history/AGENTS.md) | [ROADMAP.md](history/ROADMAP.md) |

Maintain work in its owning branch. Dated results apply to the recorded checkout; they do not validate subsequent changes.

## Completed fixture isolation

- [x] C++ filesystem-writing tests reserve separate temporary directories through
  `tests/TemporaryDirectory.hpp`, using atomic creation rather than fixed global filenames or
  timestamp-only paths. Models/scripts that must share a relative-path bundle stay together within
  one fixture. RAII removes leftovers after ordinary returns and exceptions; abrupt process
  termination can still leave its uniquely named directory. `test_provenance_writer.cpp` covers
  same-name file isolation and recursive cleanup. Optional `TRECH_REFERENCE_EMITS_DIR` output
  remains an explicitly caller-selected debug destination, outside automatic fixtures.
- Verification: Geant4 Debug/Release CTest 36/36 each and optional LibTorch/Geant4-free Release CTest 34/34
  pass. Duplicate simultaneous executions pass for 19 filesystem-writing Debug tests (38 runs)
  and the optional Torch backend (2 runs), using the same working directory for each pair.

## In progress

- [x] Scenario purity report (2026-11-11): `trech_validation.purity` generates
  `docs/TRECH_current_scenarios_purity.md` for all 68 bundles, and CTest
  `trech_scenario_purity_report` fails while it is stale. Residuals:
  - [ ] The static evidence is lexical. It cannot tell input feature scaling
    (`Math.log1p` normalisation) or render-surface math from an authored law. It does not
    analyse expressions inside template literals and cannot see whether a branch is reached.
    Calibrate with `--explain` and move true positives into comparison-named functions.
  - [ ] Model paths built at run time (`path: plan.modelPath`) are counted, not graded.
  - [ ] Performance is only what the committed `docs/validation_report.json` holds (generated
    2026-10-19 at `88c97b9`). The Compton, pair and photonuclear analytic cases and most
    single-family validators (molecular series, particle observer, spectrum prediction) are
    not in it, so those bundles show "none recorded" until a full suite refresh or a
    machine-readable sidecar per dedicated validator exists.
  - [ ] Open review flags: 7 bundles graded B–D still run hand-authored response surfaces
    on the normal path (beaker, Briggs–Rauscher, elephant's toothpaste, glass from sand
    furnace descriptors/conduction, glass of water shaken, lava lamp, polyurethane foam
    descriptors), and `spectrum_prediction` calls inference with no statically resolvable
    model. The ledger owns their migration ([scenario migrations](../../scenarios/migrations/ROADMAP.md)).
  - [x] Opt-in pre-commit hook (`scripts/git-hooks/`) regenerates and stages the report when
    staged paths are relevant or the benchmarks are older than 30 days.
  - [ ] The hook regenerates from the working tree, not the index, so a partially staged
    scenario can produce a report that matches unstaged edits. It can only warn about old
    benchmarks; refreshing them still needs a manual `run_validation_suite.sh`.

- [x] Particle observer validation retains the failed first model and verifies independent
  final-condition accuracy after explicit development selection/freeze. Eighteen final and
  eighteen fresh-MC observer cases pass the original numerical gates, alongside strict/replay/
  exact-count/RMSE checks. The separate old molecular-family gate passes all fifteen runs after
  helper extraction, including 90,000 MC photons. The full all-family physics suite was not
  rerun and its committed report was not refreshed; new observer evidence is in its manifest
  and dedicated validation report. [Scientific gaps](../../engine/inference/ROADMAP.md) remain.

- [x] The strict worker gate checks event/trajectory physics across actual two/eight-worker
  Tasking/MT runs and retains raw output/reduction differences. Optional baseline checks cover
  true Serial and Tasking-one-worker compatibility. Full byte replay remains in the
  [runtime roadmap](../../engine/runtime/ROADMAP.md).

- [x] Explicit `PUBCHEM_MODE=cache-only` suite execution uses only the selected local input
  cache, with complete preflight before builds/output deletion and actionable failures.
  Nine standard-library input/orchestration tests pass; the existing Release cache passes all
  ten required input checks. This verifies input handling, not a new full physics regression.
- [x] Input-cache snapshot hashing/pinning (2026-11-08): cache-only runs write
  `pubchem_input_snapshot.json` (per-record SHA-256 + manifest digest) and `PUBCHEM_SNAPSHOT`
  enforces it before builds; 13 offline tests cover drift, unpinned records, edited manifests,
  mode guard and fail-before-engine. **Report identity (2026-11-09):** the report metadata now
  records the self-verified snapshot digest and record count (`pubchem_inputs`, also flags an
  edited or unreadable snapshot `invalid`); `ReportSnapshotTests` covers recorded/invalid/absent.
  Residual: refresh mode records no snapshot, per-run `trech_provenance.jsonl` does not carry
  the digest, the committed `docs/validation_report.*` has not been regenerated with the new
  line, and hashes do not authenticate records against PubChem itself.

- [x] A reusable manual inference resim gate exercises independent hull/starvation/band policies,
  point/cascade cause counts, feature precedence, strict and disabled paths, event/callback
  isolation, replay and optional pre-change legacy bytes/hashes.
  [Trust workstream](../../engine/inference/trust/ROADMAP.md) owns validation scope and residuals;
  this does not replace the manual all-family physics report.

- **Validation report curation**: 45 cases now (41 pass / 0 fail / 4 info after the
  `polyurethane_operator_matches_reference` trained-operator gate; 44 with 40 pass after the
  `polyurethane_foam_expansion` + `elephants_toothpaste_eruption` reactive-foam guards; 42 with 38
  pass after the `briggs_rauscher_oscillation` guard; 41 with 37 pass after the
  `lava_lamp_inferred_thermofluid` guard; 40 with 36 pass after the beaker guard; 39 with 35 pass
  after `glass_of_water_shaken_waves`; 38 with 34 pass after the `magnetic_resonance_brain_image`
  guard; 37 with 33 pass after the `magnetic_resonance_image_line` guard; 36 with 32 pass after the
  `magnetic_resonance_tissue_contrast` guard; 35 with 31 pass after the
  `magnetic_resonance_water` guard; 34 with 30 pass after the `generic_surrogate_inference` guard;
  33 with 29 pass after the photo-fraction analytic guard; 32 after the CSDA-range guard and
  scenario-viz refresh; 31 after CNT logic gates; 30 after the H2O electrolysis +
  inverse-combustion cycle and efflux runtime-PubChem/event-drive alignment; 17 at first commit —
  12 pass, 4 info, 1 was wrong-spec and is now structural numeric replay — plus analytic
  Beer-Lambert, h2o_fluid brine, Pascal/osmosis/efflux/H2O-cycle fluid guards, end-to-end
  optics-surrogate transport, anti-degeneration sampling diversity, CNT electronic structure, and
  the Sputnik molecular-scale guards). The operator case grades eight observer gaps plus 13 trust
  checks; the lava case adds 23/23 contracts over Geant4/cascade provenance, persistent state,
  duration independence, heater-condition response, bounded volumetric motion, non-axis-locked
  x/y/azimuth transport, retained parcel-scale lineage, fluid-interface coalescence/fission,
  temporally coherent topology, dense README cadence, independent precision axes, and
  fixed-inventory refinement convergence. Expand coverage as new outputs/scenarios land. Treat
  `docs/validation_report.md` as a regression artefact: re-generate via
  `scripts/run_validation_suite.sh` whenever the engine or scenarios change, and commit the
  regenerated report alongside the code change.
- **Torch surrogate adoption**: the `OpticsSurrogate` C++ path + the Python trainer are wired and degrade gracefully when Torch is unbuilt. (a) curated dataset **landed** (`optics_training_panel.js` + engine-emitted `element_mass_fractions` + `data/optics_handbook_anchors.json`); (c) held-out validation **landed** (`scripts/validate_optics_surrogate.py`, in `run_validation_suite.sh`); (d) **transport feed landed without LibTorch** — a ridge `.json` backend (`data/optics_surrogate_ridge.json`) makes the validated model feed transport in a stock build (`TRECH_ENABLE_TORCH` no longer required for the surrogate path), cross-checked C++↔Python and guarded by `tests/test_optics_surrogate.cpp`; (b) **CI retrain/re-export landed** — `run_validation_suite.sh` re-fits + re-exports the ridge model from the freshly-derived panel each run (so `git diff data/optics_surrogate_ridge.json` flags drift), and a new end-to-end suite case (`optics_surrogate_transport_applied`, via `examples/scenarios/optics_surrogate_demo/optics_surrogate_demo.js`) asserts the learned NaI n (~1.77, where the f-sum extractor fails at ~1.33) actually reaches transport's RINDEX samples. (e) **event-stratifier learned path + dimension-scale tooling landed 2026-07-02** (see the [recorded landing note](history/ROADMAP.md)): a LibTorch-free logistic `.json` stratifier backend, a shared dataset harvester, an event-stratifier trainer, an improved optics trainer, and an active-learning Geant4 experiment planner. (f) **generic surrogate — Torch usable in ANY scenario landed 2026-07-02** (see the [recorded landing note](history/ROADMAP.md)): `models: [{name, path}]` config + `ctx.predict` hook API + `GenericSurrogate` C++ + `trech-train-surrogate`, so any scenario (present or future) attaches a learned model without new engine call-sites. (g) **multi-scale inference cascade landed 2026-07-05** — `ScaleCascade` + `ModelConfig.scale` + `ctx.cascade` generalize the per-call `ctx.predict` point-predictors into an auto-chained, Geant4-seeded ladder (the general-purpose direction of the "Multi-scale statistical inference" standing objective); the remaining work there is training real per-band stages, not more plumbing. (h) **canonical glass-of-water cascade landed 2026-07-11** — `examples/scenarios/glass_of_water_shaken/glass_of_water_shaken.js` is the first *worked, rendered* observer-scale cascade: a nano MD measures water's number density + H-bond coordination, `ctx.cascade` lifts them nano→micro→macro into the fluid parameters of a Position-Based-Fluid (spatial grid, ~4,300 particles at ~6 mm) that pours ~1 L into a wide glass, settles, and shakes it (waves/splashes, contained, stable), with **no macroscopic water property typed** and the recovered rest density (999 kg/m³) landing 0.1% off measured as a check; stage models `data/glass_cascade/` (density grounded, cohesion/viscosity illustrative), guarded by `glass_of_water_shaken_waves`, rendered `tools/viz/demos/render_glass_of_water_shaken.py` (2 mm metaball isosurface). Remaining: (optionally) building LibTorch only for the TorchScript `.pt` backends / multi-output (abs, scat) optics models; resim-confirmed teacher labels feeding stratifier retraining.
