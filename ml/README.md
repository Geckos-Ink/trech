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
for s in 1 2 3 4 5 6 7 8 9 10; do
  case $s in 1|2|3|4) k=train;; 5|6) k=valid;; 7|8) k=test;; *) k=cal;; esac
  build/dev/trech run examples/scenarios/config_stratify/config_stratify.js --seed $((1000+s)) --output build/ml_demo/${k}_$s
done
export TRECH_ML_PYTHON=python3   # an interpreter with numpy + torch
node tools/ml/bin/trech-ml.cjs train  ml/definitions/event_step_count.model.js
node tools/ml/bin/trech-ml.cjs search ml/searches/event_step_count.search.js
node tools/ml/bin/trech-ml.cjs search ml/searches/event_step_count_folds.search.js --validate
node tools/ml/bin/trech-ml.cjs list
```

Add `--validate` to `train`/`search` (or run `trech-ml validate <name>`) to grade the result with
the independent validator ([gates](../docs/ml_models.md#validating-a-model)).

On the 2026-11-11 checkout (torch 2.8), the search evaluated 19 structures (silu/tanh × uniform/
tapered widths, plus linear) with 3 seeds each. The one-standard-error rule selected
`mlp(8→4,tanh)`; the report states it is not distinguishable from the runner-up. Its test-run R²
was 0.643 against 0.661 for the fixed 16×2 definition, and both passed every validation gate. The
re-trained weights were identical to the selected candidate. That is a demonstration of the
workflow, not a validated observer model.

`event_step_count_folds.search.js` rotates the six training + selection runs through three
whole-run folds (two seeds each) and sets the winner's error bar on the two `cal_*` runs. The
between-fold loss spread was about twice the seed spread, so the seed-only search understated
selection noise. The one-standard-error rule picked `mlp(4×2,silu)`, again not distinguishable
from the runner-up. Refit on all six runs it reached test R² 0.617; its calibration-run 90%
interval covered 93.5% of the test rows, an independent check.
