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
- H2O optics beam stub: `examples/experiments/h2o_optics_beam.js`
- Optics spectrum example: `examples/experiments/config_optics.js`
- JS helpers module: `examples/experiments/trech_helpers.js`
- JS multi-beam example: `examples/experiments/config_multi_beam_units.js`
- JS flow authoring example: `examples/experiments/config_flow_language.js`
- JS include error demo: `examples/experiments/include_error_demo.js`
- CNT stub experiment: `examples/experiments/config_cnt_stub.js`
- CNT world stub experiment: `examples/experiments/config_cnt_world_stub.js`
- CNT optics stub experiment: `examples/experiments/config_cnt_optics_stub.js`
- CNT reference: `docs/CNT/BackToTheCarbon.md`
- Output schema: `docs/output_schema.md`
- Validation summary: `docs/validation_summary.md`

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
- `TRECH_FLOW(initial)` is available for flow-like JS authoring with fluent deterministic transforms (`set`/`merge`/`push`/`when`/`tap`/`build`) before JSON handoff.
- `TRECH_INCLUDE` is available for modular JS experiments; include paths resolve relative to the caller and preserve file/line references.
- Determinism is a dial: strict simulation runs are reproducible; predictive ML modes must record model hash + inference metadata.
- Long-term: keep the C++ config surface physics/chemistry agnostic; JS scenarios should express combinations.
- Avoid hardcoding domain-specific switches in C++; define physics/chemistry classes, properties, and extensions in JS scenarios.
- H2O milestone scenarios remain JS-authored (single-molecule proxy + optics beam); keep C++ as the generic engine.
- LibTorch/TorchScript is the chosen ML runtime for online learning from simulation outputs.
- System abstraction is point-agnostic: `system.*` defines ensemble aggregation and `trech_scores.jsonl` emits `system_*` density metrics plus volume source (config volume overrides medium box/world).
- TorchScript feature schema is `FeaturePipeline::kSchemaId` (`trech_event_features_v1`) with order: `total_edep_mev`, `total_track_length_mm`, `total_step_count`, `total_track_count`, `optical_photon_steps`, `optical_photon_tracks`, `optical_photon_track_length_mm`.
- TorchScript inference (when `TRECH_ENABLE_TORCH` + `stratify.modelPath` is set) expects a label string output or a 1-2 value tensor; tensor outputs map to `stratify.labelPredictable`/`stratify.labelExceptional`.
- Optical physics is toggled via `optics.enable`; photon scoring fields are emitted when enabled, and the medium box environment is driven by `detector.mediumBoxMm`, `detector.mediumMaterial`, `temperatureK`, and `pressureAtm`.
- `optics.spectrum` (optional) can provide energy/wavelength dependent refractive index, absorption, and scattering values for color response.
- Event stratification output is emitted to `trech_event_scores.jsonl` when `stratify.enable` is true, using thresholds/labels from `stratify.*` and ML stubs if configured.
- Stratification feature dumps and resim queues are emitted when `stratify.dumpFeatures` or `stratify.dumpResimQueue` are enabled.
- Chemistry/DNA wiring toggles Geant4-DNA EM physics when `chemistry.enable` and `TRECH_ENABLE_DNA_CHEM` are set; `chemistry.solver` (non-`stub`) enables the chemistry stage.
- Multi-scale wiring is stubbed behind `multiscale.enable` and does not alter physics yet.
- Keep the JS -> JSON -> C++ boundary stable; avoid binding Geant4 directly into JS (hooks are sideband, not direct Geant4 access).
- Collections should use plural names and accept either single-object or array inputs; loaders normalize to arrays (materials/components/tags/optics.spectrum/hooks.registered accept single values).
- `beams` arrays are normalized in the loader (active/first is selected); `beam` remains a single-entry alias.
- JS runtime error stacks should include filenames and line numbers (including `TRECH_INCLUDE` sources); keep `tests/test_js_runtime.cpp` up to date.
- Avoid leaning on collider-specific terminology in new features; top-level `environment`/`medium` aliases for `detector` are supported at parse time (canonical config output remains `detector`).
- Geant4 wiring order stays canonical: RunManager -> DetectorConstruction + PhysicsList + ActionInitialization -> Initialize -> BeamOn.
- Provenance is written as JSONL to `trech_provenance.jsonl` (output dir) and should include config JSON + hash + seed + Geant4 version (plus hook registrations and model hashes when enabled).
- Scoring summaries are written as JSONL to `trech_scores.jsonl` (output dir).
- Run-level scoring includes chemistry/DNA flags, option metadata, stratification summary counts, and per-volume energy deposits (`volume_edep_mev`) when enabled.
- Geometry volumes (`geometry.volumes`) define named shapes, placements, materials, and optional `scoreEdep` flags.
- Custom mixtures can be declared in `materials` (density + component fractions) and referenced by name in detector or volume materials.
- `materials` accepts an optional `smiles` field as a placeholder for future registry metadata.
- If using `G4_*` materials, document or wrap them via shared JS presets so definitions are visible to scenario authors.
- Volume placement is scenario-defined: use `placement.parent = "medium"` to sit inside the medium box, `"world"` for world placement, or named containers for nested assemblies (containers typically use vacuum material).
- CNT investigations prioritize electron transport behavior; optical photons are a secondary comparison in mixed tests.
- ML scale-up path: Geant4 outputs -> dataset -> Torch training/finetuning -> accuracy/coverage gates -> TorchScript inference, with resim when confidence is low (see `CHARTS.md`).

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

CLI flags: `--macro`, `--ui`, `--output`, `--seed`, `--events`.

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
- Latest `scripts/run_validation.sh` run failed with a SIGSEGV during `examples/experiments/h2o_fluid.js` after `ctest` passed; `docs/validation_summary.md` was not refreshed.
- `examples/experiments/config_chemistry_stub.js` run completed with `--events 5` and `--output build/dev/out_chem`; `trech_scores.jsonl` includes chemistry/DNA fields.
- Geant4 build/install is available at `build/geant4-install` from submodule `thirds/geant4`; point `Geant4_DIR` or `CMAKE_PREFIX_PATH` there when rebuilding.
- Multi-beam helper run completed with `examples/experiments/config_multi_beam_units.js` (`--output build/dev/out_multi_beam`); `trech_scores.jsonl` recorded `total_edep_mev` 25.0, `system_volume_mm3` 1000000.0, `system_edep_mev_per_mm3` 2.5e-05 (`QBBC`, optics disabled).
- Flow-language scenario run completed with `examples/experiments/config_flow_language.js` (`--events 1`, output `build/dev/out_flow_language`); provenance normalized `environment` alias fields under canonical `detector`.
- `ctest --preset dev -R trech_js_runtime` passed; includes test coverage for `TRECH_INCLUDE` error filenames/line numbers plus flow-style `TRECH_CONFIG` + `TRECH_FLOW`.
- Validation summary (auto-updated after a successful run): `docs/validation_summary.md`.
