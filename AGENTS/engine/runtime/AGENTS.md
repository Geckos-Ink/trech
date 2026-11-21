# JavaScript host and live lab — context and contracts

[Root principles](../../../AGENTS.md) · [Root roadmap](../../../ROADMAP.md) · [Parent](../AGENTS.md) · [Roadmap](ROADMAP.md)

Read the root principles and the parent handbook first; then open only the subcategory relevant to the task. Source paths and shell commands in code spans/blocks are repository-relative unless stated otherwise; Markdown links resolve from this file.

- **Strict mode disables `ctx.predict`/`ctx.cascade`/`ctx.evolve`/`ctx.react`/`ctx.interact`.** All
  five return `null` outside `predictive` mode; `ctx.evolve`/`ctx.interact` leave continuous element
  (and pair) state untouched and `ctx.react`
  consumes no RNG draw/call sequence and leaves integer state untouched, so a strict run can never
  silently pick up inferred physics. Enforced in
  [`src/js/JsRuntime.cpp`](../../../src/js/JsRuntime.cpp); counted as `hook_predict_count` (a K-stage cascade
  = K predictions; a K-stage operator over N elements = **N×K** predictions — a batched call does
  not hide N inferences behind one call). Tests:
  [`tests/test_js_runtime.cpp`](../../../tests/test_js_runtime.cpp).
- **Missing inference inputs never become synthetic zero facts.** All hook prediction paths
  require their declared inputs. A cascade stage with missing inputs is recorded and skipped;
  batched operators check intermediate availability separately per element/pair and material kind.
  Blocked stages add no inference count, state change or reaction draw. Supplied zeros are valid.
  `ctx.predict(name, features?)` now starts from the same ambient Geant4 facts as the operators and
  returns `null` for missing required inputs. The generic-surrogate demo reads composition/density
  from live material probes, with a water/ethanol perturbation guard.

- **Dispatch trust counts remain separate.** `HookDispatchReport.starvedCount` and
  `scaleMismatchCount` count successful evaluations across all five inference APIs, independently
  of hull `outOfDomainCount`. Cascade counts include inherited evidence; operators retain local
  coverage and deduplicate per-feature/joint starvation per evaluation. Point predictions compare
  their declared and trained bands only when both are known, without changing their result
  payload. Strict/blocked/absent callbacks contribute zero and each dispatch resets its counts.
  The [trust contract](../inference/trust/AGENTS.md) owns the opt-in event resim policies.

- **Strict MT replay is still incomplete.** Geant4's event safety cache is now reset for strict
  runs with multiple actual workers, eliminating the demonstrated worker-history-dependent
  transport branch. Exact event/track-keyed physics matches across the exercised Tasking/MT
  worker configurations. Strict MT event scores, features and resim candidates append in
  ascending event ID per batch. Captured trajectories use ascending event/track identity for
  retention and serialization. Strict multi-worker floating sums merge exactly before rounding
  to binary64. The [worker transport gate](../../../scripts/validate_strict_worker_transport.py)
  requires score, event and trajectory byte replay across the exercised workers, and provenance
  replay for a fixed invocation. JavaScript hooks and emits still depend on scheduling.
  Use `run.threads:1` for stateful hook replay.

### C++ engine — `trech_js` ([`src/js/`](../../../src/js), [`include/trech/js/`](../../../include/trech/js))

#### [`src/js/JsRuntime.cpp`](../../../src/js/JsRuntime.cpp) · [`JsRuntime.hpp`](../../../include/trech/js/JsRuntime.hpp)

The QuickJS host: evaluates experiments, dispatches hooks, and owns the `ctx.*` surface and the
`GenericSurrogate` model registry. **This is where the cascade/predict hook-layer entry points
live.** Change here for the authoring runtime and the JS → JSON boundary.

