# Spectrum prediction (TRECH JavaScript subproject)

Learn the light spectra of atoms and molecules from measured data, compare ML architectures
written in JavaScript, and run the best dense models inside TRECH. The contract, data
representations, protocol and current results are in [`docs/spectrum_prediction.md`](../../docs/spectrum_prediction.md).

```
catalog/molecules.json   candidate compounds (curation families for leave-one-family-out CV)
lib/                     host-neutral library (Node.js and TRECH QuickJS): grids, NIST/PubChem parsers,
                         SMILES graphs, features, autodiff, model families, architectures, validation, export
src/                     Node-only: collect.js (network + hashed cache), dataset.js, pipeline.js (+ workers)
bin/spectra.cjs          CLI: collect | build | train | all | publish  [--studio]
test/                    node --test suites (offline)
```

Requires Node.js ≥ 18. There are no npm dependencies, so no install step is needed.

```bash
node projects/spectrum_prediction/bin/spectra.cjs --help
node projects/spectrum_prediction/bin/spectra.cjs all                    # PubChem/NIST -> dataset -> models
node projects/spectrum_prediction/bin/spectra.cjs train --arch molecular --folds 5 --jobs 8
node --test projects/spectrum_prediction/test/*.test.js
```

Outputs go to `build/spectrum_prediction/run/`: `dataset.json`, `report.json`, `report.md` and
`models/spectrum_{atomic,molecular}.json` (`generic_surrogate_v1`). `publish` copies a run to
the committed fixture `data/spectrum_prediction/`. The raw response cache stays in
`build/spectrum_prediction/cache/`.

**Study a new architecture:** add an entry to `lib/architectures.js` (family + hyper-parameters
+ input set). It is cross-validated, family-CV'd, tested and ranked like every other entry. Give
it `export: "spectrum_molecular"` (dense families only) to make it the model TRECH loads.

**UI extension mode:** `--studio` turns progress into JSON lines and writes
`studio_manifest.json`. The Studio **Spectra** dock uses it to run training and then point the
`spectrum_prediction` scenario's `data_dir` at the new run.

Labels are measured spectra; the models are learned comparisons, not Geant4 results.
