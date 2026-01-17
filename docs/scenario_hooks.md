# Scenario Hook API (proposal)

This document proposes a deterministic JS hook surface that lets scenarios react to runtime
context without breaking the JSON config boundary. Hooks are optional; the canonical input
remains `TRECH_CONFIG`.

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
- `ctx.event`: `{ id }` (for event hooks).
- `ctx.track`: `{ id, particle, kineticEnergyMeV }` (for track hooks).
- `ctx.step`: `{ edepMeV, stepLengthMm, positionMm, timeNs }` (for step hooks).
- `ctx.state`: mutable per-run JS state (stored across callbacks).
- `ctx.rng`: deterministic RNG (`uniform()`, `normal()`, `int(min, max)`).
- `ctx.emit(tag, payload)`: attach a tagged record to provenance.

## Allowed operations

- Read `ctx.config` and `ctx.runtime` fields.
- Mutate `ctx.state` for derived bookkeeping.
- Use `ctx.rng` for all randomness (no `Math.random`, no time-based APIs).
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
