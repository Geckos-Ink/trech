# TRECH

**Current stage: Skeleton and roadmap only, to be implemented**

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
- Secondary reference (not first priority): simulate carbon nanotube variants (structure, chirality, diameter) and electron behavior differences, including Fermi gap modeling, per `docs/CNT/BackToTheCarbon.md`.
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
trech run <experiment.js> [--macro <file>] [--ui] [--output <dir>] [--seed <n>] [--events <n>]
```

Examples:

```
./build/dev/trech run examples/experiments/hello_world.js --output out
./build/dev/trech run examples/experiments/water_box.js --seed 42 --events 100
./build/dev/trech run examples/experiments/h2o_fluid.js
./build/dev/trech run examples/experiments/hello_world.js --macro examples/macros/minimal.mac
```

## Config examples

- `examples/experiments/hello_world.js`: minimal baseline.
- `examples/experiments/config_optics.js`: water box with optics enabled.
- `examples/experiments/config_stratify.js`: event stratification thresholds/labels.
- `examples/experiments/config_stratify_ml.js`: stratification with TorchScript model path stub.
- `examples/experiments/config_chemistry_stub.js`: chemistry/DNA stub wiring config.
- `examples/experiments/config_multiscale_stub.js`: multi-scale stub wiring config.

## Outputs

- `trech_provenance.jsonl`: run provenance records (config JSON, hash, seed, versions).
- `trech_scores.jsonl`: scoring summaries (total energy deposit, optical photon counts and track length when optics are enabled).
- `trech_event_scores.jsonl`: per-event scoring summaries when `stratify.enable` is true.
- `trech_event_features.jsonl`: per-event features when `stratify.dumpFeatures` is true.
- `trech_resim_queue.jsonl`: exceptional event queue when `stratify.dumpResimQueue` is true.

By default these are written to the current working directory; use `--output` to redirect.
Schema details: `docs/output_schema.md`.

## Dependencies

- **Geant4**: tracked as a required submodule under `thirds/geant4`.
  You still need a Geant4 build/install to build TRECH; set `Geant4_DIR` or `CMAKE_PREFIX_PATH` (for example, to the submodule build/install).
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

## Validation script

```
scripts/run_validation.sh
```

Env overrides: `BUILD_PRESET` (default `dev`), `EVENTS` (default `100`), `SCORES_FILE` (default `trech_scores.jsonl`), `PROVENANCE_FILE` (default `trech_provenance.jsonl`), `SUMMARY_FILE` (default `docs/validation_summary.md`).
Requires Ninja, a C++ compiler, Python 3, and Geant4 for the H2O run.
Successful runs write `docs/validation_summary.md` via `scripts/update_validation_summary.py`.

## Smoke test script

```
scripts/run_smoke.sh
```

Env override: `BUILD_PRESET` (default `dev`). Requires Ninja and a C++ compiler. Runs `ctest` after building.

## Validation status

- Last attempt: `scripts/run_validation.sh` configured/built successfully and `ctest` passed, but Geant4 was not found so H2O validation did not run.
- Geant4 source is present as a submodule at `thirds/geant4`, but it still needs to be built/installed and pointed to via `Geant4_DIR` or `CMAKE_PREFIX_PATH`.
- Validation summary (auto-updated after a successful run): `docs/validation_summary.md`.

## Roadmap

- Short-term next steps: `ROADMAP.md` (editable source of truth)
- Initial roadmap concept: `docs/trech-roadmap.md` (reference-only)
- H2O experiment spec (initial): `examples/experiments/h2o_fluid_spec.md`

## License

See `LICENSE`.
