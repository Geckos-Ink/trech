# Spectrum prediction — roadmap

[Root principles](../../../AGENTS.md) · [Root roadmap](../../../ROADMAP.md) · [Parent](../ROADMAP.md) · [Handbook](AGENTS.md)

Related owners: [Chemistry and molecular response](../chemistry/ROADMAP.md) · [Panels, run reports and resource controls](../../studio/workspace/ROADMAP.md) · [Training tools, model data and feature schemas](../../tooling/training/ROADMAP.md).

Maintain work in its owning branch. Dated results apply to the recorded checkout; they do not validate subsequent changes.

## Priority queue

Every open item of this branch, highest priority first. The dated records below are delivery
history: the "Residual" and "Next" notes inside them are tracked here, and this queue wins
where they disagree. Keys and route steps: [priority keys](../../ROADMAP.md#priority-keys) ·
[implementation route](../../ROADMAP.md#implementation-route). When an item lands, delete it here, add a
dated record below, and queue its residuals in the same change.

- **P2** · R2 · The cascade adds little measurable information yet: pooling the Geant4-fed atomic model gives the best molecular CV (0.2305), but every cascade delta (≤ 0.005) is far inside the CV standard deviation (≈ 0.019). Try per-element embeddings, graph-level attention, and more molecules before reading the deltas as signal. ([detail](#geant4-fed-atomic-rung-2026-11-27))
- **P2** · R2 · Out-of-group atomic generalisation is still weak. With Z and the Geant4 atomic response only (`atomic_mlp_tanh_geant4_only`), the mean leave-one-group-out RMSE (0.345) is the first below the mean baseline (0.355), but its pooled out-of-group R² (−0.30) stays below the baseline's (−0.20). ([detail](#geant4-fed-atomic-rung-2026-11-27))
- **P2** · R2 · The Geant4 atomic inputs worsen in-distribution atomic CV for ridge (+0.034) and the MLPs (+0.005, +0.011) on 42 training atoms, while improving leave-one-group-out CV. Regularise or select them (fewer energies, per-input penalties, monotone priors over the cross sections) and grow the atomic data (ionized spectra) before the exported rung's atomic accuracy is relied on. ([detail](#geant4-fed-atomic-rung-2026-11-27))
- **P2** · R4 · Conditional/normalized conformal intervals (today marginal and homoscedastic per bin; out-of-group under-covers). ([detail](#open-work))
- **P2** · R6 · Studio live re-inspection after a data change and a two-run leaderboard comparison. (owned by the [studio/workspace queue](../../studio/workspace/ROADMAP.md#priority-queue))
- **P3** · R2 · The Geant4 atomic inputs stop at 10 eV: Geant4 tabulates no optical-energy (1–6 eV) atomic response. Add other Geant4 atomic facts that reach the valence shell (subshell binding energies from `G4AtomicShells`, the lowest Livermore energies) and measure which inputs carry the signal. ([detail](#geant4-fed-atomic-rung-2026-11-27))
- **P3** · R2 · The MPNN cascade gets worse with the Geant4-fed source (ΔCV +0.0024, Δtest +0.018). ([detail](#geant4-fed-atomic-rung-2026-11-27))
- **P3** · R2 · Graph networks underperform the mean baseline at 144 molecules; grow data (more families, ionized spectra, NIST levels, measured band envelopes). ([detail](#open-work))

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

## Geant4-fed atomic rung (2026-11-27)

- [x] Geant4 atomic response harvested by a TRECH run (`geant4/atomic_probe.js`, QBBC_LIV,
  Geant4 11.4.p02): for `G4_H` … `G4_Ba`, the mean excitation energy and the per-atom `phot`
  cross section at ten energies from 10 eV to 10 keV (the material probe's existing
  `G4EmCalculator` interaction sampling; no C++ change). `spectra.cjs geant4` stores it in
  `catalog/geant4_atomic.json`; `build` folds it into the features as 11 `g4_*` inputs and
  records the catalogue's SHA-256.
- [x] Five atomic and three molecular `*_geant4` catalogue entries, a per-source cascade
  (`pubchem`/`geant4`) and three new ablation kinds. Earlier entries' metrics are byte-identical.
- [x] Re-graded ablation (full table in the [study](../../../docs/research/spectrum_prediction.md#validation-protocol)):
  Geant4 inputs hurt in-distribution atomic CV for ridge (+0.034) and the MLPs (+0.005/+0.011),
  help kNN (−0.003), and help leave-one-group-out CV for kNN and both MLPs (−0.011/−0.014/−0.002).
  Pooling the Geant4-fed atomic model gives the best molecular CV (0.2305 vs 0.2314), family-CV
  and test, all within the CV standard deviation.
- [x] Exports moved to the Geant4-fed chain (`atomic_mlp_tanh_geant4` →
  `molecular_mlp_cascade_geant4`); the trainer refuses an exported molecular cascade that pools a
  different atomic model than the exported one (`--export` overrides included).
- [x] The scenario reads the atomic `g4_*` inputs from its own live `G4_<symbol>` probes. The
  validator recomputes them from `material_probes`: max |Δ| 8.9e-16 against the run and the
  catalogue; engine vs Python forward 3.3e-16; held-out metrics equal the report.
- Verification: `node --test` 22/22 (6 new), `validate_spectrum_prediction.py` passed,
  Studio `test_spectra.py` 13/13 (ablation grouping, live-input lines), ML model audit
  regenerated (55 models, 0 failing), purity report regenerated, Release CTest 82/82, Studio
  pytest 393/393.
- Residuals (queued above): in-distribution atomic accuracy, out-of-group pooled R², the 10 eV
  floor of the Geant4 inputs, the MPNN cascade, and deltas within noise.

## Open work

- [x] **Particle-trained atomic rung** (2026-11-27): delivered as the Geant4-fed rung, see
  [the record](#geant4-fed-atomic-rung-2026-11-27).
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
