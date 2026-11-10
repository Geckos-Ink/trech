# ML model definitions

JavaScript definitions of learned models (`*.model.js`) and structure searches (`*.search.js`),
trained and managed with `node tools/ml/bin/trech-ml.cjs` and editable live in Studio's **Models**
dock. Contract, store layout and honesty rules: [`docs/ml_models.md`](../docs/ml_models.md).

| Path | Content |
| --- | --- |
| `definitions/` | fixed-structure models (`TRECH_ML.defineModel`) |
| `searches/` | structure searches (`TRECH_ML.defineSearch`) |
| `shared/` | host-neutral helpers included by definitions (column lists, run sets) |

Checkpoints are written to the store (`$TRECH_MODEL_STORE` or `build/model_store/`), never here.

## Demo

The demo files learn the per-event Geant4 step count from deposited energy and track length. They
use `config_stratify` runs with disjoint seeds:

```bash
for s in 1 2 3 4 5 6 7 8; do
  case $s in 1|2|3|4) k=train;; 5|6) k=valid;; *) k=test;; esac
  build/dev/trech run examples/scenarios/config_stratify/config_stratify.js --seed $((1000+s)) --output build/ml_demo/${k}_$s
done
export TRECH_ML_PYTHON=python3   # an interpreter with numpy + torch
node tools/ml/bin/trech-ml.cjs train  ml/definitions/event_step_count.model.js
node tools/ml/bin/trech-ml.cjs search ml/searches/event_step_count.search.js
node tools/ml/bin/trech-ml.cjs list
```

On the recorded checkout, the grid search evaluated 7 structures. It selected an 8-wide, 2-deep
MLP; held-out test-run R² was 0.63, and the re-trained weights were identical to the selected
candidate. That is a demonstration of the workflow, not a validated observer model.
