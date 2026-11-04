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
  worker configurations. Floating-point run reductions and JSONL append order still vary;
  `run.threads:1` remains the demonstrated byte-replay path. The
  [worker transport gate](../../../scripts/validate_strict_worker_transport.py) explicitly
  reports raw byte mismatches and never calls keyed equality full strict replay.

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
- **Tests:** [`tests/test_js_runtime.cpp`](../../../tests/test_js_runtime.cpp) (includes two-stage
  `ctx.cascade`, ambient-seed case, contextual `ctx.evolve` selection/no-mutation, the
  `ctx.interact` neighbour/bond case, `TRECH_INCLUDE` error filenames/lines, `TRECH_FLOW`).
- **Common mistakes:** enabling inference in strict mode; forgetting predict-count plumbing.

The C-function bindings for all authoring globals and `ctx.*` live in `JsRuntime.cpp`.
Stage training metadata and string-array serialization use shared helpers there, preserving
property order and absent-metric semantics across cascade/evolution/reaction/interaction traces.
The dispatched callback set is `onInit`, `onRunStart`, `onEventStart`, `onStep`, `onEventEnd`,
`onRunEnd`. Context uses `runtime.{seed,nEvents,mode}`, event `id` plus end-event tallies,
`step.{index,edepMeV,stepLengthMm}`, and deterministic `rng.uniform()` / inclusive `rng.int()` /
`rng.normal(mean=0,sigma=1)`. Normal sampling uses two existing uniform draws and no cached spare;
invalid parameters and zero sigma consume no draws. It works in strict mode without inference.
Mixed-stream replay, parameter guards, mean/variance/tails and fresh-runtime replay are covered
by `tests/test_js_runtime.cpp`; cross-platform transcendental rounding remains unvalidated.
Track callbacks, track context, run IDs and step positions/times are not exposed;
[`docs/scenario_hooks.md`](../../../docs/scenario_hooks.md) documents the executable surface.
Cascade traces distinguish numeric `localInDomain` from effective `inDomain`;
sorted `upstreamOutOfDomainInputs` names consumed facts produced outside their model's domain.
Hook out-of-domain counters include these inherited cascade failures. Lineage is per cascade
call. Effective `starved` / `scaleMismatch` also include consumed density/band ancestry, with
`localStarved` / `localScaleMismatch` and sorted `upstreamStarvedInputs` /
`upstreamScaleMismatchedInputs` retaining the causes. Density/band evidence does not change OOD
accounting. Cross-call/persistent-operator lineage remains in the [trust roadmap](../inference/trust/ROADMAP.md).

- **Emit guardrails silently truncate observer frames.** Symptom: a GIF ends early (MRI stage 3
  lost its reconstruction act). Cause: a callback emitting more than `hooks.maxEmitsPerCallback`
  frames — the excess is dropped and only counted in `hook_emit_dropped_count`. Fix: size the cap
  to the frames emitted per callback and check that counter is 0 after changing an emitter.

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
[`docs/atomic_stability.md`](../../../docs/atomic_stability.md).

Preserve unknown nuclear stability, widths, lifetimes and total uncertainty as `null`/not
computed. Reduced mass already includes nonrelativistic recoil. Grid interval counts must
at least double; mesh/box changes and bisection intervals are numerical diagnostics, not
physical accuracy bounds. The finite-size correction's numerical resolution remains unknown.
Node tests cover hydrogenic spectra/refinement/replay and finite-basis identities/poles;
the C++ host contract checks literal argv forwarding from outside the source directory.
