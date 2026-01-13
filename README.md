# TRECH

TRECH is a C++ simulation and learning toolkit that couples Geant4 particle transport
with a stable, scriptable experiment layer and a provenance-first data trail.
The core idea is simple: experiments are authored in JavaScript, emitted as JSON,
and executed by a deterministic C++ runtime. This keeps the configuration surface
stable while allowing the simulation and chemistry capabilities to grow over time.

## Why TRECH

- **Reproducible**: every run writes provenance (config JSON + hashes + seeds + versions).
- **Composable**: JS is an authoring layer, not a simulation API, so C++ remains in control.
- **Extensible**: chemistry (Geant4-DNA and custom RD) and ML (LibTorch) are planned.

## Sputnik milestone (north star)

- Simulate H2O fluid behavior with Geant4 using as much subatomic detail as practical.
- Learn to separate predictable events from exceptional ones so only outliers are re-simulated.
- Scale to large molecule counts with multi-scale acceleration (e.g., Lattice Boltzmann, variance reduction, reduced-order models).
- Prioritize photon transport accuracy (scattering, absorption, refraction, color response) within molecular volumes.

## Architecture (short version)

1. **JS experiment** defines configuration and writes global `TRECH_CONFIG` as JSON.
2. **C++ core** parses the JSON and applies overrides (seed, event count).
3. **Geant4 layer** runs the canonical lifecycle and emits scoring + provenance.

See `docs/structure.md` for the detailed skeleton and `docs/trech-roadmap.md` for the full plan.

## Quick start

```
git submodule update --init --recursive
cmake --preset dev
cmake --build --preset dev
./build/dev/trech run examples/experiments/hello_world.js
```

## CLI

```
trech run <experiment.js> [--macro <file>] [--output <dir>] [--seed <n>] [--events <n>]
```

Examples:

```
./build/dev/trech run examples/experiments/hello_world.js --output out
./build/dev/trech run examples/experiments/water_box.js --seed 42 --events 100
```

## Outputs

- `trech_provenance.jsonl`: run provenance records (config JSON, hash, seed, versions).
- `trech_scores.jsonl`: basic scoring summaries (total energy deposit).

By default these are written to the current working directory; use `--output` to redirect.

## Dependencies

- **Geant4**: tracked as a required submodule under `thirds/geant4`.
  You still need a system Geant4 install to build; set `Geant4_DIR` or `CMAKE_PREFIX_PATH`.
- **QuickJS**: required for JS experiments. Either vendor it under `thirds/quickjs/quickjs`
  or configure with `-DTRECH_FETCH_DEPS=ON` (enabled by presets).
- **nlohmann/json**: used for config parsing. Vendor under `thirds/json` or fetch.

## Repository layout

```
include/trech/        public headers
src/                 C++ implementation
apps/trech-cli/       CLI entrypoint
examples/experiments  JS experiments
tests/                unit tests
docs/                 roadmap and structure
thirds/               submodules and vendored dependencies
```

## Testing

```
ctest --test-dir build/dev
```

## Roadmap

- Short-term next steps: `ROADMAP.md` (editable source of truth)
- Initial roadmap concept: `docs/trech-roadmap.md` (reference-only)
- H2O experiment spec (initial): `examples/experiments/h2o_fluid_spec.md`

## License

See `LICENSE`.
