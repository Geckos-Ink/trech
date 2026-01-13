# TRECH implementation notes (initial skeleton)

## Scope

This is the M1 scaffold: JS config -> JSON -> C++ -> Geant4, with a minimal provenance JSONL log.
See `docs/trech-roadmap.md` and `docs/structure.md` for the longer-term plan.

## Build

```
cmake --preset dev
cmake --build --preset dev
./build/dev/trech run examples/experiments/hello_world.js
```

## Dependencies

- QuickJS is required for JS experiments. Either:
  - Vendor it under `thirds/quickjs/quickjs`, or
  - Build with `-DTRECH_FETCH_DEPS=ON` to fetch it at configure time.
- Geant4 sources are tracked as a submodule under `thirds/geant4`; initialize it before working on the sim layer.
  Building with Geant4 is still controlled by `TRECH_ENABLE_GEANT4` and a system install.
- `nlohmann/json` is used for config parsing.

## Outputs

- Run provenance is appended to `trech_provenance.jsonl` in the working directory.
