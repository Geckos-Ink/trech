# TRECH

**Current stage: H2O baseline with optics, stratification, and initial Geant4-DNA wiring**

TRECH is a C++ simulation and learning toolkit that couples Geant4 particle transport
with a stable, scriptable experiment layer and a provenance-first data trail.
The core idea is simple: experiments are authored in JavaScript, where scenarios can
compute and compose configuration (unit conversions, dynamic assembly, multi-entity
layouts) before emitting JSON for the deterministic-by-default C++ runtime. Prediction
layers can relax determinism in a controlled way and are logged in provenance. The JS
runtime is a standard-compliant engine today (QuickJS) and can evolve without changing
the config surface; longer-term, a small, deterministic hook surface can let JS respond
to runtime context while keeping provenance and repeatability intact.

## Why TRECH

- **Reproducible**: every run writes provenance (config JSON + hashes + seeds + versions).
- **Determinism modes**: strict simulation runs remain reproducible; predictive ML layers can be enabled with explicit provenance capture.
- **Programmable**: JS can compute and assemble configs (helpers, unit conversions, loops) while C++ remains in control.
- **Extensible**: initial Geant4-DNA physics wiring is available (guarded by `TRECH_ENABLE_DNA_CHEM`); chemistry and ML stubs remain.
- **Agnostic config**: long-term, keep the C++ config surface physics/chemistry agnostic while JS scenarios express combinations; define physics/chemistry classes, properties, and extensions in JS.
- **System abstraction**: point-agnostic, ensemble-level metrics (densities) connect particle-scale runs to macro-scale predictions.
- **Online learning**: LibTorch/TorchScript is the chosen ML runtime for learning from simulation outputs (slower inference, but richer training loops).

## "Sputnik" milestone (north star)

- Simulate H2O fluid behavior with Geant4 using as much subatomic detail as practical.
- Secondary reference ("Vostok" milestone): simulate carbon nanotube variants (structure, chirality, diameter) and electron behavior differences, including Fermi gap modeling, per `docs/CNT/BackToTheCarbon.md`.
- Learn to separate predictable events from exceptional ones so only outliers are re-simulated.
- Scale to large molecule counts with multi-scale acceleration (e.g., Lattice Boltzmann, variance reduction, reduced-order models).
- Prioritize photon transport accuracy (scattering, absorption, refraction, color response) within molecular volumes.
- "Apollo" milestone: totally generic physical simulator able to simulate and predict complex systems (chemistry on high volumes) and physical interactions 

## Architecture (short version)

1. **JS experiment** composes configuration and writes global `TRECH_CONFIG` as JSON (hooks are planned).
2. **C++ core** parses the JSON and applies overrides (seed, event count).
3. **Geant4 layer** runs the canonical lifecycle and emits scoring + provenance.
4. **System aggregation** computes point-agnostic ensemble metrics for ML and multiscale stages.

See `docs/structure.md` for the detailed skeleton and `docs/trech-roadmap.md` for the full plan.
Mermaid diagrams of the workflow, Geant4 wiring, prediction loop, and ML scale-up path live in `CHARTS.md`.

## Quick start

```
git submodule update --init --recursive
cmake --preset dev
cmake --build --preset dev
./build/dev/trech run examples/experiments/hello_world.js
```

Build artifacts live under `build/` and are ignored by git.

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
- `examples/experiments/config_optics.js`: water box with optics enabled (includes `optics.spectrum` sample).
- `examples/experiments/h2o_fluid.js`: baseline H2O fluid stub (water box + optics).
- `examples/experiments/h2o_single_molecule.js`: single-molecule proxy stub (micro water box).
- `examples/experiments/h2o_optics_beam.js`: optical photon beam through water (spectrum-enabled).
- `examples/experiments/config_stratify.js`: event stratification thresholds/labels.
- `examples/experiments/config_stratify_ml.js`: stratification with TorchScript model path stub.
- `examples/experiments/config_chemistry_stub.js`: chemistry/DNA wiring (DNA physics when enabled; chemistry stage still stubbed by default).
- `examples/experiments/config_multiscale_stub.js`: multi-scale stub wiring config.
- `examples/experiments/config_cnt_stub.js`: CNT stub aligned with the H2O config surface (uses optional `cnt` block).
- `examples/experiments/config_cnt_world_stub.js`: CNT stub with no water box (world placement) for contrast.
- `examples/experiments/config_cnt_optics_stub.js`: CNT + optics mixed testing stub (water box + optics enabled).
- `examples/experiments/trech_helpers.js`: JS helper module (units + composition utilities).
- `examples/experiments/config_multi_beam_units.js`: unit conversion + multi-beam composition example.
- `examples/experiments/include_error_demo.js`: `TRECH_INCLUDE` stack demo (intentional failure via `include_error_helper.js`).

