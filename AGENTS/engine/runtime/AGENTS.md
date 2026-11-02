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
Cascade traces distinguish numeric `localInDomain` from effective `inDomain`;
sorted `upstreamOutOfDomainInputs` names consumed facts produced outside their model's domain.
Hook out-of-domain counters include these inherited cascade failures. Lineage is per cascade
call; starvation and off-band propagation remain open in the [trust roadmap](../inference/trust/ROADMAP.md).

- **Emit guardrails silently truncate observer frames.** Symptom: a GIF ends early (MRI stage 3
  lost its reconstruction act). Cause: a callback emitting more than `hooks.maxEmitsPerCallback`
  frames — the excess is dropped and only counted in `hook_emit_dropped_count`. Fix: size the cap
  to the frames emitted per callback and check that counter is 0 after changing an emitter.
