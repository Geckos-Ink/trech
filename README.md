# TRECH

**Current stage: H2O baseline with optics, stratification, and initial Geant4-DNA wiring**

TRECH is a C++ simulation and learning toolkit that couples Geant4 particle transport
with a stable, scriptable experiment layer and a provenance-first data trail.
The core idea is simple: experiments are authored in JavaScript, where scenarios can
compute and compose configuration (unit conversions, dynamic assembly, multi-entity
layouts) before handing config to the deterministic-by-default C++ runtime (serialized to JSON).
Prediction
layers can relax determinism in a controlled way and are logged in provenance. The JS
runtime is a standard-compliant engine today (QuickJS) and can evolve without changing
the config surface; hook registrations and deterministic callback dispatch points
(init/run/event/step) are logged with run-level guardrails, patch/emit counters,
hook-emit dropped counters, and hook-emit payload records.

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

1. **JS experiment** composes configuration and writes global `TRECH_CONFIG` (object, JSON string, or function); `TRECH_HOOKS` are optional and can consume deterministic `ctx` payloads.
2. **C++ core** parses the JSON, dispatches `onInit` (deterministic patch/emit path), and applies CLI overrides (seed, event count).
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
- `examples/experiments/water_box.js`: container volume holding explicit water material (non-chemical boundary).
- `examples/experiments/config_optics.js`: medium box with optics enabled (includes `optics.spectrum` sample) and explicit water material.
- `examples/experiments/h2o_fluid.js`: H2O fluid stub with container + brine mixture + nested solute seed.
- `examples/experiments/h2o_single_molecule.js`: single-molecule proxy stub with container + nested sphere proxy.
- `examples/experiments/h2o_optics_beam.js`: optical photon beam through water (spectrum-enabled, explicit water material).
- `examples/experiments/config_stratify.js`: event stratification thresholds/labels.
- `examples/experiments/config_stratify_ml.js`: stratification with TorchScript model path stub.
- `examples/experiments/config_chemistry_stub.js`: chemistry/DNA wiring (DNA physics when enabled; chemistry stage still stubbed by default).
- `examples/experiments/config_multiscale_stub.js`: multi-scale stub wiring config.
- `examples/experiments/config_cnt_stub.js`: CNT stub modeled in a fluid container with explicit materials and nested volumes.
- `examples/experiments/config_cnt_world_stub.js`: CNT stub volume placed in a void container in the world (no medium box).
- `examples/experiments/config_cnt_optics_stub.js`: CNT geometry + optics mixed testing stub (medium box + optics enabled).
- `examples/experiments/config_flow_language.js`: flow-style scenario using `TRECH_FLOW` chaining (`set`, `defaults`, `merge`, `push`, `derive`, `ensureArray`, `normalizeDetectorAliases`, `finalize`, `require`) and function-based `TRECH_CONFIG`.
- `examples/experiments/config_hook_dispatch.js`: hook runtime smoke example (`ctx`, deterministic `emit`, `onInit` override patch, and hook guardrails: `hooks.maxStepCallbacks`, `hooks.maxEmitsPerCallback`, `hooks.maxEmitPayloadBytes`).
- `examples/experiments/trech_helpers.js`: JS helper module (units, constants, material presets, geometry helpers).
- `examples/experiments/config_multi_beam_units.js`: unit conversion + multi-beam composition example (uses `beams` array normalization).
- `examples/experiments/include_error_demo.js`: `TRECH_INCLUDE` stack demo (intentional failure via `include_error_helper.js`).

Helper modules are single-file today; load them with `TRECH_INCLUDE("trech_helpers.js")` to keep line numbers stable.

Optics can be constant or spectral. Use `optics.spectrum` with `energyEv` or `wavelengthNm`
entries to override refractive index/absorption/scatter per wavelength while keeping the
config JSON canonical.
H2O stubs author `system` blocks in JS to label ensembles and keep aggregation point-agnostic.

CNT runs are still a parallel track for schema/physics coherence, but they now use the
generic `geometry.volumes` surface. Volumes declare shapes (box/tube/sphere), materials,
placements, and optional `scoreEdep` flags. The CNT stubs steer the beam across a tube
shell volume to exercise `volume_edep_mev` while keeping comparisons focused on electron
transport; photon counts are a secondary comparison in mixed tests.

## Outputs

