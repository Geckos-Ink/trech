# Configuration, CLI and provenance — roadmap

[Root principles](../../../AGENTS.md) · [Root roadmap](../../../ROADMAP.md) · [Parent](../ROADMAP.md) · [Handbook](AGENTS.md)

Related owners: [Precision profiles and runtime budgets](../precision/ROADMAP.md) · [JavaScript host and live lab](../runtime/ROADMAP.md) · [Tests and validation ownership](../../tooling/validation/ROADMAP.md).

Maintain work in its owning branch. Dated results apply to the recorded checkout; they do not validate subsequent changes.

For config serialization and reporting changes, follow [precision profiles and runtime budgets](../precision/ROADMAP.md). CLI, inspected metadata and live-session changes belong to the [runtime workstream](../runtime/ROADMAP.md); regression and schema gates belong to [validation](../../tooling/validation/ROADMAP.md). Add new core-only gaps here when they do not belong to one of those workstreams.

## Priority queue

Every open item of this branch, highest priority first. The dated records below are delivery
history: the "Residual" and "Next" notes inside them are tracked here, and this queue wins
where they disagree. Keys and route steps: [priority keys](../../ROADMAP.md#priority-keys) ·
[implementation route](../../ROADMAP.md#implementation-route). When an item lands, delete it here, add a
dated record below, and queue its residuals in the same change.

- **P2** · R3 · Engine trace adoption: the trace sees a `null` engine result but not the authored law the scenario runs next. Add `ctx.authored(law)` at every residual-law fallback in the migration ledger (scenario purity report), then cross-check the static ledger against runtime `authored` counts per scenario in the validation suite. ([engine trace](#engine-trace-2026-11-22))
- **P2** · R4 · Engine trace depth: attribution is per hook invocation, not per emitted value (an invocation with one engine call and one unreported authored law counts as engine-backed). Carry value-level origin (lineage) into emit records, and trace the inner decisions of `RivalArbitration` (evolve/react/cascade/interact rivals), cascade stages and `ctx.evolve` operator routing as their own categories instead of only the `trace`-level result digest. ([engine trace](#engine-trace-2026-11-22))
- **P2** · R6 · Studio engine trace residuals: link a trace row to its emit/timeline frame (`hook`+`event` → Emits tab), show the summary's `roles` (validation/reference work) in the Attribution tab, and change the level of a running live lab (today it applies from the next start). No committed reference capture of the panel yet. ([script logging and Studio panel](#script-logging-and-studio-trace-panel-2026-11-22), [batches and roles](#trace-batches-provenance-and-roles-2026-11-22))
- **P3** · R3 · Library logging residuals: `trech_helpers.js` and the `.ui.js`/`.view.js` companions have no channel and no role. The host wraps only the functions of a validation companion's `TRECH_CHECKS[<stem>]` entry: a companion that registers under another key, or a scenario that runs a reference solver outside its companion without `TRECH_TRACE.role`, is still counted as the scenario's own path. ([library channels](#library-trace-channels-2026-11-22), [batches and roles](#trace-batches-provenance-and-roles-2026-11-22))
- **P3** · R1 · Trace reference checks: the validation suite does not yet read the `run_end` `trace` reference or check its `summary_hash` against the trace file's batch record; a run that fails before `run_end` has no reference (only the trace file's run summary). ([batches and roles](#trace-batches-provenance-and-roles-2026-11-22))
- **P3** · R5 · Geant4 trace depth: steps name the limiting process only, not the hadronic model or cross-section data set that sampled an interaction (`G4HadronicProcess` model/dataset of the step), and `NoProcess` steps (no defining process on the post-step point) are not explained. Geometry resolution issues are already in provenance but not yet mirrored as `geant4` records. ([library trace](#library-trace-geant4-torch-python-2026-11-22))
- **P3** · R4 · Library trace residuals: Evolvo's per-epoch training inside a candidate is not traced (only each candidate's result; tracing inside needs an Evolvo hook, a first-party Evolvo change); the `tools/torch/*.py` study and build scripts outside the `trech_torch` package log only through the trainers they call; Node `tools/ml/lib/orchestrate.js` does not yet pass the trace to the Python trainers it spawns or import their records the way `trech arch` does; Studio's trace panel shows `tallies` only in the record detail, not as a table. ([library trace](#library-trace-geant4-torch-python-2026-11-22))
- **P2** · R1 · Runtime (non-`onInit`) hooks cannot patch config, so ignored-override reporting covers `onInit` only; decide whether later hooks may patch at all before extending it. (dated records below)
- **P2** · R5 · Sweep the three PubChem-dependent scenarios (`beaker_water_n_pentane`, its Studio variant, `testscenario_h2o_electrolysis_combustion`) through inspect/type/unknown-key checks once a PubChem cache is present. (dated records below)

## Delivery records

<a name="library-trace-geant4-torch-python-2026-11-22"></a>

- [x] Library trace: Geant4, Torch and the Python tools (2026-11-22). The trace now shows when and
  how the base was simulated and what was inferred and trained. **Geant4**
  (`src/sim/Geant4Trace.cpp`): kernel (physics list, threads, materials, volumes, cuts,
  processes per particle), each run's beamOn and primary sources, events, tracks and steps
  (`geant4`, `geant4_track`, `geant4_step`), with thread-local tallies per process, particle,
  creator and volume flushed at each event end, and a Geant4 sentence in the verdict. **Torch in
  the engine** (`src/ml/MlTrace.cpp`): model loads with backend, module structure and LibTorch
  runtime; every forward pass (tallied per model, failures apart); each `ctx.learnDomains`
  residual-network Adam burst with loss before/after; `trech arch`'s native classic training.
  **Python** (`tools/torch/trech_torch/trace.py`): the same `trech_trace_v1` records with
  `host: "python"` for numpy arrays and fits, torch training loops (start, epochs, end), exports
  with SHA-256 and the Evolvo candidate results, used by six trainers and the architecture
  search; `trech arch --trace` gives the worker the same level and imports its records
  (`origin: "python"`) and tallies through `trace::childEnvironment`/`importRecords`. New
  generic `trace::tally`. Verification: Release CTest 78/78 incl. new `trech_geant4_trace`
  (serial and two workers: byte-identical scores/emits/event scores traced vs untraced, one
  track and step record per tallied track/step, tallies equal the event step counts, provenance
  reference) and `trech_python_trace` (API, numpy/torch records, `fit_mlp`/`fit_linear` weights
  byte-identical on/off, env-configured child summary), `trech_torch_backends` (TorchScript load
  and forward records, failure tally); V8 build (`trech_engine_trace`, `trech_torch_backends`,
  `trech_geant4_trace`, also with `TRECH_JS_ENGINE=v8`; on V8 two untraced two-worker runs already
  order their emits differently, the runtime P1 strict-MT replay item, so the Geant4 gate compares
  two-worker emits as a set and scores byte for byte). End to end: Briggs–Rauscher at `trace` level,
  `surrogate_generic_demo`, `optics_surrogate_demo` and the lava lamp (pinned budget) identical
  traced vs untraced; a traced `trech arch` job imported 14 worker records, counted 180 Evolvo
  candidate and 180 classic training steps, and produced the same TorchScript bytes and weights
  as an untraced run. A dangling `items()` of a temporary in the first `importRecords` crashed
  `trech arch` and was fixed before landing. Residuals queued above.

<a name="trace-batches-provenance-and-roles-2026-11-22"></a>

- [x] Trace batches, provenance reference and roles (2026-11-22). `trace::batchSummary(runId)`
  (called by `TrechRunAction::EndOfRunAction` on the master) writes a `batch attribution summary`
  per Geant4 run (the first also covers configuration and `onInit`) and returns a
  `trech_trace_ref_v1` reference (level, categories, path, batch, seq, FNV-1a `summary_hash`,
  totals, verdict) that `run_end` provenance stores as `trace` only while tracing; the run summary
  still covers the session and gains `batches`. Roles: `TRECH_TRACE.role(role, fn)` (QuickJS, V8,
  Node) and the host's wrapping of validation-companion functions tally `validation`/`reference`/
  `teacher`/`forced` work under `roles`, stamp `role` on records, and keep it out of the hooks'
  engine backing and the scenario totals. Studio's trace panel shows each batch verdict, then the
  run verdict, and an **Attribution** tab per hook for the run or one batch. Effect on the lamp:
  its validation companion's three `ctx.evolveField` calls move to `roles.validation`; on the
  furnace likewise (25 own engine calls, 3 validation calls). Verification: `trech_engine_trace`
  (batch numbering, per-batch counts, session totals, reference fields, off → null; roles:
  companion and `role()` tallies, unknown label rejected traced and untraced, `this` kept, role
  restored, emits/config identical) on Release, on the V8 build and with `TRECH_JS_ENGINE=v8`;
  `trech_provenance_writer`; Node `ml.test.js` 23/23; Studio `test_trace_log.py` 7/7 (a real run
  checks the `run_end` reference). End to end: Briggs–Rauscher run (emits and scores identical
  traced/untraced; only the traced `run_end` has `trace`), a two-batch `trech lab` (batch emits 8
  and 10, session 18, distinct hashes), glass furnace identical traced/untraced; the lava lamp is
  identical with `TRECH_COMPUTE_BUDGET` pinned (unpinned, two untraced runs already differ in the
  twin evidence: the queued [deterministic learner capacity](../lattice/ROADMAP.md#priority-queue)
  item). Residuals queued above.

<a name="library-trace-channels-2026-11-22"></a>

- [x] Trace channels in the shared JS libraries (2026-11-22). Nineteen `js/` libraries get a channel
  through one host-tolerant accessor (engine/loader `TRECH_TRACE`, plain-Node
  `js/trech_trace.js`, otherwise a no-op): process operators/runtime (engine advance vs the
  reason a process was not advanced, per-contract counters), solution processes, molecular particle
  (including the strict-mode null path), material facts, domain learning/tracking, chemistry and
  chemistry scene, ML (definitions; registry resolution vs fallback path), geometry audit, atomic
  references, and the authored reference solvers (foam, water MD, mW water, 2D/3D Euler,
  crystallization), whose every public step calls `TRECH_TRACE.authored`. Authored records are
  thinned to uses 1, 2, 4, 8, … (engine and Node), every use still counted. Libraries never write
  warn/error. Verification: byte-identical `trech_hook_emits.jsonl`/`trech_scores.jsonl`/
  `trech_event_scores.jsonl` before vs after and traced vs untraced on nine scenarios covering the
  instrumented libraries, plus a foam-solver probe (the foam scenario needs the absent PubChem
  cache, as before); `trech_engine_trace`, Node `ml.test.js`, Release CTest 76/76, V8 JS tests,
  the atomic-research tree 74/74 (Node atomic tests and the `trech-atomic` QuickJS host, which has
  no `TRECH_TRACE` and takes the no-op path); a `trace` name collision in `solve()` of
  `trech_atomic_stability.js` is why that file names its channel `log`;
  purity report regenerated (only the coefficient-density denominators moved: more code lines,
  same coefficients, sites and grades). Residuals queued above.

<a name="script-logging-and-studio-trace-panel-2026-11-22"></a>

- [x] Script logging API and Studio Engine trace panel (2026-11-22). JavaScript now logs through
  one API in every host: the global `TRECH_TRACE` (`info`/`log`/`debug`/`trace`/`warn`/`error`,
  `channel(category)`, `enabled`, `count`, `span`, `level`, `authored`) and a `console` routed into
  the trace, installed by the JS host for QuickJS and V8 alike; the Node model loader
  (`tools/ml/lib/load.js`, `logs` + `records`) and plain Node (`js/trech_trace.js`, configured by
  `TRECH_TRACE*`). `Trace` gained severities (warn/error reach stderr when not recorded), script
  counters, spans and per-record flushing. Studio's bottom dock has an **Engine trace** tab that
  requests the level/categories for the next run or live lab and tails `trech_trace.jsonl` live,
  with display filtering and the attribution verdict. Verification: `trech_engine_trace` (script
  API, console formatting, counters, spans, `enabled()` guard, off-mode stderr, and QuickJS vs V8
  identical records and emits in the V8 build); `node --test tools/ml/test/ml.test.js` 22/22 (loader
  and plain-Node API); Studio `test_trace_log.py` (tail, filter, panel request/filters/banner/settings,
  a real `trech run` followed live), `test_live_lab.py`, `test_ui_panels.py`; offscreen
  `StudioWindow` smoke with the panel on a Briggs–Rauscher trace. Residuals queued above.

<a name="engine-trace-2026-11-22"></a>

- [x] Engine trace, first implementation (2026-11-22). A configurable, observation-only verbose
  log answers whether a rendered result came from the engine or from a scenario's own law.
  `src/core/Trace.cpp` (levels `summary`/`info`/`debug`/`trace`, category filter, JSONL sink
  `trech_trace.jsonl`, stderr copy, per-category cap, bounded digests, run attribution summary
  with a verdict); CLI `--trace`/`--trace-file`/`--trace-stderr` and `TRECH_TRACE*` (run and
  lab). Instrumented: every JS-host inference entry point (attribution outcome per call:
  `engine`, `engine_extrapolated`, `engine_not_ran`, `null_strict`, `null_unavailable`, `error`),
  each hook invocation (`emits_without_inference`), model load/miss, `MethodArbiter` steps and
  leader changes, run start/error; scenario reports `ctx.log`, `ctx.authored`, `TRECH_LOG`
  (no-ops when off). Not in the config, hash or provenance. Verification: new
  `trech_engine_trace` (spec/CLI parsing, digest bound, strict/predictive outcomes, authored
  counts, category filter, summary-only level, traced vs untraced config and emits identical);
  Release CTest 76/76; smoke runs of `cascade_multiscale_demo` (5/5 engine) and
  `briggs_rauscher_oscillator` (5 of 8 emits without inference) with `--trace debug`/`trace`.
  Docs: [engine trace guide](../../../docs/engine/engine_trace.md), output schema, CLI and hook API.
  Residuals: queued above (adoption of `ctx.authored`, value-level attribution and rival/stage
  categories, provenance and per-batch summaries, Studio, Geant4 categories).
- [x] Config reader block and entry types (2026-11-17). Every object-only block reader and every
  collection entry (`beams`, `materials`, `models`, `geometry.volumes`, `nuclear.cycles`,
  reaction participants, `analytic.checks`, `precision.axes`, material components, optics
  spectrum points, beam `spread`/`polarization`/`spectrum`, volume `shape`/`placement`) now
  rejects a non-object with a located `must be …` error naming the accepted forms; `null` keeps
  the defaults. The same error stops a lab `patch` (`Patch failed: run must be an object (got
  number)`) without touching the active config. `trech inspect` adds `config_error` when the
  config would be refused, and Studio shows it before a run. Verification:
  `trech_config_roundtrip` (22 new rejection rows, null-unset row), `trech_lab_session` (scalar
  patch rows), a 62-scenario inspect sweep (60 parse cleanly; the two PubChem-dependent bundles
  still need a cache), Studio `test_ui_panels.py`. Residual: none in this item; the PubChem sweep
  stays queued below.
- [x] Lab command patches share config type and strict unknown-key validation (2026-11-16).
  Commands apply merge-patch semantics before validation. Rejected commands preserve the active
  config and planner. Explicit simulation overrides reject invalid types and overflowing counts.
  Unit and CLI checks cover strict errors, permissive warnings, and recovery after rejection.
- [x] Strict multi-worker run provenance identifies exact additive score reduction without
  adding a config field (2026-11-16). [Replay validation](../runtime/ROADMAP.md).
- [x] Independent `stratify.resimOnStarvation` / `resimOnScaleMismatch` opt-ins round-trip
  without changing absent/false legacy config bytes or hashes. Routing and remaining gaps are
  tracked in the [trust roadmap](../inference/trust/ROADMAP.md).
- [x] Named parse errors across the scalar config blocks (2026-11-15). `Config.cpp` gains shared
  typed readers (`fieldOr`/`fieldValue`, a `FieldError` type) and a `located()` wrapper that adds
  one path segment per level, replacing the geometry- and beam-local wrappers (their messages are
  unchanged). `environment`/`medium`/`detector`, every `beam(s)` field (incl. `spread`,
  `polarization`, `spectrum[i]`, `active`), `run`, `physics`, `determinism`, `system`, `optics`
  (incl. `spectrum[i]` in both array and object form), `optics.derive`/`opticsDerive` (incl.
  `validate.references[i]`), `viz`, `chemistry` and the volume `name`/`material`/`scoreEdep` now
  name the field (e.g. `opticsDerive.validate.references[1].energyEv must be a number`); every
  other top-level block, `materials[i]` and `models[i]` prefix the library message with their
  location. Behaviour change: a boolean where a number goes is now an error instead of 0/1.
  Compatibility: an inspect sweep of 67 example scenarios parses with no error, and
  `configToJsonString` of every one is byte-identical to the previous parser's (config hashes
  unchanged). Verification: Release and Debug CTest 53/53 (`trech_config_roundtrip`: 19 named
  field errors, 2 block prefixes, a pass-through range error, integer-valued numbers;
  `trech_geometry_resolution`: 4 volume scalar errors replace the old library-message check).
  Residual: ~~`nuclear`, `multiscale`, `analytic`, `materialProbe`, `precision`, `materials`,
  `models`, `hooks`, `stratify` and `lab` fields are not typed yet (block-level location only);
  `hooks`/`lab` integer limits and `determinism.predictive` still silently ignore a wrong type;
  `geometry.volumes[i].tags` silently drops non-string entries~~ (second pass below); three scenarios
  (`beaker_water_n_pentane`, its Studio variant, `testscenario_h2o_electrolysis_combustion`) were
  not swept because their inspect needs the PubChem cache.
- [x] Every config block typed (2026-11-15, second pass). `nuclear` (incl. `cycles[i]`,
  `source`/`target`, `forward`/`backward`, `reactants[i]`/`products[i]`), `multiscale`,
  `analytic` (`checks[i]`), `precision` (`profile`, `axes[i]`), `materialProbe` (incl.
  `interactions` particle/processes/energies), `materials[i]` (incl. `components[i]`),
  `models[i]`, `hooks`, `stratify`, `lab` and `geometry.overlapCheck.enable` read through the
  field readers. Former silent ignores are now named errors: the `hooks`/`lab` integer limits
  (`integerFieldOr`: `hooks.maxStepCallbacks must be an integer`), `determinism.predictive` and
  `precision.profile` of the wrong type, and non-string entries of every string list (`tags`,
  `materialProbe.materials`, `models[i].required_context_keys`, `hooks.registered`/`names`, a bare
  `hooks` array: `geometry.volumes[0] ('v').tags[1] must be a string`). A missing
  `materialProbe.interactions` key now gives the existing "requires particle, processes and
  energiesMeV" message instead of a JSON `out_of_range`. Compatibility: the 67-scenario inspect
  sweep and `examples/lab/realtime_lab_bootstrap.json` parse with no error, and every config's
  canonical serialization is byte-identical to the pre-session parser's. Verification: Release
  and Debug CTest 53/53 (`trech_config_roundtrip`: 23 more named errors replacing the two
  block-prefix cases, accepted list/limit forms). Residual: ~~floats still truncate into the
  remaining non-limit integer fields (`run.nEvents`, `optics.derive.nEnergyBins`,
  `lab.minRoundsPerTick`, ...) as nlohmann always did~~ (closed 2026-11-16, entry below); ~~unknown keys are still ignored, so a
  misspelled field is silent~~ (reported since 2026-11-15, entry below); the three
  PubChem-dependent scenarios remain unswept.
- [x] Unknown config keys reported (2026-11-15). `configFromJsonString` keeps a key-read ledger
  (`has` replaces all 79 `json::contains` calls in the parse section) and fills
  `TrechConfig::unknownKeys` with every key of a queried object the parser never read; it is not
  serialized, so config hashes are unchanged. `trech run`/`lab` warn on stderr, `trech inspect`
  adds `config_unknown_keys` (when the config parses), and `run_start`, `run_end` and
  `geometry_refused` provenance carry `config_unknown_keys` when non-empty. **Finding (67-scenario
  sweep):** 3 scenarios had 5 unknown keys. `aerodynamics_reference` and
  `nacl_dehydration_reference` set `beam.positionMm`, which the engine never read, so their beam
  started at the origin inside the probe volume instead of 250/40 mm upstream; both now use
  `originMm` (see the [process roadmap](../../scenarios/processes/ROADMAP.md)). They and
  `water_salt_recipe` also set a meaningless `hooks.enable`, now removed. After the fix the sweep
  finds no unknown key. Verification: Release and Debug CTest 53/53 (`trech_config_roundtrip`:
  every serialized key of the full fixture is read; six reported paths over root, nested, array
  and model entries; free-form `hooks.inputs`, hook toggles and aliases are not reported;
  `trech_geometry_resolution`: conditional provenance field), a scratch run with `run.nEvent` and
  `beam.positionMm` warns twice and records both in each provenance record. Residual: ~~unknown
  keys never fail a run (no strict opt-in)~~; ~~the onInit patcher's own whitelist ignores unknown
  patch keys without reporting them~~ (both closed 2026-11-15, entry below); unknown keys are not
  in `trech_scores.jsonl`; a key read
  only by another consumer would be reported (~~`TRECH_ML.modelEntry()`'s `models[i].registry`~~,
  accepted since 2026-11-16, entry below).
- [x] `--strict-config` and unapplied `onInit` override paths (2026-11-15). The new CLI flag
  (run, inspect, lab) makes unknown config keys an error before any output is written
  (`requireNoUnknownConfigKeys`: `--strict-config: config has 2 key(s) the engine never reads:
  beam.positionMm, run.nEvent`); without it they remain warnings. `JsRuntime::dispatchHook` now
  reports the leaf paths of an `override` that no patchable field applied (unknown,
  non-patchable or wrong-typed: `HookDispatchReport::ignoredPatchPaths`); the CLI warns per path,
  `--strict-config` refuses them, and `run_start`/`run_end`/`geometry_refused` provenance carry
  `hook_patch_ignored_paths` when non-empty. `scripts/audit_flow_presets.py` gained a `keys`
  check (in `all`) that reports `trech inspect`'s `config_unknown_keys`: `--all` gives 67 pass, 0
  issues, 3 not audited (PubChem cache). Spot runs (Release): a scratch config with
  `beam.positionMm`/`run.nEvent` exits 1 under `--strict-config` with no output directory and
  runs (with two warnings) without it; an `onInit` override `{run: {nEvents: 3, nEvent: 9},
  beam: {energyMeV: "2"}}` runs 3 events with `hook_patch_ignored_paths` `["beam.energyMeV",
  "run.nEvent"]` and is refused under the flag; `hello_world` passes with the flag.
  Verification: Release and Debug CTest 53/53 (`trech_cli_parse`, `trech_config_roundtrip`,
  `trech_js_runtime`, `trech_geometry_resolution`), `tests/test_flow_preset_audit.py` 3/3, Studio
  pytest 301/301. Residual: the validation suite does not run with `--strict-config`; runtime
  (non-`onInit`) hooks cannot patch, so only `onInit` is covered; a lab command-stream patch's
  unknown keys are not reported.
- [x] Integer fields take only integers; `models[i].registry` accepted (2026-11-16). Every
  integral field read through `fieldOr`/`fieldValue`/`integerFieldOr` now goes through
  `integerFieldValue`: a fractional or float-typed number (`run.nEvents: 2.5` or `10.0`) is
  `run.nEvents must be an integer`, a negative `run.seed` is `must be a non-negative integer`
  (it used to wrap to 2^64-1) and `run.nEvents: 3000000000` is `is out of range` (it used to
  overflow). Signed fields still accept negatives where they clamp (`hooks.maxTrackCallbacks:
  -5` → 0). Messages that named a type (`run.nEvents must be a number`, `nuclear` `z`/`a`) now
  say "integer". **Finding:** a scenario that loads a registered checkpoint through
  `TRECH_ML.modelEntry()` carries `models[i].registry`, which the parser never read, so
  `--strict-config` refused it; `registry` is now an accepted annotation (an object; not
  serialized, so hashes are unchanged) and such a scenario inspects strictly. Verification:
  Debug CTest (`trech_config_roundtrip`: ten integer cases incl. edges `2147483647`,
  `18446744073709551615`, `-1`, the registry type error, unchanged bytes with/without
  `registry`); the 68-scenario `audit_flow_presets.py --all` (inspect + keys) passes with 3
  PubChem bundles not audited; `trech lab` with `realtime_lab_bootstrap.json` and its command
  stream runs. The three PubChem-dependent scenarios remain unswept in that audit.
