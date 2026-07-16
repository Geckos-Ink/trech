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
- [x] Camera (orbit / pan / dolly, perspective, fit-to-bounds), CPU mesh generation. Tubes now
  preserve outer/inner radii, inner-facing normals and annular end faces; spheres remain modest
  fixed-resolution meshes.
- [~] wgpu viewport: lit volumes (physics-derived colour/opacity + Fresnel specular) + ground
  grid via WGSL; the camera frames the **placed volumes** (not the whole world box) and the grid
  is a subtle plane sunk under them. Falls back to a message widget if wgpu is unavailable. TODO:
  back-to-front transparency *sorting* of translucent volumes, in-viewport MSAA, picking. (The
  offscreen capture already supersamples + downsamples for clean anti-aliased frames.)
- [~] Code editor: JS scenario editor with syntax highlighting + a Run button wired to the runner.
  TODO: LSP-less autocomplete for the `ctx.*`/config surface, inline error markers.

## Milestone 1 — view any run faithfully

- [x] `--open <output_dir>` loads scene + trajectories + emits and populates every panel
  (scene → viewport/outliner, scores → run summary, trajectories/emits → timeline playback).
- [x] Trajectory rendering: **glowing camera-facing beam ribbons** (wavelength→RGB for optical
  photons, per-particle palette otherwise; additive, `trajectory.wgsl`) so a run's photon paths
  read as a bright beam through clear glass, not thin 1-px scribbles a milky volume hides.
  **Time slider** drives a playback cursor from the engine's per-step `time_ns` (segments sorted
  by end-time → a growing beam). `render/playback.py` + `ui/timeline.py`.
  Fixed 2026-07-13: clear dielectrics now render genuinely see-through (`surface.wgsl` suppresses
  the flat fill for low-alpha media, Fresnel rim carries the shape) + a `viz_shell` hint forces a
  clear glass shell — the optics scenes were unreadable milky blocks before.
- [x] **Medium/process-exact optics playback (2026-07-15):** each segment consumes engine-emitted
  `material`, `process`, and `interaction`. Air is named in the playback/precision UI and drawn
  0.58× as wide / 0.72× as opaque as condensed media; a scatter halo is applied only when Geant4
  recorded `interaction:"scatter"`, never from a bend. Ribbon width and opacity follow sampled
  optical-track count (one photon stays tight/translucent, overlapping photons build brightness).
  Tests cover weak-vs-strong and air-vs-water paths.
