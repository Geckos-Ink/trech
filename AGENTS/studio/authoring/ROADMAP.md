# Scenario and process editing — roadmap

[Root principles](../../../AGENTS.md) · [Root roadmap](../../../ROADMAP.md) · [Parent](../ROADMAP.md) · [Handbook](AGENTS.md)

Maintain work in its owning branch. Dated results apply to the recorded checkout; they do not validate subsequent changes.

## Priority queue

Every open item of this branch, highest priority first. The dated records below are delivery
history: the "Residual" and "Next" notes inside them are tracked here, and this queue wins
where they disagree. Keys and route steps: [priority keys](../../ROADMAP.md#priority-keys) ·
[implementation route](../../ROADMAP.md#implementation-route). When an item lands, delete it here, add a
dated record below, and queue its residuals in the same change.

- **P1** · R6 · Real-time lab loop: Inspector edits become `patch` commands to a live `trech lab` and `simulate` streams snapshots back (engine reinitialization is a runtime P1). ([detail](#milestone-2--real-time-scenario-editing))
- **P1** · R6 · Complete the `SceneModel → scenario .js` round-trip for source dependencies and volume hierarchy. ([detail](#milestone-2--real-time-scenario-editing))
- **P2** · R6 · All-scenario render parity: moving apparatus meshes, scalar colour bars, chart/text overlays, simultaneous streams and an all-family capture matrix. ([detail](#js-process-editing-and-comparison-scenarios-2026-10-30))
- **P2** · R6 · Transform gizmos (translate/rotate/scale) on the selected volume. ([detail](#milestone-2--real-time-scenario-editing))
- **P2** · R6 · Inspector extensions: nested primitive creation and reparenting, custom materials, per-field engine diagnostics, undo/redo. ([detail](#milestone-2--real-time-scenario-editing))
- **P2** · R6 · Code editor: inline error markers, dynamic aliases/computed properties, template interpolation and complete config-schema completion (from Milestone 0). ([detail](../ROADMAP.md#milestone-0--the-basis-this-scaffold-landed-2026-07-11))
- **P3** · R6 · Live authoring extensions: asynchronous inspection, draft persistence, crash recovery, atomic multi-file saves, source-content provenance, widget layout, workflow jobs, validated model/kernel hot swap. ([detail](#js-process-editing-and-comparison-scenarios-2026-10-30))

## JS process editing and comparison scenarios (2026-10-30)

- [x] Engine-inspected root/include source inventory; editor retains per-source drafts,
  rejects overwriting external changes and keeps Run tied to the root scenario. Save + apply UI
  re-inspects typed declarations, removes stale override names and reapplies `TRECH_STUDIO`
  titles, panel visibility and process descriptions without restarting Studio.
- [x] Processes displays configured model paths/scales and declared transport/training/inference
  roles. These are descriptions; actual execution/trust remains the engine's run/scale trace.
- [x] Generic material stream selector, explicit comparison step-clock units, and optional
  `show_geant4_scene:false` to hide unrelated transport probes without changing their physics.
  Precision/capture metadata reports scene visibility. NaCl and Euler-airflow comparison
  scenarios use existing frame/sphere/vector playback and normal output inspection.
- [ ] All-scenario render parity remains incomplete: moving apparatus meshes, legends/scalar colour bars, chart/text overlays and simultaneous streams need
  generic implementations plus an all-family engine/capture matrix. The stream selector
  chooses one recorded stream; it does not composite them or implement those missing families.
- [x] JS source draft guard: dirty markers cover visible and dormant root/include drafts;
  Save/Discard/Cancel protects scenario switches and window close, with Cancel as default.
  Cancel/failed Save preserves source text, playback and active jobs, including browser/Chemistry
  switch paths. Browser activation runs once per action. External changes are checked across all
  changed sources before writes; Save still affects the next run only.
- [ ] Live authoring extensions: asynchronous inspection, typed-option/Chemistry draft persistence,
  crash recovery and atomic multi-file disk saves, source-content provenance, arbitrary JS widget
  layout, workflow job execution with
  progress/cancellation and validated model/kernel hot swap. Current Save affects the next run;
  active Geant4/model workers are unchanged. Offline trainers remain outside the UI process.
- [ ] V8 is a pinned optional source/standalone probe foundation, not Studio's or TRECH's host
  backend. Upstream build, runtime/API/replay parity and performance validation remain engine work in this
  roadmap. No training or Geant4 logic moves into Studio's viewer/render layer.

Contracts: `docs/studio_authoring.md`, `docs/process_references.md`, `docs/v8.md`.
Behavioural tests: `studio/tests/test_authoring.py` (real-engine reinspection plus Qt editor/stream checks).
Source-guard verification: full pytest 106 passed, one GPU-detail check skipped because the sandbox
exposes no Metal adapter. Tests preserve dormant/visible drafts and active jobs on Cancel/failed
Save, reject conflicting external edits before writes, preserve drafts after failed target opens,
and exercise Save/Discard plus browser/Chemistry/close paths. Dirty labels and the actual guard
dialog were visually checked; no reference media was regenerated.
Earlier comparison-foundation verification passed 99/99 with local Metal access, including the
five GPU playback cases.
Fresh NaCl/airflow run captures were rendered with Studio's wgpu path and visually inspected;
quantitative comparison physics remains unvalidated as recorded in the [reference workstream](../../scenarios/references/ROADMAP.md).

## Milestone 2 — real-time scenario editing

- [x] **Typed scenario Options (2026-07-15):** `TRECH_VALUE` declarations are evaluated by the
  engine through Geant4-free `trech inspect` (never regex-parsed by Studio), mapped to grouped
  number/integer/boolean/choice/text controls in the right sidebar, preserved across compatible
  source refreshes, and sent back as validated JSON `--param` values on batch Run. Refraction,
  H2O-fluid, and CNT-fluid examples exercise sizes/levels, temperatures, source and sampling.
- [x] **Transport Inspector drafts:** world size/material, primitive box/sphere/tube/cylinder
  dimensions, volume pose/material and single/named beam particle/energy update the SceneModel,
  Outliner and viewport after lossless-writer validation. Apply is atomic on invalid values;
  callback/model-bearing or mismatched runs stay read-only. Drafts hide recorded playback and
  precision, retain original provenance/results, and never modify open JS drafts or active jobs.
  Save/export, Discard and default-Cancel protect replacement/close; failed/cancelled export keeps
  the draft. Exported scenarios must be opened/run separately. Geometry overlap/material/particle
  validity remains the engine's responsibility. Focused Inspector/export/source-guard checks pass
  35 tests, including rejected scene-less loads preserving the previous scene/run pairing;
  reference media was not regenerated.
- [x] **Beam source Inspector controls:** direction/origin, disk spot radius, divergence cone
  half-angle and fractional energy sigma use the recorded source config plus optional scene-draft
  overrides. Apply validates finite/nonzero direction, nonnegative spreads and a 0–180° cone
  before updating the scene. No-op/default omissions, reverting fields, exact untouched energy,
  spectra/polarization and named source identity survive export; invalid edits remain atomic.
  Exported sources pass real-engine inspection. These are authored settings; the viewport does
  not preview a newly simulated beam until the exported scenario is run.
  Verification (2026-11-04): full Studio pytest 240 passed, five GPU checks skipped because
  the sandbox exposes no adapter; Debug CTest 36/36 pass. A fresh run was edited through the
  actual Inspector and exported with an exact expected config. Its 24 primary birth positions
  stay in the edited perpendicular disk, directions stay within the edited cone, and energies
  vary with the retained spectrum/spread. Two serial reruns match score/scene/trajectory bytes.
  Inspector layout was visually checked; reference media and the full physics report were not
  regenerated. These checks validate source authoring/replay, not physical accuracy.
- [x] **Primitive creation and deletion (2026-11-16):** add world-level box, sphere, tube
  or cylinder primitives from World. Remove leaf volumes in the volume Inspector. Invalid
  sizes, colliding names and orphaned children are rejected before committing the draft.
  Outliner selection and the viewport follow the edited draft. The original source and recorded
  config are retained. The exported JS round-trips through real `trech inspect --strict-config`.
  A serial Geant4 run of that export recorded the replacement box with its edited dimensions
  and position. Studio pytest passed 303 tests, with five GPU tests skipped for lack of an adapter.
- [ ] Inspector extensions: nested primitive creation and reparenting, custom material
  definitions, per-field engine diagnostics, undo/redo and crash recovery. Current
  Inspector drafts require a matching, exportable transport run; callback/model-bearing scenarios
  continue through the source editor and typed Options.
- [ ] **Real-time lab loop:** inspector edits become `{"action":"patch",…}` commands to a live
  `trech lab` session; `simulate` streams snapshots back into the viewport (the 60 Hz path).
  The engine-side adaptive round planner is landed: omitted counts learn seconds/round online and
  fit the next batch to `targetHz`; `studio/trech_studio/engine/lab.py` routes `lab_round_plan` telemetry separately.
  Compatible batches now reuse one initialized Geant4 kernel, with per-batch config provenance;
  event count, seed and planner changes are live. Remaining work is wiring inspector edits and
  live snapshots/precision into the viewport, plus a restart/reinitialize handshake for
  kernel-bound geometry/beam/physics/scoring edits (currently rejected explicitly).
- [ ] Transform gizmos (translate/rotate/scale) on the selected volume.
- [ ] Complete `SceneModel → scenario .js` round-trip. **Transport foundation landed:**
  pure `scene_to_config` / `scene_to_js` plus `File → Export scene scenario…` export loaded
  transport runs using the full recorded config. Exact unchanged config and isolated geometry/
  energy edits are verified through real `trech inspect`; origin/spread, isotopes, unused
  materials, physics options and independent primary sources survive. Derived appearance is
  excluded. Export rejects missing/mismatched config, JS callbacks and external models instead
  of silently stripping them or breaking relative dependencies. The File action preserves the
  current source workspace and cannot overwrite its sources/drafts. Remaining: scene
  hierarchy authoring, typed declarations/companions/callback source reconstruction, portable dependency
  packaging and full multi-file scenario round-trip. Named beam source identity survives
  reorder/nonprimary deletion; primary replacement, renaming/adding identities and ambiguous
  unnamed-source edits still require the original scenario. Geometry overlap/material validation and
  physical results remain the engine's responsibility; inspection alone does not validate them.

Transport draft verification: full Studio pytest 226 passed, five GPU checks skipped because the
sandbox exposes no adapter. Completion/authoring focused checks also pass 42 cases after the final
keyboard polish. Inspector and completion popup captures were visually checked. A fresh serial
transport run was loaded, edited through Inspector, exported and inspected with an identical
expected config; its Geant4 rerun emits the edited volume dimensions/placement. Draft/source/job
isolation and cancellation are covered by focused tests. This verifies authoring, not physical
accuracy; reference media and the full manual physics report were not regenerated.
