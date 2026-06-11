# AGENTS.md

Guidance for agents working in this repository.

## Directives for AI agents
- At every action, update markdowns (README, ROADMAP and AGENTS for fast references access)
- Keep `CHARTS.md` updated when architecture, dataflow, or Geant4 integration changes.
- High priority: treat "implementation" as C++ source changes under `src/` (documentation-only updates do not count).
- When Geant4 is needed, check for a local clone at `thirds/geant4` before asking for it.
- Avoid writing absolute Geant4 paths in-repo; use relative paths such as `thirds/geant4-build` or `thirds/geant4-install`.
- Prefer building Geant4 into `build/geant4-build` and installing to `build/geant4-install` to keep submodules clean.
- Build artifacts under `build/` are gitignored; keep them local-only.

## Core references

- Initial roadmap concept (reference-only; do not edit): `docs/trech-roadmap.md`
- Baseline structure: `docs/structure.md`
- Architecture charts (Mermaid): `CHARTS.md`
- Short-term plan (editable source of truth): `ROADMAP.md` (keep this updated as work progresses)
- Scenario hook proposal: `docs/scenario_hooks.md`
- H2O experiment spec: `examples/experiments/h2o_fluid_spec.md`
- H2O experiment stub: `examples/experiments/h2o_fluid.js`
- H2O single-molecule proxy stub: `examples/experiments/h2o_single_molecule.js`
- H2O molecular-dynamics ladder (Sputnik, classical MD in the hook layer): single molecule `examples/experiments/h2o_molecule_stability.js`, cluster droplet `examples/experiments/h2o_cluster_fluid.js`, periodic bulk + g(r) `examples/experiments/h2o_bulk_water.js`
- H2O cluster-fluid MD (Sputnik fluid-behavior step): `examples/experiments/h2o_cluster_fluid.js`
- H2O optics beam stub: `examples/experiments/h2o_optics_beam.js`
- Nitrogen-carbon cycle scenario: `examples/experiments/config_nitrogen_carbon_cycle.js`
- Optics spectrum example: `examples/experiments/config_optics.js`
- JS helpers module: `examples/experiments/trech_helpers.js`
- JS multi-beam example: `examples/experiments/config_multi_beam_units.js`
- JS flow authoring example: `examples/experiments/config_flow_language.js`
- JS hook dispatch example: `examples/experiments/config_hook_dispatch.js`
- JS include error demo: `examples/experiments/include_error_demo.js`
- CNT stub experiment: `examples/experiments/config_cnt_stub.js`
- CNT world stub experiment: `examples/experiments/config_cnt_world_stub.js`
- CNT optics stub experiment: `examples/experiments/config_cnt_optics_stub.js`
- CNT reference: `docs/CNT/BackToTheCarbon.md`
- Output schema: `docs/output_schema.md`
- Validation summary: `docs/validation_summary.md`
- Real-time lab bootstrap config: `examples/lab/realtime_lab_bootstrap.json`
- Real-time lab command stream example: `examples/lab/realtime_lab_commands.jsonl`
- Viz refraction demo scenario: `examples/experiments/viz_refraction_demo.js`
- Glass-of-water scenarios: `examples/experiments/validation_glass_of_water.js` (strict single photon), `glass_of_water_varied.js` (spread source), `glass_of_water_spectral.js` (blackbody spectrum → chromatic dispersion)
- Bulk-water comparison video (MD snapshots + engine g(r) vs measured 2.80 Å peak): `tools/viz/demos/render_bulk_water.py` (consumes `md_snapshot` hook emits from `h2o_bulk_water.js`)
- Viz refraction design note: `docs/viz_refraction.md`
- Python 3D viewer (PyVista): `tools/viz/` (entry point `tools/viz/trech_viz/__main__.py`, console script `trech-viz`)
- MolecularOptics extractor: `include/trech/sim/MolecularOptics.hpp` + `src/sim/MolecularOptics.cpp`
- Viz trajectory recorder: `include/trech/sim/VizRecorder.hpp` + `src/sim/VizRecorder.cpp`
- Online event stats (Welford + optional Torch): `include/trech/ml/OnlineEventStats.hpp` + `src/ml/OnlineEventStats.cpp`
- Optics surrogate (TorchScript `.pt` + LibTorch-free ridge `.json` backends): `include/trech/ml/OpticsSurrogate.hpp` + `src/ml/OpticsSurrogate.cpp`; ridge math test `tests/test_optics_surrogate.cpp`
- Optics surrogate trainer (Python, TorchScript): `tools/torch/trech_torch/train_optics_surrogate.py`
- Optics surrogate ridge export + held-out validator: `scripts/validate_optics_surrogate.py --export data/optics_surrogate_ridge.json`; deployable model committed at `data/optics_surrogate_ridge.json`
- Optics surrogate demo (opt-in, corrects NaI where the f-sum fails): `examples/experiments/optics_surrogate_demo.js`
- Validation suite (Python): `tools/validation/trech_validation/` (CLI `python -m trech_validation`)
- Validation report (committed to git for regression tracking): `docs/validation_report.md` + sidecar `docs/validation_report.json`
- Validation orchestrator: `scripts/run_validation_suite.sh`

