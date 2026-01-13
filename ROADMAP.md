# ROADMAP

This file tracks the short-term execution plan; keep it updated as items are completed or re-scoped.

## Short-term next steps

- Add a minimal batch macro example and optional `--ui` flag for interactive runs.
- Document the JSON schema for provenance and scoring outputs.
- Add a smoke test target or script to run `trech` on `examples/experiments/hello_world.js`.

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

- Geant4 submodule initialized and documented.
- Dependency acquisition decision: default FetchContent via presets, with vendoring optional.
- CLI flags for macro execution, output directory, seed override, and event count.
- Provenance logging expanded (physics list, RNG engine, CLI args).
- First scoring output (total energy deposit summary).
- Unit tests for CLI parsing, JS config evaluation, and provenance output.