- **Key symbols:** `evalExperimentAndGetConfigJson` (runs the JS, returns config JSON);
  `dispatchHook("onInit"|"onRun"|"onEvent"|"onStep", …)` → `HookDispatchReport` (patch/emit/
  predict counts); `setScriptParameterOverrides` / `scriptParametersJson` (the `TRECH_VALUE` /
  `trech inspect` / `--param` path); `loadedModelNames`; **`buildAmbientGeant4Seed`** (auto-seeds
  the bottom of the cascade from real Geant4 per-event tallies + `material.*`/`optics.*` probes
  for `ctx.predict`/`ctx.cascade` and every batched operator; lazily cached per hook dispatch,
  copied before caller overrides, and invalidated for every new context). `ctx.predict(name, features?)` and
  `ctx.cascade(seed?, modelNames?) -> {...context, __cascade}` are implemented here. `ctx.evolve`
  also owns contextual operator selection: `operator_role` + `element_kind` +
  `required_context_keys` choose one compatible scale-ordered group from ambient/context facts,
  surfaced through `result.selection`; ambiguous/no-compatible results do not mutate state.
  `ctx.react` reuses that selection and binds integer inventories + declared stoichiometry to
  `DiscreteTransition`, deriving a deterministic sub-seed per call. `ctx.interact` reuses it again
  and binds positions/cutoff, declared field symmetry and persistent links + pair state to
  `PairInteraction`.
