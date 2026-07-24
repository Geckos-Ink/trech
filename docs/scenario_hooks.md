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
- `ctx.cascade(seed?)`: run all declared scale-tagged models in ascending scale order. Without an
  argument, the seed is automatic Geant4 event tallies + material probes + derived optics. An
  explicit object augments/overrides keys. The result carries flat facts/predictions and
  `__cascade{stagesRun,stagesExtrapolating,seedKeys,trace}`; strict mode returns `null`.

Ambient cascade optics keys use
`optics.<material>.{mean_refractive_index,mean_absorption_length_mm,mean_scatter_length_mm,display_r,display_g,display_b}`.
Material keys use `material.<material>.*`; event keys include `event.edep_mev`, track/step counts
and optical-photon counts/length. Missing stage inputs are recorded in the trace, never hidden.

### Training-domain coverage (per-stage low-confidence flag)

Every learned prediction reports whether its inputs fell inside the region the model was
**trained on** — the honest signal that lets a stage flag a low-confidence guess instead of
silently extrapolating. Each `__cascade.trace[i]` entry (and the `ctx.predict` `__coverage`
object) carries: `inDomain` (all inputs within the trained hull), `domainMeasured` (the hull came
from training, not a heuristic fallback), `extrapolation` (how far past the hull edge the worst
input sat, in training-σ units; 0 in-domain), `maxStandardizedDeviation` (max |z| over the
inputs), and `outOfDomainInputs` (the input names beyond their domain). `__cascade.stagesExtrapolating`
counts the ran stages flagged out-of-domain. The domain is the per-feature standardized hull the
trainer exports as `input_domain.standardized_radius` (`trech-train-surrogate`); models without it
(the committed ridge/logistic and illustrative hand-authored maps) fall back to a heuristic 3σ
radius and report `domainMeasured: false`. A defaulted-to-0 missing input that sits far from its
trained mean is honestly counted as out-of-domain.

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
