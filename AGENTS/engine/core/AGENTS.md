# Configuration, CLI and provenance — context and contracts

[Root principles](../../../AGENTS.md) · [Root roadmap](../../../ROADMAP.md) · [Parent](../AGENTS.md) · [Roadmap](ROADMAP.md)

Related owners: [Precision profiles and runtime budgets](../precision/AGENTS.md) · [JavaScript host and live lab](../runtime/AGENTS.md) · [Tests and validation ownership](../../tooling/validation/AGENTS.md).

Read the root principles and the parent handbook first; then open only the subcategory relevant to the task. Source paths and shell commands in code spans/blocks are repository-relative unless stated otherwise; Markdown links resolve from this file.

- **New config fields are conditionally serialized.** Emit a field only when non-default so config
  hashes stay byte-identical for scenarios that don't use it (`materialProbe`, `analytic.checks`,
  `models[].scale`/`operator_role`/`element_kind`/`required_context_keys`, `precision`, beam
  spread/polarization/spectrum, `run.threads`, `physics`, …). Enforced in
  [`src/core/Config.cpp`](../../../src/core/Config.cpp); round-trip in [`tests/test_config_roundtrip.cpp`](../../../tests/test_config_roundtrip.cpp).

### C++ engine — `trech_core` ([`src/core/`](../../../src/core), [`include/trech/core/`](../../../include/trech/core))

#### [`src/core/Config.cpp`](../../../src/core/Config.cpp) · [`Config.hpp`](../../../include/trech/core/Config.hpp)

Owns `TrechConfig` and all config JSON (de)serialization. Change here for the config surface,
new collections, and conditional serialization.

- **Key symbols:** `TrechConfig` (the whole config tree: `run`/`determinism`/`detector`/`beam(s)`/
  `optics`/`materials`/`geometry`/`hooks`/`models`/`materialProbe`/`analytic`/`nuclear`/`precision`/
  `stratify`/`viz`/`lab`/`system`/`multiscale`/`physics`); `PhysicsConfig` (`physics.list` names a
  Geant4 reference list — empty keeps QBBC; `radioactiveDecayThresholdYears` raises Geant4's 1-year
  very-long-decay cut; string shorthand = list); `configFromJsonString`; `configToJson`. Collections
  normalize single-or-array; `environment`/`medium` alias `detector` at parse time (canonical output
  stays `detector`). `ModelConfig` carries cascade `scale` plus contextual operator
  `operatorRole`/`elementKind`/`requiredContextKeys`. `PrecisionConfig`/`PrecisionAxisConfig` carry
  the run's precision rung and the scenario-mapped axes (`precision` shorthand: a bare string is the
  profile; an unknown name normalizes to `custom`; a `representation` role is forced display-only).
- **Typed field readers:** `fieldOr` / `fieldValue` read a present field of the wrong JSON type
  as a `FieldError` naming the field, and `located(where, ...)` prefixes each nesting level, so a
  parse error reads `optics.spectrum[1][1] must be a number` or
  `beams[0] ('p').spread.divergenceDeg must be a number`. Every config block is typed (2026-11-15);
  any JSON error a reader does not name itself still carries its block/entry location
  (`models[0] ('m'): [json.exception...]`). String lists
  (`appendStringListFromJson`) reject non-string entries. Numbers are never read from booleans.
  Every integer-typed field (`fieldOr`/`fieldValue` with an integral type, and `integerFieldOr`)
  goes through `integerFieldValue` (2026-11-16): `2.5`, `10.0` or `"3"` is `must be an integer`,
  a negative value into an unsigned field (`run.seed`) is `must be a non-negative integer`, and a
  value outside the C++ type is `is out of range`, where nlohmann used to truncate, wrap or
  overflow. JavaScript's `JSON.stringify` never writes `10.0`, so integral JS numbers parse.