- **`ctx.detectDomains`** binds equal-length numeric arrays and optional routing parent IDs to
  the [statistical subdivision engine](../inference/ROADMAP.md#live-statistical-domain-subdivision).
  Strict mode returns `null`. The hook leaves model-evaluation counts and state intact.
- **Tests:** [`tests/test_js_runtime.cpp`](../../../tests/test_js_runtime.cpp) (includes two-stage
  `ctx.cascade`, ambient-seed case, contextual `ctx.evolve` selection/no-mutation, the
  `ctx.interact` neighbour/bond case, `TRECH_INCLUDE` error filenames/lines, `TRECH_FLOW`).
- **Common mistakes:** enabling inference in strict mode; forgetting predict-count plumbing.

The C-function bindings for all authoring globals and `ctx.*` live in `JsRuntime.cpp`.
Stage training metadata and string-array serialization use shared helpers there, preserving
property order and absent-metric semantics across cascade/evolution/reaction/interaction traces.
The dispatched callback set is `onInit`, `onRunStart`, `onEventStart`, `onTrackStart`, `onStep`,
`onTrackEnd`, `onEventEnd`, `onRunEnd`. The track pair (2026-11-14) comes from
`TrechTrackingAction` (registered by `TrechActionInitialization` only when `registersTrackHook`),
which copies identity, vertex/final point, length and step count into `HookRuntimeContext`
(`hasTrackDetail`) and calls `TrechRunAction::DispatchTrackHook`; `ctx.track` is serialized in
`JsRuntime.cpp`, and `hashHookSeed` mixes the track ID only when `hasTrackDetail`. Guardrail
`hooks.maxTrackCallbacks` (per callback, conditionally serialized); counters
`hook_on_track_{start,end}_{count,raw_count,dropped_count}` plus
`hooks_guardrail_max_track_callbacks` appear in scores and provenance only when a track hook is
registered. Context uses `runtime.{seed,nEvents,mode,runId}` (`runId` = `G4Run::GetRunID`,
`null` without a run), event `id` plus end-event tallies, `step.{index,edepMeV,stepLengthMm}`
and, for engine `onStep` dispatches, the Geant4 step detail (`trackId`, `parentTrackId`,
`particle`, `volume`, `process`, `pre/postPositionMm`, `pre/postTimeNs`,
`pre/postKineticEnergyMeV`) copied by `SteppingAction` into `HookRuntimeContext` and sent through
`TrechRunAction::DispatchStepHook`. The detail and `runId` are excluded from `hashHookSeed`, so
hook RNG replay is unchanged; and deterministic `rng.uniform()` / inclusive `rng.int()` /
`rng.normal(mean=0,sigma=1)`. Normal sampling uses two existing uniform draws and no cached spare;
invalid parameters and zero sigma consume no draws. It works in strict mode without inference.
Mixed-stream replay, parameter guards, mean/variance/tails and fresh-runtime replay are covered
by `tests/test_js_runtime.cpp`, which now requires bit equality with the deterministic host math
(below), including the `mean + sigma * z` transform.
[`docs/engine/scenario_hooks.md`](../../../docs/engine/scenario_hooks.md) documents the executable surface.
Cascade traces distinguish numeric `localInDomain` from effective `inDomain`;
sorted `upstreamOutOfDomainInputs` names consumed facts produced outside their model's domain.
Hook out-of-domain counters include these inherited cascade failures. Lineage is per cascade
call. Effective `starved` / `scaleMismatch` also include consumed density/band ancestry, with
`localStarved` / `localScaleMismatch` and sorted `upstreamStarvedInputs` /
`upstreamScaleMismatchedInputs` retaining the causes. Density/band evidence does not change OOD
accounting. Cross-call/persistent-operator lineage remains in the [trust roadmap](../inference/trust/ROADMAP.md).

#### Deterministic host math — `trech_dmath` ([`src/js/DeterministicMath.c`](../../../src/js/DeterministicMath.c) · [`DeterministicMath.h`](../../../include/trech/js/DeterministicMath.h))

Hook-layer numerics replay across platforms only if every transcendental is computed by the
same code. `trech_dmath_*` is one fdlibm 5.3-derived implementation (FreeBSD/V8 revisions for
log2, cbrt, log1p, cosh, sinh) of all 22 transcendental JavaScript Math functions (including
`pow`, `atan2` and `hypot`).
It uses integer bit access and IEEE add/sub/mul/div/sqrt only, returns one canonical quiet NaN
(`0x7ff8000000000000`) for every NaN result, and its target is compiled with
`-ffp-contract=off -fno-fast-math` (an `#error` refuses fast-math or non-binary64 evaluation).

- **Routing.** CMake force-includes [`src/js/QuickJsMathRedirect.h`](../../../src/js/QuickJsMathRedirect.h)
  into `quickjs.c` only (no submodule patch): it includes `<math.h>` and then renames the libm
  transcendentals, so `Math.*` (including its function table) and the `**` operator call
  `trech_dmath`. Exact functions (`sqrt`, `fabs`, `floor`, `fmod`, ...) stay on libm. `dtoa.c`
  keeps libm `log2` for integer radix sizing. QuickJS and `JsRuntime.cpp` are also compiled
  without contraction; `ctx.rng.normal` uses `trech_dmath_log`/`cos`.
- **Identity.** `TRECH_DMATH_ID` (`trech-dmath-fdlibm-5.3/1`) is written as provenance
  `hooks_math` only when hooks are enabled. Changing any result requires bumping it and
  re-recording the goldens deliberately.
- **Tests.** CTest `trech_deterministic_math` holds per-function FNV-1a golden digests over 4096
  fixed inputs (the cross-host contract), IEEE special cases with exact bits, a loose ulp guard
  against the platform libm (1–3 ulp; macOS libm is nearly correctly rounded, fdlibm is not),
  and a check that QuickJS `Math.*`/`**` equal `trech_dmath` bit for bit. CTest
  `trech_dmath_constants` checks every decimal constant against its IEEE words. Define
  `TRECH_DMATH_STANDALONE` to build the library checks without QuickJS for another host.
- **Measured (2026-11-16, macOS):** identical goldens for arm64 and x86_64 (Rosetta) at
  -O0/-O2/-O3, including `-march=x86-64-v3` where FMA exists; the same library built with
  `-ffp-contract=fast` fails 18 digests. Against Node 24.21.0 / V8 13.6 on arm64, a
  contraction-enabled build of this source matches `Math.*` bit for bit on 50 000 inputs for 15
  functions, which shows the algorithms are V8's fdlibm and that Node's arm64 binary fuses FMA
  (so V8 itself is not bit-portable across FMA/non-FMA hosts). Node 24 defaults to
  `--use-std-math-pow` (platform `pow`); V8's legacy fdlibm `pow` and this `pow` disagree on
  ~3% of inputs, all within 1 ulp (max error 0.76 ulp here vs 0.91 ulp in V8, against
  60-digit decimal references). `Math.hypot` uses fdlibm `hypot` pairwise (QuickJS
  semantics); V8's own scaled-sum algorithm differs.

- **V8 hosts (2026-11-21).** [`scripts/build_dmath_wasm.py`](../../../scripts/build_dmath_wasm.py)
  compiles this same C file with Emscripten (`-O2 -ffp-contract=off -fno-fast-math`, standalone,
  no imports) into [`js/trech_dmath_wasm_data.js`](../../../js/trech_dmath_wasm_data.js) (base64
  module + source/header SHA-256 + compiler). [`js/trech_dmath_v8.js`](../../../js/trech_dmath_v8.js)
  instantiates it synchronously and `install(math)` replaces the 22 functions with QuickJS-equivalent
  wrappers (ToNumber in order, `pow` NaN for |x| = 1 with non-finite y, pairwise variadic
  `hypot`); exact functions and `Math.random` stay. WebAssembly f64 arithmetic never fuses, so the
  result is host-independent. CTest `trech_dmath_wasm` recomputes the 22 C goldens (parsed from
  `tests/test_deterministic_math.cpp`) in V8 and fails when the C source/header hash differs from
  the committed module (regenerate; `--check` verifies byte-reproducible output). The `**`
  operator cannot be replaced from JavaScript: V8 keeps its own pow there. QuickJS evaluates
  `**` and `Math.pow` through the same `js_pow`, so repository scripts use `Math.pow` only;
  [`scripts/check_js_pow_operator.py`](../../../scripts/check_js_pow_operator.py) (CTest
  `trech_js_pow_operator`) tokenizes `js/`, `examples/` and `projects/` and fails on any `**`.
  Regenerating needs `emcc`; running needs only Node/V8.

- **Emit guardrails silently truncate observer frames.** Symptom: a GIF ends early (MRI stage 3
  lost its reconstruction act). Cause: a callback emitting more than `hooks.maxEmitsPerCallback`
  frames — the excess is dropped and only counted in `hook_emit_dropped_count`. Fix: size the cap
  to the frames emitted per callback and check that counter is 0 after changing an emitter.

#### Live lab script host — [`src/js/LabScriptHost.cpp`](../../../src/js/LabScriptHost.cpp)

`trech lab <experiment.js>` (2026-11-21) hosts a scenario's hooks in the persistent Geant4
session and re-evaluates the scenario between batches (`reload`, `params`, and with
`--watch` automatically before a batch when a file it read changed). Header:
[`LabScriptHost.hpp`](../../../include/trech/js/LabScriptHost.hpp).

- **Stable runtime address.** The Geant4 actions copy `RunOptions::hookRuntime` when the
  kernel is built, so `LabScriptHost` owns one `JsRuntime` for the session and `commit` swaps
  a re-evaluated runtime's `Impl` into it (`JsRuntime::swap`; the QuickJS context opaque is
  `&Impl::state`, so it moves with the `Impl`). Never swap during a batch.
