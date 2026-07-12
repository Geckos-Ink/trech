# ROADMAP — TRECH Studio

Short-term execution plan for the desktop UI. Keep it updated as items land or are re-scoped.
The engine's own roadmap is the repo-root `ROADMAP.md`; this file only tracks Studio.

> ## ⭐ Studio's north star
>
> Make the multi-scale cascade **observable and editable by a human**. A user should open
> Studio, load or author a scenario, press Run, and *watch* the macroscopic answer the engine
> inferred from the Geant4 base — then reach into the scene, change it, and re-run, all without
> hand-editing JSONL. Studio succeeds when the distance between "a question about the world" and
> "a running TRECH scenario" is a few clicks, and when nothing on screen lies about what the
> engine actually computed.

## Stack decision (settled — do not relitigate without a reason here)

| Concern | Choice | Why |
| --- | --- | --- |
| 3D API | **wgpu-py (WebGPU)** | WGSL → Vulkan (Lin/Win) / Metal (mac) via `naga`, automatically. OpenGL is deprecated on macOS; raw Vulkan means hand-managing MoltenVK. |
| Shading language | **WGSL** | One shader source, cross-compiled to SPIR-V / MSL. Compute shaders available for future particle/fluid overlays. |
| UI toolkit | **PySide6 (Qt 6)** | Industry-standard dockable editor shell (outliner/inspector/viewport), native `wgpu` Qt canvas integration. |
| Math | **numpy** | Matrices + mesh gen without pulling a math lib. |

**Alternative considered and declined:** Godot 4 + GDExtension (`godot-python`). Batteries-included
(scene graph, gizmos, UI all free) and Vulkan-native, but it makes Studio a Godot app embedding
Python rather than a Python app — heavier to ship alongside the engine, and it couples our UI to
Godot's release cadence. Revisit only if hand-writing the render/gizmo layer becomes the bottleneck.

## Status legend

`[x]` done · `[~]` scaffolded (runs, minimal, has TODOs) · `[ ]` not started

## Milestone 0 — the basis (this scaffold, landed 2026-07-11)

- [x] Package skeleton (`trech_studio/`), `pyproject.toml`, entry point `python -m trech_studio`.
- [x] App shell: `QMainWindow` with dockable panels (viewport centre, outliner + inspector,
  code editor, console), dark theme.
- [x] Engine bridge: locator (`TRECH_BIN` / `build/**/trech`), `trech run` subprocess runner
  (QProcess, streamed stdout), real-time `trech lab` bridge (JSONL stdin ↔ snapshot stdout).
- [x] Output parsing: provenance / scores / hook-emits / viz-scene / trajectories → typed objects.
- [x] Scene model + loader (`trech_viz_scene.json` → editable `SceneModel`).
- [x] Camera (orbit / pan / dolly, perspective, fit-to-bounds), CPU mesh generation (box/grid;
  sphere/cylinder/tube minimal).
- [~] wgpu viewport: lit volumes + ground grid via WGSL; falls back to a message widget if wgpu
  is unavailable. TODO: transparency sort from `derived_optics` opacity, MSAA, picking.
- [~] Code editor: JS scenario editor with syntax highlighting + a Run button wired to the runner.
  TODO: LSP-less autocomplete for the `ctx.*`/config surface, inline error markers.

## Milestone 1 — view any run faithfully

- [x] `--open <output_dir>` loads scene + trajectories + emits and populates every panel
  (scene → viewport/outliner, scores → run summary, trajectories/emits → timeline playback).
- [x] Trajectory rendering: coloured polylines (wavelength→RGB for optical photons, per-particle
  palette otherwise); **time slider** driving a playback cursor from the engine's per-step
  `time_ns` (segments sorted by end-time → a growing beam). `render/playback.py` + `ui/timeline.py`.
- [x] Particle-frame playback: `fluid_frame` emits (metres→mm) scrubbed as a point cloud — the
  shaken glass of water previews in the viewport (M3 upgrades points → metaballs).
- [x] Scenario browser: left-sidebar tree over `examples/` (the shipped scenarios as a test
  suite), activate to open + auto-load a prior run. `ui/scenarios.py`. (Was the M4 gallery seed.)
- [ ] Run summary panel: seed, determinism mode, physics list, primaries transmitted/uncollided,
  analytic-check deltas — straight from provenance/scores, with the honesty labels. *(Console
  Run tab shows most of this; a dedicated panel is still open.)*
- [ ] Emit inspector: filter `trech_hook_emits.jsonl` by tag, pretty-print payloads, jump a
  `fluid_frame`/`md_snapshot` tag onto the timeline.
- [ ] Volume opacity/colour from `derived_optics` (glass translucent, water tinted) — the same
  channel `tools/viz/` uses, so Studio and the PyVista viewer agree.

## Milestone 2 — real-time scenario editing

- [ ] Inspector drives the `SceneModel`: edit world size, a volume's pose/shape/material, beam
  particle/energy; changes reflect live in the viewport.
- [ ] **Real-time lab loop:** inspector edits become `{"action":"patch",…}` commands to a live
  `trech lab` session; `simulate` streams snapshots back into the viewport (the 60 Hz path).
- [ ] Transform gizmos (translate/rotate/scale) on the selected volume.
- [ ] `SceneModel → scenario .js` serialisation — the round-trip that lets the visual editor
  emit a runnable, reviewable scenario (mirrors `scene/loader.py` in reverse). **Core deliverable.**

## Milestone 3 — the cascade, made legible

- [ ] Scale ladder widget: show `__cascade` stages (nano→micro→macro), `seedKeys`, and which
  Geant4 ambient facts seeded the run — make the doctrine visible, not buried in JSON.
- [ ] Overlay inferred macro quantities (rest density, cohesion, viscosity for the glass-of-water)
  next to their measured nano base, with the gap-to-truth shown (honesty rule).
- [ ] Compute-shader particle/fluid overlay for `fluid_frame` emits (WGSL compute → instanced
  points/metaballs) so a shaken glass renders in the viewport, not only in the offline MP4.

## Milestone 4 — authoring & polish

- [~] Scenario gallery: browse `examples/**/*.js` (landed as the `Scenarios` tree in M1);
  remaining — thumbnails from a cached scene, search/filter.
- [ ] Material editor tied to the composition surface (element/SMILES) + PubChem lookups.
- [ ] Undo/redo on the scene model; project/session persistence.
- [x] Screenshot / turntable export: `trech_studio/capture.py` renders a run offscreen to a
  still PNG + MP4/GIF (turntable, timeline playback), and `run_examples_suite.sh` runs the
  example scenarios + captures each into a `manifest.json`/`index.md` for AI/human validation.

## Known scaffolds to finish (the gap, stated honestly)

- Renderer draws opaque boxes + a grid + **playback overlays** (coloured trajectory polylines,
  particle point clouds). Still missing: volume transparency sort (M1), and particle frames are
  1-px points drawn with the depth test off — a metaball/compute overlay + proper occlusion is M3.
- Inspector is **read-only**; editing does not yet mutate the model or the live session (M2).
- No `SceneModel → .js` writer yet — Studio edits `.js` text, it does not generate it (M2).
- Sphere/cylinder/tube meshes are minimal placeholders; only box is production-quality (M1).
- Lab bridge protocol is implemented but not yet wired to inspector edits (M2).
