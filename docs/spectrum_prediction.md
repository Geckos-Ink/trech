# Spectrum prediction (JavaScript subproject)

Maturity: **experimental research track**. The subproject collects measured light spectra of
atoms and molecules, trains a catalogue of JavaScript ML architectures to predict them, and
exports the dense winners to TRECH, where the `spectrum_prediction` scenario evaluates them
through `ctx.cascade` with the engine's ordinary trust profile. An optional Studio extension mode
plots and compares the results.

Everything is JavaScript: the shared library ([`projects/spectrum_prediction/lib/`](../projects/spectrum_prediction/lib))
runs unchanged on Node.js (collection, training, validation) and inside TRECH's QuickJS host
(the scenario's feature extraction and atomic pooling). Node-only code (network, hashing, files,
worker threads) lives in [`src/`](../projects/spectrum_prediction/src). Studio's extension is the
only Python part, and it neither trains nor evaluates models.

> **Honesty labels.** Labels are **measurements** (NIST ASD, PubChem/HSDB). The models are learned
> **comparisons**: `geant4_trained: false`, `measured_labels: true`. The atomic rung is not
> particle-trained, so this track does not close the Geant4-linked cascade gap; it prepares the
> molecular-spectrum rung that a particle-trained atomic response must eventually feed.

## Data

| Level | Path | What is stored |
| --- | --- | --- |
| Atoms | PubChem periodic table → PubChem element record *Atomic Spectra* section → the NIST ASD line list it links to (neutral spectrum `X I`, 200–1000 nm CSV); *Ground Level* section | Element facts (Z, mass, configuration, ionization energy, electronegativity, electron affinity, radius, ground term) and lines with A<sub>ki</sub>, g<sub>i</sub>, g<sub>k</sub>, level energies |
| Molecules | PubChem name → CID → properties (SMILES, formula) → PUG-View *UV Spectra* | Measured absorption-maximum statements (mostly HSDB): λ<sub>max</sub>, log ε or linear molar ε, solvent |

`spectra.cjs collect` stores every response verbatim under `build/spectrum_prediction/cache/raw/`
with URL, HTTP status, UTC fetch time and SHA-256 in `manifest.json`. Requests are rate-limited
(≈4/s PubChem, ≈1/s NIST) with a generic user agent. 4xx answers ("no such heading") are cached
so absence is recorded once. `--offline` never touches the network; tampered cache bytes are
rejected by hash. The raw cache is build-local and never committed.

`build` is a pure function of the cached bytes and writes `dataset.json`. Every skipped record is
listed in `rejected` with its reason. The UV parser accepts only:

- `λ nm (log e = x)` pairs, including shoulders, unitless pairs inside an explicit
  maximum statement (`219 (LOG E= 3.89)`) and `log epsilon = x at λ nm`;
- linear molar ε (`250 nm (epsilon 13800)`, `(E= 14,500)`, list forms `230, 260 nm (epsilon = 20,800, 16,200)`),
  converted with log10.

It rejects collection catalogue numbers (`UV: 89 (Sadtler …)`), E(1 %, 1 cm) specific
absorbance, wavelength ranges and prose. Malformed statements lose the unreadable band instead of
gaining an invented one. Wavelength-only maxima are kept in the record but carry no envelope
weight.

The molecule catalogue is [`catalog/molecules.json`](../projects/spectrum_prediction/catalog/molecules.json)
(≈400 names in 12 curation families). Committed fixture
([`data/spectrum_prediction/`](../data/spectrum_prediction)): **53 atoms** (Z 1–56; Se, Zr and Nb have
fewer than 5 weighted lines) and **180 molecules** (221 candidates rejected, mostly because
PubChem lists no ε).

## Target representations

These are declared representation choices (see [`lib/grid.js`](../projects/spectrum_prediction/lib/grid.js)):

- **Atomic line-strength shape:** 40 bins over 200–1000 nm (NIST medium, air above 200 nm).
  Each bin sums g<sub>k</sub>A<sub>ki</sub>; lines without A<sub>ki</sub> are counted but carry no weight.
  Target is `log10(1 + 999·I/I_max)/3`. It has no level populations, temperature, density or
  instrument response, so it is **not a plasma emission spectrum**.