- **Transactional.** `prepare(changes)` evaluates in a fresh runtime with the merged
  `TRECH_VALUE` overrides (null removes one), then dispatches `onInit` on the candidate config.
  The CLI then rebases the session (replaying accepted patches) and asks
  `GeantLabRunner::accepts` (same `labKernelSignature`). Only then does it call `commit`.
  Any throw leaves the active hooks, JS state, models and config intact. Hook-set changes alter
  `hooks.registered` and are refused, because action initialization decides which Geant4
  callbacks exist; hook bodies and hook-only values are accepted.
- **Per-batch accounting.** `prepareBatch` sets `RuntimeRunMetadata::{hasHookInit, hookInit,
  labScriptJson}`; RunAction reads them at `BeginOfRunAction` into `activeHookInit_` /
  `activeLabScriptJson_` instead of the construction-time `RunOptions` copy. A load's `onInit`
  tallies go to the first completed batch after it (`batchCompleted`), and later batches report 0.
  `lab_script` = generation, trigger (`start`/`params`/`reload`/`watch`), entry, per-source
  SHA-256 relative to the entry directory, `TRECH_READ_JSON` data digests (`data`), a combined
  digest and the overrides. It is written to provenance and scores only in this mode, so other
  outputs are byte-unchanged. Hook code is not in `config_json`, which is why the identity is needed.
- **Digests are taken at read time.** `JsRuntime::sourceDigests()` returns the SHA-256 of the
  bytes each evaluation read (first read wins), so an edit saved between evaluation and commit
  is never credited to the generation that ran.
