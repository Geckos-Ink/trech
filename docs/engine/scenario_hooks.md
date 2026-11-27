# Scenario hook API

[Documentation home](../README.md) · [Engine index](README.md) · [How a run works](../architecture/runtime.md) · [Author a scenario](../scenarios/authoring.md)

Hooks read a serialized runtime context at lifecycle boundaries. The canonical
configuration comes from `TRECH_CONFIG`. For examples and the records written by
`ctx.emit`, see the [scenario catalog](../scenarios/catalog.md) and
[output schema](output_schema.md#trech_hook_emitsjsonl).

| Task | API |
| --- | --- |
| Set typed inputs and attach callbacks | [Typed values](#typed-authoring-values) · [Registration](#registration) |
| Read Geant4 facts or keep scenario state | [Context object](#context-object) |
| Predict a named quantity or chain across bands | [`ctx.predict`](#ctxpredict) · [`ctx.cascade`](#ctxcascade) |
| Advance state, inventories or interactions | [`ctx.evolve`](#ctxevolve) · [`ctx.react`](#ctxreact) · [`ctx.interact`](#ctxinteract) |
| Lift a population or discover response laws | [`ctx.lift`](#ctxlift) · [`ctx.detectDomains`](#ctxdetectdomains) · [`ctx.learnDomains`](#ctxlearndomains) |
| Grade field methods or inspect operators | [`ctx.evolveField`](#engine-field-evolution) · [`ctx.operatorCatalog`](#read-only-operator-catalog) |
| Interpret coverage or carry selection evidence across runs | [Trust profile](#per-stage-trust-profile-low-confidence-flags-carried-with-the-model) · [Arbitration state](#arbitration-state) |

## Typed authoring values

Scenarios can declare the small set of values they intentionally want a UI or caller to override:

```js
const temperatureK = TRECH_VALUE.number("temperature_k", {
  label: "Temperature", group: "Environment", unit: "K",
  default: 293.15, min: 273.15, max: 353.15, step: 1.0
});
const quality = TRECH_VALUE.choice("quality", {
  default: "balanced", choices: ["fast", "balanced", "fine"]
});
```

Available helpers are `number`, `integer`, `boolean`, `string`, and `choice`; the generic
`TRECH_VALUE(name, {type, ...})` form is equivalent. Without an override every function returns
its declared default, so normal TRECH behavior is unchanged and has no UI dependency. Use
`trech inspect scenario.js` to obtain `{config, parameters, authoring}` without initializing Geant4, and
repeat `--param name=<json>` on `trech inspect` or `trech run` to select values. The engine rejects
unknown, duplicate, mistyped, out-of-range, or non-choice overrides before simulation. Studio uses
this contract to create its right-sidebar Options controls; it does not parse JavaScript source.
In a live `trech lab experiment.js` session, a `params` command changes these values between
batches and swaps in the re-evaluated hooks without restarting Geant4, as long as the new config
still fits the initialized kernel ([live lab](cli.md#scenario-backed-lab-re-tune-hooks-between-batches)).

The optional `TRECH_STUDIO` global supplies a data-only `trech_studio_v1` description with
title, description, panel booleans and process roles. `authoring.sources` lists the evaluated root
and included JS files in first-encounter order (unique absolute paths); optional `authoring.studio`
holds that descriptor. Studio edits these files while keeping Run tied to the root and reapplies
the UI on Save. This metadata is outside simulation config/hash; physics-relevant process choices
must remain in config/`hooks.inputs`. See [Studio JS authoring](../studio/studio_authoring.md) for limits.

## Co-located field error diagnostics

`TRECH_FIELD_ERROR(actual, reference, spacing)` calls generic C++ `scalarFieldError` without
inference or RNG. Supply equal nonempty arrays (at most 131072 finite numbers) of cell averages
on the same support and in the same units, plus positive isotropic spacing. It reports
`cell_count`, `support_volume`, volume-normalized `l1` (mean absolute error), `l2` (RMS error),
`linf` and signed `bias` (actual minus reference). It rejects malformed arrays, non-finite
differences and unrepresentable support/norms; it never interpolates or supplies missing values.
Matching units/geometry and the credibility of the reference remain the caller's responsibility.
These numerical errors do not certify physical accuracy or make independent references valid
Geant4 training labels. The exact 3D Euler verification fixture uses this API.

## Engine field evolution

[Field walkthrough and method selection](field_evolution.md) · [Emit schema](output_schema.md#engine-field-evolution-emits)

`ctx.evolveField(spec)` hands a continuum field to the engine. **Validation companions only:** a
scenario forces nothing about how the engine organises its system (root principle *A scenario
forces nothing*), so it declares no field. A `<name>.validation.js` companion may declare one to
grade the engine's methods against a reference ([scenario bundles](../scenarios/scenario_bundles.md)).
Whether fields should also emerge from the engine is an open question in the lattice roadmap. The engine owns every
prediction method and chooses among them (`trech::ml::FieldEvolution`,
[lattice handbook](../../AGENTS/engine/lattice/AGENTS.md)). It runs in predictive mode only (the
choice is statistical); strict mode returns `null`. The arbiter persists across hook calls under
`name`. The creating call must carry:

- `region`: `{shape: "cylinder", radius_mm, length_mm}` (axis z; x and y in [−R, R]) or
  `{shape: "box", size_mm: [x, y, z]}`;
- `cells`: `{min_mm: [[x,y,z]…], max_mm: [[x,y,z]…]}`, the caller's own field cells;
- `values`: the initial field per cell;
- `properties`: `kinematic_viscosity_m2_s`, `diffusivity_m2_s`, `expansion_per_unit`,
  `body_acceleration_m_s2`;
- optional `options`: `cell_mm`, `mach_target`, `twin_ratio` and `min_elements`. These are
  method numerics, not a choice of method. `options.warm_start` restores the learned state an
  earlier run exported (`export_state`), and `options.frozen: true` deploys it unchanged: the
  arbiter and the learned operator select and grade, but learn nothing. That is the held-out
  test of the choice. Both are read only on the call that creates the named field. The
  declared system must give the same cells, candidate methods and context features; otherwise
  that call throws and leaves no field behind. Physical method state (the lattices) and the
  engine's current field are not carried: they restart from the declared values. Where every
  candidate's restored error law is remote from the context (a regime the earlier run never
  reached), the restored arbiter uses the median prior there, as before any evidence, and the
  summary reports `unseen_context_share`.

Every call carries `time_s` and may carry:

- `exchanges`: `rate_per_s`, `target` and `load_per_s`, per cell;
- `reference`: per cell, the field at `time_s` to grade against (a validation teacher or a
  measurement);
- `report: "summary"`;
- `export_state: true` (plus `export_rows: true` for the learners' buffered rows), to return the
  learned state as `state` (`trech_field_evolution_v1`: the arbiter, each candidate's learned
  state — today the `learned_operator`'s learner — the candidate list and the context features).

On the first call the engine builds every method of its field-method registry
(`trech::ml::fieldMethodRegistry`, [`FieldMethods.hpp`](../../include/trech/ml/FieldMethods.hpp))
for the declared system. A method that cannot represent the system is excluded and its reason is
reported (for example, the convective lattice without a declared viscosity). The built-in
methods are:

- `lattice_convective`: lattice Boltzmann D3Q19 + D3Q7 with Boussinesq buoyancy;
- `lattice_conductive`: D3Q7 without flow;
- `learned_operator`: an online domain-learned local operator over the call context. It learns
  each cell's increment per interval from the observed transitions. It predicts persistence
  before it has a law, and abstains (no prediction) where it is far from its learned support;
- `persistence`: the last observed state.

A method registered later (an algorithm or a learned model) joins with no change to the hook or
to scenarios. Every candidate advances to `time_s` from the same observed state. The engine's
`MethodArbiter` ([`MethodArbiter.hpp`](../../include/trech/ml/MethodArbiter.hpp)) then selects
per cell, from:

- the method-independent call context: `diffusive_drive`, `exchange_drive`, `load_drive`,
  `recent_change`, `field_level` and `exposed_fraction`, in field-span units;
- the descriptors candidates contribute, named `<method>.<descriptor>`: the convective lattice's
  local Mach, cell Reynolds and Péclet numbers, scalar step, velocity curvature and wall
  distance, and the learned operator's remoteness from its support.

One domain learner per method predicts that method's log error before the call is learned. Two
policies are scored on every graded call:

- the learned per-domain selection, which leaves the leader only when the predicted advantage
  exceeds the error learners' own uncertainty;
- the recent leader: the method with the lowest decayed log error.

The learned policy is applied only while it is better on both the decayed log-ratio and the
decayed total squared error. Before any evidence separates the methods, the lower median of the
candidates' distinct predictions is used. After grading, each method observes the reference:
lattices are nudged to the reference cell means (sub-cell structure and flow kept), and the
learned operator learns the transition. Every method therefore competes one interval ahead from
the same state. Without a reference the arbitrated field becomes the state. A coarser twin
lattice supplies self-consistency evidence for the convective lattice.

The result holds:

- `field` (the arbitrated values) and `selection` (the method per cell);
- `methods`: per candidate its field, call RMSE and family, plus method reports (lattice
  steps, Mach, failure; learned `law_share` and `abstained_share`). An excluded method carries
  `available: false` and `reason`;
- `arbitrated_rmse` and `oracle_rmse`;
- `arbitration`: the policy, the leader, the policy scores and each method's populated error
  domains (`predicted_error_at_mean` and `context_envelope`);
- `self_consistency`.

With `report: "summary"` it also holds the run `summary`. A restored field's summary carries
`restored: "frozen"` or `"continued"`, and a frozen arbiter's summary also carries `frozen: true`. Nothing is written back into the
scenario: a scenario that uses `field` takes that decision itself, and must document it.

## Portable model output links

Portable `generic_surrogate_v2` models may declare per-output `identity`, `exp` or `sigmoid`
inverse links under `output_transforms`, applied after output destandardization. Sigmoid bounds
fractions numerically to [0,1] with stable finite-logit saturation; a non-finite encoded value
fails before any output is published. These numerical links supply no physical law or accuracy
guarantee. The trainer's `--logit-outputs` requires finite train/holdout targets strictly inside
(0,1), with no implicit clipping/pseudocounts. Existing identity/exp and unlinked-v1 paths retain
their arithmetic and schema. See the [trainer contract](../../tools/torch/README.md).

`generic_surrogate_v3` models are permutation-invariant set networks (DeepSets or message
passing) over element blocks of the same flat named inputs; `ctx.predict` and the batched
operators call them like any other model. Absent elements (mask feature ≤ 0.5) take no part.
See [set networks](../inference/ml_models.md#set-networks-deepsets--message-passing).

## Read-only operator catalog

`ctx.operatorCatalog()` returns a detached `trech_operator_catalog_v1` object with an
`operators` array sorted by config model name. It includes declarations with a nonempty
`operator_role`, including unloaded models, and omits ordinary point/cascade-only models.
Each entry carries `name`, the authored `path`, `loaded`, `operator_role`, `element_kind`,
`required_context_keys`, `scale`, `model_id`, `content_id`, `sha256`, `size_bytes`, `load_note`,
loaded `inputs`/`outputs`, `domain_measured`,
`trained_scale_bands`, optional `holdout` (`{r2_min,samples}` or null) and `output_accuracy`
(output name → available `r2`/`mae`/`rmse`). Optional model `feature_units` is exposed as
`{inputs:{name:unit,...},outputs:{name:unit,...}}`, or null for unloaded/legacy artifacts.
Labels describe natural inputs and decoded outputs, before input standardization and after
output destandardization/inverse links; they imply no unit conversion. If present in JSON,
both maps must contain exactly every named feature, with nonblank string labels and no extra
keys; malformed unit metadata fails model loading. Missing measured errors remain absent. Unloaded
artifacts have empty IO/model ID, null `content_id` and absent metrics. `path` remains the authored
declaration. Loaded `content_id` is `fnv1a64:<16 lowercase hex digits>` of the exact byte snapshot
consumed by the loader, independent of path. It includes whitespace and remains unchanged if
the file is replaced after loading; a fresh load gets the new identity. This noncryptographic
fingerprint is not a proof of authenticity, compatible units or physical origin. `sha256` is the
64-character lowercase SHA-256 hex digest and `size_bytes` the byte count of the **same** snapshot;
both are null for failed loads. The SHA-256 digest also establishes byte identity, not physical
validity or a signature. A sorted snapshot of the entire scenario model registry (including
point/cascade-only models) is recorded in provenance and scores as
[`model_artifacts`](output_schema.md#scenario-model-artifact-manifest).
Reads run no inference, consume no RNG/transition sequence and work in strict mode.
These are artifact descriptors, not a promise of runtime input availability, compatible units,
physical training origin or validated response. Selection and trust still come from ordinary
engine reports. Shared [process bindings](../scenarios/solution_processes.md#pinning-loaded-model-artifacts)
can optionally pin the complete loaded role/kind group before invoking an operator; the catalog
does not itself select or pin anything, and reads never reopen artifact paths. Optional
[process unit checks](../scenarios/solution_processes.md#checking-model-unit-labels) compare these loaded
labels with explicit expected IO labels. Equality checks do not prove dimensional correctness.

## Goals

- Preserve reproducibility (deterministic by default).
- Allow JS to select or adjust scenario behavior based on runtime context.
- Keep Geant4 APIs out of JS; hooks are a sideband, not a direct binding.
- Record all hook decisions in provenance.

## Registration

Experiments register hooks by setting a global `TRECH_HOOKS` object:

```js
globalThis.TRECH_HOOKS = {
  onInit(ctx) {},
  onRunStart(ctx) {},
  onEventStart(ctx) {},
  onTrackStart(ctx) {},
  onStep(ctx) {},
  onTrackEnd(ctx) {},
  onEventEnd(ctx) {},
  onRunEnd(ctx) {}
};
```

All hooks are optional. `onTrackStart` / `onTrackEnd` (since 2026-11-14) fire once per Geant4
track, before its first step and after its last, with `ctx.track`; the engine installs its
tracking action only when one of them is registered.

**A hook that throws ends the run.** The engine stops the event loop after the current event,
runs no further hook (not even `onRunEnd`), and `trech run` exits 1 with
`TRECH error: hook <name> threw: <message>` and the JS stack. Output written before the failure
stays on disk but is incomplete. Before 2026-11-26 a throw from an event, track or step hook
hung the run on a Geant4 worker with no message. For example, `ctx.evolve` returns `null` in
strict mode, so a guard such as
`if (!report) throw new Error("needs the motion model")` now fails the run, with that text,
when you forget `determinism: { mode: "predictive" }`.

### Initialization overrides

`onInit` may return `{ override: { ... } }` before TRECH creates the Geant4 kernel. For
example, this sets the source 5 mm along the negative z axis and requests a single worker
for a hook that accumulates state across events.

```js
onInit() {
  return { override: { beam: { originMm: [0, 0, -5] }, run: { threads: 1 } } };
}
```

`beam.particle` must be a name in the Geant4 particle table of the run's physics list
(`gamma`, `e-`, `proton`, `geantino`, `opticalphoton`, …). An unknown name ends the run with
`TRECH error: beam.particle '<name>' …` and exit status 1. Until 2026-11-27 the primary generator
silently fired electrons instead, while the scores still reported the requested name.

`beam.originMm` and `beam.direction` both accept `[x, y, z]` or an object such as
`{ z: -5 }` that changes only the named axes. The first three array components must all
be numeric for the vector to apply. `run.threads` accepts a nonnegative integer within
the engine's integer range. Zero restores Geant4's default worker selection. `run.nEvents`
accepts a positive integer within the same range.

TRECH reports unsupported paths and invalid values in `hook_patch_ignored_paths` and warns
while applying any valid fields. With `--strict-config`, TRECH refuses a run or lab scenario
with an ignored path. A scenario-backed lab can apply source and worker settings on initial
load. Changing either after startup requires a restart.

<a name="context-object-draft"></a>

## Context object

- `ctx.config`: immutable config object (parsed from `TRECH_CONFIG`).
- `ctx.runtime`: `{ seed, nEvents, mode, runId }`. `runId` is the Geant4 run ID of the
  dispatching run (`G4Run::GetRunID`, 0 for the first run, incrementing across lab runs) and
  `null` where no run exists (`onInit`).
- `ctx.event`: `{ id }` for event hooks; on `onEventEnd`, also includes
  Geant4 event metrics (`edepMeV`, `totalTrackLengthMm`, `totalStepCount`,
  `totalTrackCount`, `opticalPhotonSteps`, `opticalPhotonTracks`,
  `opticalPhotonTrackLengthMm`) for simulation-driven hook inference.
- `ctx.step`: `{ index, edepMeV, stepLengthMm }` for step hooks; otherwise `null`. Engine
  `onStep` dispatches also carry the Geant4 step detail: `trackId`, `parentTrackId` (0 for
  primaries), `particle`, `volume` (pre-step physical volume), `process` (post-step defining
  process, e.g. `msc`, `eIoni`, `Transportation`; `null` when none), `prePositionMm` /
  `postPositionMm` (`[x, y, z]` in the world frame), `preTimeNs` / `postTimeNs` (global time) and
  `preKineticEnergyMeV` / `postKineticEnergyMeV`. These are serialized copies of Geant4 values,
  not object bindings. They do not enter the hook RNG seed, so `ctx.rng` replay is unchanged.
  Step-hook volume stays bounded by `hooks.maxStepCallbacks`; multi-worker event order is not
  yet deterministic (see the runtime roadmap), so order-sensitive step tallies should use
  `run.threads: 1`.
- `ctx.track`: for `onTrackStart` / `onTrackEnd` only (otherwise `null`; `ctx.step` is `null` in
  them and `ctx.event` carries the event `id`). Fields: `id`, `parentId` (0 for primaries),
  `primary`, `particle`, `volume` (the vertex volume at start; the last step's pre-step volume at
  end, so a track that left the world reports where it was), `process` (the creator process at
  start, `null` for a primary; the last step's defining process at end), `positionMm`, `timeNs`
  and `kineticEnergyMeV` (vertex at start, final point at end), `lengthMm` and `stepCount`
  (0 at start; the track's totals at end, equal to its `onStep` count and summed
  `stepLengthMm`). Serialized copies of Geant4 values. The track ID enters the hook RNG seed for
  these two hooks only, so each track has its own `ctx.rng` stream and every other hook replays
  as before. Volume is bounded by `hooks.maxTrackCallbacks` (default 100000, counted separately
  for start and end; serialized only when set); the same `run.threads: 1` advice applies.
  Worked example: [`hooks_track_ledger.js`](../../examples/scenarios/hooks_track_ledger/hooks_track_ledger.js),
  graded by the suite case `hooks_track_ledger_consistent`.
- `ctx.state`: mutable per-run JS state (stored across callbacks).
- `ctx.rng`: deterministic hook-local RNG: `uniform()` in [0, 1), `int(min, max)` with
  inclusive bounds, and `normal(mean = 0, sigma = 1)` for Gaussian samples. Normal draws
  use Box–Muller and exactly two uniform draws per sample, without a cached spare. Parameters
  must be finite numbers and sigma nonnegative; omitted/`undefined` arguments use the defaults.
  Invalid parameters and sigma zero consume no draws (zero sigma returns the mean). A sample
  overflowing the finite numeric range throws `RangeError` after its two draws. The seed and
  hook/event/step identity determine replay on the same platform/runtime; cross-platform
  transcendental rounding has not been validated. RNG remains available in strict mode and
  does not count as model inference.
- `ctx.emit(tag, payload)`: write a tagged hook-emit record.
- `ctx.log(message, data?)` and `ctx.authored(law, detail?)`: reports for the
  [engine trace](engine_trace.md). `ctx.log` writes a `scenario` note. `ctx.authored` declares
  that the value about to be used comes from a law the scenario wrote, such as a fallback after
  a `null` engine result. Each law is counted in the run attribution summary. Both return
  `undefined` and do nothing while tracing is off. They never change results, RNG or emits.
  `TRECH_LOG(message, data?)` is the evaluation-time form of `ctx.log`. For levels, channels,
  counters, spans and `console`, use the global
  [`TRECH_TRACE` API](engine_trace.md#log-from-any-javascript-trech_trace-and-console), which
  works both at evaluation time and in hooks.
- `ctx.materials`: when `materialProbe.enable` is active, named Geant4 material probes plus
  `.list` (density, electron density, element number densities, mean excitation energy,
  radiation length). This is serialized engine data, not a Geant4 object binding.
- `ctx.optics`: when derived optics are available, the exact engine result used by transport and
  `trech_viz_scene.json`, keyed by both Geant4 material name and config material key plus `.list`.
  Entries include the derived spectrum, mean refractive/absorption/scatter values,
  neutral-preserving `display_rgb`, availability/note and validation deltas.

### `ctx.predict`

- `ctx.predict(modelName, features?)`: run one declared named-IO surrogate in predictive mode.
  Ambient Geant4 event/material/optics facts seed the inputs; numeric features override keys.
  Missing required inputs or strict mode return `null`, without counting an inference.
  Successful calls count toward `hook_predict_count`. The returned object also
  carries a reserved `__coverage{inDomain,domainMeasured,extrapolation,maxStandardizedDeviation,
  outOfDomainInputs}` — the honest "am I extrapolating?" signal for that prediction (see below) —
  and, when the model carries held-out metrics, a reserved `__accuracy{<output>:{r2?,mae?,rmse?,interval_half_width?,interval_coverage?}}`
  with that model's **measured** per-output error (`rmse` = held-out root mean square residual).

### `ctx.cascade`

- `ctx.cascade(seed?, modelNames?, options?)`: run declared scale-tagged models in ascending scale order.
  Within a band, dependency-ready models run first, with registration order breaking ties. When
  every fact has one writer per band and no fact a band's model writes is already present when the
  band starts, the result does not depend on the order the models were registered in (the
  [`ctx.cascade` registration-order law](formal_laws.md)); a seeded fact that a model in its band
  replaces is read as seeded by models registered before that producer. There
  is no fixed stage-depth limit. Optional `maxStages` (0 = all) and `targetOutputs` bound work
  deterministically; metadata reports omitted stages and stop reasons. See
  [adaptive precision](adaptive_precision.md#prediction-depth).
  Without an argument, the seed is automatic Geant4 event tallies + material probes + derived
  optics. An explicit object augments/overrides keys. The optional string array narrows the pass to
  named stages; use it when one config declares independent model families (for example a property
  cascade plus a per-element operator), so a model is never evaluated on unrelated missing inputs
  merely because it shares `models[]`. The result carries flat facts/predictions and
  `__cascade{stagesRun,stagesExtrapolating,seedKeys,trace}`; strict mode returns `null`.
  **Rival models.** Models in the same band that declare a shared output are rivals. By default
  the last one to run sets the fact. `options.reference: {output: value}` is evidence for those
  shared outputs (a teacher or measurement; `null` entries and outputs that no rival set shares
  are ignored). When a band ends, the engine chooses for each rival set: one member's outputs
  alone, or `ensemble_mean` (the mean of the members that ran). The chosen values replace the
  facts before any higher band reads them, and their trust lineage follows the members that
  produced them. The engine keeps one `MethodArbiter` per rival set for the run, separate from
  `ctx.evolve` and `ctx.react`. Its context is the union of the members' inputs plus each
  member's extrapolation distance. A later call without `reference` applies what was learned,
  once the evidence has separated the candidates. Without evidence and without a learned
  arbiter, nothing changes. Each call adds only one row, so the per-context choice needs many
  calls. A model in the same band that reads a rival's output before the band ends still reads
  the last writer. `__cascade.rival_arbitration` has the shape described under rival arbitration
  below (`fields` lists the shared outputs). `report_arbitration: true` adds `summary`.
  `ctx.predict` names a single model, so it has no rivals.
  To show an inferred observer quantity beside an independent reference in Studio's Scale
  ladder, emit a top-level `observer_comparisons` list (with the `__cascade` report anywhere in
  the same payload):

  ```js
  ctx.emit("cascade", {cascade_trace: c.__cascade, observer_comparisons: [{
    quantity: "rest_density", label: "Rest density", unit: "kg/m^3",
    inferred: c.macro_rest_density_kg_per_m3, stage_output: "macro_rest_density_kg_per_m3",
    reference: 998.2, reference_source: "measured water at 20 C (comparison only)",
    basis: [{quantity: "nano_number_density", value: nano.numberDensity, unit: "1/A^3",
             source: "nano MD measurement"}]}]});
  ```

  `reference: null` marks a quantity with no independent reference (shown as not graded).
  `stage_output` links the quantity to the stage whose `outputs` list names it, so that stage's
  engine trust badges appear beside the gap. The reference only grades a result; it never feeds
  the cascade. `glass_of_water_shaken.js` emits rest density, cohesion and viscosity this way.

### `ctx.evolve`

- `ctx.evolve(spec)`: the per-element **operator** — where `ctx.cascade` infers *properties*,
  `ctx.evolve` infers how a declared per-element *state* changes over `dt`, so a scenario does not
  have to hand-write the rate law. Operator stages declare contextual metadata:

  ```js
  models: [{
    name: "reaction_operator", path: "data/reaction_operator.json", scale: "meso",
    operator_role: "reaction_state",
    element_kind: "foam_parcel",
    required_context_keys: ["temperature_k", "reaction_drive"]
  }]
  ```

  The engine chains the compatible scale-tagged group over every element in one deterministic
  pass and integrates:

  ```js
  const report = ctx.evolve({
    dt,                                              // the bounded step
    fields: [{ name: "gel", min: 0, max: 1 }, "temperature_k"],
    state:  { gel: gelArray, temperature_k: tempArray },  // MUTATED IN PLACE
    aux:    { exposure: exposureArray },                  // read-only per element
    context:{ ...run-constant facts },                    // over the ambient Geant4 seed
    operator_role: "reaction_state",
    element_kind: "foam_parcel"
    // models: ["reaction_operator"]                      // optional explicit override
    // report_rates: true   // adds rates: {field: [d_<field>_dt | null]} before bounds
  });
  ```

  `report_rates: true` adds `rates`, each element's accumulated `d_<field>_dt` before
  integration and before the declared bounds (`null` for elements no operator claimed; 0 for a
  field no stage rates). A learner of the operator (`ctx.learnDomains`) must read these: a finite
  difference of the bounded state teaches the clamp, not the law.

  Without an explicit `models` list, contextual selection considers only loaded models carrying
  an `operator_role`, matches the requested role/element kind, and requires every
  `required_context_keys` entry in the ambient Geant4/material + caller context. One compatible
  role/kind group is selected; multiple groups report `ambiguous`, zero report `no_compatible`.
  Both non-selected outcomes return `ran:false` and leave state untouched. Point/cascade models
  without an operator role are recorded as `not_operator`, never executed accidentally.

  **Domain routing: unnamed groups, decided up the scale ladder** (`ctx.evolve`, `ctx.react` and,
  over pairs, `ctx.interact`).
  A call that declares no `element_kind` does not have to name its populations. When the
  compatible operators share ONE role but carry several element kinds (formerly `ambiguous`), or
  when the pool holds operator models with a role and no `element_kind`, the engine selects the
  whole pool (`selection.status: "selected"`, `selection.grouping: "domain"`, trace reason
  `domain_routed`) and routes per element:
  - Stages at the same scale band that produce a shared output are **rivals** (alternative
    descriptions of that quantity). A rival runs on an element only when its own training-domain
    check covers that element's current context: inside the per-input radius, not jointly starved
    when the model carries a joint reference, and inside its optional **`routing_domain`**.
  - `routing_domain: {features, min, max, scale}` is the measured range of per-element facts the
    law does NOT read as inputs (state fields, aux facts, intermediates or shared context), taken
    from the rows it was trained on. Laws often read the same inputs over overlapping ranges, and
    what separated their training populations was such a fact (a phase fraction). It is measured
    with `trech-measure-routing-domain`, never authored, and a malformed block fails the load.
    Prediction never reads it.
  - Measured ranges leave thin gaps between neighbouring regimes. An element no rival covers but
    inside the rivals' combined envelope (per feature, the union of their ranges) runs the single
    nearest rival, by overflow in each model's own scale units, and is counted as
    `elementsNearest`. An element outside the envelope belongs to no trained regime.
  - The check runs band by band in execution order, so a meso decision reads the intermediates
    the nano band just inferred for that element.
  - Rivals trained on the same regime both cover and both contribute unless evidence
    arbitrates them (below). In `ctx.evolve` their rates accumulate. In `ctx.react` the last
    covering rival to run sets each hazard output.
    Laws with separate domains split the population. An element no rival covers is left untouched
    by that quantity and counted (`ctx.react`: no RNG draw).
  - Stages without a rival run exactly as before.

  **Rival arbitration (evidence decides alternatives vs cooperation).** When two or more rivals
  cover the same element, coverage cannot tell whether they are alternative descriptions (one is
  right) or cooperating contributions (their rates add). By default they add. A routed
  `ctx.evolve` call may carry evidence: `reference_rates: {field: [d_field_dt per element]}` (a
  teacher or measurement; `null` entries are skipped). The engine then keeps one `MethodArbiter`
  per rival set for the run, keyed by its members and rated fields. Its candidates are every
  rival alone plus `cooperating_sum`. Its context is the element's state fields and aux facts
  plus each rival's extrapolation distance. It chooses per element from prequential evidence
  ([inference handbook](../../AGENTS/engine/inference/AGENTS.md)). Later calls without a reference
  apply what was learned, but only once the evidence has separated the candidates. Without
  evidence and without a learned arbiter, nothing changes (byte-identical). Only rate outputs are
  arbitrated; intermediates and assignments of covering rivals still all apply. The result adds
  `rival_arbitration: {sets:[{models, fields, elements, graded, applied, policy, leader,
  selected{candidate:n}, call_rmse, arbitrated_rmse, oracle_rmse}]}`, and with
  `report_arbitration: true` also `summary` (each arbiter's run summary).

  A routed `ctx.react` call takes the same evidence as
  `reference_hazards: {channel: [probability per element]}`: the probability that the cell takes
  that channel in this step (`null` entries are skipped). Its candidates are each rival's
  per-channel probabilities as if it ran alone, plus `cooperating_sum`: the probabilities with no
  rival of the set, plus every rival's change, renormalized when they exceed 1. The arbiter's
  context is the cell's species counts and aux facts, plus each rival's extrapolation distance.
  The choice is made before any draw. Draws still happen once per cell in cell order, so a
  replay with the same evidence is byte-identical. Without evidence and without a learned
  arbiter, draws and state are unchanged. `ctx.react` keeps its own arbiters, separate from
  `ctx.evolve`'s. The result's `rival_arbitration` has the same shape (`fields` lists the
  channels).

  The result carries `routing: {mode:"domain", sets:[{scale, models, elementsCovered{model:n},
  domainMeasured{model:bool}, elementsUncovered, elementsNearest, elementsOverlapping,
  elementsUnscorable}],
  groups:[{id, path, elements}], elementGroups:[id per element]}`. A group has **no name**: its
  `path` is the list of covering rival stages the element took, and its `id` is `"d"` + 8 hex digits
  of FNV-1a over that path, stable across ticks and runs. A scenario can feed `elementGroups` to
  `ctx.interact`'s per-element `element_kind` array to compose pair operators.
  Worked example: `glass_from_sand.js` with `grouping: "domain"` (validation case
  `glass_domain_routing_matches_declared`).
  `group_by: "declared"` keeps the label-only contract (an undeclared call over several kinds
  stays `ambiguous`); any other value than `"domain"`/`"declared"` throws. Different roles stay
  ambiguous, and declared kinds and explicit `models` lists keep their semantics. `ctx.interact`
  routes too, with each canonical pair as the routed element (see that call). Calls that selected before this change produce byte-identical results: the
  `grouping` and `routing` fields appear only on routed calls.

  **Several materials in one call (dynamic, in-scenario inference level).** `element_kind` may be
  a single string (one population) **or an array of per-element kinds** — `element_kind: ["wax_parcel",
  "carrier_cell", …]`, one entry per element. The engine then selects an operator **per kind**, from
  each kind's own context, and binds each group's stages to its own elements. The inference level is
  therefore not fixed for a run: two materials living in the same state arrays are advanced by the
  operators their own contexts selected, and a material that selects nothing is reported and left
  **bit-identical** rather than being pushed through another material's law. `selection.groups[]`
  carries `{elementKind, status, selectedModels, elements}` for every requested kind (one entry for
  the scalar form, so consumers read one shape), each `trace[i]` carries `elementKind` +
  `elementsMatched`, and the run-level `selection.status` becomes `partial` when some materials
  selected an operator and others did not. Accounting stays honest: `hook_predict_count` grows by
  the number of *matched* element-stages, not by stages × all elements.

  Optional `require_complete_selection: true` blocks the entire call when selection status is
  not `selected`. It returns `{ran:false, blockedReason:"incomplete_selection", inferenceCount:0,
  drawCount:0, selection}` before any inference/state write. The flag must be boolean when
  supplied; absent/false retains ordinary partial execution. This checks operator selection
  (role/kind and required context), not declared model input completeness, intermediate availability,
  topology or physical validity. Explicit `models` overrides keep their existing selection semantics.
  Shared process bindings enable this flag for per-element kinds.

  A call whose state arrays have zero elements returns `null` (nothing to evolve). Optional
  boolean `report_empty_population: true` (also accepted by `ctx.react`) instead returns
  `{ran:false, blockedReason:"no_elements", elementCount:0, inferenceCount:0, drawCount:0,
  selection}` after the usual spec validation, selection and `require_complete_selection` gate,
  so a caller can tell "nothing to advance" from an unavailable operator. No inference, draw or
  `ctx.react` call-sequence index is consumed.

  A stage output named `d_<field>_dt` is a **rate** (accumulated across stages, integrated once per
  call as `f + rate·dt`, then held inside the field's declared bounds); `set_<field>` is an **assignment** applied
  immediately and visible to higher stages; any other output is an **intermediate** a higher-scale
  stage can consume. A field's `min` and `max` must be ordered (`min <= max`, neither NaN):
  `ctx.evolve` and `ctx.interact` (for `fields` and `pair_fields`) throw a `RangeError` otherwise,
  because an unordered pair would let the clamp push a value below `min`. With ordered bounds the
  step provably lands inside them (Lean `Trech.Methods.Evolve`, see
  [formal laws](formal_laws.md)); a NaN rate still yields NaN. `dt` is a reserved readable input. Input precedence is
  field > aux > intermediate > `dt` > `context`/ambient. Missing inputs skip the
  affected element-stage, report `missingInputs`, and contribute no prediction or state change.
  An intermediate must have been produced for this element/material, or explicitly supplied in
  `context`; another material's registered producer does not supply an implicit zero. Strict mode returns `null` **and leaves the state untouched**. Every model
  evaluation counts: a K-stage operator over N elements adds **N×K** to `hook_predict_count`.
  The report carries `{ran, stagesRun, elementsEvolved, nonFiniteSteps, inferenceCount, outOfDomainInferences,
  sharedKeys, auxKeys, selection, trace}`. `nonFiniteSteps` counts the field steps whose increment
  `rate·dt` was not finite or whose result was NaN. The engine does not reject or repair them: an
  overflowing increment lands on the bound it points to, and a NaN stays NaN (no comparison with
  NaN is true, so the bounds cannot catch it). For example, a learned rate of `1e308` with
  `dt: 10` overflows to infinity and puts a `[0, 1]` field at `1`; the report then shows
  `nonFiniteSteps: 1`. A finite call reports `0`. `selection` contains the explicit/contextual mode,
  `selected`/`ambiguous`/`no_compatible` status, selected model names, and a per-model trace with
  compatibility reason and missing context keys. Each evolution `trace[i]` adds
  `integratedFields`, `assignedFields`,
  `intermediateOutputs`, `unappliedFieldOutputs` (an output naming an undeclared field — reported,
  not a silent no-op) and the per-element-aggregated trust profile `elementsOutOfDomain`,
  `elementsStarved`, `maxExtrapolation` alongside the usual `domainMeasured`/`scaleMismatch`/
  `trainedScale`/`holdoutR2`/`outputAccuracy` (the measured per-output error — see the trust-profile
  section).

  The first committed operator is
  `data/polyurethane_cascade/meso_reaction_operator.json`: 27 named inputs (eight parcel-state
  fields, two per-parcel auxiliaries, 16 shared coefficients and `dt`) → six rates plus two
  assignments. It was distilled from 115,437 reference-law rows across 285–310 K / 0.02–0.08 s
  steps and independently validated on 38,565 rows; its carried worst-output held-out
  R² is 0.9929. Its model note explicitly says `teacher=...polyurethane_foam.js` and
  `measured:false`: this proves migration fidelity, not new measured chemistry. After passing the
  paired observer and nominal/zero-gravity guards it is the scenario default; the reference path
  remains selectable as its audit/harvest teacher.

  Polyurethane also offers the experimental `constitutive_response` / `foam_parcel` group via
  `mechanics_source=operator`: six state/context inputs produce `set_relax_rate_per_s`,
  `set_drag_per_s`, `set_strength_scale`. The portable v2 model decodes log-space drag in C++;
  operators receive physical values, and reported residuals use physical units. This candidate
  is distilled from synthetic reduced-law samples (`measured:false`) and fails full-run shape
  gates despite held-out R²≥0.998. `mechanics_source=reference` therefore remains the default;
  `scripts/validate_foam_mechanics.sh` grades its separate promotion suite. Bond/contact and
  thermal laws remain comparison physics.

### `ctx.react`

- `ctx.react(spec)`: the discrete counterpart to `ctx.evolve`. It evaluates the same contextual
  operator model family over N independent integer-state elements, then keeps the stochastic and
  conservation-sensitive part inside the engine:

  The same optional `require_complete_selection` gate applies before allocating the reaction
  call sequence or drawing RNG. A blocked selection cannot perturb the next accepted reaction.

  ```js
  const report = ctx.react({
    dt,
    species: ["water", "hydrogen", "oxygen"],
    state: { water, hydrogen, oxygen }, // integer arrays, mutated atomically
    aux: { electrode_exposure },        // optional per-element numeric arrays
    context: { event_drive, field_strength },
    operator_role: "discrete_reaction",
    element_kind: "reaction_site",
    channels: [
      { name: "electrolysis",
        delta: { water: -2, hydrogen: 2, oxygen: 1 } },
      { name: "combustion",
        delta: { water: 2, hydrogen: -2, oxygen: -1 } }
    ],
    conservation: [
      { name: "H_atoms", coefficients: { water: 2, hydrogen: 2 } },
      { name: "O_atoms", coefficients: { water: 1, oxygen: 2 } },
      { name: "charge", coefficients: { water: 0, hydrogen: 0, oxygen: 0 } }
    ]
  });
  ```

  Models use exactly one output interface:

  - direct competing hazards: `hazard_electrolysis`, `hazard_combustion`, …;
  - one event hazard plus routing weights: `hazard`, `weight_cross_out`,
    `weight_cross_in`, ….

  Every learned hazard/weight is bounded to [0,1]. Direct hazards summing above one are
  deterministically renormalized. The engine draws at most one channel per element/call, checks
  that every resulting inventory remains non-negative, and applies the complete integer delta or
  none of it. Every conservation vector is checked exactly against every channel before inference;
  duplicate/malformed/non-conserving topology returns `transitionSchemaValid:false` without
  inference, RNG, or mutation. Mixing the two hazard interfaces returns
  `hazardSchemaValid:false`; model inferences remain counted, but no draw/mutation occurs.

  The report separates `inferenceCount` (N×K learned evaluations), `drawCount`,
  `transitionAttempts`, `transitionsAccepted`, and `rejectedAvailability`, and carries per-channel
  attempt/accept/conservation trace, contextual `selection`, and the same per-stage coverage,
  starvation, scale and holdout trust fields as `ctx.evolve`. Each call gets a deterministic
  sub-seed from the hook/run/event identity plus `rngCallIndex`. Strict mode returns `null` before
  consuming that call sequence and leaves every integer array untouched.

  Promoted scenario use:

  - `testscenario_h2o_electrolysis_combustion.js` defaults to a meso `ctx.react` model over
    90 two-water cells. JS declares only the phase-eligible channel and H/O coefficient vectors;
    the old probability functions are reachable solely with `reaction_source=reference`.
  - `testscenario_osmotic.js` uses a micro `ctx.evolve` model for each molecule's velocity
    response and a micro `ctx.react` channel-passage model with two direct hazards
    (`hazard_cross_out`, `hazard_cross_in`) over `inside`/`outside` molecule identity. The
    passage model infers selectivity from declared size, polarity and channel width/polarity;
    certain passage and blocking are trained past the [0,1] bound so the clamp makes them exact.
    Its membrane response is still an authored law (`physics_source=reference` runs the old
    Langevin and passage rule).
  - `testscenario_efflux.js` uses micro `ctx.evolve` for continuous particle transport and a
    separate micro `ctx.react` crossing model. Boundary-candidate selection and packet identity are
    topology/invariants; the old OU/advection/drift and crossing law is reachable solely with
    `physics_source=reference`.

  Each summary includes `trech_operator_reference_pair_v1`, and the paired validator checks
  observer gaps plus contextual selection, held-out accuracy, scale/domain trust and exact
  `hook_predict_count` accounting.

  `ctx.react` takes the same per-element `element_kind` array as `ctx.evolve`: each cell's
  chemistry is chosen by its own material class, an unclaimed cell consumes **no RNG draw** and
  mutates nothing, and each stage reports `elementKind` + `elementsMatched`. That is what a run in
  which a cell *becomes* another material needs — see `glass_from_sand.js`, where a formed glass
  cell has no declared chemistry left and is reported unclaimed rather than kept reacting.

### `ctx.interact`

- `ctx.interact(spec)`: the **pair/neighbour** operator. `ctx.evolve` answers "how does THIS
  element change?"; `ctx.interact` answers "what does one element do TO ANOTHER" — the shape of
  every remaining authored solver loop (MD force loops, bonded foam networks, PBF neighbourhood
  sums, parcel cohesion/collision terms). The engine owns the neighbour search, the canonical pair
  order and the equal-and-opposite application; the learned stages own the material response:

  ```js
  const report = ctx.interact({
    dt,
    fields: [{ name: "vx",  symmetry: "antisymmetric" },   // what a gains, b loses
             { name: "rho", symmetry: "symmetric", min: 0 }],  // both gain
    state:  { vx: vxArray, rho: rhoArray },                // MUTATED IN PLACE
    aux:    { mass: massArray },                           // read-only per element
    positions: { x: xArray, y: yArray, z: zArray },
    cutoff: 7.0,             // dynamic neighbours (<= 0 disables the search)
    maxPairs: 400000,        // bounded search; truncation is reported, not silent
    links: { a: bondA, b: bondB },                   // persistent topology (bonds)
    pair_fields: [{ name: "rest_length", min: 0 }],  // state carried BY the pair
    pair_state: { rest_length: restArray },          // MUTATED IN PLACE
    context: { ...run-constant facts },
    operator_role: "pair_interaction",
    element_kind: "foam_bond"
  });
  ```

  Stage selection, the ambient-Geant4 shared context, strict-mode gating and the trust profile are
  identical to `ctx.evolve`. Output names say what the output DOES: `d_<field>_dt` is a **rate**
  contribution to both members (integrated once over `dt`), `add_<field>` a **direct increment**
  (the neighbourhood-sum form — the caller pre-loads the field with its own self term),
  `d_<pair field>_dt` / `set_<pair field>` drive the pair's own persistent state, and anything else
  is an intermediate a higher-scale stage consumes. `set_<element field>` is refused and reported in
  `unappliedFieldOutputs`: many pairs cannot assign one element a single value.

  Each member's facts are read with the reserved `a_`/`b_` prefixes (`a_mass`, `b_temperature_k`).
  `lo_`/`hi_` give the smaller and larger of the two members' values (`lo_melt_fraction`): facts
  of the unordered pair that do not depend on which member the canonical order calls `a`. A law
  that serves a pair of materials in either order reads them as inputs or as `routing_domain`
  features. The pair geometry is read through the reserved `r`, `dx`/`dy`/`dz`, `ux`/`uy`/`uz`
  (separation `b - a` and its unit vector) plus `dt`. Input precedence is pair state > member
  facts > geometry > `lo_`/`hi_` > `dt` > `context`/ambient. Missing inputs skip the affected pair-stage and appear in
  `missingInputs`. Neighbours without a persistent link have no pair state; links without
  positions have no geometry inputs. Unclaimed/blocked links keep their state bit-identical.
  When supplied, `positions` must contain complete x/y/z arrays (Array or Float64Array), each
  exactly matching the element count with finite numeric entries; missing axes are rejected
  rather than filled with zeros. Omit `positions` for link-only calls without geometry facts.

  Engine-owned invariants: pairs are canonical `(a, b)` with `a < b`, enumerated by ascending index
  so the floating-point accumulation order **cannot** change with the cell size or hash-map layout;
  a declared link is always evaluated (a stretched bond is the interesting case) and is never
  double-counted when it also falls inside the cutoff; a symmetry-declared contribution applies the
  *same double* to both members, so an antisymmetric field's pair exchange cancels exactly;
  contributions accumulate and are applied once at the end, so no member sees a half-updated
  neighbour. Self-pairs/out-of-range links (`invalidLinks`), repeats (`duplicateLinks`) and a
  budget-truncated search (`neighborPairsSkipped`, `neighborPairsTruncated`) are reported rather
  than dropped quietly. Honest accounting: **pairs × stages** inferences are added to
  `hook_predict_count`.

  **Per material COMBINATION.** `element_kind` also accepts a per-element array here. The engine
  composes the canonical unordered pair kind from the two members' materials (`sand|sand`,
  `melt|sand`, `melt|melt`, …) and selects an operator for each combination, because what happens
  between two grains of one solid, a grain and its melt, and two melt cells are three different
  interactions. Each `trace[i]` reports `pairKind` + `pairsMatched`; a combination nobody declared
  is simply not evaluated (and its members stay untouched).

  **Pairs routed by trained domain.** A call without `element_kind` over several kinds of one
  role routes like `ctx.evolve` (`group_by: "declared"` keeps the `ambiguous` verdict). Rival
  laws (same band, a shared output, kind-free) run on a pair only when their trained domain
  covers that pair's context: member facts, geometry, pair state and lower-band intermediates.
  The result adds `routing` (its `elementGroups` holds one id per canonical pair) and
  `pairs: [[a, b], ...]` in the same order. Rivals that cover the same pair both contribute
  unless evidence arbitrates them. A routed call may carry
  `reference_pairs: {pairs?: [[a,b], ...], values: {output: [value per pair]}}`. `pairs` defaults
  to the declared links, and each value is the pair's total contribution to an accumulating
  output (`d_<field>_dt`, `add_<field>`, `d_<pair field>_dt`) of a selected model. The engine
  then chooses per pair between each rival alone and their `cooperating_sum`. The choice is
  applied to both members with the declared symmetry, so an antisymmetric exchange still cancels
  exactly. The pair's own state integrates after the choice. The arbiter's context is the union
  of the members' inputs, plus each rival's extrapolation distance. `ctx.interact` keeps its own
  arbiters. Later ungraded calls apply what was learned. Without evidence and without a learned
  arbiter, results are byte-identical. `set_` and intermediate outputs are not arbitrated. The
  result's `rival_arbitration` has the shape described for `ctx.evolve` (`fields` lists the
  arbitrated outputs).
  Optional `require_complete_selection:true` instead blocks the entire call before inference or
  element/pair-state writes, returning `ran:false`, `blockedReason:"incomplete_selection"`, zero
  inference/draw counts and the selection report. It conservatively checks all combinations of
  kinds present in the call, including combinations with no neighbouring pair. Default raw calls
  retain partial execution. This certifies selection completeness, not stage input availability.
  Shared [spatial process bindings](../scenarios/solution_processes.md#spatial-neighbour-bindings) enable this
  gate and add unit/pin checks and transactional proposal acceptance around the raw operator.

  The report carries `{ran, pairCount, linkPairs, neighborPairs, neighborPairsSkipped,
  neighborPairsTruncated, invalidLinks, duplicateLinks, nonFiniteSteps, stagesRun, inferenceCount,
  outOfDomainInferences, sharedKeys, auxKeys, selection, trace}`, plus
  `blockedReason:"no_pairs"` when a well-formed call found no link or neighbour to evaluate
  (distinct from a malformed block; `ran` stays false). `nonFiniteSteps` counts link and element
  steps with a non-finite increment or a NaN result, as in `ctx.evolve` (opposite rates that cancel
  exactly before `dt` multiplies them leave a finite step); each `trace[i]` names
  `ratedElementFields`, `incrementedElementFields`, `ratedPairFields`, `assignedPairFields`,
  `intermediateOutputs`, `unappliedFieldOutputs` and the per-pair-aggregated trust profile
  (`pairsOutOfDomain`, `pairsStarved`, `maxExtrapolation`, …). The
  [glass furnace](../../examples/scenarios/glass_from_sand/glass_from_sand.js)
  uses pair operators for conduction, with domain routing as the default.
  The [inference roadmap](../../AGENTS/engine/inference/ROADMAP.md#furnace-pair-conduction-routed-by-domain-2026-11-20)
  records evidence for those pair laws.

### `ctx.detectDomains`

- `ctx.detectDomains({features, parent_groups?, min_elements?, max_depth?, method?, shared_distance_scale?})` measures candidate
  subdomains in the current batch. Each field of `features` is an equal-length numeric array or
  typed array. Pass `routing.elementGroups` from `ctx.evolve` or `ctx.react` for the same element
  order to subdivide each routing group independently. With no parents, all rows start in one
  population.

  The default `method: "projected"` looks for gaps on named feature axes and standardized principal components
  computed with LibTorch on the CPU. If those axes provide no cut, it also checks standardized
  pairwise diagonals. Each side must have at least `min_elements` rows (default 16). A gap must
  exceed 12% of the projection span (20% for fallback diagonals), twice the uniform spacing
  heuristic `log(n)/(n-1)`, and three times the median positive spacing when multiple positive
  spacings exist. The strongest accepted gap recursively splits its population up to `max_depth` (default
  3, range 0–16). The result is `{groups: [{parent, path, elements}], elementGroups}`. `parent`
  defaults to the empty string and `path` lists the binary splits from that parent. Each
  `elementGroups` entry is an index into `groups`, or `null` for a row with a non-finite feature.
  Paths and indices describe one call. Recompute or match membership explicitly when tracking
  elements over time. Constant features and repeated grid spacings provide no split evidence.

  With `method: "density"`, LibTorch computes Euclidean distances in each parent. Two rows
  are adjacent when their distance is at most 1.15 times the smaller local radius. The radius is
  the distance to the sixth nearest other row (or `min_elements - 1` when smaller). At least two
  connected components must reach `min_elements`. The component count must fit within
  `2 ** max_depth`, and at most 10% of the rows may fall outside those components. Accepted
  components use paths `n0`, `n1`, and so on. Residual rows use `u`. A refused subdivision
  returns the unsplit population. The exact graph is evaluated in row blocks (about 32 MiB of
  distances at a time, identical to the full matrix) and supports up to 65,536 rows per parent and
  32 features. Set `shared_distance_scale: true` for coordinates in common units to preserve
  physical distances. The default scales each feature by its population standard deviation.

  Predictive mode returns diagnostics without changing state, model choice or inference counts.
  Strict mode returns `null`. For recorded examples, enable `detect_domains=true` in the glass
  furnace or lava lamp scenarios. See [output schema](output_schema.md#statistical-domain-discovery-emits).

### `ctx.learnDomains`

- `ctx.learnDomains({name, features, targets?, time?, options?, report?, export_rows?, tendencies?})` grows
  **response domains** of a live population online (`trech::ml::DomainLearner`). `features` and
  `targets` are objects of equal-length numeric arrays (sorted by name). `targets` is the response
  the scenario's own operator produced for those rows (the teacher). The learner persists across
  hook calls of one run under `name`; `options` are read on the first call only.

  - **Domains.** A tree of half-space splits over the features; its leaves are domains, each with
    a weighted-ridge law over an affine or full quadratic basis (LibTorch batched solves). A domain
    is subdivided where one law cannot explain its rows. Candidate directions are the feature
    axes, leading principal axes and directions regressed from the parent law's residuals. Cuts
    are scored at quantiles, then refined between the neighbouring quantiles. A split must lower
    a BIC-penalised error (`split_penalty`), cut the two-fold cross-validated error by `min_gain`
    (default 5%) and by more than `exact_law` (default 1e-6) of the target variance. Each side
    needs `min_elements` rows from at least `min_support_calls` calls. Siblings whose single law
    leaves less than half the BIC penalty unexplained merge back. Domain ids are persistent;
    lineage records predecessors, birth and retirement calls.
  - **Prequential grading.** Each call predicts before learning, so reported errors are
    out-of-sample. Every graded row is also predicted by a pooled single-domain law fed the same
    rows (`metrics.routed_rmse` vs `metrics.pooled_rmse`). Per domain and per context (inside
    the domain's envelope or extrapolating), the predictor is chosen from the domain's ridge law,
    ridge plus an online LibTorch residual network (when the capacity allows one) and the pooled
    law by exponentially weighted prequential error; a fourth candidate adds the forecast of the
    domain law's own residual-bias tendency (`tendency_predictor`, default on). Extrapolating rows
    start on the pooled law, and leaving it needs ten times the evidence and half its error.
    A row is extrapolating when it leaves the domain's per-feature envelope or lies more than 1.5
    support radii from its joint support (up to 32 farthest-point centres of the buffered rows,
    exported with the state). A row half a span past the box, or three radii from the support, is
    remote; it uses the pooled law whenever the pooled law is less remote. A residual network may
    move its domain's law by at most three of the law's residual standard deviations. Linear terms extrapolate at most two spans past the envelope, curvature
    terms never, and predictions stay within one span of the domain's observed responses.
  - **Frozen.** `options.frozen: true` routes and predicts; with targets it grades
    (`metrics`) but changes nothing that drives a prediction: laws, predictor choices and trend
    histories stay as restored.
  - **Change and drift.** A domain's own-law error far above its history (`drift_z`²×) marks a
    change point. A forgetting learner (`forgetting` < 1, default 0.97) then drops the domain's
    pre-change rows. A stationary learner (`forgetting: 1`) keeps reservoir-sampled rows of
    everything it saw, across runs when warm-started with rows. Either way the drift forces an
    immediate subdivision search.
  - **Tendencies.** Per domain, exponentially weighted linear trends of its population, feature
    and target means, prediction error, model value at the mean and raw-unit local
    sensitivities (model parameters), with slope, standard error, forecast at the next call and
    the latest observation's z-score; plus learner-level trends of domain count and errors. A
    significant shrinking population reports `extinction_eta`. Per call, each domain returns its
    `elements` and `error` trends plus the significant ones (`tendencies: "significant"`, the
    default for summaries); `tendencies: "all"` (default for `report: "full"`) returns every series.
  - **Cost.** Uniformly decayed weights leave a weighted fit unchanged, so a domain is refit only
    once a 32nd of its buffer (or 8 rows) is new; residual networks train once an eighth is new;
    merge checks follow refits.
  - **Capacity.** Buffer rows, maximum domains, basis degree, split candidates and residual
    network width/steps derive from the host's `ComputeBudget` (threads, memory, measured LibTorch
    matmul throughput; `trech budget` prints it). `TRECH_COMPUTE_BUDGET` (JSON or a path) pins it;
    `options.capacity` overrides fields. Results under different budgets differ, so the resolved
    `budget` and `capacity` are returned and stored in the state.
  - **State.** `report: "full"` adds `state` (`trech_domain_learner_v1`: options, capacity, budget,
    tree, per-domain scalers, envelopes, laws, residual networks, predictor choices, pooled law,
    lineage); `export_rows: true` includes the reservoir rows. `options.warm_start` restores a
    state; `options.frozen: true` routes and predicts only (targets may be omitted). Options are
    read only on the call that creates the named learner; later calls ignore them, apart from
    rejecting non-objects.

  It returns `{name, call, time, frozen, features, targets, elementDomains, predictionDomains,
  predictions, predictionStd, scored, extrapolated, metrics, domains[], events[], tendencies,
  capacity, budget, seconds}`. `predictions` are made before this call's learning; `elementDomains`
  is the membership after it. Events are `birth`, `split`, `merge`, `drift`, `reset`, `rescale`
  and `model`. The learner never changes scenario state; a scenario that applies its predictions
  (the furnace's and the efflux scenario's `learn_domains=deploy`) does so itself and must label
  the result as learned.
  Strict mode returns `null`. Set `TRECH_DEBUG_LEARNER=1` to print per-call errors and split and
  merge statistics to stderr. See [output schema](output_schema.md#response-domain-learning-emits).

### Arbitration state

- `ctx.arbitrationState({rows?})` and `ctx.restoreArbitration(state, {frozen?})` carry the learned
  rival arbiters of `ctx.evolve`, `ctx.react`, `ctx.cascade` and `ctx.interact` across runs.
  - **Export.** `ctx.arbitrationState` returns
    `{format: "trech_rival_arbitration_pools_v1", pools: {evolve, react, cascade, interact}}`.
    Each pool (`trech_rival_arbitration_v1`) holds every learned rival set with its key, its
    arbitrated names, its scales, its call clock and the arbiter (`trech_method_arbiter_v1`: its
    options, its per-candidate error learners, and its leader and policy scores). Learner rows
    are included only with `rows: true`. Run totals are not exported, so a restored pool reports
    only its new run.
  - **Restore.** `ctx.restoreArbitration` replaces the pools present in the state, after
    validating all of them; a bad state throws and changes nothing. It returns
    `{pools: {name: sets}, frozen}`.
    - With `frozen: false`, learning continues. Restored with rows, a pool continues exactly where
      the exporting run stopped.
    - With `frozen: true`, the pool selects from what it learned. It grades calls that carry
      evidence in its summary (`frozen: true`), but learns nothing. That is the held-out test of
      the choice. A frozen pool creates no arbiter for a rival set it has not seen, so that set
      stays unchanged. A restored arbiter that meets a call with another context shape leaves the
      set unchanged and reports `error`.
  - **Moving the state.** A scenario emits the export, and a later run reads it with
    `TRECH_READ_JSON`.
  - **Strict mode** returns `null`.
  - **Field arbiters:** `ctx.evolveField` carries its field arbiters through `export_state` and
    `options.warm_start` instead.

### `ctx.lift`

- `ctx.lift(spec)`: **recursive group lifting** of a population (elements → groups → … →
  observer). Each level partitions the current elements (`cell_size` lattice, explicit `groups`
  ids, or `all`) and evaluates a trained v3 set model carrying `group_lift` on every group's
  members. Members read the level-below outputs plus the synthesized `present`, `weight` and
  `rel_x/y/z`. Groups become the next level's elements (centroid position, summed weight). Any depth
  equals grouping the base elements once by their ancestor, so a group's weight and centroid are
  those of the base elements it stands for ([law](formal_laws.md), `Trech.Methods.Group`).
  Without `levels` the engine plans the hierarchy from declared `operator_role: "group_lift"`
  models by scale. Over-capacity groups are blocked, never truncated; blocked members block their
  ancestors. Out-of-domain/starved lineage propagates to the observer, through blocked groups too.
  `spec.weight` must be finite and positive (a `RangeError` otherwise). Each group evaluation is
  one inference, and strict mode returns `null`. `r.top` is the observer when the last level has
  exactly one valid group. Contract and report fields: [group lifting](../inference/group_hierarchy.md).

Ambient cascade optics keys use
`optics.<material>.{mean_refractive_index,mean_absorption_length_mm,mean_scatter_length_mm,display_r,display_g,display_b}`.
Material keys use `material.<material>.*`; event keys include `event.edep_mev`, track/step counts
and optical-photon counts/length. Missing stage inputs are recorded in the trace, never hidden.

### Per-stage trust profile (low-confidence flags carried with the model)

Every learned prediction reports whether it should be trusted for the point it ran on — the honest
signals that let a stage flag a low-confidence guess instead of silently extrapolating. Each
`__cascade.trace[i]` entry (and the `ctx.predict` `__coverage` object) carries:

- **Training-domain coverage:** `inDomain` (all inputs within the trained hull, with cascade ancestry
  as described below), `domainMeasured`
  (the hull came from training, not a heuristic fallback), `extrapolation` (how far past the hull
  edge the worst input sat, in training-σ units; 0 in-domain), `maxStandardizedDeviation` (max |z|
  over the inputs), `outOfDomainInputs` (the input names beyond their domain). A non-finite input
  (NaN or an infinity) is always out of domain: it is named, and `extrapolation` and
  `maxStandardizedDeviation` are `Infinity` (which `JSON.stringify` writes as `null`). Before
  2026-11-26 a NaN input read as in domain, because its NaN excess never compared above the
  radius; a scenario that passes a NaN now sees it counted out of domain. The domain is the
  per-feature standardized hull the trainer exports as `input_domain.standardized_radius`
  (`trech-train-surrogate`); models without it (committed ridge/logistic, illustrative hand-authored
  maps) fall back to a heuristic 3σ radius and report `domainMeasured: false`. A missing
  required input blocks prediction instead: `missingInputs` records the gap, `ran` remains false
  unless this stage evaluated another element/pair, and no inference/OOD count is added.
- **Starved region (density inside the hull):** `starvedInputs` — inputs that are within the trained
  range but land in a bin the training set never populated (a hole the model interpolated through,
  distinct from the beyond-the-edge extrapolation). Only reported when the model carries an
  `input_domain.occupancy` histogram (exported by `trech-train-surrogate`). The engine finds a
  value's bin exactly as `numpy.histogram` counted it in training, including numpy's one-bin
  correction near an edge, so a training value never reads as starved. Before 2026-11-26 the
  engine skipped that correction: a value within about one ulp below an edge read as the next bin
  up, and was flagged starved when that bin was empty. Models need no re-export; the counts were
  always numpy's ([law](formal_laws.md), `Trech.Methods.Domain`).
- **Joint starved region (the multivariate hole):** `jointMeasured` / `jointStarved` /
  `jointDistance` / `jointRadius`. Both checks above are **per feature**, so neither can see a point
  that is in range on every axis yet nowhere near any training point — train on (cold, slow) and
  (hot, fast), ask for (cold, fast), and every per-feature check passes while the model interpolates
  across a hole it never saw. The model carries a compact covering set of standardized training rows
  (`input_domain.joint.centers`, deterministic farthest-point selection) plus the distance covering
  `quantile` of the training set (`radius`); the engine reports the standardized distance to the
  nearest covered region and flags a point beyond it. `jointMeasured:false` means the model carries
  no joint reference and **the check was not performed** — unknown, not a pass; the other fields are
  then `null`. `jointDistance` is exact when starved (the case worth measuring) and the distance to
  a covering center otherwise; the shortcuts behind this never change the verdict (the
  [joint-coverage law](formal_laws.md)). Joint starvation counts into the run-level `stagesStarved`, and the
  batched operators report `elementsJointStarved` / `pairsJointStarved` + `maxJointDistance`.
  `python -m trech_torch.plan_experiments --models <model.json>` turns the same evidence into the
  operating points to simulate next, in the model's own raw input units.
- **Trained-scale band:** `trainedScale` (the dimension-scale band(s) the model was trained on, from
  the harvester's per-run band tags; empty = unknown) and `scaleMismatch` (true when the stage runs
  at a scale NOT among those bands — the model is applied off the band it learned).
- **Held-out accuracy carried with the model:** `holdoutR2` (worst output's held-out R², the
  grade-the-gap number) and `holdoutSamples`; both `null` when the model carries no metrics (never a
  fake 0 == perfect for an illustrative map).
- **Measured per-output uncertainty:** `outputAccuracy` — `{ <output>: { r2?, mae?, rmse?, interval_half_width?, interval_coverage? } }`, the
  per-quantity split of that held-out accuracy. `rmse` is the held-out root mean square residual in
  the output's own units. Each metric is independently optional and an
  unmeasured output is simply **absent** (a metric-less illustrative map reports `{}`) — absent means
  unknown, never zero error. Reported on every learned-inference path: `__cascade.trace[i]`, each
  `ctx.evolve` / `ctx.react` / `ctx.interact` stage trace, and — keyed the same way — the reserved
  `__accuracy` object on a `ctx.predict` result. Exported by `trech-train-surrogate` as
  `holdout.{r2,mae,rmse}`. A model that also carries a calibrated
  `prediction_interval{nominal_coverage, half_width{<output>}}` block adds `interval_half_width`
  (prediction ± this is meant to contain the truth with marginal probability `interval_coverage`);
  the spectrum-prediction trainer exports one from split-conformal CV residuals.

`__cascade.outputUncertainty` lists one entry per final predicted key. Each entry holds
`rmse`, the interval fields, or both from the last successful producer. An output with neither
has a `null` entry. Seed-only keys are absent and skipped stages leave previous entries intact.
`measuredUncertaintyFraction` is the fraction of final predicted keys with either metric,
counting each key once. It is `null` if no predictions ran. These are model-level error metrics
in the original output units. Read query coverage and extrapolation from the stage trace.

For cascade stages, `localInDomain` reports the current model's numeric coverage alone and
`upstreamOutOfDomainInputs` lists the sorted consumed keys whose current values came from a locally
or transitively out-of-domain prediction. Effective `inDomain` requires both `localInDomain` and
an empty upstream list. Thus a bounded lower-stage output cannot silently regain trust just by
fitting the next model's hull. `outOfDomainInputs`, `extrapolation`, `maxStandardizedDeviation` and
`domainMeasured` remain local measurements; an inherited-only failure can have zero local
extrapolation. Trust follows consumed dependencies, so independent branches remain independent;
a successful clean overwrite replaces the overwritten key's ancestry, while a skipped stage
cannot clear it. This lineage is scoped to one cascade call.

Cascade density and band evidence follow the same consumed-key lineage independently of hull
coverage. `localStarved` combines the current model's per-feature and joint starvation checks;
`starved` also includes the sorted `upstreamStarvedInputs`. Effective `scaleMismatch` includes
both `localScaleMismatch` (the current model's declared band versus its trained bands) and sorted
`upstreamScaleMismatchedInputs`. `starvedInputs`, `jointMeasured`/`jointStarved`/`jointDistance`/
`jointRadius`, and `trainedScale` retain their local meanings: inherited evidence never invents a
local measurement or trained band. Neither starvation nor band mismatch changes `inDomain`, the
hook OOD counter, or OOD resim routing. Batched operators retain their local trust contract;
cross-call and persistent-state lineage are not inferred from matching numeric values or names.

Run-level rollups on `__cascade`: `stagesExtrapolating` (ran stages locally or transitively out-of-domain),
`stagesScaleMismatched` (ran stages locally or transitively off-band), and `stagesStarved` (ran
stages with local per-feature/joint starvation or consuming starved predictions). The whole run
reports `hook_predict_out_of_domain_count` in
`trech_scores.jsonl` / `trech_provenance.jsonl` — the auditable count of learned predictions made
outside their trained domain or consuming such a cascade prediction (a subset of `hook_predict_count`).

**Acting on the flag (resim routing).** Setting `stratify.resimOnLowConfidence: true` (with
`stratify.enable` + `stratify.dumpResimQueue`) makes an event whose `onEventEnd` inference ran
out-of-domain a **resim candidate**: it is written to `trech_resim_queue.jsonl` with
`reason: "inference_out_of_domain"` / `source: "cascade_coverage"` even when the feature-based
stratifier labels it predictable, and counted in `stratify_low_confidence_count` (distinct from the
stratifier's own `stratify_exceptional_count`). This is how the coverage flag drives the
exceptional/resim path, not just surfaces itself.

Two independent opt-ins extend this to sparse-training and off-band evidence:
`stratify.resimOnStarvation: true` queues per-feature or joint starvation, and
`stratify.resimOnScaleMismatch: true` queues declared-versus-trained scale mismatches.
Both default to false and require `stratify.enable`; writing candidates also requires
`stratify.dumpResimQueue`. All five inference APIs contribute their successful evaluations from
this event's `onEventEnd` dispatch. Cascade counts include inherited causes; batched operators
use their local checks and count overlapping per-feature/joint starvation once per evaluation.
Point predictions check off-band use only when their declared and trained scales are both known;
their existing result payload is unchanged.
Strict mode contributes zero. Other callbacks and earlier events do not contribute.

When either new policy is enabled, event `stratification` and queue records carry
`inference_starved_count`, `inference_scale_mismatch_count` and `inference_resim_reasons`.
The latter lists every enabled triggering cause, in hull/starvation/band order:
`inference_out_of_domain`, `inference_starved`, `inference_scale_mismatch`.
Feature-exceptional events retain their stratifier reason/source; otherwise the queue uses the
first inference reason and `source: "cascade_coverage"`. `low_confidence_inference` and
`stratify_low_confidence_count` cover the union of enabled inference policies, once per event,
even if queue writing is disabled. Hull OOD counts retain their original meaning. These are
resimulation candidates; the runtime does not automatically rerun or retrain them.

The policies read the trust metadata a model carries, whatever its format. A TorchScript module
(`.pt`, run by LibTorch) carries it in its `.pt.io.json` sidecar: `input_domain`
(`standardized_radius`, `input_min`/`input_max`, `occupancy`, `joint`) and
`trained_scale_bands`, exactly as a JSON network carries them in its own file. Without an
`input_domain` the module has no measured reference, so it never reports starvation or an
out-of-domain input. The [resim policy gate](../../scripts/validate_inference_resim.py) runs every
case on both formats and requires identical scores (apart from the loaded-model block), event
scores, emits and queue; CTest `trech_inference_resim_backends` runs seven of its cases.

## Allowed operations

- Read `ctx.config` and `ctx.runtime` fields.
- Mutate `ctx.state` for derived bookkeeping.
- Use `ctx.rng` for all randomness (no `Math.random`, no time-based APIs).
- `Math.*` transcendentals and `**` are host-supplied deterministic math (fdlibm-derived,
  identical bits on every platform; provenance `hooks_math`), not the platform libm. They are
  within about 1 ulp of the true value (up to ~2 ulp for the hyperbolics/`log10`), not
  correctly rounded, so do not compare them bit for bit with another JavaScript engine.
- Use `TRECH_PUBCHEM(name)` to load fetched PubChem JSON metadata from
  `TRECH_PUBCHEM_CACHE_DIR` (or the legacy `data/pubchem` fallback) without
  binding PubChem/network access into Geant4.
- Return a patch object with allowed overrides:
  - `override.beam` (particle, energy, direction)
  - `override.run` (event count, seed)
  - `override.optics` (enable flags, optical properties)
  - `override.system` (ensemble labels, volume)
  - `override.stratify` (thresholds, labels)

Example patch:

```js
return {
  override: {
    beam: { energyMeV: 1.5 },
    run: { nEvents: 250 }
  }
};
```

<a name="provenance-requirements"></a>

## Provenance

The run records its effective config, hook registrations, dispatch and inference
counts, guardrails and model artifact identities when present. Tagged payloads
written with `ctx.emit` appear in `trech_hook_emits.jsonl`. Read the
[output schema](output_schema.md) for the exact records and their fields.

<a name="determinism-modes-proposal"></a>

## Determinism modes

- `strict` disables model inference. Use a single worker for order-sensitive hook state.
- `predictive` enables configured model paths. Hook reports and artifact provenance
  identify the executed model and any coverage or accuracy metadata it carries.

See [run controls and modes](cli.md#strict-and-predictive-runs) and
[scenario bundles](../scenarios/scenario_bundles.md) for typed inputs and companions.