- **Molecular UV/Vis envelope:** 32 bins over 180–500 nm. Each measured maximum becomes a
  Gaussian in wavenumber with a fixed σ = 1500 cm⁻¹ (PubChem lists maxima, not band shapes). The
  target is `log10(1 + ε(λ))/5`.

## Features and the atomic → molecular lift

- Atomic inputs: 19 PubChem facts (`features.ATOMIC_FEATURES`), with explicit `*_missing` flags.
  A missing value is never imputed silently.
- Molecular inputs: 27 SMILES graph counts plus the measured solvent class
  (`features.MOLECULAR_DESCRIPTORS`). The graph comes from a minimal SMILES reader (organic-subset
  implicit H only); counts cover pi centres, conjugated components and auxochrome positions. No
  Woodward–Fieser, Hückel or other spectroscopic rule is applied.
- **Cascade rung:** the exported atomic model predicts a line-strength profile for every element.
  Six summaries per element (strength, centroid, four band means) are pooled, count-weighted,
  over the molecule's atoms (`features.ATOMIC_POOL`). Graph networks can also attach them per
  node (`cascadeNodeFeatures`).

## Architecture catalogue

Declarative specs in [`lib/architectures.js`](../projects/spectrum_prediction/lib/architectures.js)
run on a tiny deterministic reverse-mode autodiff ([`lib/tensor.js`](../projects/spectrum_prediction/lib/tensor.js),
gradient-checked in tests). Families: `mean`, `knn`, `ridge` (closed form), `mlp`, `deepsets`
(atom set, no bonds) and `mpnn` (message passing over bonds). To study a new variant, add an
entry; the pipeline trains and grades every entry identically. Only dense families (`ridge`,
`mlp`) can carry `export`, because TRECH's `GenericSurrogate` evaluates dense layers.

## Validation protocol

1. A hash-stable 20 % held-out test split per task (FNV-1a of the record id with a salt). It
   stays stable as records are added and is scored once per architecture.
2. 5-fold CV on the training split; ranking uses mean CV RMSE, never test metrics.
3. Molecules additionally get leave-one-family-out CV (out-of-family generalisation).
   Atoms additionally get a split-noise check on the training split: 5× repeated 5-fold CV
   (re-salted fold assignments; per-fold metrics plus one pooled R² over each repetition's
   out-of-fold predictions) and leave-one-chemical-group-out CV over PubChem's group block.
   Both are reported (`repeated_cv`, `group_cv`), never used for ranking. `--repeats R`
   (0 disables) and `--no-group-cv` control them.
4. Final refit on the full training split. Exported models carry the **test** metrics as their
   `holdout` block, the training hull, occupancy and a joint covering set (same conventions as
   `trech-train-surrogate`), plus `trained_from` (architecture, seed, dataset SHA-256, train/test ids).

Committed results (`data/spectrum_prediction/report.md`; RMSE in target units):

| Task | Best by CV | CV RMSE | Mean baseline CV RMSE | Test RMSE / R² / cosine |
| --- | --- | --- | --- | --- |
| Atomic (53, 6 test) | `atomic_mlp_silu_wide` | 0.297 | 0.333 | exported `atomic_mlp_tanh`: 0.325 / −0.11 / 0.58 |
| Molecular (180, 33 test) | `molecular_mlp_cascade` | 0.231 | 0.255 | exported `molecular_mlp_cascade`: 0.228 / 0.35 / 0.75 |

Findings at this data size: dense descriptor MLPs beat the mean baseline modestly. The graph
networks (DeepSets, MPNN) do not beat the mean baseline yet. The pooled atomic-model features
change CV RMSE by less than 0.003, so the cascade rung adds no measurable information beyond
composition at this size. The atomic test split (6 elements) is too small for stable R².
The repeated CV removes that noise: pooled out-of-fold R² is 0.13–0.14 (± 0.03 over 5
repetitions) for the MLPs and kNN against −0.05 for the mean baseline, so the learned atomic
models explain real variance even though their 6-element test R² is negative. Leave one
chemical group out, every learned model is worse than the mean baseline (group-CV RMSE
0.372–0.394 against 0.355; pooled R² −0.41 to −0.62 against −0.20). The atomic models
interpolate within chemical groups and do not extrapolate to an unseen group.

