# Training tools, model data and feature schemas — roadmap

[Root principles](../../../AGENTS.md) · [Root roadmap](../../../ROADMAP.md) · [Parent](../ROADMAP.md) · [Handbook](AGENTS.md)

Related owners: [Multi-scale inference](../../engine/inference/ROADMAP.md) · [Coverage, uncertainty and trust](../../engine/inference/trust/ROADMAP.md) · [Tests and validation ownership](../validation/ROADMAP.md).

Maintain work in its owning branch. Dated results apply to the recorded checkout; they do not validate subsequent changes.

Training-tool work serves the [multi-scale inference plan](../../engine/inference/ROADMAP.md). Domain/holdout export, measured residuals and experiment-planning gaps are tracked in [trust](../../engine/inference/trust/ROADMAP.md); whole-run splits and observer promotion gates follow [validation](../validation/ROADMAP.md). Add new tooling-only gaps here when they do not belong to one of those workstreams.

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
