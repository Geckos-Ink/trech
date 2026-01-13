# AGENTS.md

Guidance for agents working in this repository.

## Core references

- Roadmap: `docs/trech-roadmap.md`
- Baseline structure: `docs/structure.md`

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
- Keep the JS -> JSON -> C++ boundary stable; avoid binding Geant4 directly into JS.
- Geant4 wiring order stays canonical: RunManager -> DetectorConstruction + PhysicsList + ActionInitialization -> Initialize -> BeamOn.
- Provenance is written as JSONL to `trech_provenance.jsonl` and should include config JSON + hash + seed + Geant4 version.

## Dependencies

- QuickJS sources live under `thirds/quickjs/quickjs` (or configure with `TRECH_FETCH_DEPS=ON`).
- Geant4 can be cloned under `thirds/geant4`.
- nlohmann/json can be vendored under `thirds/json` (or fetched).

## Build

```
cmake --preset dev
cmake --build --preset dev
./build/dev/trech run examples/experiments/hello_world.js
```

Options: `TRECH_ENABLE_GEANT4`, `TRECH_ENABLE_DNA_CHEM`, `TRECH_ENABLE_TORCH`, `TRECH_FETCH_DEPS`.
