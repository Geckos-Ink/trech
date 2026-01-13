# H2O Fluid Experiment Spec (Initial)

This spec anchors the Sputnik milestone by defining the first H2O fluid experiment
that TRECH should support. It is a reference for implementation work, not a full
design document.

## Goals

- Simulate H2O fluid behavior with Geant4 at the highest practical subatomic detail.
- Prioritize photon transport accuracy in water (scattering, absorption, refraction, color response).
- Preserve the JS -> JSON -> C++ boundary; JS only authors config (global TRECH_CONFIG).
- Provide hooks for event stratification (predictable vs exceptional) and multi-scale acceleration.

## Non-goals (initial)

- Full chemical reaction-diffusion networks.
- Coupled fluid solvers or lattice Boltzmann integration.
- ML training or inference pipelines.

## Baseline configuration (current schema)

The initial experiment should fit the existing config shape:

```json
{
  "detector": { "worldSizeMm": 200.0, "worldMaterial": "G4_WATER" },
  "beam": { "particle": "gamma", "energyMeV": 2.0 },
  "run": { "nEvents": 1000, "seed": 424242 }
}
```

JS experiments must emit this as a JSON string:

```js
const cfg = {
  detector: { worldSizeMm: 200.0, worldMaterial: "G4_WATER" },
  beam: { particle: "gamma", energyMeV: 2.0 },
  run: { nEvents: 1000, seed: 424242 }
};

globalThis.TRECH_CONFIG = JSON.stringify(cfg);
```

## Proposed config extensions (phase 1)

These fields are proposed for future support, not required today:

- `detector.waterBoxMm`: explicit water volume size separate from world size.
- `detector.temperatureK`, `detector.pressureAtm`: environmental conditions.
- `beam.direction`: initial beam direction vector.
- `optics.absorptionLengthMm`, `optics.scatterLengthMm`: simple optical material tuning.

## Physics and scoring focus

- Use a reference Geant4 physics list (e.g., QBBC) as baseline.
- Add optical physics when available to model photon transport in water.
- Record photon-related summaries in `trech_scores.jsonl` when implemented.

## Milestones

1. Phase 0 (now): use `G4_WATER` world volume with gamma/e- beams and baseline scoring.
2. Phase 1: introduce optical physics toggles and per-event photon stats.
3. Phase 2: add event stratification hooks and multi-scale acceleration candidates.

## Acceptance criteria (initial)

- Runs with current CLI and config schema.
- Produces provenance and scoring JSONL outputs.
- Serves as a stable reference for future water-focused experiments.