- **Watch** (`--watch`, 2026-11-21). Before each batch the CLI calls
  `changedSourceFingerprint()`: a size or modification-time change triggers a re-read and hash
  of that file, and equal bytes are no edit (the new stamp is cached). A changed on-disk state
  is re-evaluated through the same `reloadScript` path with trigger `watch`. A refusal is
  remembered by fingerprint (`refuseWatchedEdit`) so it is reported once, and the batch runs on
  the previous script even from a command file. Reverting to the active generation's bytes is
  no change.
- **Studio client.** [`studio/trech_studio/engine/live_lab.py`](../../../studio/trech_studio/engine/live_lab.py)
  (`LiveScenarioLab`) starts `trech lab <scenario> --watch`, sends Options changes as debounced,
  changed-only `params`, and runs a batch after saving a file the active generation read (the
  engine's watch does the reload). [`engine/lab.py`](../../../studio/trech_studio/engine/lab.py)
  strips the `trech-lab> ` prompt that prefixes the first line of each interactive reply and
  routes `lab_script` and `lab error:` lines.
- **Tests:** [`tests/test_lab_script_host.cpp`](../../../tests/test_lab_script_host.cpp) (stable
  address, overrides, refused out-of-range/unknown/syntax-error re-evaluations leave the hooks
  intact, edited-hook reload, null default, onInit once, identity changes, read-time digests,
  data files, triggers, watch change detection and refused-state suppression);
  [`tests/test_lab_watch.py`](../../../tests/test_lab_watch.py) (CTest `trech_lab_watch`, real
  Geant4: watched hook edits, one refusal for a beam edit, revert-is-no-change);
  [`studio/tests/test_live_lab.py`](../../../studio/tests/test_live_lab.py) (protocol routing,
  controller diffing, real-engine params/refusal/save loop when a build exists);
  [`tests/test_lab_session.cpp`](../../../tests/test_lab_session.cpp) (actions, rebase order,
  kernel signature); [`tests/test_cli_parse.cpp`](../../../tests/test_cli_parse.cpp).
  Real-kernel example: [`examples/lab/live_hook_tuning.js`](../../../examples/lab/live_hook_tuning.js).

## Lab command validation

The CLI passes `--strict-config` to the lab session. Patch validation occurs before a batch
reaches Geant4. See the [core lab contract](../core/AGENTS.md) for command semantics.

## Atomic stability research

[`js/trech_atomic_stability.js`](../../../js/trech_atomic_stability.js) numerically solves the
one-electron reduced-mass radial Coulomb problem with Sturm bisection, separate mesh/box
refinement, and a separately labelled leading charge-radius contact correction. Analytic
levels are validation references. [`js/trech_atomic_composition.js`](../../../js/trech_atomic_composition.js)
provides real-symmetric finite-basis eigenpairs and closed-sector Feshbach projection on
**supplied** matrix elements; it does not generate nuclear/QED physics.

[`tools/atomic/run.cjs`](../../../tools/atomic/run.cjs) executes both cores with installed
Node.js >=18/V8; the opt-in `trech-atomic` C++ launcher
([`src/js/AtomicResearchMain.cpp`](../../../src/js/AtomicResearchMain.cpp)) forwards arguments
without a shell. `--input` selects hydrogenic requests, `--composition` supplied matrices;
both accept bounded batches. This is an independent research/reference path, never a Geant4
tally, learned cascade, or switch of the QuickJS hook backend. Scientific scope, units, CLI,
and the standalone `trech.atomic_research.v1` report are in
[`docs/research/atomic_stability.md`](../../../docs/research/atomic_stability.md).

Preserve unknown nuclear stability, widths, lifetimes and total uncertainty as `null`/not
computed. Reduced mass already includes nonrelativistic recoil. Grid interval counts must
at least double; mesh/box changes and bisection intervals are numerical diagnostics, not
physical accuracy bounds. The finite-size correction's numerical resolution remains unknown.
Node tests cover hydrogenic spectra/refinement/replay and finite-basis identities/poles;
the C++ host contract checks literal argv forwarding from outside the source directory.