Helper modules are single-file today; load them with `TRECH_INCLUDE("trech_helpers.js")` to keep line numbers stable.

Optics can be constant or spectral. Use `optics.spectrum` with `energyEv` or `wavelengthNm`
entries to override refractive index/absorption/scatter per wavelength while keeping the
config JSON canonical.
H2O stubs author `system` blocks in JS to label ensembles and keep aggregation point-agnostic.

CNT runs are defined as a parallel track for schema/physics coherence; `cnt` is an optional
config block today and does not change physics until the CNT milestone is implemented.
When `cnt.enable` is true, the detector builds a simple CNT geometry stub (hollow cylinder)
inside the water box when `detector.waterBoxMm` is set, otherwise in the world. The CNT
stubs steer the beam across the CNT wall to ensure `cnt_edep_mev` is exercised (thicker
walls, low-energy proton beam in base stubs; low-energy electron beam in the optics stub
to drive optical photons). CNT analysis prioritizes electron transport behavior; photon
counts are a secondary comparison in mixed tests.

## Outputs

- `trech_provenance.jsonl`: run provenance records (config JSON, hash, seed, versions).
- `trech_scores.jsonl`: scoring summaries (total energy deposit, CNT energy deposit, optical photon counts/track length when optics are enabled, system-level density metrics, plus chemistry/DNA flags and stratify counts).
- `trech_scores.jsonl` also includes CNT config echoes (`cnt_*`) for quick run filtering.
- `trech_event_scores.jsonl`: per-event scoring summaries when `stratify.enable` is true.
- `trech_event_features.jsonl`: per-event features when `stratify.dumpFeatures` is true.
- TorchScript models consume the feature vector in `FeaturePipeline::kSchemaId` order (`trech_event_features_v1`: `total_edep_mev`, `total_track_length_mm`, `total_step_count`, `total_track_count`, `optical_photon_steps`, `optical_photon_tracks`, `optical_photon_track_length_mm`).
- `trech_resim_queue.jsonl`: exceptional event queue when `stratify.dumpResimQueue` is true.

By default these are written to the current working directory; use `--output` to redirect.
Schema details: `docs/output_schema.md`.
System aggregation uses `system.volumeMm3` when provided; otherwise it derives volume from the water box (if present) or the world cube.
Hook metadata and predictive mode details are planned to be logged in provenance when hooks/ML are enabled.

## Scenario authoring direction

- JS is a full authoring runtime: use helpers to convert units, assemble multi-entity configurations, and gate choices on runtime arguments.
- Collections should use plural names and accept either a single object or an array; loaders normalize single objects into arrays for consistency.
- Multi-beam, multi-source, and layered systems are intended targets; the engine should grow toward generic particle/source definitions without schema fragmentation.
- Use `TRECH_INCLUDE` to load helper modules while preserving per-file line numbers.
- JS runtime errors include stack traces with filenames (including `TRECH_INCLUDE` sources).
- Planned: deterministic JS hook callbacks (init/run/event/step) to steer scenario logic while preserving a stable JSON config and provenance trace.
- Hook API proposal: `docs/scenario_hooks.md` (names, allowed operations, provenance requirements).

## Dependencies

