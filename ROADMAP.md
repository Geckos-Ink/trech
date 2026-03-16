# ROADMAP

This file tracks the short-term execution plan; keep it updated as items are completed or re-scoped.
`docs/trech-roadmap.md` is the initial roadmap concept and is reference-only.

## Sputnik milestone (north star)

- Simulate a single H2O melecule starting from its elementar particle: their behavior and bonds prediction over the time should be stable without "exploding".
- Secondary reference (not first priority): simulate carbon nanotube variants (structure, chirality, diameter) and electron behavior differences, including Fermi gap modeling, per `docs/CNT/BackToTheCarbon.md`.
- Simulate H2O fluid behavior with Geant4 using as much subatomic detail as practical.
- Define a "system" abstraction: stable, point-agnostic ensemble behavior that bridges particle runs to macro-scale predictions.
- In parallel, learn to separate predictable events from exceptional ones so only outliers are re-simulated.
- Optimize large-scale molecule simulations with congenial multi-scale methods (e.g., Lattice Boltzmann, variance reduction, reduced-order models).
- Use Geant4 with the "right creativity" to maximize the available physics within library boundaries and maintain provenance parity.
- Treat photon transport as a key Geant4 focus: scattering, absorption, refraction, and color response in molecular volumes.

## Short-term next steps

- Use `docs/validation_summary.md` to track baseline H2O run metrics and watch for regressions as physics/optics work expands.
- Refresh validation outputs after example refreshes (container volumes, explicit materials, nested geometry).
- Continue expanding hook runtime guardrails after `ctx` + deterministic patch/emit landing (next: patch whitelist growth). Stricter emit payload validation and per-callback emit caps are implemented via `hooks.maxEmitsPerCallback` and `hooks.maxEmitPayloadBytes`.
- Extend determinism controls beyond mode selection (strict/predictive implemented) and add guardrails for mixed runtime workflows.
- Define the TorchScript model output contract (label string or 1-2 value tensor) and add a LibTorch-backed smoke test once LibTorch is available.
- Expand system observables beyond current density + event energy moments (mean/variance/stddev) as new per-run accumulables land.
- Keep `CHARTS.md` aligned with runtime changes (workflow, Geant4 wiring, outputs, stratification/prediction).
- Stage a CNT milestone track in parallel to validate config/output coherence without diverging from the H2O baseline.
- Improve geometry authoring beyond primitive shapes: scene graph/nesting, imports (GDML), and procedural generators for complex assemblies.
- Continue de-colliderizing terminology: parser now accepts `environment`/`medium` aliases for `detector`; next extend alias visibility across examples/docs/CLI hints without breaking existing configs.
- Expand flow-oriented JS authoring (`TRECH_FLOW`) beyond current helpers (defaults/derive/normalize/finalize/require) with reusable validation presets while preserving the JS -> JSON boundary.
- Extend nuclear-cycle analysis beyond static consistency/Q-value checks by adding event-level transmutation/decay tallies (Geant process attribution) for scenario-level closure metrics.
- Bootstrap the real-time 3D lab runtime path: support a live command stream (`patch`, `simulate`, `snapshot`, `quit`) over canonical JSON config so users can interact without a fixed JS scenario.
- Use LibTorch/TorchScript for fluid-scale statistical modeling; wire incremental learning as the runtime evolves.
- Long-term: keep the C++ config surface physics/chemistry agnostic, relying on JS scenarios and lab command streams to express combinations.

## Validation status

