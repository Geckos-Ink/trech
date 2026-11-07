# Spectrum prediction — context and contracts

[Root principles](../../../AGENTS.md) · [Root roadmap](../../../ROADMAP.md) · [Parent](../AGENTS.md) · [Roadmap](ROADMAP.md)

Related owners: [Chemistry and molecular response](../chemistry/AGENTS.md) · [Panels, run reports and resource controls](../../studio/workspace/AGENTS.md) · [Training tools, model data and feature schemas](../../tooling/training/AGENTS.md) · [Coverage, uncertainty and trust](../../engine/inference/trust/AGENTS.md).

Read the root principles and the parent handbook first; then open only the subcategory relevant to the task. Source paths and shell commands in code spans/blocks are repository-relative unless stated otherwise; Markdown links resolve from this file.

**Experimental JavaScript subproject.** [`projects/spectrum_prediction/`](../../../projects/spectrum_prediction)
collects measured atomic/molecular light spectra and trains a declarative catalogue of JS
architectures. Dense exports run in TRECH through
[`examples/scenarios/spectrum_prediction/`](../../../examples/scenarios/spectrum_prediction); Studio's
Spectra dock is its optional UI extension mode. Contract and current numbers:
[`docs/spectrum_prediction.md`](../../../docs/spectrum_prediction.md).

## Source map

- `lib/` is **host-neutral**: the same files load through Node `require` and QuickJS
  `TRECH_INCLUDE` (`lib/index.js`), attach to `globalThis.TRECH_SPECTRA`, and reuse
  `js/trech_random.js` (mulberry32). Keep Node APIs (`require`, `process`, `Buffer`, `node:`)
  out of everything except `index.js`; `test/library.test.js` enforces this.
  `grid.js` holds target representations; `nist.js`/`pubchem.js` are strict parsers;
  `smiles.js`/`features.js` hold graph counts, feature vocabularies and atomic pooling;
  `tensor.js`/`models.js` are the autodiff and families; `architectures.js` is the study
  catalogue; `validate.js` holds splits/metrics; `export.js` writes `generic_surrogate_v1`.
- `src/` is Node-only: `collect.js` (rate-limited fetch, SHA-256 cache manifest, `--offline`),
  `dataset.js` (pure rebuild from cached bytes; every rejection keeps a reason) and
  `pipeline.js` (protocol, worker-thread lanes, report/markdown). `bin/spectra.cjs` is the CLI;
  `--studio` emits JSON lines plus `studio_manifest.json`.
- Committed fixture: `data/spectrum_prediction/{dataset,report}.json`, `report.md`,
  `models/spectrum_{atomic,molecular}.json`. The raw cache stays in `build/spectrum_prediction/cache/`.

## Contracts and pitfalls

- **Labels are measurements, models are comparisons.** NIST ASD lines (reached via PubChem
  element records) and PubChem/HSDB UV maxima; exports carry `geant4_trained:false`,
  `measured_labels:true`. Never describe a spectrum prediction as Geant4 output. The
  `spectrum_geant4_context` emit is composition context only, not an input.
- **Parsers reject rather than reinterpret.** Sadtler catalogue numbers, E(1 %, 1 cm), ranges and
  prose stay out; malformed text drops bands. Extend parsers only with a test for the exact
  source form.
- **Representations are declared choices** (atomic gA shape, molecular 1500 cm⁻¹ envelope).
  Changing a grid changes every target, model and fixture: bump the `kind` and republish.
- **Protocol:** a hash-stable 20 % test split per task; ranking by CV only; molecular
  leave-one-family-out CV; exported `holdout` = test split. `trained_from.test_ids` drives the
  scenario's `split` flag, so a training member is never shown as generalisation evidence.
- **Determinism:** same dataset gives byte-identical report/models, independent of `--jobs`
  (fixture-tested; the committed run was re-trained and compared). `dataset_sha256` is the hash
  of the `dataset.json` bytes.
- **Scenario:** both rungs go through `ctx.cascade(..., [name])`, so the engine's trust trace
  (OOD, starved, joint, holdout R²) reaches the emit. In strict mode `predicted` is null and
  `hook_predict_count` is 0. `TRECH_PARAMETER` may be resolved only once: the UI descriptor reads
  `TRECH_SPECTRUM_DATA.studioMode` instead of re-declaring `studio_mode`. `--param` values are
  JSON (`selection="test_split"`).
- **Studio mode** = `studio_mode=true` → `hooks.inputs.schema = trech_spectrum_inputs_v1` +
  `TRECH_STUDIO.extensions = ["spectrum_prediction"]` + the `spectrum_model_report` emit.

## Tests

`node --test projects/spectrum_prediction/test/*.test.js` (CTest `trech_spectrum_prediction_js`):
parsers, SMILES, grids, gradient check, families, export layout, splits, offline cache →
dataset → training determinism (in-thread = workers) → CLI/`--studio`.
`scripts/validate_spectrum_prediction.py` (CTest `trech_spectrum_prediction_scenario`) runs the
engine and checks four things: Python dense forward equals engine output, engine held-out metrics
equal the report, strict gating, and the Studio declaration. Studio: `studio/tests/test_spectra.py`.
