# Engine bridge and output contracts — context and contracts

[Root principles](../../../AGENTS.md) · [Root roadmap](../../../ROADMAP.md) · [Parent](../AGENTS.md) · [Roadmap](ROADMAP.md)

Related owners: [Configuration, CLI and provenance](../../engine/core/AGENTS.md) · [JavaScript host and live lab](../../engine/runtime/AGENTS.md) · [Recorded process and scalar views](../processes/AGENTS.md).

Read the root principles and the parent handbook first; then open only the subcategory relevant to the task. Source paths and shell commands in code spans/blocks are repository-relative unless stated otherwise; Markdown links resolve from this file.

**Model artifacts:** `studio/trech_studio/engine/outputs.RunResult.model_artifacts()` selects the recorded scenario
model registry snapshot from completed scores or provenance. Run summary displays loaded/missing
entries, SHA-256, byte sizes and declared role/kind/scale, including ordinary point/cascade models.
It never reopens model paths or infers physical validity from hashes. Old loaded-name-only runs
say identities were not recorded; unknown manifest schemas remain visible as unsupported.
The optional `loaders` list records separate optics/stratifier byte snapshots and distinguishes
failed loads from intentional strict/disabled states. Disabled loaders are not warnings.

#### `studio/trech_studio/engine/` — the only code that talks to the binary

##### [`studio/trech_studio/engine/locator.py`](../../../studio/trech_studio/engine/locator.py) · [`runner.py`](../../../studio/trech_studio/engine/runner.py)

`locator.py` (`EngineLocation`, `locate_engine`) honors explicit/`TRECH_BIN` choices, then tries
newest executable builds and PATH against a bounded Geant4-free inspection-protocol probe.
It checks typed overrides, bundle sources and Studio metadata; it does not establish source/version
or every scenario/backend compatibility. Each probe is synchronous with a three-second timeout.
Relative paths are normalized at `EngineLocation` construction before subprocess cwd changes.
Missing/nonexecutable explicit choices report their path without fallback. Tests: `test_engine_locator.py`.
`runner.py` (`EngineRunner`, `RunResult`) runs `trech run` and returns the output dir.

##### [`studio/trech_studio/engine/outputs.py`](../../../studio/trech_studio/engine/outputs.py) · [`parameters.py`](../../../studio/trech_studio/engine/parameters.py) · [`lab.py`](../../../studio/trech_studio/engine/lab.py)

`outputs.py` parses an output dir into typed objects (`Trajectory`, `HookEmit`, scores/provenance).
`parameters.py` (`ScenarioInspection`, `ScenarioParameter`) asks `trech inspect` for real
`TRECH_VALUE` declarations and passes JSON-typed `--param` back on Run — **never** regex-parses
scenario source or computes physics. `lab.py` (`LabSession`) owns the real-time protocol
(`patch`/`simulate`/`snapshot`/`quit`, snapshot JSON at `lab.targetHz`, `round_plan` telemetry).

### Output contracts Studio depends on (do not silently break)

Schemas live in [`docs/output_schema.md`](../../../docs/output_schema.md). Change a field there →
update the parser in `studio/trech_studio/engine/outputs.py` and the consuming scene/render adapters in the same change.

| File | Studio consumer | What Studio uses |
| --- | --- | --- |
| `trech_viz_scene.json` | `studio/trech_studio/scene/loader.py` → `studio/trech_studio/scene/appearance.py` | world/medium, volumes (shape/pose/tags), materials, `derived_optics` (mean n + absorption/scatter lengths + visible-band `samples[]`), beams |
| `trech_viz_trajectories.jsonl` | `studio/trech_studio/engine/outputs.py` → `studio/trech_studio/render/playback.py` | sampled polylines + per-step `time_ns`, `material`, `process`, `interaction` → timeline-scrubbed beam |
| `trech_hook_emits.jsonl` | `studio/trech_studio/ui/console`, `studio/trech_studio/render/playback.py` | `fluid_frame` (m) and `material_frame` (native units) become held frames. Radii/bonds/vectors retain emitted centres and units. `grid` draws continuous class boundaries and honors `replaces_points`; disjoint `material_groups` draw separate Gaussian liquid/gas bodies. Non-mm streams hide the mm scene. Processes/capture share held clock/HUD/legend text. Moving apparatus, 3D labels, charts and mesh `vertex_rgba` still need viewport support ([rendering roadmap](../rendering/ROADMAP.md)). |
| `trech_scores.jsonl` / `trech_provenance.jsonl` | `studio/trech_studio/ui/console`, run summary, `precision.py` | tallies, determinism/seed provenance, event/trajectory counts and caps |