## Strategic goals (Sputnik milestone)

- Define the "Sputnik" milestone as H2O fluid simulation with Geant4 at the highest practical subatomic detail.
- Secondary reference (not first priority): simulate carbon nanotube variants (structure, chirality, diameter) and electron behavior differences, including Fermi gap modeling, per `docs/CNT/BackToTheCarbon.md`.
- In parallel, build learning-based event stratification to separate predictable events from exceptional ones that must be re-simulated.
- Optimize large-scale runs with congenial multi-scale methods (e.g., Lattice Boltzmann, variance reduction, reduced-order models).
- Use Geant4 with the "right creativity" to maximize available physics and tooling without breaking the JS -> JSON boundary (hooks must remain deterministic and logged).
- Treat photon transport as a key Geant4 focus: scattering, absorption, refraction, and color response in molecular volumes.
- Use the CNT parallel track to stress-test config/output coherence with the H2O baseline; avoid schema fragmentation.

## Repository layout

- Public headers: `include/trech`
- Implementations: `src/`
- CLI entrypoint: `apps/trech-cli/main.cpp`
- JS experiments: `examples/experiments/`
- Tests: `tests/` (CTest, minimal)
- CMake helpers: `cmake/`
- Third-party deps: `thirds/` (QuickJS, Geant4, nlohmann/json)

## Key invariants

