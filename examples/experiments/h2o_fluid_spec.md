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
  "detector": {
    "worldSizeMm": 200.0,
    "worldMaterial": "G4_AIR",
    "waterBoxMm": 100.0,
    "temperatureK": 293.15,
    "pressureAtm": 1.0
  },
  "beam": { "particle": "gamma", "energyMeV": 2.0, "direction": [0, 0, 1] },
  "run": { "nEvents": 1000, "seed": 424242 },
  "optics": {
    "enable": true,
    "refractiveIndex": 1.333,
    "absorptionLengthMm": 10000.0,
    "scatterLengthMm": 10000.0
  }
}
```

JS experiments must emit this as a JSON string:

```js
const cfg = {
  detector: {
    worldSizeMm: 200.0,
    worldMaterial: "G4_AIR",
    waterBoxMm: 100.0,
    temperatureK: 293.15,
    pressureAtm: 1.0
  },
  beam: { particle: "gamma", energyMeV: 2.0, direction: [0, 0, 1] },
  run: { nEvents: 1000, seed: 424242 },
  optics: {
    enable: true,
    refractiveIndex: 1.333,
    absorptionLengthMm: 10000.0,
    scatterLengthMm: 10000.0
  }
};

globalThis.TRECH_CONFIG = JSON.stringify(cfg);
```

## Phase 1 config extensions (implemented)

These fields are implemented and form the phase 1 H2O extensions:

- `detector.waterBoxMm`: explicit water volume size separate from world size.
- `detector.temperatureK`, `detector.pressureAtm`: environmental conditions.
- `beam.direction`: initial beam direction vector.
- `optics.enable`, `optics.refractiveIndex`: optical physics toggle and constant refractive index.
- `optics.absorptionLengthMm`, `optics.scatterLengthMm`: simple optical material tuning.
- `optics.spectrum`: optional spectral table (energy/wavelength) to tune color response.

## Phase 2 config extensions (implemented)

- `stratify.enable`: emit per-event scoring records in `trech_event_scores.jsonl`.
- `stratify.*Threshold`: classify events via thresholds (energy deposit, track length, step/track counts).
- `stratify.label*`: override stratification labels.
- `stratify.modelPath`: stub hook for future TorchScript stratifiers.
- `stratify.dumpFeatures`, `stratify.dumpResimQueue`: optional per-event feature dumps and resim queues.
- `chemistry.enable`, `chemistry.model`, `chemistry.solver`: Geant4-DNA physics wiring (chemistry stage when solver is not `stub`).
- `multiscale.enable`, `multiscale.method`, `multiscale.mode`: multi-scale wiring stub.

## Physics and scoring focus

- Use a reference Geant4 physics list (e.g., QBBC) as baseline.
- Add optical physics when available to model photon transport in water.
- Record run-level photon summaries (tracks, steps, track length) in `trech_scores.jsonl`.

## Milestones

1. Phase 0 (now): baseline water volume (world or water box) with gamma/e- beams and baseline scoring.
2. Phase 1: introduce optical physics toggles and run-level photon stats.
3. Phase 2: add event stratification hooks and multi-scale acceleration candidates.

## Acceptance criteria (initial)

- Runs with current CLI and config schema.
- Produces provenance and scoring JSONL outputs.
- Serves as a stable reference for future water-focused experiments.
