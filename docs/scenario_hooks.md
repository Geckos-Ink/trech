# Scenario Hook API (proposal)

This document proposes a deterministic JS hook surface that lets scenarios react to runtime
context without breaking the JSON config boundary. Hooks are optional; the canonical input
remains `TRECH_CONFIG`.

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
`trech inspect scenario.js` to obtain `{config, parameters}` without initializing Geant4, and
repeat `--param name=<json>` on `trech inspect` or `trech run` to select values. The engine rejects
unknown, duplicate, mistyped, out-of-range, or non-choice overrides before simulation. Studio uses
this contract to create its right-sidebar Options controls; it does not parse JavaScript source.

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

All hooks are optional.

## Context object (draft)

- `ctx.config`: immutable config object (parsed from `TRECH_CONFIG`).
- `ctx.runtime`: `{ runId, seed, nEvents, mode }`.
- `ctx.event`: `{ id }` for event hooks; on `onEventEnd`, also includes
  Geant4 event metrics (`edepMeV`, `totalTrackLengthMm`, `totalStepCount`,
  `totalTrackCount`, `opticalPhotonSteps`, `opticalPhotonTracks`,
  `opticalPhotonTrackLengthMm`) for simulation-driven hook inference.
- `ctx.track`: `{ id, particle, kineticEnergyMeV }` (for track hooks).
- `ctx.step`: `{ edepMeV, stepLengthMm, positionMm, timeNs }` (for step hooks).
- `ctx.state`: mutable per-run JS state (stored across callbacks).
- `ctx.rng`: deterministic RNG (`uniform()`, `normal()`, `int(min, max)`).
- `ctx.emit(tag, payload)`: attach a tagged record to provenance.
- `ctx.materials`: when `materialProbe.enable` is active, named Geant4 material probes plus
  `.list` (density, electron density, element number densities, mean excitation energy,
  radiation length). This is serialized engine data, not a Geant4 object binding.
- `ctx.optics`: when derived optics are available, the exact engine result used by transport and
  `trech_viz_scene.json`, keyed by both Geant4 material name and config material key plus `.list`.
  Entries include the derived spectrum, mean refractive/absorption/scatter values,
  neutral-preserving `display_rgb`, availability/note and validation deltas.
- `ctx.predict(modelName, features)`: run one declared named-IO surrogate in predictive mode;
  strict mode returns `null`. Calls count toward `hook_predict_count`. The returned object also
  carries a reserved `__coverage{inDomain,domainMeasured,extrapolation,maxStandardizedDeviation,
  outOfDomainInputs}` — the honest "am I extrapolating?" signal for that prediction (see below).
- `ctx.cascade(seed?, modelNames?)`: run declared scale-tagged models in ascending scale order.
  Without an argument, the seed is automatic Geant4 event tallies + material probes + derived
  optics. An explicit object augments/overrides keys. The optional string array narrows the pass to
  named stages; use it when one config declares independent model families (for example a property
  cascade plus a per-element operator), so a model is never evaluated on unrelated missing inputs
  merely because it shares `models[]`. The result carries flat facts/predictions and
  `__cascade{stagesRun,stagesExtrapolating,seedKeys,trace}`; strict mode returns `null`.