- **Block and entry types (2026-11-17):** object-only blocks and collection entries go through
  `objectAt(j, where, expected)`: JSON `null` still means "unset" (defaults kept, entry skipped),
  any other non-object is a `FieldError` such as `run must be an object (got number)`,
  `physics must be a string or an object (got number)`, `materials[1] must be an object` or
  `geometry.volumes must be an array or an object` (`rejectCollection`). Before, a scalar in an
  object position silently ran with that block's defaults, also through a lab `patch`. An inner
  message starting with a space joins `located()` without a dot. Permissive `trech inspect`
  reports the located message as `config_error` (Studio's options panel shows it); strict
  inspect still exits 1. All 60 parseable example scenarios inspect without `config_error`.
- **Unknown keys (2026-11-15):** a thread-local key-read ledger records every key the parser asks
  an object about (`has`, which replaced `json::contains` in the parse section, and the field
  readers); afterwards `collectUnknownKeys` lists each key of a queried object that was never
  asked about as a dotted path (`geometry.volumes[1].colour`, sorted per object) in
  `TrechConfig::unknownKeys`. Objects the parser never queries (free-form `hooks.inputs`) are not
  judged, and hook-toggle booleans count as read. The list is never serialized (hashes
  unchanged); `trech run`/`lab` print one `TRECH config: ignoring unknown key` line per key,
  `trech inspect` adds `config_unknown_keys`, and provenance records it. When adding a parser key,
  read it through `has`/`fieldOr`, or it will be reported as unknown (the round-trip test fails if
  any serialized key is unread). `--strict-config` (all commands) turns them into an error
  (`requireNoUnknownConfigKeys`) before any output is written; it also refuses an `onInit`
  override whose leaves were not applied (`HookDispatchReport::ignoredPatchPaths`, recorded in
  provenance as `hook_patch_ignored_paths` and warned on stderr without the flag).
  `models[i].registry`, the checkpoint annotation `TRECH_ML.modelEntry()` adds, is an accepted
  key (it must be an object; not serialized, not acted on), so a strict config can load a
  registered checkpoint.
  Fully located range errors (`run.timeBudgetSeconds must be ...`) pass through unchanged. Use
  `fieldOr` for new fields.
- **Tests:** [`tests/test_config_roundtrip.cpp`](../../../tests/test_config_roundtrip.cpp) (byte-stable hashes; named parse errors).
- **Common mistakes:** unconditionally serializing a new field breaks every scenario's config hash;
  gate it on non-default and extend the round-trip test.

`StratifyConfig.resimOnStarvation` and `resimOnScaleMismatch` are independent false-default,
conditionally serialized inference resim policies. `resimOnLowConfidence` retains its hull-only
meaning; the [trust contract](../inference/trust/AGENTS.md) owns evidence/routing semantics.

#### [`src/core/RunOptions.cpp`](../../../src/core/RunOptions.cpp) · [`RunOptions.hpp`](../../../include/trech/core/RunOptions.hpp)

CLI parsing and run-time option carrier. Owns the command dispatch surface.

- **Key symbols:** `enum class CliCommand { Run, Inspect, Lab }`; `RunOptions` (carries
  `command`, paths, seed/events overrides, `scriptParameterOverrides`, hook counters, the
  post-`Initialize` carriers `analyticChecks`/`derivedOptics`/`materialProbes`, `hookRuntime`,
  and the observation-only 3D capture `captureViz`/`captureVizNonOptical`/
  `captureVizMaxTrajectories` from `--viz`/`--viz-all`/`--viz-max-trajectories`);
  `parseRunOptions`; `runUsage`; `applyRunOverrides` (applies the capture to `cfg.viz`).
- **Common mistakes:** a `--viz` capture changes the captured run's serialized config/hash (it is
  a different, honestly-recorded run); never make it the default.
- **Tests:** [`tests/test_cli_parse.cpp`](../../../tests/test_cli_parse.cpp).

#### [`src/core/LabSession.cpp`](../../../src/core/LabSession.cpp) · [`LabSession.hpp`](../../../include/trech/core/LabSession.hpp)

Owns the real-time `trech lab` protocol (no Geant4 dependency; the runner calls it).

- **Key symbols:** `LabSession::applyCommandJson` (parses `patch`/`simulate`/`snapshot`/`help`/
  `quit`), `observeSimulation` (feeds the wall-seconds/round EWMA), `roundTelemetryJson`
  (`lab_round_plan`), `config`. Omitted `simulate.events` → EWMA picks a count fitting
  `lab.targetHz`, bounded by `min/maxRoundsPerTick`.
- Lab patches parse a detached JSON merge result through the ordinary typed config reader and
  honor `--strict-config`. Permissive commands return ignored config paths for CLI warnings.
  Invalid patches and invalid explicit `simulate` overrides leave configuration and planner
  telemetry intact.