- `ctest --preset dev` passed (latest run); optics spectrum smoke run completed with `examples/experiments/config_optics.js` (`--events 5`, output `build/dev/out_optics_spectrum`).
- H2O single-molecule proxy stub run completed with `examples/experiments/h2o_single_molecule.js` (`--events 50`, output `build/dev/out_h2o_single`).
- H2O optics beam stub run completed with `examples/experiments/h2o_optics_beam.js` (`--events 50`, output `build/dev/out_h2o_optics`).
- CNT smoke runs completed with `examples/experiments/config_cnt_stub.js` and `examples/experiments/config_cnt_world_stub.js` (`--events 5`, outputs `build/dev/out_cnt`, `build/dev/out_cnt_world`); stubs now use container volumes with explicit materials (diameter 3.0 nm, wallCount 5) and a 0.8 MeV electron beam, rerun to refresh outputs.
- CNT optics smoke run completed with `examples/experiments/config_cnt_optics_stub.js` (`--events 5`, output `build/dev/out_cnt_optics`); stub now uses a 1.2 MeV electron beam with thicker walls (diameter 3.0 nm, wallCount 5) and `volume_edep_mev` scoring, rerun to refresh outputs.
- CMake target link dependencies trimmed to avoid duplicate `libtrech_core.a` warnings on macOS.
- QuickJS header warnings are suppressed for the `trech_js` target via scoped compile flags (Clang/GNU).
- Latest `scripts/run_validation.sh` run failed with a SIGSEGV during `examples/experiments/h2o_fluid.js` after `ctest` passed; `docs/validation_summary.md` was not refreshed.
- `examples/experiments/config_chemistry_stub.js` run completed with `--events 5` and `--output build/dev/out_chem`; `trech_scores.jsonl` includes chemistry/DNA fields.
- Nitrogen-carbon cycle scenario run completed with `examples/experiments/config_nitrogen_carbon_cycle.js` (`--events 5`, output `build/dev/out_nitrogen_cycle`); run scores/provenance now include `nuclear_cycle_count`, `nuclear_consistent_cycle_count`, and detailed `nuclear_cycles` reaction/Q-value metrics.
- Geant4 build/install is available at `build/geant4-install` from submodule `thirds/geant4`; point `Geant4_DIR` or `CMAKE_PREFIX_PATH` there when rebuilding.
- When Geant4 is needed, check `thirds/geant4` first before fetching elsewhere.
- `Geant4Config.cmake` is generated by the build/install (currently at `build/geant4-install/lib/cmake/Geant4/Geant4Config.cmake`); the template lives at `thirds/geant4/cmake/Templates/Geant4Config.cmake.in`.
- Prefer building in `build/geant4-build` and installing to `build/geant4-install` to avoid submodule changes.
- Multi-beam helper run completed with `examples/experiments/config_multi_beam_units.js` (`--output build/dev/out_multi_beam`); `trech_scores.jsonl` recorded `total_edep_mev` 25.0, `system_volume_mm3` 1000000.0, `system_edep_mev_per_mm3` 2.5e-05 (`QBBC`, optics disabled).
- Flow-language scenario run completed with `examples/experiments/config_flow_language.js` (`--events 1`, output `build/dev/out_flow_language`); provenance normalized `environment` alias fields under canonical `detector`.
- Hook runtime extension smoke run completed with `examples/experiments/config_hook_dispatch.js` (`--output build/dev/out_hook_runtime_ext`); scores/provenance include `hook_on_*` counters plus `hook_patch_count`/`hook_emit_count`, `hooks.maxStepCallbacks` guardrail fields, and deterministic hook emits in `trech_hook_emits.jsonl`.
- Hook emit guardrails extended: `hooks.maxEmitsPerCallback` + `hooks.maxEmitPayloadBytes` now bound `ctx.emit` per callback, oversize/over-cap emits are dropped deterministically, and scores/provenance include `hook_emit_dropped_count` plus emit guardrail metadata (`hooks_guardrail_max_emits_per_callback`, `hooks_guardrail_max_emit_payload_bytes`).
- System observables now include event energy moments (`system_event_count`, `system_event_edep_mean_mev`, `system_event_edep_variance_mev2`, `system_event_edep_stddev_mev`) in run scores/provenance.
- `ctest --preset dev -R trech_js_runtime` passed; includes test coverage for `TRECH_INCLUDE` error filenames/line numbers plus flow-style `TRECH_CONFIG` function and expanded `TRECH_FLOW` helpers (`defaults`, `derive`, `ensureArray`, `selectBeam`, `normalizeDetectorAliases`, `finalize`, `require`).
- Determinism/provenance smoke run completed with `examples/experiments/config_stratify_ml.js` (`--events 1`, output `build/dev/out_determinism`); emitted `determinism_mode`, `predictive_mode`, stratify model hash metadata, and stratify source counters in provenance.
- Real-time lab bootstrap landed in CLI/core: `trech lab` now runs without JS scenarios, loading optional JSON config (`--config`) and line-delimited command streams (`--commands`) with actions `patch`, `simulate`, `snapshot`, `help`, and `quit`; covered by new `trech_lab_session` and updated `trech_cli_parse` tests.

## Photon transport milestones (optical physics plan)

- Phase 1: add `optics.enable` config flag and wire Geant4 optical physics when enabled.
- Phase 2: map water optical properties (absorption, scattering, refraction) into materials.
- Phase 3: add photon-focused scoring summaries and validation runs.
- Phase 4: support spectral optics tables (energy/wavelength dependent properties) for color response.

## CNT milestone parallel track (consistency check)

