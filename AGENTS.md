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
- H2O experiment spec: `examples/experiments/h2o_fluid_spec.md`
- H2O experiment stub: `examples/experiments/h2o_fluid.js`
- Optics spectrum example: `examples/experiments/config_optics.js`
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
- Use Geant4 with the "right creativity" to maximize available physics and tooling without breaking the JS -> JSON boundary.
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

- JS is authoring only: experiments must set global `TRECH_CONFIG` to a JSON string.
- Long-term: keep the C++ config surface physics/chemistry agnostic; JS scenarios should express combinations.
- Avoid hardcoding domain-specific switches in C++; define physics/chemistry classes, properties, and extensions in JS scenarios.
- Optical physics is toggled via `optics.enable`; photon scoring fields are emitted when enabled, and water box environment is driven by `detector.waterBoxMm`, `temperatureK`, and `pressureAtm`.
- `optics.spectrum` (optional) can provide energy/wavelength dependent refractive index, absorption, and scattering values for color response.
- Event stratification output is emitted to `trech_event_scores.jsonl` when `stratify.enable` is true, using thresholds/labels from `stratify.*` and ML stubs if configured.
- Stratification feature dumps and resim queues are emitted when `stratify.dumpFeatures` or `stratify.dumpResimQueue` are enabled.
- Chemistry/DNA wiring toggles Geant4-DNA EM physics when `chemistry.enable` and `TRECH_ENABLE_DNA_CHEM` are set; `chemistry.solver` (non-`stub`) enables the chemistry stage.
- Multi-scale wiring is stubbed behind `multiscale.enable` and does not alter physics yet.
- Keep the JS -> JSON -> C++ boundary stable; avoid binding Geant4 directly into JS.
- Geant4 wiring order stays canonical: RunManager -> DetectorConstruction + PhysicsList + ActionInitialization -> Initialize -> BeamOn.
- Provenance is written as JSONL to `trech_provenance.jsonl` (output dir) and should include config JSON + hash + seed + Geant4 version.
- Scoring summaries are written as JSONL to `trech_scores.jsonl` (output dir).
- Run-level scoring includes chemistry/DNA flags, option metadata, stratification summary counts, and CNT energy deposit (`cnt_edep_mev`).
- Run-level scoring echoes `cnt_*` fields for CNT filtering when enabled.
- `cnt` is an optional config block for CNT staging and does not affect physics yet.
- When `cnt.enable` is true, a simple CNT geometry stub (hollow cylinder) is placed in the detector.
- CNT placement is scenario-defined: if `detector.waterBoxMm` is set, the stub sits in the water box; otherwise it sits in the world.
- CNT investigations prioritize electron transport behavior; optical photons are a secondary comparison in mixed tests.

## Dependencies

- QuickJS sources live under `thirds/quickjs/quickjs` (or configure with `TRECH_FETCH_DEPS=ON`).
- Geant4 is a required submodule at `thirds/geant4` (init with `git submodule update --init --recursive`); build/install it and set `Geant4_DIR` or `CMAKE_PREFIX_PATH`.
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

- `ctest --preset dev` passed; optics spectrum smoke run completed with `examples/experiments/config_optics.js` (`--events 5`, output `build/dev/out_optics_spectrum`).
- CNT smoke runs completed with `examples/experiments/config_cnt_stub.js` and `examples/experiments/config_cnt_world_stub.js` (`--events 5`, outputs `build/dev/out_cnt`, `build/dev/out_cnt_world`); stubs now use a 0.8 MeV proton beam with thicker walls (diameter 3.0 nm, wallCount 5), rerun to refresh outputs.
- CNT optics smoke run completed with `examples/experiments/config_cnt_optics_stub.js` (`--events 5`, output `build/dev/out_cnt_optics`); stub now uses a 1.2 MeV electron beam with thicker walls (diameter 3.0 nm, wallCount 5), rerun to refresh outputs.
- CMake target link dependencies trimmed to avoid duplicate `libtrech_core.a` warnings on macOS.
- QuickJS header warnings are suppressed for the `trech_js` target via scoped compile flags (Clang/GNU).
- `scripts/run_validation.sh` reran to refresh `docs/validation_summary.md`; `ctest` passed, and the H2O Geant4 run completed with `CMAKE_PREFIX_PATH=build/geant4-install`.
- `examples/experiments/config_chemistry_stub.js` run completed with `--events 5` and `--output build/dev/out_chem`; `trech_scores.jsonl` includes chemistry/DNA fields.
- Geant4 build/install is available at `build/geant4-install` from submodule `thirds/geant4`; point `Geant4_DIR` or `CMAKE_PREFIX_PATH` there when rebuilding.
- Validation summary (auto-updated after a successful run): `docs/validation_summary.md`.
