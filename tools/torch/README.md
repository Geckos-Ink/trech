# trech-torch

Torch-side companion tools for TRECH. Install:

```bash
cd tools/torch
python -m venv .venv
source .venv/bin/activate
pip install -e .
```

Tools provided:

## Optics surrogate trainer

`trech-train-optics-surrogate` reads a directory of `trech_viz_scene.json` files (output of `trech run` with `optics.derive.enable: true` and `optics.derive.writeSpectrum: true`), builds a training set mapping **(element mass fractions + density) → (mean refractive index, mean absorption length, mean scatter length)** from the `derived_optics` block, trains a small MLP, and exports a TorchScript model + manifest that the engine can load via `optics.derive.surrogateModelPath`.

```bash
trech-train-optics-surrogate \
  --scenes build/dev/out_viz_refraction \
  --out build/dev/optics_surrogate.pt \
  --manifest build/dev/optics_surrogate.manifest.json \
  --epochs 200
```

The model's input vector layout matches `OpticsSurrogate::kCompositionElements` in `include/trech/ml/OpticsSurrogate.hpp` — keep the two in lock-step.

### When to retrain

The surrogate predicts what the C++ `MolecularOpticsExtractor` would compute, so retraining is only needed when:

- The extractor (KK integration window, Beer–Lambert / cross-section sources) changes.
- The training dataset expands to more material compositions.

Otherwise the surrogate is just a fast inference cache.