- Define a CNT experiment stub that stays within the JS -> JSON boundary and reuses the shared config structure (detector/beam/optics/stratify).
- Express CNT geometry as a generic `geometry.volumes` entry (tube shell) with `scoreEdep` enabled.
- CNT placement stays scenario-defined: use `placement.parent = "medium"` to sit inside the medium box, `placement.parent = "world"` for world placement, or named container volumes for nested assemblies.
- Run-level scores stay schema-agnostic; CNT observables are tracked via `volume_edep_mev` on the named volume.
- Validate that CNT runs exercise the same physics wiring order and that optics/stratify toggles behave identically across medium/CNT media.
- Mixed testing: add a CNT + optics stub to confirm photon scoring fields coexist with `volume_edep_mev` on the same engine.
- Gate: proceed with CNT implementation only if it improves overall consistency (shared config surface, shared scoring outputs, fewer special cases).
- CNT smoke run: `./build/dev/trech run examples/experiments/config_cnt_stub.js --events 5 --output build/dev/out_cnt`.
- CNT world smoke run: `./build/dev/trech run examples/experiments/config_cnt_world_stub.js --events 5 --output build/dev/out_cnt_world`.
- CNT optics smoke run: `./build/dev/trech run examples/experiments/config_cnt_optics_stub.js --events 5 --output build/dev/out_cnt_optics`.
- Expected scoring: `trech_scores.jsonl` includes `total_edep_mev`, `volume_edep_mev`, `optics_enabled`, optical photon counts, `n_events`, `seed`, `physics_list`.
- Expected provenance: `trech_provenance.jsonl` includes `config_json` (with `geometry.volumes` and hook registrations when present), `config_hash`, `geant4_version`, `physics_list`, `seed`, `n_events`.

## Long-term structure

- core/ (config, provenance, storage)
- js/ (runtime + bindings)
- sim/ (Geant4 integration and scoring)
- chem/ (species registry, reaction network, RD engine, DNA bridge)
- ml/ (TorchScript runtime + feature pipelines)
- data/ (PubChem cache + dataset builders)
- bench/ (benchmarks, manifests, reproducible datasets)
- docs/ (architecture, APIs, user guides)
- thirds/ (submodules and vendored dependencies)

## Completed

