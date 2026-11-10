# Training tools, model data and feature schemas — roadmap

[Root principles](../../../AGENTS.md) · [Root roadmap](../../../ROADMAP.md) · [Parent](../ROADMAP.md) · [Handbook](AGENTS.md)

Related owners: [Multi-scale inference](../../engine/inference/ROADMAP.md) · [Coverage, uncertainty and trust](../../engine/inference/trust/ROADMAP.md) · [Tests and validation ownership](../validation/ROADMAP.md).

Maintain work in its owning branch. Dated results apply to the recorded checkout; they do not validate subsequent changes.

Training-tool work serves the [multi-scale inference plan](../../engine/inference/ROADMAP.md). Domain/holdout export, measured residuals and experiment-planning gaps are tracked in [trust](../../engine/inference/trust/ROADMAP.md); whole-run splits and observer promotion gates follow [validation](../validation/ROADMAP.md). Add new tooling-only gaps here when they do not belong to one of those workstreams.

## JS model definitions and checkpoint store (2026-11-10)

- [x] `TRECH_ML.defineModel` / `defineSearch` (grid, seeded random, custom generator, Evolvo).
  The `trech-ml` CLI trains/searches through the existing Python trainers. The typed, versioned
  checkpoint store refuses structure conflicts and records usage from provenance SHA-256. It
  supports pin/activate/delete/prune/verify/gc. Scenarios resolve checkpoints with
  `TRECH_ML.modelEntry`; Studio has a Models dock. Verification: `node --test` 12/12, CTest
  `trech_ml_models_js` + `trech_ml_registry_quickjs`, Studio `test_models.py` 7/7. A real
  torch run on 8 `config_stratify` runs took 7 candidates to an 8×2 MLP: test-run R² 0.63,
  retrain identical.
- [ ] Register other loader formats (logistic stratifier, optics ridge, operator manifests).
  Today only `generic_surrogate_v1/v2` JSON + TorchScript twins are accepted.
- [ ] Repeated-seed / repeated-split candidate scoring so a search reports selection noise
  between close structures (single-run selection only today).
- [ ] Richer structure families: per-layer widths, other activations once the trainer and
  `GenericSurrogate` export them; DeepSets/MPNN from the spectrum catalogue.
- [ ] Engine-side usage recording (runs outside Studio need `trech-ml touch --run`); an
  optional age/size budget enforced automatically after searches.
- [ ] Migrate scenarios that hand-write `models[]` paths onto definitions + `modelEntry` with
  committed fallbacks, so retraining a stage is a definition edit rather than a path edit.

- [x] Explicit logit targets export portable v2 sigmoid links without implicit clipping or
  pseudocounts. Mixed-link NumPy/trainer/optional Python TorchScript tests pass, including natural-unit
  metrics, invalid train/holdout targets, saturation and non-finite encoded failures.
- [ ] Bounded outputs do not establish calibrated uncertainty or good generalization. Preserve
  independent physics/observer promotion gates and record any finite-MC label smoothing explicitly.

- [x] A real MC-trained meso observer extends the shared atomic/nano CHNO models, retaining
  222 raw-label rows, frozen model evidence, independent final conditions and a failed-attempt
  archive. Runtime and offline C++/Python decoder results agree within 2.78e-16 in reviewed emits.
  Future cache reuse checks engine/model/feature-source identity; no legacy cache is silently trusted.
- [ ] Resolve measured per-feature/joint coverage holes with additional training and new final
  holdouts before broader promotion; calibrate physical uncertainty and validate varied
  density/source/geometry against independent references. See the [observer limits](../../../docs/particle_observer.md).
