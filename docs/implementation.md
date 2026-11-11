# TRECH implementation notes (initial skeleton)

## Scope

This is the M1 scaffold: JS config -> JSON -> C++ -> Geant4, with a minimal provenance JSONL log.
See `docs/trech-roadmap.md` and `docs/structure.md` for the longer-term plan.
Scenarios can now use a flow-like JS authoring surface via global `TRECH_FLOW(initial)` and can set
`globalThis.TRECH_CONFIG` as an object, JSON string, or function returning one.
`TRECH_FLOW` now includes higher-level deterministic helpers (`defaults`, `ensureArray`, `derive`,
`selectBeam`, `normalizeDetectorAliases`, `finalize`, `require`/`assert`) so scenarios can read as a
flow language while still emitting plain JSON config.
Determinism mode is configurable via `determinism.mode` (`strict` by default, `predictive` to enable
ML inference paths), and provenance captures model hash/inference source metadata.
Hook registrations from `TRECH_HOOKS` are normalized into config metadata, and run outputs now include
deterministic hook dispatch counters (`hook_on_*`) plus `hooks.maxStepCallbacks` guardrail fields.
Hook runtime dispatch now provides deterministic callback context (`ctx.config`, `ctx.runtime`,
optional `ctx.event`/`ctx.step`, persistent `ctx.state`, deterministic `ctx.rng.uniform/int`,
and `ctx.emit(tag, payload)`) across init/run/event/step boundaries.
`onInit` can return `{ override: { ... } }` for deterministic runtime patching on a whitelisted
config surface (`beam`, `run`, `optics`, `system`, `stratify`), and outputs now persist
`hook_patch_count`, `hook_emit_count`, and `trech_hook_emits.jsonl`.
System aggregation now emits run-level event energy moments (`system_event_count`,
`system_event_edep_mean_mev`, `system_event_edep_variance_mev2`, `system_event_edep_stddev_mev`)
alongside existing density metrics, plus the distribution's shape (`system_event_edep_stderr_mev`,
`_min_mev`/`_max_mev`, `_zero_fraction`, `_skewness`, `_excess_kurtosis`, `_shape_defined`) built from
additive power sums in `include/trech/sim/EventMoments.hpp`. The same summary covers the per-event
secondary multiplicity (`system_event_secondaries_*`, with a `dispersion_index` = variance/mean, split
by species as `system_event_secondaries_<species>_*` from `include/trech/sim/SecondarySpecies.hpp`) and
the per-event summed track length (`system_event_track_length_*_mm`).
`TRECH_FLOW` also carries reusable read-only validation presets (`run`, `beam`, `materials`,
`geometry`, `models`, `hooks`, `determinism`, `environment`): `flow.check(names)` returns every issue, `flow.validate(names)` throws one
aggregated error, `TRECH_FLOW.check(config, names)` audits a plain config, and
`TRECH_FLOW.definePreset(name, fnOrRules)` registers scenario-level presets. The `geometry` preset
reads the same nested `shape.*` / `placement.parent` keys DetectorConstruction reads, so it flags
exactly the volumes the engine would skip or re-parent; flat `parent`/`sizeMm` keys on a raw volume
are reported as ignored. At run time the engine records any substitution it still makes in the
provenance `geometry_resolution` block. The `environment` preset flags keys given with different
values in more than one of the `environment`/`medium`/`detector` aliases (the parser merges them in
that order, so the later alias silently wins).

## Build

```
cmake --preset dev
cmake --build --preset dev
./build/dev/trech run examples/scenarios/hello_world/hello_world.js
```

Usage:

```
trech run <experiment.js> [--macro <file>] [--output <dir>] [--seed <n>] [--events <n>]
```

Flow-style example:

```
./build/dev/trech run examples/scenarios/config_flow_language/config_flow_language.js
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
- Hook registration/dispatch metadata and guardrail counters are emitted in both files.