- Mermaid architecture charts added in `CHARTS.md` (workflow, Geant4 wiring, outputs, stratification/prediction).
- Geant4 submodule initialized and documented.
- Dependency acquisition decision: default FetchContent via presets, with vendoring optional.
- CLI flags for macro execution, output directory, seed override, and event count.
- Provenance logging expanded (physics list, RNG engine, CLI args).
- First scoring output (total energy deposit summary).
- Event-level scoring and stratification hooks added (`trech_event_scores.jsonl`, `stratify.enable`).
- Stratification expanded with richer event features, thresholds, labels, and ML hook stubs.
- ML feature pipeline + TorchScript stub added for event stratification.
- Chemistry/DNA wiring stub added (`chemistry.enable`, `chemistry.model`, `chemistry.solver`).
- Multi-scale wiring stub added (`multiscale.enable`, `multiscale.method`, `multiscale.mode`).
- Initial Geant4-DNA wiring added (`chemistry.enable`, `TRECH_ENABLE_DNA_CHEM`, solver-gated chemistry stage).
- Run-level scoring now includes chemistry/DNA flags and option metadata.
- Run-level scoring now includes stratification summary counts.
- CTest presets added to avoid passing `--test-dir` flags.
- Stratification feature dumps + resim queue outputs added (`trech_event_features.jsonl`, `trech_resim_queue.jsonl`).
- Unit tests for CLI parsing, JS config evaluation, and provenance output.
- Stratification unit tests and smoke script now run `ctest`.
- Draft initial H2O experiment spec (`examples/experiments/h2o_fluid_spec.md`).
- Initial H2O experiment stub (`examples/experiments/h2o_fluid.js`).
- H2O single-molecule proxy stub (`examples/experiments/h2o_single_molecule.js`).
- H2O optics beam stub (`examples/experiments/h2o_optics_beam.js`).
- H2O config schema extended (medium box, environment, beam direction, optics) with updated spec and stub.
- Detector now supports medium box geometry, environment settings, and optical material properties.
- Optical physics wiring and photon scoring fields (tracks, steps, track length) added.
- Spectral optics support added for energy/wavelength dependent refractive index, absorption, and scattering.
- Optics spectrum example added in `examples/experiments/config_optics.js`.
- Geometry volumes and custom materials added (`geometry.volumes`, `materials`) to keep the schema agnostic.
- Per-volume energy deposit scoring added (`volume_edep_mev`), keyed by volume name.
- CNT stubs now model tube-shell geometry volumes with `scoreEdep` enabled; examples cover medium, world, and container placements with explicit materials.
- LibTorch/TorchScript selected as the ML runtime for online learning from detailed simulations.
- CNT optics stub added to validate optics + volume scoring on the same engine.
- H2O single-molecule proxy and optics-beam stubs run; baseline scores/provenance captured in `build/dev/out_h2o_single` and `build/dev/out_h2o_optics`.
- TorchScript feature schema defined (`FeaturePipeline::kSchemaId = trech_event_features_v1`) and a minimal LibTorch inference hook added behind `TRECH_ENABLE_TORCH`.
- ML scale-up flowchart added to `CHARTS.md` (Geant4 -> Torch training -> inference gate).
- System config block (`system.*`) added with point-agnostic aggregation, and `trech_scores.jsonl` now emits `system_*` density metrics.
- Event summary accumulables now feed system moment metrics (event count + energy mean/variance/stddev) in `trech_scores.jsonl` and `trech_provenance.jsonl`.
- Generic nuclear cycle config + Geant-backed analyzer added (`nuclear.cycles`): reaction participant mass/Q evaluation, charge/baryon conservation checks, and macro phase/density consistency metrics in scores/provenance.
- Validation automation script added (`scripts/run_validation.sh`).
- Validation summary template + updater script added (`docs/validation_summary.md`, `scripts/update_validation_summary.py`) and wired into `scripts/run_validation.sh`.
- Smoke test script added (`scripts/run_smoke.sh`).
- Output JSON schema documented (`docs/output_schema.md`).
- Minimal batch macro example added (`examples/macros/minimal.mac`) and `--ui` flag implemented.
- Config example experiments added (optics, stratify, ML stub, chemistry stub, multiscale stub, nitrogen-carbon cycle).
- Hook API proposal documented (`docs/scenario_hooks.md`).
- JS helper module and multi-beam unit conversion example added (`examples/experiments/trech_helpers.js`, `examples/experiments/config_multi_beam_units.js`).
- JS helpers expanded with physical constants + material presets (including SMILES placeholders).
- JS include helper (`TRECH_INCLUDE`) added to load scenario modules with stable file/line references.
- JS runtime now accepts object-based `TRECH_CONFIG` and registers `TRECH_HOOKS`; error stacks still surface include filenames/line numbers with test coverage in `tests/test_js_runtime.cpp`.
- Hook dispatcher telemetry is wired at init/run/event/step boundaries with deterministic run-level counters and `hooks.maxStepCallbacks` guardrails in scores/provenance outputs.
- Hook runtime extension now dispatches deterministic `ctx` payloads (`config/runtime/event/step/state/rng`), supports whitelisted `onInit` override patching, records `hook_patch_count`/`hook_emit_count` in scores+provenance, and writes `trech_hook_emits.jsonl`.
- Hook runtime guardrails now include per-callback emit caps + payload-size caps (`hooks.maxEmitsPerCallback`, `hooks.maxEmitPayloadBytes`) with dropped emit telemetry in scores/provenance.
- JS runtime now bootstraps `TRECH_FLOW` (fluent `set`/`defaults`/`merge`/`push`/`ensureArray`/`derive`/`selectBeam`/`normalizeDetectorAliases`/`finalize`/`require`/`assert`/`when`/`tap`/`build`) and accepts function-based `TRECH_CONFIG` for flow-like scenario authoring.
- Core runtime now supports a lab-session command channel (`trech lab`) for real-time JSON-driven interaction without fixed JS scenarios; config schema includes `lab.*` metadata (`enable`, `mode`, command schema/channel, targetHz).
- Determinism config added (`determinism.mode`: `strict`/`predictive`) with stratifier gating (`strict` disables model inference path even when `stratify.modelPath` is set) and provenance/scores metadata (`stratify_model_hash`, source counts, predictive flags).
- Beams array normalization added in the config loader (`beams` array selects active/first; `beam` remains an alias).
- Config loader now accepts top-level `environment` and `medium` aliases for `detector` (canonical serialization remains `detector`).
- Collection normalization expanded beyond `beams` (materials/components/tags/optics.spectrum/hooks accept single object/string forms).
- Material registry fields extended with optional `smiles` metadata for future schema expansion.
- Include error demo added (`examples/experiments/include_error_demo.js`, `examples/experiments/include_error_helper.js`).
- Example scenarios refreshed with container volumes, explicit substances, nested geometry, and system volume declarations.
- Master run action now initializes in MT mode; accumulables merge from workers and provenance captures Geant4 version.
- Geant4 build/install completed under `build/geant4-install` and H2O validation run succeeded.
- Build outputs under `build/` are gitignored and treated as local-only artifacts.
