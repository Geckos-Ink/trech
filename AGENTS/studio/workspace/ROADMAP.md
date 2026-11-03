# Panels, run reports and resource controls — roadmap

[Root principles](../../../AGENTS.md) · [Root roadmap](../../../ROADMAP.md) · [Parent](../ROADMAP.md) · [Handbook](AGENTS.md)

Related owners: [Coverage, uncertainty and trust](../../engine/inference/trust/ROADMAP.md) · [Precision profiles and runtime budgets](../../engine/precision/ROADMAP.md).

Maintain work in its owning branch. Dated results apply to the recorded checkout; they do not validate subsequent changes.

## Adaptive precision and resources

- [x] Precision and resources dock: continuous scenario refinement, predictive soft time limits,
  independent render detail/target FPS/memory allowance. Engine remains the only physics owner.
- [x] Interactive CPU frame-cost feedback with hysteresis, viewport/particle complexity bounds,
  dynamic sphere/tube tessellation and surface-grid spacing, and estimated GPU cache budgets.
- [x] Configurable track/segment loading budgets; fixed capture overrides (including all recorded
  samples), representation metadata, engine stop reasons and limited-stage ladder badges.
- [ ] Residual: GPU timestamps and measured available VRAM are unavailable; CPU submission timing
  and RAM-based defaults are scheduling estimates, not a measured GPU throughput or hard memory cap.
- [ ] Residual: hook emits/particle frames still load in memory. Streaming/out-of-core loading and
  worker-thread surface extraction are needed for very large runs; surface neck construction can
  still require quadratic temporary memory. Trajectory budget changes apply on reopening output.
- [ ] Residual: automatic simulation accuracy/convergence control needs engine/scenario error
  estimates; Studio currently submits continuous factors and event/time budgets. It never invents
  missing models or claims a render refinement improves simulation accuracy.

## Milestone 3 — the cascade, made legible

- [x] Cascade dependency warnings: the ladder reads effective starvation and inherited
  out-of-domain/starvation/off-band input names while retaining local coverage fields. The panel
  names the consumed facts behind each inherited warning; legacy/operator traces without lineage
  remain unreported. Builder/panel regressions cover inherited warnings, absent lineage, local
  joint-check wording and skipped missing-input evaluations; the full Studio suite passes with
  GPU-only checks skipped in the sandbox. Cross-call/operator
  lineage remains an [engine gap](../../engine/inference/trust/ROADMAP.md).
- [x] Scale ladder widget (**landed 2026-08-15**): a `Scale ladder` dock (tabbed with Console / Run
  summary / Emits) over a new pure `studio/trech_studio/cascade.py` builder. It reads every recorded
  inference pass out of `trech_hook_emits.jsonl` — a `ctx.cascade` **property** pass or a
  `ctx.evolve`/`ctx.react`/`ctx.interact` **operator** pass — and shows: the bands the run bridged
  (`bands_bridged`, the [inference workstream](../../engine/inference/ROADMAP.md#cascade-metrics-to-watch-regression-signals) headline cascade metric — a narrow point-predictor bridges
  one, `polyurethane_foam.js` bridges nano → meso → macro), which `seedKeys` came from the **Geant4
  base** (per-event tallies + `material.*` probes) rather than from the scenario, and per stage its
  band, what it predicted, and the engine's own trust flags rendered as badges: `EXTRAPOLATING`,
  `STARVED REGION`, `STARVED REGION (JOINT)` (in range on every axis yet far from any training
  point), `OFF TRAINED BAND`, `HEURISTIC DOMAIN` (an unmeasured hull) and `NO MEASURED
  ACCURACY`, alongside the stage's held-out R² and its **measured per-output error** (the engine's
  new `outputAccuracy`, whose `rmse` is a measured 1-σ residual). Honesty by construction: Studio
  sets no flag of its own — every badge names a boolean the engine decided — a counter a scenario
  renamed is reported as unrecorded rather than guessed, and a model with no metrics is described in
  words ("an illustrative map, not a trained-and-validated stage") instead of being shown with a
  flattering blank or a 0. The joint density check keeps **three** outcomes — covered, starved, and
  *not checked* — so a model carrying no joint reference can never read as one that passed. Detection keys on the **stage record's shape**, not the container name,
  because scenarios nest these traces under their own keys (`cascade`, `cascade_trace`,
  `chemistry_inference.stage_trace`). Verified against real runs: `glass_from_sand.js` (two
  illustrative maps, both badged) and `polyurethane_foam.js` (the same two maps plus its trained
  meso operator, badge-free, reporting `d_gel_dt` R²=0.99959 σ=8.25e-5). Tests:
  `studio/tests/test_cascade_ladder.py` (6 cases). *Remaining:* it is a read-only report — no click-through
  from a stage to the emit that produced it, no per-event scrub of how a stage's coverage changed
  over the run, and `trech_resim_queue.jsonl` (which events the coverage flag routed to resim) is
  still not read by Studio at all.
  **Engine signal (2026-07-24):** each `__cascade.trace[i]` carries a per-stage **trust
  profile** — training-domain coverage (`inDomain`, `domainMeasured`, `extrapolation`,
  `outOfDomainInputs`), in-hull starvation (`starvedInputs`), off-trained-band use (`scaleMismatch`,
  `trainedScale`), and held-out accuracy (`holdoutR2`/`holdoutSamples`, null for untrained maps) —
  plus run-level `stagesExtrapolating` + `stagesScaleMismatched` + `stagesStarved` and the run's
  `hook_predict_out_of_domain_count` / `stratify_low_confidence_count` in scores/provenance. The
  widget can badge an *extrapolating / starved / off-band / low-confidence* stage, show its held-out
  R², distinguish a trained-domain guarantee (`domainMeasured:true`) from a heuristic fallback, and
  even surface which events the coverage flag routed to resim (`trech_resim_queue.jsonl` with
  `source:"cascade_coverage"`) — the same honesty discipline as the determinism/gap-to-truth labels.
  Scenarios expose the trace via hook emits (e.g. `cascade_multiscale_demo.js`).
- [ ] Overlay inferred macro quantities (rest density, cohesion, viscosity for the glass-of-water)
  next to their measured nano base, with the gap-to-truth shown (honesty rule). The per-stage
  `extrapolation` (training-σ past the trained hull) is the natural low-confidence marker here.
- [ ] Compute-shader particle/fluid overlay for `fluid_frame` emits (WGSL compute → instanced
  points/metaballs) so a shaken glass renders in the viewport, not only in the offline MP4.
