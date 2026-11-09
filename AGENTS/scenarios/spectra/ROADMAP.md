# Spectrum prediction — roadmap

[Root principles](../../../AGENTS.md) · [Root roadmap](../../../ROADMAP.md) · [Parent](../ROADMAP.md) · [Handbook](AGENTS.md)

Related owners: [Chemistry and molecular response](../chemistry/ROADMAP.md) · [Panels, run reports and resource controls](../../studio/workspace/ROADMAP.md) · [Training tools, model data and feature schemas](../../tooling/training/ROADMAP.md).

Maintain work in its owning branch. Dated results apply to the recorded checkout; they do not validate subsequent changes.

## Foundation (2026-11-07)

- [x] JS subproject `projects/spectrum_prediction/`. PubChem element records → NIST ASD neutral
  line lists (Z 1–56), and PubChem compound UV maxima (≈400 candidates), in a hashed build-local
  cache with offline rebuild. Committed fixture: 53 atoms, 180 molecules, every rejection reasoned.
- [x] Declarative architecture catalogue on a gradient-checked JS autodiff: mean, kNN, ridge, MLP,
  DeepSets and MPNN, with and without pooled atomic-model predictions. 5-fold CV, molecular
  leave-one-family-out CV and a single-use hash-stable test split. Deterministic report and
  exports, independent of worker count.
- [x] `generic_surrogate_v1` exports with hull/occupancy/joint domain and test-split holdout.
  The `spectrum_prediction` scenario evaluates both rungs via `ctx.cascade`; the engine output
  equals the trainer report and an independent Python forward pass.
- [x] Studio extension mode (Spectra dock): plot, trust badges, leaderboard/ablation, and a
  Node training job feeding `data_dir`.

## Open work

- [ ] **Particle-trained atomic rung.** No model consumes Geant4 facts yet. Feed Geant4
  material/atomic response (mean excitation energy, photo-absorption cross sections from
  `trech_molecular_particle.js` or a new optical-energy probe) as atomic inputs. Then re-grade the
  cascade ablation. Until then this track does not close the Geant4-linked molecular gap.
- [ ] **Cascade adds no measurable information yet** (|ΔCV RMSE| < 0.003). Try per-element
  embeddings (hidden-layer activations) instead of profile summaries, and graph-level
  attention over atomic predictions.
- [ ] **Graph networks underperform the mean baseline** at 144 training molecules. Tune
  (readout, depth, dropout-free regularisation, learning-rate schedules), add descriptor-hybrid
  MPNNs, and grow the dataset before drawing architecture conclusions.
- [ ] **Data growth:** more PubChem name lists/families, ionized atomic spectra (X II), the NIST
  levels endpoint, and solvent/pH metadata. Band widths are not measured; a
  measured-envelope source with licence-compatible spectra would replace the fixed-σ representation.
- [x] **Calibrated per-bin intervals (2026-11-07).** Exported models carry a
  `prediction_interval` (split-conformal |residual| quantile of the ranking CV's out-of-fold
  predictions, nominal 0.9 per bin; `lib/uncertainty.js`). The engine reads it into every
  learned path's per-output accuracy (`interval_half_width`/`interval_coverage`), the scenario
  emits `interval{lower,upper}` next to the holdout rmse and Studio shades the band. Test-split
  cell coverage: atomic 0.887 (6 atoms; mean width 1.10, i.e. nearly the whole [0,1] range),
  molecular 0.902 (33; width 0.74, 0.55 of molecules covered in every bin). Out-of-group
  coverage of the same interval: 0.840 (leave-one-group-out) / 0.892 (leave-one-family-out);
  out-of-group-calibrated widths are 1.25× / 1.08×. All earlier report/model fields are
  byte-identical. Verification: `node --test` 16/16, validator incl. interval checks, Studio
  `test_spectra.py` 10/10, `trech_generic_surrogate`.
- [ ] Interval residuals: intervals are marginal and homoscedastic per bin (no input-conditional
  width), the atomic interval is uninformative, and out-of-group use under-covers; try
  normalized/conditional conformal scores or ensembles.
- [x] Atomic split-noise metrics (2026-11-07). Each atomic architecture now reports 5× repeated
  5-fold CV (per-fold + pooled out-of-fold metrics) and leave-one-chemical-group-out CV on the
  training split, without changing ranking or exports (both models re-trained byte-identical).
  Pooled R²: MLPs/kNN 0.13–0.14 ± 0.03 vs mean −0.05, so the negative 6-element test R² was
  split noise. Verification: `node --test` 15/15 (new repeated/group assertions, two-group
  fixture), CTest `trech_spectrum_prediction_{js,scenario}`, Studio `test_spectra.py` 9/9.
- [ ] **No out-of-group atomic generalisation.** Leave-one-chemical-group-out, every learned
  atomic model is worse than the mean baseline (RMSE 0.372–0.394 vs 0.355). Try group-aware
  inputs (valence-shell occupancy, term symbols), monotone/physics-shaped priors over Z, or
  ionized-spectrum data before using the atomic rung outside sampled groups. Studio's
  leaderboard now shows the Studio-mode `split_noise` copy of `repeated_cv`/`group_cv`
  (per-fold RMSE ± std, group-CV RMSE with the worst group, per-group tooltip; 2026-11-09).
- [ ] Studio: live re-inspection when `data_dir` changes the target choice lists, and a split view
  comparing two runs' leaderboards.