- `trech_provenance.jsonl`: run provenance records (config JSON/hash, seed, Geant4/runtime metadata, determinism mode, stratify model path/hash, stratify source counters, hook registration/dispatch counters with step/emit guardrail metadata, `hook_patch_count`/`hook_emit_count`/`hook_emit_dropped_count`, and system event moment summaries).
- `trech_scores.jsonl`: scoring summaries (total energy deposit, per-volume energy deposits when `scoreEdep` is enabled, optical photon counts/track length when optics are enabled, determinism mode, stratify model hash metadata, hook dispatch counters/guardrail fields including emit guardrails, `hook_patch_count`/`hook_emit_count`/`hook_emit_dropped_count`, system-level density metrics plus event-level moments, and chemistry/DNA flags and stratify counts).
- `trech_hook_emits.jsonl`: deterministic hook `ctx.emit(tag, payload)` records (hook name, event/step context, tag, parsed payload).
- `trech_event_scores.jsonl`: per-event scoring summaries when `stratify.enable` is true.
- `trech_event_features.jsonl`: per-event features when `stratify.dumpFeatures` is true.
- TorchScript models consume the feature vector in `FeaturePipeline::kSchemaId` order (`trech_event_features_v1`: `total_edep_mev`, `total_track_length_mm`, `total_step_count`, `total_track_count`, `optical_photon_steps`, `optical_photon_tracks`, `optical_photon_track_length_mm`).
- `trech_resim_queue.jsonl`: exceptional event queue when `stratify.dumpResimQueue` is true.

By default these are written to the current working directory; use `--output` to redirect.
Schema details: `docs/output_schema.md`.
System aggregation uses `system.volumeMm3` when provided; otherwise it derives volume from the medium box (if present) or the world cube.
Hook registrations are recorded in the config JSON; determinism and stratify model provenance fields are emitted directly by the runtime.

## Scenario authoring direction

- JS is a full authoring runtime: use helpers to convert units, assemble multi-entity configurations, and gate choices on runtime arguments.
- Experiments set `globalThis.TRECH_CONFIG` to an object, JSON string, or function returning one; `globalThis.TRECH_HOOKS` is optional and recorded for provenance.
- `TRECH_FLOW(initial)` is available globally for flow-like authoring with deterministic fluent transforms and checks: `set`, `defaults`, `merge`, `push`, `ensureArray`, `derive`, `selectBeam`, `normalizeDetectorAliases`, `finalize`, `require`/`assert`, `when`, `tap`, and `build`.
- Determinism is explicit via `determinism.mode` (`"strict"` default, `"predictive"` to enable ML inference paths when configured).
- Use `geometry.volumes` to describe named shapes and placements; enable `scoreEdep` to capture per-volume energy deposits.
- Build recursive scenes by assigning `placement.parent` to other volume names; container volumes (vacuum material) can bound fluids without modeling container chemistry.
- Use `materials` to define simple mixtures (density + component fractions) when NIST materials are insufficient; optional `smiles` is a placeholder for future registry metadata.
- `beams` is supported for array definitions (normalized to the active/first entry); `beam` remains as a single-entry alias.
- `detector` remains the canonical runtime key, but top-level `environment` and `medium` are accepted as authoring aliases and normalized by the loader.
- `G4_*` materials refer to the Geant4/NIST database; wrap them with JS presets when clarity matters.
- Collections should use plural names and accept either a single object or an array; loaders normalize single objects into arrays (materials/components/tags/optics.spectrum/hooks.registered accept single values).
- Multi-beam, multi-source, and layered systems are intended targets; the engine should grow toward generic particle/source definitions without schema fragmentation.
- Use `TRECH_INCLUDE` to load helper modules while preserving per-file line numbers.
- JS runtime errors include stack traces with filenames (including `TRECH_INCLUDE` sources).
- Hook callback dispatch points are wired at init/run/event/step boundaries and exported as deterministic run-level counters (`hook_on_*`) with `hooks.maxStepCallbacks` guardrails.
- Hook callbacks receive deterministic context (`ctx.config`, `ctx.runtime`, optional `ctx.event`, optional `ctx.step`, persistent `ctx.state`, deterministic `ctx.rng.uniform/int`, and `ctx.emit(tag, payload)`), with per-callback emit guardrails (`hooks.maxEmitsPerCallback`, `hooks.maxEmitPayloadBytes`) and dropped-emit accounting.
- `onInit` supports deterministic config patching through return value `{ override: { ... } }`; patch application is intentionally whitelisted (`beam`, `run`, `optics`, `system`, `stratify`) and tracked in outputs.
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