- [x] Particle-frame playback: `fluid_frame` emits (metres→mm) scrubbed as **camera-facing sprite
  billboards** (world-sized from the cloud's own spacing) — the shaken glass of water previews as
  an upright body of water in the viewport (M3 upgrades sprites → a true metaball isosurface).
  Fixed 2026-07-13: `fluid_frame` is z-up but the viewport is y-up, so frames are remapped
  z-up→y-up (`playback._to_yup`) — the water stood on its side before.
- [x] Material-resolved playback: `material_frame` emits preserve engine positions in mm and
  per-particle RGBA. The water/n-pentane beaker uses 61 held (never interpolated) frames for empty
  beaker → sequential pours → intermix/separate → moving plume. When frames declare an accelerated
  `playback_time_s`, Studio retains/discloses their physical time and scale in the timeline and
  capture sidecar; it never derives the mapping. **Lava-lamp coverage landed 2026-07-16:**
  `lava_lamp.js` emits stable ordered `particle_ids` with heat/phase/density/velocity state from a
  bounded persistent solver. Its default emits 121 states over a configurable 600 s horizon;
  duration is not scenario identity. Studio replays the emitted state and never creates parcels.
  Camera fitting now unions rotation-aware apparatus bounds with particle bounds, so the real
  lamp cap/base stay visible instead of being cropped by a cloud-only fit.
- [x] Scenario-declared fused particle surfaces (**landed 2026-07-16**): `material_frame` may carry
  a labelled Gaussian `render_surface` hint. Lava frames use it to turn unchanged parcel centres
  into an interpolated marching-tetrahedra mesh, depth-tested and shaded by Studio's existing
  WGSL surface pipeline. Classic TRECH consumes the same contract with PyVista contouring. An
  eight-frame GPU-resource LRU keeps scrubbing bounded; frames without the hint still use sprites.
  Capture/preview precision reports disclose grid spacing, sigma, iso-level and the no-position-
  interpolation invariant. Remaining scaling work: move density splatting/extraction to compute
  when materially larger interactive particle fields require it.
- [x] **Simulation + representation precision (2026-07-15):** `precision.py` reports actual MC
  events, trajectory counts/caps/drops, medium/process-label coverage, binomial standard errors,
  native mean segment step, beam display strength/width/opacity, emitted frame count, raster size
  and supersampling. Preview shows it in status/console + the world inspector; headless rendering
  writes the same structured report to its provenance sidecar. Loaded-vs-recorded trajectories
  and exact segment-budget truncation are explicit rather than silently dropping render samples.
  **Extended 2026-07-16:** lava exposes spatial parcel count at fixed inventory, temporal maximum
  step, output ticks, and representation-only surface grid separately; a 480-parcel/0.2 s run
  validates aggregate convergence against the 240-parcel/0.4 s baseline. Studio reports the
  fused-surface parameters rather than presenting one ambiguous “quality” level.
- [x] Scenario browser: left-sidebar tree over `examples/` (the shipped scenarios as a test
  suite), activate to open + auto-load a prior run. `ui/scenarios.py`. (Was the M4 gallery seed.)
- [ ] Run summary panel: seed, determinism mode, physics list, primaries transmitted/uncollided,
  analytic-check deltas — straight from provenance/scores, with the honesty labels. *(Console
  Run tab shows most of this; a dedicated panel is still open.)*
- [ ] Emit inspector: filter `trech_hook_emits.jsonl` by tag, pretty-print payloads, jump a
  `fluid_frame`/`md_snapshot` tag onto the timeline.
- [x] Volume opacity/colour from `derived_optics` (**landed 2026-07-13**, `scene/appearance.py`):
  transparency from Beer–Lambert over the volume thickness, reflectivity from Fresnel(n) as a
  real specular in `surface.wgsl`, and a CIE transmission tint from the visible spectrum. Glass
  renders transparent+glossy, water transparent+matte; the tint stays neutral where the EM base
  does not resolve differential absorption (honest — water's vibrational blue is out of scope).
  Plus an authored `viz_*` render-hint channel (`RenderHint`) so scenarios can bump opacity /
  tint / hide / glow a volume for legibility, labelled as a rendering choice. The inspector shows
  the derived optics breakdown + any hint. Tests: `tests/test_appearance.py`.

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
  fit the next batch to `targetHz`; `engine/lab.py` routes `lab_round_plan` telemetry separately.
  Compatible batches now reuse one initialized Geant4 kernel, with per-batch config provenance;
  event count, seed and planner changes are live. Remaining work is wiring inspector edits and
  live snapshots/precision into the viewport, plus a restart/reinitialize handshake for
  kernel-bound geometry/beam/physics/scoring edits (currently rejected explicitly).
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
- [x] Reference GIFs (**landed 2026-07-13**): `capture_reference()` / `--reference` writes a
  compact committed GIF; the suite promotes a curated subset into `studio/tests/reference/` only
  under `--update-refs` (`TRECH_STUDIO_UPDATE_REFS=1`) so refs aren't churned every run.
  `tests/test_animation_capture.py` asserts the renderer produces *different* frames over the
  timeline (in-program animation preview) and that references stay small. **Refreshed
  2026-07-15:** all three existing GIFs were rerendered after the medium/process and precision
  work. The corrected `beaker_water_pentane.gif` covers the full sequential pour/intermix/separate/
  moving-plume timeline at 30 °C with explicitly labelled representation-only phase tints.
  **Corrected 2026-07-16:** the lava scenario covers the persistent thermofluid material-frame contract, while
  `lava_lamp.gif` and its paired classic-viewer GIF are generated from the same dedicated README
  run, not parallel motion sources. **Corrected:**
  README media comes from a dedicated typed ten-minute simulation at the default 333.15 K heater
  condition with 100 Geant4 ticks and 101 unique state frames; capture maps post-tick states 1–100
  to the 100 GIF frames over ten display seconds. The rejected seven-frame held excerpt,
  cadence-only scripted replay, and one-minute warm-up excerpt are gone; no optical flow or
  temporal interpolation replaces them. A 60 s duration-horizon comparison and a 310 K low-heater
  control validate state continuity and condition response outside the renderer. **Surface refresh
  2026-07-16:** both GIFs now merge nearby wax parcels through the shared emitted Gaussian-density
  contract; Studio's lava reference is portrait 260×360 so the new surface detail remains visible.
- [x] Capture quality (**fixed 2026-07-13**): frames render at N× (supersample) and are
  box-downsampled for anti-aliasing (removes specular sparkle on translucent glass/water); the
  GIF is built from **lossless raw frames** with `dither=none` (the old MP4→GIF path baked h264
  noise into flats, which the palette quantised into background speckle; `bayer` dithering had
  shredded the grid into dots). References land ~0.35–0.7 MiB — bigger than the earlier
  near-empty frames because the subject now actually fills the frame, still small enough to commit.

## Known scaffolds to finish (the gap, stated honestly)

- Renderer draws **physics-shaded volumes** (Beer–Lambert opacity + Fresnel specular from the
  derived optics) + a grid + **playback overlays** (coloured trajectory polylines, particle sprite
  billboards, plus scenario-declared fused material surfaces). Still missing: back-to-front
  transparency *sorting* of overlapping translucent volumes (they can composite out of order).
  Generic frames without `render_surface` remain soft camera-facing quads drawn with depth off;
  lava's declared surface is now a depth-tested isosurface. GPU compute extraction is a future
  scaling improvement, not missing correctness for the current 240/480-parcel case.
- Capture precision is machine-readable in the JSON sidecar but not yet optionally burned into
  image/video pixels; add a labelled overlay only if users need standalone media without sidecars.
- The lava-lamp macro response and parcel discretisation are illustrative. Wider measured training
  coverage and a general engine precision-profile schema are root ROADMAP items; the fused display
  surface must never be described as improving the underlying thermofluid model.
- The scene-node Inspector is **read-only**; the separate typed scenario Options panel can change
  authored run values, but arbitrary scene mutation and live-session patching remain M2.
- No `SceneModel → .js` writer yet — Studio edits `.js` text, it does not generate it (M2).
- Sphere meshes use modest fixed tessellation; adaptive screen-space tessellation/picking remains
  M1 polish. Tube/cylinder topology is now geometry-faithful.
- Lab bridge protocol is implemented but not yet wired to inspector edits (M2).
