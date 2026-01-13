# ROADMAP

This file tracks the short-term execution plan; keep it updated as items are completed or re-scoped.

## Short-term next steps

- Initialize the Geant4 submodule and document local build/install expectations.
- Decide on QuickJS and nlohmann/json acquisition (vendor vs fetch) and confirm CMake paths.
- Add CLI flags for macro execution, output directory, seed override, and event count.
- Expand provenance logging with physics list name, RNG engine, and CLI args.
- Add a first scoring output (e.g., energy deposit map or summary histogram).
- Add tests for JS config evaluation and provenance JSONL format.

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
