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
- [ ] **Uncertainty:** ensembles or MC-free bootstrap intervals per bin, emitted next to the
  engine's holdout RMSE; calibrate against the family-CV spread.
- [ ] Atomic test split has 6 elements; report repeated-split or leave-one-block-out metrics so
  atomic R² is not dominated by split noise.
- [ ] Studio: live re-inspection when `data_dir` changes the target choice lists, and a split view
  comparing two runs' leaderboards.
