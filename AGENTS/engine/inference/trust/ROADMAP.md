# Coverage, uncertainty and trust — roadmap

[Root principles](../../../../AGENTS.md) · [Root roadmap](../../../../ROADMAP.md) · [Parent](../ROADMAP.md) · [Handbook](AGENTS.md)

Related owners: [Multi-scale inference](../ROADMAP.md) · [Training tools, model data and feature schemas](../../../tooling/training/ROADMAP.md) · [Panels, run reports and resource controls](../../../studio/workspace/ROADMAP.md).

Maintain work in its owning branch. Dated results apply to the recorded checkout; they do not validate subsequent changes.

## Workstream 3 — coverage and uncertainty

3. **Coverage/uncertainty per band. [mechanism landed 2026-07-24]** Each stage now reports when it
   is extrapolating out of its trained domain instead of silently guessing. `GenericSurrogate::coverage`
   compares each input's standardized deviation `|z|=(x-mean)/std` against the model's per-feature
   trained hull (`input_domain.standardized_radius`, exported by `trech-train-surrogate` from the
   training split; legacy/illustrative models with no hull fall back to a heuristic 3σ and report
   `domainMeasured:false`, so an unvalidated map cannot masquerade as a trained-domain guarantee).
   `ScaleCascade` fills per-stage `inDomain`/`domainMeasured`/`extrapolation`/`maxStandardizedDeviation`/
   `outOfDomainInputs` and a run-level `stagesExtrapolating`; the flag **propagates up the ladder**
   (a low stage's out-of-domain output makes the next stage's coverage flag too). Surfaced through
   the JS boundary on `__cascade.trace[i]` + `__cascade.stagesExtrapolating` and on `ctx.predict`'s
   reserved `__coverage`. Guarded by `tests/test_generic_surrogate.cpp` (measured-vs-heuristic,
   missing-input-out-of-domain), `tests/test_scale_cascade.cpp` (per-stage in/out + propagation +
   count), `tests/test_js_runtime.cpp` (JS-boundary fields); demonstrated in a real run by
   `cascade_multiscale_demo.js` (emits per-stage coverage). **[extended 2026-07-24]** the three
   originally-remaining items landed as a full per-stage **trust profile**: (a) the out-of-domain
   flag is now an auditable *run fact* — `hook_predict_out_of_domain_count` (subset of
   `hook_predict_count`) is plumbed to `trech_scores.jsonl` + `trech_provenance.jsonl` like the
   other hook counters (proven end-to-end: a forced-OOD run reports 4/4, an in-domain run 0);
   (b) the harvester's dimension-scale band is wired into per-stage confidence — the trainer exports
   `trained_scale_bands`, `GenericSurrogate` carries them, and `ScaleCascade` flags a stage applied
   OFF its trained band (`scaleMismatch`/`trainedScale`, run-level `stagesScaleMismatched`); (c)
   held-out accuracy now travels WITH the model — the trainer embeds `holdout{r2_min,n}`, the engine
   surfaces per-stage `holdoutR2`/`holdoutSamples` (null for illustrative maps, never a fake 0).
   Guarded by extended `tests/test_generic_surrogate.cpp` (carried bands/holdout), `test_scale_cascade.cpp`
   (scale-mismatch + surfaced holdout), `test_js_runtime.cpp` (run-level OOD count + JS-boundary
   fields); a **genuine train→load→run round-trip** confirmed it (a real model trained on meso-band
   Geant4 runs, declared at `nano`, is flagged `scaleMismatch:true`/`trainedScale:"meso"` with its
   held-out R² surfaced). **[further extended 2026-07-24]** the flags now *act*, not just surface:
   (1) **resim routing** — `stratify.resimOnLowConfidence` routes an event whose `onEventEnd`
   inference ran out-of-domain into `trech_resim_queue.jsonl` (`reason:"inference_out_of_domain"`,
   `source:"cascade_coverage"`) even when the feature-based stratifier labels it predictable, counted
   in `stratify_low_confidence_count` (a new accumulable, distinct from `stratify_exceptional_count`);
   `RunAction::DispatchHook` now returns the per-dispatch out-of-domain count so `EventAction` can act
   on it (proven end-to-end: 3/3 out-of-domain events queued, `stratify_low_confidence_count=3`).
   (2) **starved-region signal** — the trainer exports a per-feature `input_domain.occupancy`
   histogram; coverage flags an input that is *within* the trained range but in an unpopulated bin
   (`starvedInputs`, run-level `stagesStarved`) — density inside the hull, not just its edge, the
   planner's starved-region notion (proven: an in-range value in an empty bin is flagged starved
   while staying `inDomain`). **[extended 2026-08-15 — measured per-output uncertainty]** the trust
   profile now also carries *how wrong the stage usually is, per quantity*. `holdoutR2` was one
   number for a whole model; `GenericSurrogate::outputAccuracy(o)` splits the carried `holdout` block
   into per-output `{r2, mae, rmse}`, and every learned-inference path reports it through the shared
   `NamedOutputAccuracy`/`collectOutputAccuracy` record: `__cascade.trace[i].outputAccuracy`, each
   `ctx.evolve`/`ctx.react`/`ctx.interact` stage trace, and a reserved `__accuracy` object on a
   `ctx.predict` result. **`rmse` is a measured 1-σ held-out residual in the quantity's own units** —
   the honest replacement for a scenario hand-typing a σ next to an inferred value (the σ=0.12/0.14/
   0.15 response-surface constants in Briggs–Rauscher / polyurethane / elephant's-toothpaste are
   exactly the pattern this exists to retire). Every metric is independently optional and an
   unmeasured output is **absent** — a metric-less illustrative map reports `{}`, never a 0 residual
   that would read as a perfect model. `trech-train-surrogate` now exports `holdout.rmse` alongside
   `r2`/`mae`; the nine committed trained operators were backfilled **from their own manifests'
   `metrics_holdout`** (metadata only — verified that the nine files differ from `HEAD` by nothing
   but the added `holdout.rmse` block, so no weight, scaler, hull or physics changed). Proven
   end-to-end: a full `polyurethane_foam.js` run reports its meso operator's per-output residuals
   (`d_gel_dt` R²=0.99959 σ=8.25e-5, `d_dissolved_co2_dt` R²=0.99426 σ=9.83e-3) beside the
   unchanged run trust record (2,812,320 inferences, 0 OOD, holdout R²=0.9929), while the same run's
   illustrative `nano_reagent_descriptors`/`macro_foam_response` cascade maps correctly report `{}`.
   Guarded by `tests/test_generic_surrogate.cpp` (independent metric blocks, absent-not-zero, the
   committed operator really carrying σ), `tests/test_scale_cascade.cpp` (per-stage split is
   name-sorted, the strong output reports its own R² while the model-wide number stays the worst
   output, absent stays empty) and `tests/test_js_runtime.cpp` (`__accuracy` on `ctx.predict`,
   present-vs-absent across two cascade stages). **Remaining (workstream-2-gated):** per-band
   held-out accuracy only becomes *meaningful* once a real trained per-band chain lands (the
   mechanism is ready; illustrative maps still report null/`{}`), **no scenario has yet switched its
   hand-typed σ over to the emitted measured one** (mechanism first, adoption next), and the residual
   is a global held-out RMSE rather than an input-conditional (heteroscedastic) uncertainty.
   **[extended 2026-08-15 — joint (multivariate) starved regions]** the last named gap in this
   workstream is closed. Both existing density checks are **per feature**, so neither can see a point
   that is in range on every axis yet nowhere near any training point: train on (cold, slow) and
   (hot, fast), ask for (cold, fast), and every per-feature check passes while the model interpolates
   across a hole it never saw. `trech-train-surrogate` now exports `input_domain.joint` — a compact
   covering set of standardized training rows chosen by **deterministic farthest-point sampling**
   (seeded from the row nearest the mean; no RNG, no k-means restarts, so the same split always
   exports the same reference) plus the distance covering the training set's `quantile` (default
   0.99). `GenericSurrogate::coverage` reports `jointMeasured`/`jointStarved`/`jointDistance`/
   `jointRadius`; `ScaleCascade` carries them per stage and counts joint starvation into
   `stagesStarved`; the three batched operators aggregate `elementsJointStarved`/`pairsJointStarved`
   + `maxJointDistance`; all of it crosses the JS boundary, with `jointMeasured:false` meaning **the
   check was not performed** (the other fields are `null`) rather than a pass. Proven by a genuine
   **train → load → run round-trip**: a two-cluster panel trained through the real
   `trech-train-surrogate` CLI, then queried through `ctx.predict` in a live run — the untrained
   (cold, fast) corner comes back `inDomain:true`, no out-of-domain input, no starved input, and
   `jointStarved:true` at distance 1.661 vs the trained covering radius 0.133, while both trained
   clusters sit at ~0.08. Calibration is asserted, not assumed: replaying the training set through
   its own exported check flags 1.3% of it against a nominal 1%. The verdict short-circuits on the
   first covering center, so the exact full scan is paid only in the starved case. **Cost, measured:**
   on a 16-input/24-center model at real training points, coverage goes 82 → 158 ns while a realistic
   MLP prediction is ~700 ns — roughly +10–20% of total inference, and exactly zero for the models
   that carry no joint reference (which is all nine committed ones until they are retrained).
   The planner consumes the same evidence: `plan_experiments --models <model.json>` reports
   per-feature empty bins and ranks the joint gaps, naming each as an **operating point in raw input
   units** to simulate next (for the two-cluster panel it proposes the middle of the gap, 8.3× the
   covering radius). Guarded by `tests/test_generic_surrogate.cpp` (the hole between clusters passes
   every per-feature check and is still flagged; unmeasured reports as unchecked; a malformed
   reference is ignored rather than half-applied), `tests/test_scale_cascade.cpp` (per-stage +
   run-level counting), `tests/test_js_runtime.cpp` (value-vs-null across the JS boundary) and the
   new `tests/test_joint_domain.py` (calibration, determinism incl. row-order independence,
   degenerate inputs, and the planner's proposals; runs in CTest). **Remaining:** no committed model
   carries a joint reference yet — they gain one when retrained — and the covering set is a fixed
   24-center budget rather than one adapted to the training set's intrinsic dimensionality.