- **Tests:** [`tests/test_lab_session.cpp`](../../../tests/test_lab_session.cpp).

#### [`src/core/Provenance.cpp`](../../../src/core/Provenance.cpp) · [`Provenance.hpp`](../../../include/trech/core/Provenance.hpp)

Writes `trech_provenance.jsonl` (config JSON/hash, seed, Geant4/runtime metadata, determinism
mode, stratify model hash, hook/patch/emit/predict counters incl. `hook_predict_out_of_domain_count`,
event moment summaries and optional registry/separate-loader snapshots). `src/core/Sha256.cpp`
hashes exact loaded model bytes; config/file legacy hashes remain FNV-1a-64.
Strict multi-worker `run_start` and `run_end` records include `score_reduction` with the
reduction algorithm identity. It is output metadata and does not enter the config hash.

- **Tests:** [`tests/test_provenance_writer.cpp`](../../../tests/test_provenance_writer.cpp).

### Entry point & build

#### [`apps/trech-cli/main.cpp`](../../../apps/trech-cli/main.cpp)

The `trech` executable. `main` parses options, then dispatches: `Lab` → `runLabSession` (JSONL
loop, `GeantLabRunner`); `Inspect` → prints `{config, parameters}` JSON; `Run` → eval JS,
`onInit` hook, `applyRunOverrides`, `runGeant4`. Geant4-free builds parse config and exit OK.

- **Config-hash churn.** Symptom: unrelated scenarios' config hashes change after adding a field.
  Cause: unconditional serialization. Fix: serialize only when non-default + extend
  `test_config_roundtrip.cpp`.

## Interface ownership map

- **CLI:** `trech run <exp.js> [--macro --ui --output/-o --seed --events --param --viz
  --viz-all --viz-max-trajectories --strict-config]`,
  `trech inspect <exp.js> [--param n=<json> --strict-config]`, `trech lab [--config --commands
  --output --seed --events --strict-config]` → [`apps/trech-cli/main.cpp`](../../../apps/trech-cli/main.cpp) + `parseRunOptions`/`runUsage`
  in [`src/core/RunOptions.cpp`](../../../src/core/RunOptions.cpp).
- **Hook `ctx` surface:** `config`/`runtime`/`event`/`step`/`state`/`rng`/`emit`/`predict`/
  `cascade`/`evolve`/`materials`/`optics` → [`src/js/JsRuntime.cpp`](../../../src/js/JsRuntime.cpp).
  Authoring globals `TRECH_CONFIG`/`TRECH_HOOKS`/
  `TRECH_VALUE`/`TRECH_PARAMETER`/`TRECH_PARAMETERS`/`TRECH_FLOW`/`TRECH_INCLUDE`
  (`TRECH_FLOW` validation presets `run`/`beam`/`materials`/`geometry`/`models`/`hooks`/
  `determinism`/`environment` are read-only: `check`/`validate`/`TRECH_FLOW.check`/`definePreset`; built-ins
  cannot be redefined. `geometry` mirrors DetectorConstruction's nested `shape`/`placement` reads;
  `hooks` flags names RunAction never dispatches, non-integer guardrails and registrations without
  a `TRECH_HOOKS` function; `determinism` flags modes the engine would coerce to strict; `environment` flags a key set to
  different values in more than one of the `environment`→`medium`→`detector` aliases, which
  `configFromJsonString` merges in that order);
  bundle companion registries `TRECH_VIEWS`/`TRECH_CHECKS`/`TRECH_VALIDATIONS`.
- **Config collections** (single-or-array, plural names): `beams`/`materials`/`geometry.volumes`/
  `hooks.registered`/`models`/`optics.spectrum`/`analytic.checks`/`nuclear.cycles` →
  [`src/core/Config.cpp`](../../../src/core/Config.cpp).
- **Lab protocol:** `patch`/`simulate`/`snapshot`/`help`/`quit` → [`src/core/LabSession.cpp`](../../../src/core/LabSession.cpp).
- **Output files** (schemas in [`docs/engine/output_schema.md`](../../../docs/engine/output_schema.md)):
  `trech_scores.jsonl`/`trech_provenance.jsonl` (core writers), `trech_event_scores.jsonl`
  (stratifier), `trech_hook_emits.jsonl` (hook emits), `trech_viz_scene.json` +
  `trech_viz_trajectories.jsonl` (`VizRecorder`, gated on `viz.enable`).
