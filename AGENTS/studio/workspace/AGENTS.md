# Panels, run reports and resource controls — context and contracts

[Root principles](../../../AGENTS.md) · [Root roadmap](../../../ROADMAP.md) · [Parent](../AGENTS.md) · [Roadmap](ROADMAP.md)

Related owners: [Coverage, uncertainty and trust](../../engine/inference/trust/AGENTS.md) · [Precision profiles and runtime budgets](../../engine/precision/AGENTS.md).

Read the root principles and the parent handbook first; then open only the subcategory relevant to the task. Source paths and shell commands in code spans/blocks are repository-relative unless stated otherwise; Markdown links resolve from this file.

##### [`studio/trech_studio/cascade.py`](../../../studio/trech_studio/cascade.py)

Builds the **scale ladder** — the multi-scale inference cascade made legible — from a run's hook
emits. Pure (numpy-free, no Qt): it finds every stage trace in the emitted payloads, groups it into
`LadderPass` (a `ctx.cascade` property pass or a `ctx.evolve`/`ctx.react`/`ctx.interact` operator
pass) and reports, per stage, the band it ran at, what it predicted, and the engine's **trust
profile**: extrapolating past its trained domain, in a starved (unpopulated) region of it, applied
off its trained band, on a heuristic rather than measured hull, **jointly** starved (in range on
every axis yet far from any training point — the multivariate check the per-feature ones cannot
make), and its measured per-output held-out error (`outputAccuracy`, whose `rmse` is a measured 1-σ
residual).

- **Key symbols:** `build_scale_ladder`, `ScaleLadder` (`bands_bridged` — the headline "how many
  scales did one run bridge" metric), `LadderPass` (`bands`, `geant4_seed_keys` — which seed facts
  came from the Geant4 base rather than the scenario), `LadderStage` (`badges`, `accuracy_note`),
  `OutputAccuracy`.
- Cascade stages retain local checks separately from effective trust. `starved` badges inherited
  starvation even when local `starvedInputs` is empty; `dependency_notes()` names the engine's
  `upstreamOutOfDomainInputs`, `upstreamStarvedInputs` and `upstreamScaleMismatchedInputs` in the
  panel. Absent lineage on older runs/operators remains unreported; Studio never reconstructs it
  from matching values or names.
  Joint-density notes explicitly describe the local check; partial operator missing inputs are
  described as skipped evaluations, never synthetic zero facts.
- **Detection keys on the STAGE record, not the container name** (`_is_stage`): scenarios nest their
  reports under whatever key they like (`cascade`, `cascade_trace`, `chemistry_inference.stage_trace`)
  and rename the surrounding counters, so keying on a container would silently miss runs.
- **Common mistakes:** inventing a count the scenario did not emit (a renamed `inferenceCount` stays
  `None`, reported as unrecorded); showing an unmeasured accuracy as 0 — absent must read as absent;
  collapsing `joint_measured is None` (not checked) into "not starved".
- **Observer comparisons:** `ScaleLadder.comparisons` (`ObserverComparison`, `BasisValue`) reads
  a payload's top-level `observer_comparisons` list ([convention](../../../docs/scenario_hooks.md)):
  inferred value, independent reference, unit, lower-scale basis and `stage_output`. The last emit
  wins per (tag, quantity). `relative_gap` is plain arithmetic on the two recorded numbers; a
  `null` or zero reference is reported as not graded/undefined, never as agreement. Stage trust
  comes from the linked stage's engine badges, not from the size of the gap. A run with
  comparisons but no stage trace is not empty.
- **Tests:** [`studio/tests/test_cascade_ladder.py`](../../../studio/tests/test_cascade_ladder.py).

##### [`studio/trech_studio/precision.py`](../../../studio/trech_studio/precision.py) · [`run_summary.py`](../../../studio/trech_studio/run_summary.py) · [`settings.py`](../../../studio/trech_studio/settings.py)