- JS is a programmable authoring runtime: experiments set global `TRECH_CONFIG` to an object, JSON string, or function returning one; `TRECH_HOOKS` is optional and must stay deterministic/provenance-aware.
- Real-time lab bootstrap path is available via `trech lab`: runtime accepts canonical JSON config plus deterministic command stream actions (`patch`, `simulate`, `snapshot`, `help`, `quit`) without requiring fixed JS scenarios.
- Hook runtime callbacks consume deterministic `ctx` payloads (`config`, `runtime`, optional `event`/`step`, persistent `state`, deterministic `rng`, and `emit`) and may return whitelisted `onInit` overrides.
- `TRECH_FLOW(initial)` is available for flow-like JS authoring with fluent deterministic transforms/checks (`set`/`defaults`/`merge`/`push`/`ensureArray`/`derive`/`selectBeam`/`normalizeDetectorAliases`/`finalize`/`require`/`assert`/`when`/`tap`/`build`) before JSON handoff.
- `TRECH_INCLUDE` is available for modular JS experiments; include paths resolve relative to the caller and preserve file/line references.
- Determinism is explicit via `determinism.mode` (`strict`/`predictive`): strict runs remain reproducible and disable model inference paths; predictive mode permits model inference and provenance capture.
- `run.threads` (default 0 = Geant4's MT default) sets the worker-thread count; `GeantRunner` calls `SetNumberOfThreads` when it is positive (conditionally serialized to preserve config hashes). Hook-driven scenarios whose state accumulates across events (e.g. the MD baths in `testscenario_pascal`/`osmotic`, one tick per event) must set `threads: 1` — MT distributes events across threads, so their completion order otherwise makes the accumulation non-reproducible for a fixed seed.
- Long-term: keep the C++ config surface physics/chemistry agnostic; JS scenarios and lab command streams should express combinations.
- Avoid hardcoding domain-specific switches in C++; define physics/chemistry classes, properties, and extensions in JS scenarios.
- H2O milestone scenarios remain JS-authored (single-molecule proxy + optics beam); keep C++ as the generic engine.
- LibTorch/TorchScript is the chosen ML runtime for online learning from simulation outputs.
- System abstraction is point-agnostic: `system.*` defines ensemble aggregation and `trech_scores.jsonl` emits `system_*` density metrics plus event energy moments (`system_event_*`) and volume source (config volume overrides medium box/world).
- TorchScript feature schema is `FeaturePipeline::kSchemaId` (`trech_event_features_v1`) with order: `total_edep_mev`, `total_track_length_mm`, `total_step_count`, `total_track_count`, `optical_photon_steps`, `optical_photon_tracks`, `optical_photon_track_length_mm`.
- TorchScript inference (when `TRECH_ENABLE_TORCH` + `stratify.modelPath` is set) expects a label string output or a 1-2 value tensor; tensor outputs map to `stratify.labelPredictable`/`stratify.labelExceptional`.
- Optical physics is toggled via `optics.enable`; photon scoring fields are emitted when enabled, and the medium box environment is driven by `detector.mediumBoxMm`, `detector.mediumMaterial`, `temperatureK`, and `pressureAtm`.
- `optics.spectrum` (optional) can provide energy/wavelength dependent refractive index, absorption, and scattering values for color response.
- Event stratification output is emitted to `trech_event_scores.jsonl` when `stratify.enable` is true, using thresholds/labels from `stratify.*` and ML stubs if configured.
- Stratification feature dumps and resim queues are emitted when `stratify.dumpFeatures` or `stratify.dumpResimQueue` are enabled.
- Chemistry/DNA wiring toggles Geant4-DNA EM physics when `chemistry.enable` and `TRECH_ENABLE_DNA_CHEM` are set; `chemistry.solver` (non-`stub`) enables the chemistry stage.
- Nuclear cycle analysis is scenario-driven via `nuclear.enable` + `nuclear.cycles`; each cycle declares source/target isotope hints and forward/backward reaction participants (`{z,a}` ions or Geant particle names) for Geant-backed Q-value + conservation checks.
- Multi-scale wiring is stubbed behind `multiscale.enable` and does not alter physics yet.
- Keep the JS -> JSON -> C++ boundary stable; avoid binding Geant4 directly into JS (hooks are sideband, not direct Geant4 access).
- Collections should use plural names and accept either single-object or array inputs; loaders normalize to arrays (materials/components/tags/optics.spectrum/hooks.registered accept single values).
- `beams` arrays are normalized in the loader (active/first is selected); `beam` remains a single-entry alias.
- Beam source variety draws from Geant4's seeded engine: `beam.originMm` + `beam.spread` (`spotRadiusMm`/`divergenceDeg`/`energySpreadFractional`) spread position/direction/energy; `beam.polarization` (`""`/`unpolarized` → random transverse linear state per event; `linear` + `polarizationAngleDeg` → fixed; `none` → legacy Geant4 fallback) controls optical-photon polarization; and `beam.spectrum` (a weighted line list — each entry `{energyMeV|energyEv|wavelengthNm, weight}`) makes each event sample a line by weight instead of the single `energyMeV` (then `energySpreadFractional` broadens it). Polarization applies only to optical photons (other particles untouched) and kills the `ZeroPolarization` warning by default. All of these are conditionally serialized so existing config hashes hold and are owned by `TrechPrimaryGeneratorAction`; keep it reproducible under a fixed seed. The JS `spectra` helper (`blackbody`/`whiteVisible`/`lines`) generates spectrum tables and `helpers.beamProfiles.spread(name, overrides)` provides named spread presets (`pencil`/`laser`/`ledLamp`/`flashlight`/`sunbeam`) so the engine stays physics-agnostic.
- JS runtime error stacks should include filenames and line numbers (including `TRECH_INCLUDE` sources); keep `tests/test_js_runtime.cpp` up to date.
- Hook dispatcher telemetry is deterministic and score/provenance-aware: init/run/event/step callback points emit `hook_on_*` counters, unknown registrations are counted, `hooks.maxStepCallbacks` bounds recorded step callbacks, emit guardrails (`hooks.maxEmitsPerCallback`, `hooks.maxEmitPayloadBytes`) bound per-callback `ctx.emit`, and patch/emit totals (`hook_patch_count`, `hook_emit_count`, `hook_emit_dropped_count`) are persisted.
- Avoid leaning on collider-specific terminology in new features; top-level `environment`/`medium` aliases for `detector` are supported at parse time (canonical config output remains `detector`).
- Geant4 wiring order stays canonical: RunManager -> DetectorConstruction + PhysicsList + ActionInitialization -> Initialize -> BeamOn.
- Provenance is written as JSONL to `trech_provenance.jsonl` (output dir) and includes config JSON/hash, seed, Geant4/runtime metadata, determinism mode, stratify model path/hash metadata, run-end stratify source counters, hook registration/dispatch guardrail counters, patch/emit totals, and system event moment summaries.
- Scoring summaries are written as JSONL to `trech_scores.jsonl` (output dir).
- Hook emit payload records are written as JSONL to `trech_hook_emits.jsonl` (output dir) with `hook`, `event_id`, `step_index`, `tag`, and parsed `payload`.
- Run-level scoring includes chemistry/DNA flags, option metadata, stratification summary counts, per-volume energy deposits (`volume_edep_mev`), and nuclear cycle summaries (`nuclear_cycle_count`, `nuclear_consistent_cycle_count`, `nuclear_cycles`) when enabled.
- Geometry volumes (`geometry.volumes`) define named shapes, placements, materials, and optional `scoreEdep` flags.
- Custom mixtures can be declared in `materials` (density + component fractions) and referenced by name in detector or volume materials. Each component is either a `material` (NIST `G4_*` or a previously-declared custom mixture) or an `element` symbol (e.g. `{ element: "Na", fraction: 0.39 }`) — element components let scenarios build compounds Geant4 has no NIST entry for (there is no `G4_SODIUM_CHLORIDE`). `buildCustomMaterials` resolves every component before constructing the `G4Material`, mass-fraction-renormalizes over what resolved, and warns + skips unresolvable components/materials rather than leaving a malformed material (which previously crashed Geant4's table builders).
- `materials` accepts an optional `smiles` field as a placeholder for future registry metadata.
- If using `G4_*` materials, document or wrap them via shared JS presets so definitions are visible to scenario authors.
- Volume placement is scenario-defined: use `placement.parent = "medium"` to sit inside the medium box, `"world"` for world placement, or named containers for nested assemblies (containers typically use vacuum material).
- CNT investigations prioritize electron transport behavior; optical photons are a secondary comparison in mixed tests.
- ML scale-up path: Geant4 outputs -> dataset -> Torch training/finetuning -> accuracy/coverage gates -> TorchScript inference, with resim when confidence is low (see `CHARTS.md`).
- Material optical constants (n, absorption length, scatter length) must be derived from Geant4 particle-level cross sections when `optics.derive.enable` is true; the `MolecularOpticsExtractor` queries `G4EmCalculator` (photoelectric + Compton + Rayleigh), builds the imaginary refractive index via Beer-Lambert, and recovers the real part via a discrete Kramers-Kronig transform over the wide-energy extinction spectrum. Handbook references live only under `optics.derive.validate.references` for logged deltas — they must never feed back into the **extractor** (the physics derivation stays anchor-free). The opt-in `OpticsSurrogate` (`optics.derive.surrogateModelPath`) is the one sanctioned exception: it is an ML layer *trained* on the handbook anchors and, when configured, shifts the derived dispersion curve to its predicted level in transport. It is leave-one-out validated for generalisation (and memorises in-panel materials), so it is off by default and the headline physics demos never set it.
- Viz outputs are gated on `viz.enable`. The scene manifest (`trech_viz_scene.json`) and the sampled trajectory log (`trech_viz_trajectories.jsonl`) are the only artefacts the 3D viewer consumes; the C++ engine must keep them in sync with `docs/output_schema.md`.
- Trajectory sampling is deterministic via `viz.sampleEveryNth` (stride mixed with `run.seed`), `viz.maxTrajectories` (hard cap), and `viz.maxSegmentsPerTrajectory` (per-track truncation). The `VizRecorder` is a singleton with a single mutex; SteppingActions on Geant4 workers may push into it concurrently and the master flushes on `EndOfRunAction`. Each recorded point's `dx/dy/dz` is the momentum direction of its *outgoing* segment: post-step points carry the post-boundary (refracted/reflected) direction, and the birth point carries the **pre-step (emission)** direction (`GetPreStepPoint()->GetMomentumDirection()` — not the track's post-step `dir`, which would mis-record emission for a photon that interacts on step 1). For geometry-derived analysis prefer the point-to-point displacement, which is robust regardless.
- Visualization-only forcing is allowed on volume `tags`: `viz_emitter` and `viz_forced_white` make the viewer render a fixed look regardless of derived optics. Tags must never alter Geant4 transport.
- Validation report (`docs/validation_report.md`) is committed alongside code changes. Regenerate with `scripts/run_validation_suite.sh` whenever physics/output surface changes; the Markdown layout is intentionally stable (alphabetical case order, fixed columns) so `git diff` between commits shows physical-consistency deltas cleanly.
- Per-event feature accumulation runs unconditionally now (no longer gated on `stratify.enable`); both the stratifier and `OnlineEventStats` consume the same `EventFeatures` snapshot. `trech_scores.jsonl` always carries `event_feature_stats` and `event_feature_stats_torch_backed`.
- Primary fate accounting: `primaries_emitted` (per-event vertex count), `primaries_transmitted` (primaries exiting the world via `fWorldBoundary`), `primaries_absorbed` (primaries killed elsewhere) — emitted in `trech_scores.jsonl`. Beer-Lambert-style transmission validations rely on this triple.
- Torch integration ladder: stratifier classifier (`TorchScriptStub`) -> online event stats (`OnlineEventStats`, vectorized accumulator when `TRECH_ENABLE_TORCH`) -> optics surrogate (`OpticsSurrogate`, `(n, abs, scat)` prediction loaded via `optics.derive.surrogateModelPath`). All degrade gracefully when Torch is not built. `OpticsSurrogate` has **two backends chosen by the model file**: a TorchScript `.pt` module (needs `TRECH_ENABLE_TORCH`) and a **LibTorch-free ridge `.json`** (standardised linear `n = bias + Σ wᵢ(xᵢ-meanᵢ)/stdᵢ`) — the latter is the validated composition→n model exported by `scripts/validate_optics_surrogate.py --export`, so the surrogate path works in a stock build. The ridge backend predicts n only (abs/scat carry a negative "not predicted" sentinel; the caller keeps its extractor values). Composition schema (`kCompositionElements`, now 14 element slots incl. `I` + density) must stay in lock-step across the C++ surrogate, the TorchScript trainer, and the ridge validator; the C++ ridge math is guarded by `tests/test_optics_surrogate.cpp`.

## Dependencies

- QuickJS sources live under `thirds/quickjs/quickjs` (or configure with `TRECH_FETCH_DEPS=ON`).
- Geant4 is a required submodule at `thirds/geant4` (init with `git submodule update --init --recursive`); build/install it and set `Geant4_DIR` or `CMAKE_PREFIX_PATH`.
- LibTorch is optional for `TRECH_ENABLE_TORCH`; point `Torch_DIR` or `CMAKE_PREFIX_PATH` at the LibTorch install.
- nlohmann/json can be vendored under `thirds/json` (or fetched).

## Build

```
cmake --preset dev
cmake --build --preset dev
./build/dev/trech run examples/experiments/hello_world.js
```

Options: `TRECH_ENABLE_GEANT4`, `TRECH_ENABLE_DNA_CHEM`, `TRECH_ENABLE_TORCH`, `TRECH_FETCH_DEPS`.

CLI flags: `--macro`, `--ui`, `--output`, `--seed`, `--events`; lab mode also supports `--config` and `--commands`.

## Validation script

```
scripts/run_validation.sh
```

Requires Ninja, a C++ compiler, and Python 3. Env overrides: `BUILD_PRESET`, `EVENTS`, `SCORES_FILE`, `PROVENANCE_FILE`, `SUMMARY_FILE`.
Requires Geant4 for the H2O validation run.
Successful runs update `docs/validation_summary.md` via `scripts/update_validation_summary.py`.
CTest runs via presets when available.

## Smoke test script

```
scripts/run_smoke.sh
```

Requires Ninja and a C++ compiler. Env override: `BUILD_PRESET`. Runs `ctest` after building (uses presets when available).

## Validation status

- `ctest --preset dev` passed (latest run); optics spectrum smoke run completed with `examples/experiments/config_optics.js` (`--events 50`, output `build/dev/out_optics_spectrum`).
- H2O single-molecule proxy stub run completed with `examples/experiments/h2o_single_molecule.js` (`--events 50`, output `build/dev/out_h2o_single`).
- H2O optics beam stub run completed with `examples/experiments/h2o_optics_beam.js` (`--events 50`, output `build/dev/out_h2o_optics`).
- CNT smoke runs completed with `examples/experiments/config_cnt_stub.js` and `examples/experiments/config_cnt_world_stub.js` (`--events 5`, outputs `build/dev/out_cnt`, `build/dev/out_cnt_world`); stubs now use container volumes with explicit materials (diameter 3.0 nm, wallCount 5) and a 0.8 MeV electron beam, rerun to refresh outputs.
- CNT optics smoke run completed with `examples/experiments/config_cnt_optics_stub.js` (`--events 5`, output `build/dev/out_cnt_optics`); stub now uses a 1.2 MeV electron beam with thicker walls (diameter 3.0 nm, wallCount 5) and `volume_edep_mev` scoring, rerun to refresh outputs.
- CMake target link dependencies trimmed to avoid duplicate `libtrech_core.a` warnings on macOS.
- QuickJS header warnings are suppressed for the `trech_js` target via scoped compile flags (Clang/GNU).
- `examples/experiments/h2o_fluid.js` SIGSEGV **fixed** (2026-06-06): `G4_SODIUM_CHLORIDE` is not a Geant4 NIST material, so `buildCustomMaterials` silently dropped the component and left a malformed `G4Material` (declared > added) that crashed Geant4's cut/table builders. Fixed via `MaterialComponentConfig.element` (build NaCl from Na+Cl) plus fail-safe material building (resolve up front, warn + renormalize/skip unresolvable, never construct a half-built material). h2o_fluid now runs clean (@50 events: 50/50 primaries, total_edep 12.66 MeV); full scenario sweep is green except the by-design `include_error_demo`.
- `examples/experiments/config_chemistry_stub.js` run completed with `--events 5` and `--output build/dev/out_chem`; `trech_scores.jsonl` includes chemistry/DNA fields.
- Nitrogen-carbon cycle scenario run completed with `examples/experiments/config_nitrogen_carbon_cycle.js` (`--events 5`, output `build/dev/out_nitrogen_cycle`); scores/provenance now include nuclear cycle consistency counters and detailed reaction/Q-value records.
- Geant4 build/install is available at `build/geant4-install` from submodule `thirds/geant4`; point `Geant4_DIR` or `CMAKE_PREFIX_PATH` there when rebuilding.
- Multi-beam helper run completed with `examples/experiments/config_multi_beam_units.js` (`--output build/dev/out_multi_beam`); `trech_scores.jsonl` recorded `total_edep_mev` 25.0, `system_volume_mm3` 1000000.0, `system_edep_mev_per_mm3` 2.5e-05 (`QBBC`, optics disabled).
- Flow-language scenario run completed with `examples/experiments/config_flow_language.js` (`--events 1`, output `build/dev/out_flow_language`); provenance normalized `environment` alias fields under canonical `detector`.
- `ctest --preset dev -R trech_js_runtime` passed; includes test coverage for `TRECH_INCLUDE` error filenames/line numbers plus flow-style `TRECH_CONFIG` + `TRECH_FLOW`.
- Determinism/provenance smoke run completed with `examples/experiments/config_stratify_ml.js` (`--events 1`, output `build/dev/out_determinism`); emitted determinism fields and stratify model hash/source metadata in outputs.
- Hook runtime extension smoke run completed with `examples/experiments/config_hook_dispatch.js` (`--output build/dev/out_hook_runtime_ext`); scores/provenance include `hook_patch_count` + `hook_emit_count`, and `trech_hook_emits.jsonl` captured deterministic emit payloads.
- Hook emit guardrails now enforce per-callback caps + payload-size caps (`hooks.maxEmitsPerCallback`, `hooks.maxEmitPayloadBytes`); scores/provenance include `hooks_guardrail_max_emits_per_callback`, `hooks_guardrail_max_emit_payload_bytes`, and `hook_emit_dropped_count`.
- Lab runtime bootstrap landed: `trech lab` supports a live JSON command stream (stdin or `--commands` file) and canonical `lab.*` config metadata for real-time interaction prep; smoke run completed with `examples/lab/realtime_lab_bootstrap.json` + `examples/lab/realtime_lab_commands.jsonl` (`--output build/dev/out_lab_boot`).
- Refraction viz smoke run completed with `examples/experiments/viz_refraction_demo.js` (`--events 60`, output `build/dev/out_viz_refraction`); derived optics produced n_glass > n_water > n_air ordering (now 1.47217 / 1.33075 / 1.00038 — at ~handbook after the f-sum valence oscillator landed, up from the earlier KK-truncation-low 1.00582 / 1.00118 / 1.00001) with `modelValidMinEv = 100 eV`. `trech_viz_scene.json` + `trech_viz_trajectories.jsonl` populated; `trech_scores.jsonl` carries `viz_enabled`, `viz_trajectories`, `viz_segments`. Reference deltas vs handbook values logged in `derived_optics[].reference_deltas` (see `docs/viz_refraction.md`).
- Optical-photon polarization sampling landed in `TrechPrimaryGeneratorAction` + `BeamConfig` (`beam.polarization`, default unpolarized): the `ZeroPolarization` warning is gone (count 0/photon), `ctest --preset dev` passes (8/8, round-trip covers polarization), and a fixed s/p discrimination run confirms Geant4 honors the set polarization (air→glass reflects 51 s-pol vs 23 p-pol, ~Fresnel R_s/R_p). Glass-of-water demo runs (`out_validation_gow` @4000, `out_gow_varied` @2000) + `tools/viz/demos/*.mp4|gif` regenerated with the current engine; `scripts/run_validation_suite.sh` re-run (now 18 cases, 14 pass / 0 fail — added an h2o_fluid brine scenario guard) with optics recovery water 99.3% / glass 102.6% and inverse-Fresnel/Snell unchanged to ULP.
- Emission spectra landed (`beam.spectrum` + `spectra` JS helper): `glass_of_water_spectral.js` (`--events 3000`) samples a 5778 K blackbody across the visible band (wavelength stddev 22.9 → 102 nm); ctest 8/8 (round-trip covers spectrum). Fixed two pre-existing `tools/viz` CLI bugs found while rendering it (`Beam.active` missing; polyline implicit vertex cells breaking per-segment `rgb`) — `trech-viz --screenshot` now works and shows the chromatic fan with derived n(λ) dispersion (violet refracts more).
- Fluid-physics validation cases added: the validation suite now reads hook emits (`RunOutputs.hook_emits`) and asserts the Pascal's-principle and osmosis scenarios' own physics validations (`out_pascal` rigid≪deformable wall displacement + `pascal_principle_holds`; `out_osmotic` `dimensional_exclusion_holds` + `osmotic_shift_observed`). Wired into `scripts/run_validation_suite.sh` (`SKIP_FLUID`, `N_EVENTS_PASCAL`/`N_EVENTS_OSMOTIC`). These hook-MD scenarios were non-deterministic under MT (osmosis flux 77/67/73 for a fixed seed) until `run.threads: 1` was added — now reproducible and the committed report is byte-stable.
- Optics surrogate suite integration landed: `run_validation_suite.sh` re-exports the ridge model from the fresh panel (`SKIP_SURROGATE`, `RIDGE_MODEL`; drift shows in `git diff data/optics_surrogate_ridge.json`) and runs `optics_surrogate_demo.js` so the `optics_surrogate_transport_applied` case can assert the learned NaI n (~1.77) reaches transport's RINDEX samples (the f-sum extractor alone gives ~1.33). Confirmed earlier that derived `n(λ)` feeds transport `RINDEX` (per-energy vector via `attachToMaterial`); the ~0.006 visible-band dispersion is too small to resolve from transport-angle noise, so it is tracked via the derived scene samples, not a transport validator.
- Anti-degeneration sampling-diversity case landed (`sampling_diversity_non_degenerate`, category `degeneration`): `run_validation_suite.sh` runs `glass_of_water_varied` (`N_EVENTS_VARIED`) and the case asserts a real sampled distribution (>1 distinct primary exit point / incidence-angle stddev >0 / wavelength stddev >0) vs the degenerate 1 / 0° / 0 nm baseline — making the primary standing objective a tracked regression signal. The incidence metric uses the first-segment displacement (robust), matching `scripts/degeneration_metrics.py`. Suite is now 22 cases (18 pass / 0 fail), ctest 9/9.
- Sputnik single-molecule stability landed (`examples/experiments/h2o_molecule_stability.js`): the north-star "stable H2O molecule without exploding" item, as a classical flexible-water MD (harmonic O-H bonds + H-O-H angle, velocity-Verlet NVE) run in the deterministic hook layer (`threads: 1`, no RNG → byte-reproducible). Over 400 fs the bonds ring around equilibrium (mean 0.958 Å, max 1.157 Å), angle stays at 104.5°, total energy drifts <0.5%. The `h2o_molecule_bonds_stable` validation case (category `molecule`) guards it. Honest scope: Geant4 transports particles but cannot form/evolve bound molecular states, so the bonds are classical MD with Geant4 as the per-tick clock.
- Sputnik H2O fluid-behavior step landed (`examples/experiments/h2o_cluster_fluid.js`): extends the single molecule to an 8-molecule ensemble with intermolecular forces (LJ on O-O + soft-cored Coulomb on SPC charges, Berendsen-like thermostat, soft droplet boundary standing in for the bulk). It settles into a stable hydrogen-bonded liquid-like droplet (~10.5 O-O contacts, Rg ~2.9 Å bounded, ~313 K) that neither evaporates nor collapses over 2400 fs; byte-reproducible (seeded mulberry32 RNG + `threads: 1`). The `h2o_cluster_fluid_stable` case (category `fluid`) guards it; byte-reproducible. Next was periodic bulk — now landed.
- Sputnik bulk-water step landed (`examples/experiments/h2o_bulk_water.js`): 48 molecules in a periodic box at liquid density, minimum-image + damped-shifted-force (DSF) real-space Coulomb (Fennell-Gezelter, an Ewald alternative). It reproduces the measured liquid structure — the O-O g(r) first peak at **2.798 Å** (experiment 2.8 Å), at a controlled temperature; guarded by `h2o_bulk_water_structure`. Honest residual: a small flexible-SPC + short-cutoff model over-counts coordination (~5 vs ~4.3), reported not tuned. The inner pair loop is inlined (no per-pair array allocation) since QuickJS pays heavily for GC there; it is the slowest scenario (~50 s), so `run_validation_suite.sh` gates it behind `SKIP_BULK`. Suite is now 25 cases (21 pass / 0 fail), ctest 9/9.
- Bulk-water comparison video landed (2026-06-11): `h2o_bulk_water.js` now emits a deterministic `md_snapshot` every 10 ticks (per-molecule-wrapped [O,H,H] positions + the running g(r) histogram — viz sideband only; the bulk_summary physics is byte-identical) and `tools/viz/demos/render_bulk_water.py` renders the periodic box next to the engine's accumulating O-O g(r) vs the measured 2.80 Å hydrogen-bond peak (amber experiment marker / green TRECH curve, same palette as the glass-of-water demo; end card states the coordination over-count honestly). Outputs `tools/viz/demos/h2o_bulk_water_gr.mp4|.gif`, embedded in README. Note for reused off-screen PyVista plotters: call `plotter.render()` before each `screenshot()` or every frame silently repeats the first.
- Full comparison re-run (2026-06-11, this session): ctest 9/9; `scripts/run_validation_suite.sh` 25 cases 21 pass / 0 fail with the report diff vs the 2026-06-07 baseline only timestamp/SHA + last-ULP float noise (no physics drift, no ridge-model drift); glass-of-water videos re-rendered from the fresh runs — physics vs TRECH exit angles 30.00° / 30.00°, ray gap 0.0 mm.
- Sputnik bulk-water scale-up landed (2026-06-11): `h2o_bulk_water.js` N 48 → 108 molecules (box 14.8 Å), DSF cutoff 5.4 → 7.0 Å, RDF_BINS 150 over a 7.4 Å range — the **~4.5 Å tetrahedral second shell is resolved** (`second_shell_near_tetrahedral` flag, reported not folded into `bulk_water_stable`), mean T now production-phase-only ~303 K. Run cost ~4.3 min (O(N²) pair loop in QuickJS), still gated by `SKIP_BULK`. Beam-profile presets also landed: `helpers.beamProfiles.spread(name, overrides)` (`pencil`/`laser`/`ledLamp`/`flashlight`/`sunbeam`); `glass_of_water_varied.js` adopted `ledLamp` (its historical values — verified hash-preserving, canonical beam JSON byte-identical).
- Sputnik bulk-water SPC/E parameterisation landed (2026-06-11): moved the force field from plain-SPC to flexible SPC/E (Berendsen 1987: q_O=-0.8476/q_H=0.4238, r_OH=1.0 Å, HOH 109.47°, σ=3.166 Å, ε=0.1553 kcal/mol), deepening the O-O g(r) first minimum 0.95 → 0.85. New emitted observable `gr_first_min_height` (depletion depth).
- Sputnik bulk-water **rigid SPC/E via SHAKE/RATTLE** landed (2026-06-11): made the canonical rigid SPC/E — geometry held by holonomic constraints (`shake()` on positions + velocity fold-in, `rattle()` on velocities; 3 pair constraints per molecule: 2×O-H at 1.0 Å + H-H at `2·r_OH·sin(θ/2)`=1.633 Å), no intramolecular force terms. Removing the O-H stretch sharpened the structure onto experiment: first-peak height 2.48 → **3.00**, inter-shell min **0.85 → 0.775 (exp ~0.75)** at **3.38 Å (exp ~3.4)**, coordination **4.73** to both bounds (measured ~4.3-4.7), second shell 4.36 Å, mean T 305 K. Timestep 0.2 → **2 fs** (rigid water's fastest motion is libration, not the O-H stretch), so 2500 ticks now span 5000 fs (10× more sampling) at comparable cost; pre-allocated `state.pOld` scratch avoids per-step GC. Temperature dof corrected to `6·N_mol − 3` (rigid). Rigidity is proven, not assumed: the max post-SHAKE bond residual (~1e-9, emitted as `max_constraint_violation`) gates `bulk_water_stable` via `rigid_constraints_held`. Note: the *pre*-correction per-step drift is naturally a few % at 2 fs — gate on the *post*-correction residual, not the drift.
- Sputnik bulk-water **self-diffusion (first dynamic observable)** landed (2026-06-11): the production-phase O-atom mean-squared displacement (Einstein relation MSD = 6 D t; `atom.p` is never wrapped in the integrator so it is already the continuous/unwrapped trajectory — MSD is a direct difference from a reference set captured on the first production tick). Slope is least-squares-fit over the second half of the MSD curve (diffusive regime) → **D = 2.57e-9 m²/s**, ≈ the SPC/E literature ~2.5e-9 and within ~12% of experiment 2.3e-9 (the run sits at ~305 K vs the 298 K reference; D rises with T). Emitted `self_diffusion_m2_per_s` + downsampled `msd_curve`, range-checked via `self_diffusion_physical` (reported, not gating). Rendered as a standalone comparison plot `tools/viz/demos/h2o_self_diffusion.png` (MSD vs t + Einstein fit + D vs SPC/E/experiment) and a line on the animation end card. Caveat honesty: D came out slightly ABOVE literature (not "finite-size low" as first assumed) — the ~305 K production T + single-origin MSD noise dominate, stated accurately.
- Validation summary (auto-updated after a successful run): `docs/validation_summary.md`.
