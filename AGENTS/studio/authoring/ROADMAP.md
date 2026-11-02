# Scenario and process editing — roadmap

[Root principles](../../../AGENTS.md) · [Root roadmap](../../../ROADMAP.md) · [Parent](../ROADMAP.md) · [Handbook](AGENTS.md)

Maintain work in its owning branch. Dated results apply to the recorded checkout; they do not validate subsequent changes.

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
- [ ] Inspector drives the `SceneModel`: edit world size, a volume's pose/shape/material, beam
  particle/energy; changes reflect live in the viewport.
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
  current source workspace and cannot overwrite its sources/drafts. Remaining: inspector-driven
  edits, typed declarations/companions/callback source reconstruction, portable dependency
  packaging and full multi-file scenario round-trip. Named beam source identity survives
  reorder/nonprimary deletion; primary replacement, renaming/adding identities and ambiguous
  unnamed-source edits still require the original scenario. Geometry overlap/material validation and
  physical results remain the engine's responsibility; inspection alone does not validate them.

Transport export verification: full Studio pytest 176 passed, five GPU checks skipped because the
sandbox exposes no adapter. The File menu was visually checked with the fallback viewport.
A fresh refraction scene exports to an identical inspected config; its Geant4 rerun preserves
score/scene bytes and trajectory records (line ordering can vary under the existing default-MT
replay gap). Reference media was not regenerated.
