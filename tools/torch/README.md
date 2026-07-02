# trech-torch

Torch-side companion tools for TRECH: harvest Geant4 run outputs into training
sets, fit the surrogate/stratifier models the engine runs inference with, and
plan which Geant4 experiments to run next. Install:

```bash
cd tools/torch
python -m venv .venv
source .venv/bin/activate
pip install -e .          # numpy-only: dataset harvester, ridge/logistic
                          # .json trainers, and the experiment planner
pip install -e '.[torch]' # adds torch for the TorchScript (.pt) exports
```

The `.json` model paths (optics ridge, event-stratifier logistic) and the
experiment planner are **numpy-only**, so they work in a stock environment;
only the TorchScript `.pt` exports need `torch`. All tools share one
schema-checked harvester, `trech_torch/dataset.py`, whose schemas are locked to
the C++ side (`FeaturePipeline` `trech_event_features_v1` and
`OpticsSurrogate::kCompositionElements`).

Tools provided:

## Optics surrogate trainer

`trech-train-optics-surrogate` reads `trech_viz_scene.json` files (output of
`trech run` with `optics.derive.enable: true`), builds a training set mapping
**(element mass fractions + density) → (mean refractive index, mean absorption
length, mean scatter length)** from the `derived_optics` block, trains a small
MLP with input standardization baked into the exported module, and writes a
TorchScript model + manifest (with model size and leave-one-out validation
metrics). With `--anchors` the handbook n overrides the extractor's n target so
the surrogate learns the measured residual.

```bash
trech-train-optics-surrogate \
  --scenes build/dev/out_optics_panel \
  --anchors ../../data/optics_handbook_anchors.json \
  --out build/dev/optics_surrogate.pt \
  --manifest build/dev/optics_surrogate.manifest.json \
  --epochs 200 --seed 1234
```

The input vector layout matches `OpticsSurrogate::kCompositionElements` in
`include/trech/ml/OpticsSurrogate.hpp` — keep them in lock-step. The **deployed
composition→n model is the ridge `.json`** exported by
`scripts/validate_optics_surrogate.py --export` (LibTorch-free,
`data/optics_surrogate_ridge.json`), which passes the LOO promotion gate on the
current 15-material panel where the MLP does not; the MLP path is available for
multi-output (abs, scat) models once the panel grows.

## Event stratifier trainer

`trech-train-event-stratifier` reads run directories with
`trech_event_features.jsonl` dumps (`stratify.enable` + `stratify.dumpFeatures`)
and fits a **standardised logistic regression** mapping the 7-feature
`trech_event_features_v1` vector → p(exceptional). The teacher labels are the
engine's deterministic thresholds (later: resim-confirmed labels). It exports
the LibTorch-free logistic `.json` the C++ `TorchScriptStub` json backend loads
via `stratify.modelPath`, plus an optional bit-parity TorchScript `.pt`.

```bash
trech-train-event-stratifier \
  --runs build/dev/out_stratify_* \
  --out-json build/dev/stratify_logistic.json \
  --out build/dev/stratify_logistic.pt \
  --manifest build/dev/stratify_model.manifest.json
```

Deploy the `.json` only when the manifest's `beats_majority_baseline` gate is
true; the engine additionally requires `determinism.mode: "predictive"`.

## Geant4 experiment planner

`trech-plan-geant4-experiments` is the active-learning half of the loop: it
diagnoses where the trained models are starved (optics element/density coverage
gaps, LOO hotspots, event label balance, degenerate features, beam-energy and
dimension-scale coverage) and emits a ranked `geant4_experiment_plan.json` of
concrete simulation requests, each naming a scenario + config levers to run.

```bash
trech-plan-geant4-experiments \
  --optics-run build/dev/out_optics_panel \
  --anchors ../../data/optics_handbook_anchors.json \
  --runs build/dev/out_stratify_* \
  --out build/dev/geant4_experiment_plan.json
```

### When to retrain

The optics surrogate predicts what the C++ `MolecularOpticsExtractor` would
compute (shifted toward handbook anchors), so retrain when the extractor (KK
window, cross-section sources) changes or the material panel grows. The event
stratifier retrains when the threshold teacher, feature schema, or the set of
Geant4 scenarios feeding it changes. See `CHARTS.md` →
"Geant4 → training → inference linkage" for the full per-prediction map.