- `ctest --preset dev` passed (latest run); optics spectrum smoke run completed with `examples/experiments/config_optics.js` (`--events 50`, output `build/dev/out_optics_spectrum`).
- H2O single-molecule proxy stub run completed with `examples/experiments/h2o_single_molecule.js` (`--events 50`, output `build/dev/out_h2o_single`).
- H2O optics beam stub run completed with `examples/experiments/h2o_optics_beam.js` (`--events 50`, output `build/dev/out_h2o_optics`).
- CNT smoke runs completed with `examples/experiments/config_cnt_stub.js` and `examples/experiments/config_cnt_world_stub.js` (`--events 5`, outputs `build/dev/out_cnt`, `build/dev/out_cnt_world`); stubs now use container volumes with explicit materials (diameter 3.0 nm, wallCount 5) and a 0.8 MeV electron beam, rerun to refresh outputs.
- CNT optics smoke run completed with `examples/experiments/config_cnt_optics_stub.js` (`--events 5`, output `build/dev/out_cnt_optics`); stub now uses a 1.2 MeV electron beam with thicker walls (diameter 3.0 nm, wallCount 5) and `volume_edep_mev` scoring, rerun to refresh outputs.
- CMake target link dependencies trimmed to avoid duplicate `libtrech_core.a` warnings on macOS.
- QuickJS header warnings are suppressed for the `trech_js` target via scoped compile flags (Clang/GNU).
- Last run: `scripts/run_validation.sh` failed with a SIGSEGV during `examples/experiments/h2o_fluid.js` after `ctest` passed; `docs/validation_summary.md` was not refreshed.
- `examples/experiments/config_chemistry_stub.js` run completed with `--events 5` and `--output build/dev/out_chem`; `trech_scores.jsonl` includes chemistry/DNA fields.
- Geant4 build/install is available at `build/geant4-install` (from submodule `thirds/geant4`); point `Geant4_DIR` or `CMAKE_PREFIX_PATH` there when rebuilding.
- Multi-beam helper run completed with `examples/experiments/config_multi_beam_units.js` (`--output build/dev/out_multi_beam`); `trech_scores.jsonl` recorded `total_edep_mev` 25.0, `system_volume_mm3` 1000000.0, `system_edep_mev_per_mm3` 2.5e-05 (`QBBC`, optics disabled).
- Flow-language scenario run completed with `examples/experiments/config_flow_language.js` (`--events 1`, output `build/dev/out_flow_language`); provenance normalized `environment` to `detector` and preserved flow-composed optics/materials/beam fields.
- `ctest --preset dev -R trech_js_runtime` passed; includes test coverage for `TRECH_INCLUDE` error filenames/line numbers plus flow-style `TRECH_CONFIG` + `TRECH_FLOW`.
- Determinism/provenance smoke run completed with `examples/experiments/config_stratify_ml.js` (`--events 1`, output `build/dev/out_determinism`); outputs now include `determinism_mode`, `predictive_mode`, `stratify_model_hash`, and provenance stratify source counters.
- Hook runtime extension smoke run completed with `examples/experiments/config_hook_dispatch.js` (`--output build/dev/out_hook_runtime_ext`); scores/provenance now include `hook_patch_count` and `hook_emit_count`, and `trech_hook_emits.jsonl` captures deterministic emit payloads.
- Hook emit guardrails now enforce per-callback caps and payload-size caps (`hooks.maxEmitsPerCallback`, `hooks.maxEmitPayloadBytes`); scores/provenance include `hooks_guardrail_max_emits_per_callback`, `hooks_guardrail_max_emit_payload_bytes`, and `hook_emit_dropped_count` (`ctest --preset dev` passed).
- Validation summary (auto-updated after a successful run): `docs/validation_summary.md`.

## Roadmap

- Short-term next steps: `ROADMAP.md` (editable source of truth)
- Initial roadmap concept: `docs/trech-roadmap.md` (reference-only)
- H2O experiment spec (initial): `examples/experiments/h2o_fluid_spec.md`
- CNT parallel track for schema/physics coherence: `ROADMAP.md`

## License

See `LICENSE`.
