# AGENTS.md

Guidance for agents working in this repository.

## Directives for AI agents
- At every action, update markdowns (README, ROADMAP and AGENTS for fast references access)

## Core references

- Initial roadmap concept (reference-only; do not edit): `docs/trech-roadmap.md`
- Baseline structure: `docs/structure.md`
- Short-term plan (editable source of truth): `ROADMAP.md` (keep this updated as work progresses)
- H2O experiment spec: `examples/experiments/h2o_fluid_spec.md`
- H2O experiment stub: `examples/experiments/h2o_fluid.js`
- CNT reference: `docs/CNT/BackToTheCarbon.md`

## Strategic goals (Sputnik milestone)

- Define the "Sputnik" milestone as H2O fluid simulation with Geant4 at the highest practical subatomic detail.
- Secondary reference (not first priority): simulate carbon nanotube variants (structure, chirality, diameter) and electron behavior differences, including Fermi gap modeling, per `docs/CNT/BackToTheCarbon.md`.
- In parallel, build learning-based event stratification to separate predictable events from exceptional ones that must be re-simulated.
- Optimize large-scale runs with congenial multi-scale methods (e.g., Lattice Boltzmann, variance reduction, reduced-order models).
- Use Geant4 with the "right creativity" to maximize available physics and tooling without breaking the JS -> JSON boundary.
- Treat photon transport as a key Geant4 focus: scattering, absorption, refraction, and color response in molecular volumes.

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
- Optical physics is toggled via `optics.enable`; photon scoring fields are emitted when enabled, and water box environment is driven by `detector.waterBoxMm`, `temperatureK`, and `pressureAtm`.
- Keep the JS -> JSON -> C++ boundary stable; avoid binding Geant4 directly into JS.
- Geant4 wiring order stays canonical: RunManager -> DetectorConstruction + PhysicsList + ActionInitialization -> Initialize -> BeamOn.
- Provenance is written as JSONL to `trech_provenance.jsonl` (output dir) and should include config JSON + hash + seed + Geant4 version.
- Scoring summaries are written as JSONL to `trech_scores.jsonl` (output dir).

## Dependencies

- QuickJS sources live under `thirds/quickjs/quickjs` (or configure with `TRECH_FETCH_DEPS=ON`).
- Geant4 is a required submodule at `thirds/geant4` (init with `git submodule update --init --recursive`).
- nlohmann/json can be vendored under `thirds/json` (or fetched).

## Build

```
cmake --preset dev
cmake --build --preset dev
./build/dev/trech run examples/experiments/hello_world.js
```

Options: `TRECH_ENABLE_GEANT4`, `TRECH_ENABLE_DNA_CHEM`, `TRECH_ENABLE_TORCH`, `TRECH_FETCH_DEPS`.

CLI flags: `--macro`, `--output`, `--seed`, `--events`.

## Validation script

```
scripts/run_validation.sh
```

Requires Ninja, a C++ compiler, and Python 3. Env overrides: `BUILD_PRESET`, `EVENTS`, `SCORES_FILE`.

## Validation status

- `scripts/run_validation.sh` failed preflight because Ninja is missing (prior `cmake --preset dev` also reported missing C/C++ compilers).
- `ctest --test-dir build/dev` and H2O validation did not run; `trech_scores.jsonl` not generated.
