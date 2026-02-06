# TRECH implementation notes (initial skeleton)

## Scope

This is the M1 scaffold: JS config -> JSON -> C++ -> Geant4, with a minimal provenance JSONL log.
See `docs/trech-roadmap.md` and `docs/structure.md` for the longer-term plan.
Scenarios can now use a flow-like JS authoring surface via global `TRECH_FLOW(initial)` and can set
`globalThis.TRECH_CONFIG` as an object, JSON string, or function returning one.
Determinism mode is configurable via `determinism.mode` (`strict` by default, `predictive` to enable
ML inference paths), and provenance captures model hash/inference source metadata.

## Build

```
cmake --preset dev
cmake --build --preset dev
./build/dev/trech run examples/experiments/hello_world.js
```

Usage:

```
trech run <experiment.js> [--macro <file>] [--output <dir>] [--seed <n>] [--events <n>]
```

Flow-style example:

```
./build/dev/trech run examples/experiments/config_flow_language.js
```

Presets enable `TRECH_FETCH_DEPS=ON` by default to fetch QuickJS and nlohmann/json when not vendored.

## Dependencies

- QuickJS is required for JS experiments. Either:
  - Vendor it under `thirds/quickjs/quickjs`, or
  - Build with `-DTRECH_FETCH_DEPS=ON` to fetch it at configure time.
- Geant4 sources are tracked as a submodule under `thirds/geant4`; initialize with `git submodule update --init --recursive`.
  Building with Geant4 is still controlled by `TRECH_ENABLE_GEANT4` and a system install.
  If you build Geant4 from the submodule, ensure `Geant4_DIR` or `CMAKE_PREFIX_PATH` points at the install.
- `nlohmann/json` is used for config parsing.

## Outputs

- Run provenance is appended to `trech_provenance.jsonl` under the output directory (default: current working directory).
- Scoring summaries are appended to `trech_scores.jsonl` under the output directory.
