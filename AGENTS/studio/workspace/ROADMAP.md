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

## Bundle-declared validation in Run summary (2026-11-09)

- [x] Run summary grades the loaded run against its bundle's declared output/family checks with
  the suite's shared evaluator (declarations through `trech inspect` with recorded `--param`s).
  Verification: `studio/tests/test_bundle_checks.py` (10, incl. a real-engine inspection of the
  photofraction bundle) and an offscreen window opening two recorded post-split runs (2/2 pass for
  `glass_from_sand`; 0/2 for an aerodynamics run that recorded no scores, matching
  `validate_scenario.py`). Pre-split runs whose recorded `examples/experiments/...` path no longer
  exists read "not graded".
- [ ] Residual: declarations are read from the current source, not a snapshot recorded with the
  run (no source/config-hash comparison yet); inspection runs synchronously on open (15 s cap);
  sweep gates are not graded from sibling runs inside Studio; no per-check jump to the emit/score
  row that supplied the value.

## Event deposit distribution in Run summary (2026-11-09)

- [x] Run summary shows the engine's event-deposit shape (mean ± engine stderr, stddev, min/max,
  zero-deposit fraction, skewness/excess kurtosis) as straight reads; an undefined shape is a warned
  row, and runs without the keys show no section (`test_run_summary_reads_event_deposit_shape_verbatim`).
- [x] Histogram (2026-11-11): the engine now bins the per-event deposit
  (`system_event_edep_histogram`); Run summary lists its bins verbatim in an "Event deposit
  histogram" section (`test_run_summary_lists_engine_event_histograms_verbatim`).
- [x] Per-volume histograms (2026-11-12): one "Per-volume deposit histogram · <name>" section per
  hit volume, and "Per-volume track length histogram · <name>" / "Per-volume secondaries
  histogram · <name>" sections per stepped volume (secondaries only where some were created), in
  the tables' order, read verbatim through the shared `_histogram_section`
  (`test_run_summary_lists_per_volume_histograms_verbatim`; a 200-event assembly run gives 25
  histogram sections over 19 scored volumes).
- [ ] Residual: histograms are text tables with bars, not plotted charts; many scored volumes give
  many sections (no collapse/filter); per-species per-volume histograms do not exist in the engine.

## Geometry resolution in Run summary (2026-11-09)

- [x] Run summary lists the engine's provenance `geometry_resolution` substitutions (material and
  parent fallbacks, volumes not built) as warned rows with a caveat; absent block → no section
  (`test_run_summary_lists_engine_geometry_substitutions`).
- [x] Outliner marks (2026-11-10): declared nodes the engine re-parented, skipped or gave a
  fallback material carry `⚠ engine substituted` and `engine:` tooltip lines from the provenance
  block (`test_outliner_marks_engine_geometry_substitutions`).
- [x] Overlaps (2026-11-10): Run summary shows the engine's `overlap` issues
  (`overlaps <sibling> by ≥ d mm` / `protrudes from <mother> by ≥ d mm`) and an "overlap count",
  plus a "Geometry overlap check" section (clean/overlap result, volumes, pairs, samples,
  tolerance) whenever provenance carries `geometry_overlap_check`; the Outliner marks both volumes
  of a sibling overlap and the protruding volume (`test_run_summary_shows_engine_overlap_check`,
  extended `test_outliner_marks_engine_geometry_substitutions`). Completion lists
  `geometry.overlapCheck`.
- [x] Refused runs (2026-11-12): a `geometry_refused` provenance record (engine
  `geometry.refuseOn`) yields a "Geometry refusal" section (refused kinds, refused issue count,
  "events run: 0") and a caveat, beside the existing resolution/overlap sections read from the same
  record (`test_run_summary_shows_engine_geometry_refusal`). Completion lists `geometry.refuseOn`.
- [ ] Residual: the 3D Scene layer still draws the declared geometry and does not highlight overlap
  regions (a re-parented volume at its
  declared position, a skipped volume as if built); the medium box has no Outliner node, so its
  material fallback appears only in Run summary; marks are lost when a draft is applied.

## Event multiplicity in Run summary (2026-11-10)

- [x] Run summary reads the engine's secondary-multiplicity and track-length shape verbatim
  (`test_run_summary_reads_event_multiplicity_verbatim`); older runs show no section.
- [x] Species split (2026-11-11): the section lists each secondary species the engine reports
  (optical photons separate).
- [x] Histogram (2026-11-11): "Secondary multiplicity histogram" lists the engine's
  `system_event_secondaries_histogram` bins verbatim. Per-species sections (2026-11-12) list each
  produced species' `system_event_secondaries_<species>_histogram` the same way.
- [x] Track-length histogram (2026-11-12): "Event track length histogram" lists the engine's
  `system_event_track_length_histogram` bins verbatim (`test_run_summary_lists_engine_event_histograms_verbatim`).

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
- [x] Inferred macro quantities beside their measured nano base, with gap-to-truth (2026-11-08).
  `glass_of_water_shaken.js` emits `observer_comparisons` + its `__cascade` report; the Scale
  ladder shows rest density 999.16 vs 998.2 kg/m³ (+0.096%), cohesion/viscosity as not graded
  (illustrative stages, no reference), the nano MD basis and the producing stage's badges.
  The recorded run shows `macro_fluid_params` as EXTRAPOLATING / HEURISTIC DOMAIN / NO MEASURED
  ACCURACY: the density agreement comes from an unvalidated macro map. Residual: only the glass
  scenario adopts the convention (MR `gap_to_truth`, beaker and lava endpoints do not yet), the
  values appear in the dock rather than as a viewport overlay, and the full-horizon media were not
  recaptured.
- [ ] Compute-shader particle/fluid overlay for `fluid_frame` emits (WGSL compute → instanced
  points/metaballs) so a shaken glass renders in the viewport, not only in the offline MP4.

## Models dock (2026-11-10)

- [x] Live JS definition/search editing (debounced draft inspection, line-numbered errors, search
  candidates, on-disk reload) and checkpoint management: sort by uses/recent/name/size,
  pin/activate, guarded delete, prune preview, verify, automatic usage after runs. Offscreen
  tests drive the real CLI.
- [ ] Per-candidate search report view (loss vs parameters plot, discarded candidates) and a diff
  of two checkpoints' carried metrics.
- [ ] Insert a `TRECH_ML.modelEntry(...)` snippet into the open scenario from a selected
  checkpoint; show which loaded run used which checkpoint.
- [ ] Native screenshot of the dock for the documentation gallery (media gates apply).

## Spectrum-prediction extension (2026-11-07)

- [x] Spectra dock activated by the scenario's `studio_mode` declaration: measured vs learned
  plot on emitted grids, engine trust badges, leaderboard/ablation, Node training job and
  `data_dir` hand-off. Offscreen tests cover parsing, badges, the panel and option switching.
- [x] Architectures tab shows the trainer's atomic split-noise checks (Repeated-CV and Group-CV
  RMSE columns, worst group, per-group tooltip) from the emitted `split_noise` block; values are
  parsed, never recomputed, molecular rows show "—", and a malformed group row rejects the
  report (2026-11-09). Residual: no side-by-side comparison of two runs' leaderboards.
- [ ] Re-inspect target choices automatically after **Use trained run** when the new dataset
  changes molecule/element lists; compare two runs' leaderboards side by side.
- [ ] Native screenshots of the Spectra dock for the documentation gallery (media gates apply).