- **Geant4**: tracked as a required submodule under `thirds/geant4`.
  You still need a Geant4 build/install to build TRECH; set `Geant4_DIR` or `CMAKE_PREFIX_PATH` (for example, to the submodule build/install).
  Build with `-DTRECH_ENABLE_DNA_CHEM=ON` to enable Geant4-DNA physics when `chemistry.enable` is true.
  If a local clone exists under `thirds/geant4`, prefer it before fetching elsewhere.
  `Geant4Config.cmake` is generated by the Geant4 build/install; the template lives at `thirds/geant4/cmake/Templates/Geant4Config.cmake.in`.
  Recommended: build in `build/geant4-build` and install to `build/geant4-install` to keep the submodule clean.
- **QuickJS**: required for JS experiments. Either vendor it under `thirds/quickjs/quickjs`
  or configure with `-DTRECH_FETCH_DEPS=ON` (enabled by presets).
- **LibTorch**: optional for `TRECH_ENABLE_TORCH`. Provide `Torch_DIR` or `CMAKE_PREFIX_PATH` for the LibTorch install.
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
ctest --preset dev
```

Fallback if presets are unavailable:

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

- `ctest --preset dev` passed (latest run); optics spectrum smoke run completed with `examples/experiments/config_optics.js` (`--events 5`, output `build/dev/out_optics_spectrum`).
- H2O single-molecule proxy stub run completed with `examples/experiments/h2o_single_molecule.js` (`--events 200`, output `build/dev/out_h2o_single`); `trech_scores.jsonl` recorded `total_edep_mev` 0.4809873923 (`QBBC`, optics disabled).
- H2O optics beam stub run completed with `examples/experiments/h2o_optics_beam.js` (`--events 500`, output `build/dev/out_h2o_optics`); `trech_scores.jsonl` recorded `optical_photon_tracks` 500, `optical_photon_steps` 1098, `optical_photon_track_length_mm` 53140.1876, `total_edep_mev` 5e-06 (`QBBC+Optical`).
- CNT smoke runs completed with `examples/experiments/config_cnt_stub.js` and `examples/experiments/config_cnt_world_stub.js` (`--events 5`, outputs `build/dev/out_cnt`, `build/dev/out_cnt_world`); stubs now use a 0.8 MeV proton beam with thicker walls (diameter 3.0 nm, wallCount 5), rerun to refresh outputs.
- CNT optics smoke run completed with `examples/experiments/config_cnt_optics_stub.js` (`--events 5`, output `build/dev/out_cnt_optics`); stub now uses a 1.2 MeV electron beam with thicker walls (diameter 3.0 nm, wallCount 5), rerun to refresh outputs.
- CMake target link dependencies trimmed to avoid duplicate `libtrech_core.a` warnings on macOS.
- QuickJS header warnings are suppressed for the `trech_js` target via scoped compile flags (Clang/GNU).
- Last run: `scripts/run_validation.sh` reran to refresh `docs/validation_summary.md`; `ctest` passed, and the H2O Geant4 run completed with Geant4 resolved via `CMAKE_PREFIX_PATH=build/geant4-install`.
- `examples/experiments/config_chemistry_stub.js` run completed with `--events 5` and `--output build/dev/out_chem`; `trech_scores.jsonl` includes chemistry/DNA fields.
- Geant4 build/install is available at `build/geant4-install` (from submodule `thirds/geant4`); point `Geant4_DIR` or `CMAKE_PREFIX_PATH` there when rebuilding.
- Multi-beam helper run completed with `examples/experiments/config_multi_beam_units.js` (`--output build/dev/out_multi_beam`); `trech_scores.jsonl` recorded `total_edep_mev` 25.0, `system_volume_mm3` 1000000.0, `system_edep_mev_per_mm3` 2.5e-05 (`QBBC`, optics disabled).
- `ctest --preset dev -R trech_js_runtime` passed; includes test coverage for `TRECH_INCLUDE` error filenames and line numbers.
- Validation summary (auto-updated after a successful run): `docs/validation_summary.md`.

## Roadmap

- Short-term next steps: `ROADMAP.md` (editable source of truth)
- Initial roadmap concept: `docs/trech-roadmap.md` (reference-only)
- H2O experiment spec (initial): `examples/experiments/h2o_fluid_spec.md`
- CNT parallel track for schema/physics coherence: `ROADMAP.md`

## License

See `LICENSE`.