`precision.py` builds the multidimensional simulation-precision report (events, trajectory
counts/caps, medium/process coverage, Monte-Carlo proportion standard errors, representation
settings) shown in the UI and embedded in every capture sidecar. Radius-bearing frames report
emitted-radius spheres, native length units, declared bond counts and whether the Geant4 mm scene
is visible. When the run declares one, it also
carries the engine's **precision profile** (`precision_profile` + the scenario-mapped
`precision_axes`, each with its role and representation-only flag) — Studio reports the rung and
the axes the scenario actually moved, never a Studio-invented quality score. `run_summary.py` builds the
**honest run header** the Run-summary panel renders — determinism/seed/physics list (flagging that
a `predictive` run's inferred results are not strict Geant4 tallies), Geant4's primary tallies with
a labelled binomial sampling error, the analytic cross-check **gaps**, the learned-inference
counters (`hook_predict_count` + how many ran out of trained domain) and the hook sideband. Both
are pure (no Qt) and unit-tested headless. `settings.py` holds app settings.

#### `studio/trech_studio/ui/` — PySide6 panels (glue only; no physics, no direct engine IO)

##### [`studio/trech_studio/ui/main_window.py`](../../../studio/trech_studio/ui/main_window.py) + panels

[`outliner.py`](../../../studio/trech_studio/ui/outliner.py), [`inspector.py`](../../../studio/trech_studio/ui/inspector.py),
[`code_editor.py`](../../../studio/trech_studio/ui/code_editor.py) (JS editor + Run), [`console.py`](../../../studio/trech_studio/ui/console.py)
(log stream only), [`run_summary.py`](../../../studio/trech_studio/ui/run_summary.py) (sectioned run header from
`studio/trech_studio/run_summary.py`), [`emits.py`](../../../studio/trech_studio/ui/emits.py) (tag-filtered hook-emit browser;
payload arrays are truncated for **display** with a note, and "Show on timeline" maps the n-th emit
of the played tag to the n-th emitted frame's own time — the timeline stays the only clock),
[`scenario_options.py`](../../../studio/trech_studio/ui/scenario_options.py) (typed controls from `trech inspect`),
[`scenarios.py`](../../../studio/trech_studio/ui/scenarios.py) (filesystem tree rooted at `examples/`),
[`cascade.py`](../../../studio/trech_studio/ui/cascade.py) (the **Scale ladder** dock: every recorded inference pass,
its bands, its Geant4-derived seed facts and each stage's engine-set trust badges + measured
per-output error; `stage_summaries` is the flat form tests assert on),
[`timeline.py`](../../../studio/trech_studio/ui/timeline.py) (the one scalar cursor; follows an emitted accelerated
`playback_time_s` only when `physical_time_s` is retained, showing both clocks), and
[`theme.py`](../../../studio/trech_studio/ui/theme.py).

- **Tests:** [`studio/tests/test_ui_panels.py`](../../../studio/tests/test_ui_panels.py) (browser, typed options,
  timeline scrub/`set_cursor` rejection, run-summary sections/labels, emit filtering + frame jump),
  [`studio/tests/test_cascade_ladder.py`](../../../studio/tests/test_cascade_ladder.py) (ladder bands, Geant4-vs-scenario
  seed split, badges, absent-accuracy wording, operator report under a scenario-chosen key).

- **Spectra dock (spectrum-prediction extension) — Experimental (2026-11-07).** Pure
  `studio/trech_studio/spectra.py` builds the workspace from `spectrum_prediction` /
  `spectrum_summary` / `spectrum_model_report` / `spectrum_geant4_context` emits. It rejects
  wrong-length or non-finite vectors, keeps null predictions null and shows only engine-set badges
  (an unchecked joint test reads JOINT NOT CHECKED). `ui/spectra.py` holds the plot, leaderboard and
  training tabs; the leaderboard adds the emitted atomic `split_noise` (Repeated-CV / Group-CV RMSE,
  worst group, per-group tooltip) without recomputing it. `engine/spectra.py` launches the Node pipeline (`TRECH_NODE` or PATH) via QProcess.
  The dock is visible when `is_spectrum_mode` sees the declared schema/extension, or when a loaded
  run carries spectrum emits. `ScenarioOptions.set_value` flips `studio_mode` / `data_dir`. Tests:
  `studio/tests/test_spectra.py`. Contract: [spectrum branch](../../scenarios/spectra/AGENTS.md).
- **Models dock — Experimental (2026-11-10).** Pure `studio/trech_studio/models.py` parses
  `trech_model_registry_v1` / `trech_ml_inspection_v1`. Absent accuracy reads "no carried
  accuracy", absent use reads "never", and holdout sources are spelled out, with selection runs
  marked optimistic. `engine/models.py` reads the index, runs quick CLI commands synchronously
  and runs `ModelJob` (train/search) and `DraftInspector` (live `inspect --stdin`, newest draft
  wins) on QProcess. `ui/models.py` holds the editor, outline, checkpoint tree, actions,
  `PruneDialog` (preview-before-delete) and a `QFileSystemWatcher` on `ml/` and the store
  index. `confirm` is injectable. `StudioWindow._on_run_finished` calls `record_run_usage`.
  Every store change goes through the CLI ([contract](../../../docs/ml_models.md)).
  Tests: `studio/tests/test_models.py`.
- **Scale ladder — Shipped (2026-08-15).** The `Scale ladder` dock (tabbed with Console/Run
  summary/Emits) reads every `ctx.cascade` / `ctx.evolve` / `ctx.react` / `ctx.interact` trace out of
  `trech_hook_emits.jsonl` and shows the run's ladder: bands bridged (nano → meso → macro), which
  seed facts came from the **Geant4 base** rather than the scenario, and per stage the engine's own
  trust flags as badges (`EXTRAPOLATING`, `STARVED REGION`, `OFF TRAINED BAND`, `HEURISTIC DOMAIN`,
  `NO MEASURED ACCURACY`, `STARVED REGION (JOINT)`) plus the measured per-output held-out error.
  Studio sets no flag of its own and invents no count: a counter a scenario renamed is reported as
  unrecorded, an unmeasured accuracy is stated in words rather than rendered as 0, and the joint
  density check has **three** outcomes — covered, starved, and *not checked* (the model carries no
  joint reference), because showing an unchecked stage as clean would be the silent guess the trust
  profile exists to prevent.
- **Precision profile surfaced — Shipped (2026-08-15).** A run that declares `config.precision`
  shows its rung (`preview`/`balanced`/`high`/`convergence`/`custom`) and every mapped axis in the
  Run-summary panel, the preview status line and each capture sidecar. A `custom` rung says which
  control overrode the profile; a `representation` axis is labelled REPRESENTATION ONLY so a
  display grid can never read as improved physics.

- **Run summary + emit inspector — Shipped (2026-08-15).** A dedicated Run-summary panel replaces
  the old Console "Run" tab: grouped provenance/tallies/analytic gaps/inference counters, each row
  carrying its honesty label (predictive mode flagged; the only Studio-computed numbers are a
  labelled binomial standard error and percentages). The Emits panel filters
  `trech_hook_emits.jsonl` by tag, pretty-prints payloads with disclosed display truncation, and
  jumps a played frame tag onto the timeline cursor.
- **Event deposit distribution in Run summary (2026-11-09).** When a run's scores carry
  `system_event_edep_zero_fraction`, [`run_summary.py`](../../../studio/trech_studio/run_summary.py) adds a
  section that reads mean ± engine stderr, stddev, min/max, zero-deposit fraction and (only when
  `system_event_edep_shape_defined`) skewness/excess kurtosis verbatim; an undefined shape is a
  warned "not defined" row. Older runs show no section.
- **Geometry resolution in Run summary (2026-11-09).** When provenance carries a
  `geometry_resolution` block, [`run_summary.py`](../../../studio/trech_studio/run_summary.py) adds a
  warned section: non-zero substitution counts, then one row per engine-recorded issue
  (`requested → resolved`, reason as the note) plus a caveat that results describe what Geant4 built.
  Runs whose geometry resolved as declared show no section. The deposit section now reads
  `system_event_edep_shape_defined` from scores or `run_end` provenance.
- **Event multiplicity in Run summary and Outliner geometry marks (2026-11-10).** When scores
  carry `system_event_secondaries_zero_fraction`, [`run_summary.py`](../../../studio/trech_studio/run_summary.py)
  adds an "Event multiplicity" section (mean ± engine stderr, stddev, min/max secondaries,
  zero-secondary fraction, dispersion index only when non-null, skewness/kurtosis only when
  defined, mean/min/max track length) read verbatim; older runs show no section.
  `geometry_resolution_marks(result)` turns the provenance `geometry_resolution` issues into
  `(kind, name)` → lines (`("volume", name)`, `("world", "")`, `("medium", "")`), and
  `MainWindow.open_output_dir` hands them to `Outliner.set_resolution_marks`, which appends
  `⚠ engine substituted` (warn colour, `engine:` tooltip lines) to matching declared nodes. The
  tree still shows the declared scene; the next `set_scene` (including an applied draft) clears
  the marks, and a skipped volume absent from the declared tree, or the medium box, is reported
  only in Run summary. Tests: `test_run_summary_reads_event_multiplicity_verbatim`,
  `test_outliner_marks_engine_geometry_substitutions`.
- **Geometry overlaps in Run summary and Outliner (2026-11-10).** Engine `overlap` issues appear in
  the Geometry resolution section as `overlaps <sibling> by ≥ d mm` / `protrudes from <mother> by
  ≥ d mm` (reason as the note), and a separate "Geometry overlap check" section reads
  `geometry_overlap_check` verbatim (result, volumes/pairs checked, samples per volume, tolerance;
  a clean result is not warned). `geometry_resolution_marks` marks both volumes of a sibling
  overlap and only the protruding volume of a protrusion. Test:
  `test_run_summary_shows_engine_overlap_check`.
- **Bundle validation checks in Run summary (2026-11-09).** [`bundle_checks.py`](../../../studio/trech_studio/bundle_checks.py)
  finds the scenario named by the run's provenance `cli_args` (absolute, or relative to the repo or
  an output-folder ancestor), reads its `authoring.validation` through `trech inspect` with the
  recorded `--param` values (`ScenarioInspection.validation`) and grades the recorded outputs with
  the validation suite's own `declarative.py` (installed `trech_validation`, else the checkout copy
  loaded by file path) — no second copy of the rules. Output and family checks show pass/FAIL with
  field/aggregate/actual/op/expected; `family_sweeps` are listed as not graded for one run. Missing
  engine, provenance, scenario file, companion or evaluator reads "not graded" with the reason.
  Declarations come from the current source on disk and may postdate the run.
  Tests: [`studio/tests/test_bundle_checks.py`](../../../studio/tests/test_bundle_checks.py).