- `ctx.evolve(spec)`: the per-element **operator** — where `ctx.cascade` infers *properties*,
  `ctx.evolve` infers how a declared per-element *state* changes over `dt`, so a scenario does not
  have to hand-write the rate law. The engine chains the scale-tagged models over every element in
  one deterministic pass and integrates:

  ```js
  const report = ctx.evolve({
    dt,                                              // the bounded step
    fields: [{ name: "gel", min: 0, max: 1 }, "temperature_k"],
    state:  { gel: gelArray, temperature_k: tempArray },  // MUTATED IN PLACE
    aux:    { exposure: exposureArray },                  // read-only per element
    context:{ ...run-constant facts },                    // over the ambient Geant4 seed
    models: ["reaction_operator"]                         // optional; default = all declared
  });
  ```

  A stage output named `d_<field>_dt` is a **rate** (accumulated across stages, integrated once per
  call, then held inside the field's declared bounds); `set_<field>` is an **assignment** applied
  immediately and visible to higher stages; any other output is an **intermediate** a higher-scale
  stage can consume. `dt` is a reserved readable input. Input precedence is
  field > aux > intermediate > `dt` > `context`/ambient > missing-as-0 (missing names are reported,
  never hidden). Strict mode returns `null` **and leaves the state untouched**. Every model
  evaluation counts: a K-stage operator over N elements adds **N×K** to `hook_predict_count`.
  The report carries `{ran, stagesRun, elementsEvolved, inferenceCount, outOfDomainInferences,
  sharedKeys, auxKeys, trace}`; each `trace[i]` adds `integratedFields`, `assignedFields`,
  `intermediateOutputs`, `unappliedFieldOutputs` (an output naming an undeclared field — reported,
  not a silent no-op) and the per-element-aggregated trust profile `elementsOutOfDomain`,
  `elementsStarved`, `maxExtrapolation` alongside the usual `domainMeasured`/`scaleMismatch`/
  `trainedScale`/`holdoutR2`.

  The first committed operator is
  `data/polyurethane_cascade/meso_reaction_operator.json`: 27 named inputs (eight parcel-state
  fields, two per-parcel auxiliaries, 16 shared coefficients and `dt`) → six rates plus two
  assignments. It was distilled from 115,437 reference-law rows across 285–310 K / 0.02–0.08 s
  steps and independently validated on 38,565 rows; its carried worst-output held-out
  R² is 0.9929. Its model note explicitly says `teacher=...polyurethane_foam.js` and
  `measured:false`: this proves migration fidelity, not new measured chemistry. After passing the
  paired observer and nominal/zero-gravity guards it is the scenario default; the reference path
  remains selectable as its audit/harvest teacher.

Ambient cascade optics keys use
`optics.<material>.{mean_refractive_index,mean_absorption_length_mm,mean_scatter_length_mm,display_r,display_g,display_b}`.
Material keys use `material.<material>.*`; event keys include `event.edep_mev`, track/step counts
and optical-photon counts/length. Missing stage inputs are recorded in the trace, never hidden.

### Per-stage trust profile (low-confidence flags carried with the model)

Every learned prediction reports whether it should be trusted for the point it ran on — the honest
signals that let a stage flag a low-confidence guess instead of silently extrapolating. Each
`__cascade.trace[i]` entry (and the `ctx.predict` `__coverage` object) carries:

- **Training-domain coverage:** `inDomain` (all inputs within the trained hull), `domainMeasured`
  (the hull came from training, not a heuristic fallback), `extrapolation` (how far past the hull
  edge the worst input sat, in training-σ units; 0 in-domain), `maxStandardizedDeviation` (max |z|
  over the inputs), `outOfDomainInputs` (the input names beyond their domain). The domain is the
  per-feature standardized hull the trainer exports as `input_domain.standardized_radius`
  (`trech-train-surrogate`); models without it (committed ridge/logistic, illustrative hand-authored
  maps) fall back to a heuristic 3σ radius and report `domainMeasured: false`. A defaulted-to-0
  missing input far from its trained mean is honestly counted as out-of-domain.
- **Starved region (density inside the hull):** `starvedInputs` — inputs that are within the trained
  range but land in a bin the training set never populated (a hole the model interpolated through,
  distinct from the beyond-the-edge extrapolation). Only reported when the model carries an
  `input_domain.occupancy` histogram (exported by `trech-train-surrogate`).
- **Trained-scale band:** `trainedScale` (the dimension-scale band(s) the model was trained on, from
  the harvester's per-run band tags; empty = unknown) and `scaleMismatch` (true when the stage runs
  at a scale NOT among those bands — the model is applied off the band it learned).
- **Held-out accuracy carried with the model:** `holdoutR2` (worst output's held-out R², the
  grade-the-gap number) and `holdoutSamples`; both `null` when the model carries no metrics (never a
  fake 0 == perfect for an illustrative map).

Run-level rollups on `__cascade`: `stagesExtrapolating` (ran stages out-of-domain),
`stagesScaleMismatched` (ran stages off their trained band), and `stagesStarved` (ran stages with an
input in an unpopulated training bin). The whole run reports `hook_predict_out_of_domain_count` in
`trech_scores.jsonl` / `trech_provenance.jsonl` — the auditable count of learned predictions made
outside their trained domain (a subset of `hook_predict_count`).

**Acting on the flag (resim routing).** Setting `stratify.resimOnLowConfidence: true` (with
`stratify.enable` + `stratify.dumpResimQueue`) makes an event whose `onEventEnd` inference ran
out-of-domain a **resim candidate**: it is written to `trech_resim_queue.jsonl` with
`reason: "inference_out_of_domain"` / `source: "cascade_coverage"` even when the feature-based
stratifier labels it predictable, and counted in `stratify_low_confidence_count` (distinct from the
stratifier's own `stratify_exceptional_count`). This is how the coverage flag drives the
exceptional/resim path, not just surfaces itself.

## Allowed operations

- Read `ctx.config` and `ctx.runtime` fields.
- Mutate `ctx.state` for derived bookkeeping.
- Use `ctx.rng` for all randomness (no `Math.random`, no time-based APIs).
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

## Provenance requirements

- Record hook source hash (experiment file hash + hook object hash).
- Record hook enablement and all patches applied, per run.
- Record all `ctx.emit` events with timestamps in run order.
- When ML inference is used, record model path + hash and inference outputs.

## Determinism modes (proposal)

- `strict`: no ML inference; hooks are deterministic and fully logged.
- `predictive`: ML inference allowed; outputs are logged with model hash and confidence.

## Notes

- Hooks do not expose Geant4 objects or pointers.
- Hooks may only influence the runtime through whitelisted overrides.
- Unit conversions and multi-entity assembly are still done in JS before emitting config.