## Running

```bash
node projects/spectrum_prediction/bin/spectra.cjs all            # collect + build + train (network)
node projects/spectrum_prediction/bin/spectra.cjs train --offline --out build/spectrum_prediction/run
node projects/spectrum_prediction/bin/spectra.cjs publish --out build/spectrum_prediction/run   # refresh committed fixture
node --test projects/spectrum_prediction/test/*.test.js
build/dev/trech run examples/scenarios/spectrum_prediction/spectrum_prediction.js --param 'selection="test_split"' --output build/out_spectra
python3 scripts/validate_spectrum_prediction.py
```

Full training takes about 4 minutes on 8 cores (the atomic split-noise checks add ~1 minute); `--jobs` sets the number of worker threads.
Results are byte-identical across runs and across worker counts.

## TRECH scenario contract

[`examples/scenarios/spectrum_prediction/`](../examples/scenarios/spectrum_prediction) declares
`spectrum_atomic` (scale `atomic`) and `spectrum_molecular` (scale `nano`). Parameters:
`data_dir` (empty = committed fixture), `selection` (`single`, `test_split`, `all_molecules`,
`all_atoms`), `target_kind`, `molecule`, `element`, `mode` and `studio_mode`. Per target, the
scenario runs `ctx.cascade(element facts, ["spectrum_atomic"])` for each element, then
`ctx.cascade(descriptors + pooled atomic predictions, ["spectrum_molecular"])`.

Emits:

- `spectrum_prediction`: kind, id, label, `split` (`test` = held out, `train` = training member),
  grid (unit, start, stop, bins, centers), `measured`, `predicted` (null in strict mode),
  `model_inputs`, engine `stages` trust (inDomain, extrapolation, starved/joint flags, holdout R²),
  comparison `metrics`, source text/URLs, `display` hints from the view companion, honesty labels.
- `spectrum_summary`: pooled metrics per model and split counts.
- `spectrum_model_report` (Studio mode only): the trainer's leaderboard, ablation and protocol.
- `spectrum_geant4_context` (single target): Geant4 material-probe facts for the same composition
  at a declared density (mean excitation energy, electron density). This is context, not a model
  input.

Strict mode disables both stages (`hook_predict_count` 0) and still emits the measured
reference. `scripts/validate_spectrum_prediction.py` checks four things: engine outputs equal an
independent Python dense forward of the committed JSON (|Δ| ≈ 4e-16); engine held-out metrics
equal the trainer's report; strict-mode gating; and the Studio-mode declaration via `trech inspect`.

## Studio extension mode

`studio_mode=true` makes the scenario declare `hooks.inputs.schema = "trech_spectrum_inputs_v1"`
and `TRECH_STUDIO.extensions = ["spectrum_prediction"]`. Studio then shows the **Spectra** dock
(menu **Spectra → Open spectrum prediction workspace** turns the switch on). The dock has three tabs:

- **Predictions:** target list, measured vs learned curve on the emitted grid with measured maxima
  ticks, engine trust badges per stage, source statement and Geant4 context.
- **Architectures:** the emitted leaderboard and cascade ablation.
- **Training:** runs the Node pipeline via QProcess (`--studio` JSON-lines progress, offline by
  default). **Use trained run** sets `data_dir`; the new models reach the plot only through a
  TRECH run.

Studio computes no metric and fills no missing prediction (`studio/trech_studio/spectra.py`,
tests in `studio/tests/test_spectra.py`).

## Limits

- Small held-out sets; graph models undertrained; envelope band width is fixed, not measured.
- Solvent is a 3-class feature; pH, concentration and vibronic structure are absent.
- Atomic profiles ignore ionized spectra (X II …), level populations and instrument response.
- PubChem UV coverage favours HSDB compounds; families are unevenly represented (pesticides: 5).
- No Geant4-derived feature enters a model yet; the Geant4 context emit is a placeholder for that lift.
