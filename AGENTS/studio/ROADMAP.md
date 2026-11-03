# Studio desktop client — roadmap

[Root principles](../../AGENTS.md) · [Root roadmap](../../ROADMAP.md) · [Parent](../ROADMAP.md) · [Handbook](AGENTS.md)

## Choose a subcategory

| Scope | Context | Work remaining |
| --- | --- | --- |
| Scenario and process editing | [AGENTS.md](authoring/AGENTS.md) | [ROADMAP.md](authoring/ROADMAP.md) |
| Preview export and native media | [AGENTS.md](capture/AGENTS.md) | [ROADMAP.md](capture/ROADMAP.md) |
| Chemistry workspace and field inspection | [AGENTS.md](chemistry/AGENTS.md) | [ROADMAP.md](chemistry/ROADMAP.md) |
| Engine bridge and output contracts | [AGENTS.md](engine/AGENTS.md) | [ROADMAP.md](engine/ROADMAP.md) |
| Recorded process and scalar views | [AGENTS.md](processes/AGENTS.md) | [ROADMAP.md](processes/ROADMAP.md) |
| Rendering, appearance and playback | [AGENTS.md](rendering/AGENTS.md) | [ROADMAP.md](rendering/ROADMAP.md) |
| Panels, run reports and resource controls | [AGENTS.md](workspace/AGENTS.md) | [ROADMAP.md](workspace/ROADMAP.md) |

Maintain work in its owning branch. Dated results apply to the recorded checkout; they do not validate subsequent changes.

## Studio desktop UI

Studio is the desktop client workstream of this shared roadmap. [Bulk-material rendering](rendering/ROADMAP.md),
[scenario bundles](../scenarios/bundles/ROADMAP.md) and [unified media](../tooling/media/ROADMAP.md)
own the shared engine/viewer items; the branches linked above retain desktop-specific delivery,
validation and M1–M4 milestones. This page retains the stack decision and M0 foundation. Later dated entries
and explicit updates qualify the original milestone snapshots. Open viewer work never authorizes
invented physics, geometry or clocks; contracts live in [AGENTS.md](AGENTS.md#studio-desktop-ui).

> ### ⭐ Studio's north star
>
> Make the multi-scale cascade **observable and editable by a human**. A user should open
> Studio, load or author a scenario, press Run, and *watch* the macroscopic answer the engine
> inferred from the Geant4 base — then reach into the scene, change it, and re-run, all without
> hand-editing JSONL. Studio succeeds when the distance between "a question about the world" and
> "a running TRECH scenario" is a few clicks, and when nothing on screen lies about what the
> engine actually computed.

### Stack decision (settled — do not relitigate without a reason here)

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

### Status legend

`[x]` done · `[~]` scaffolded (runs, minimal, has TODOs) · `[ ]` not started

### Milestone 0 — the basis (this scaffold, landed 2026-07-11)

- [x] Package skeleton (`studio/trech_studio/`), `studio/pyproject.toml`, entry point `python -m trech_studio`.
- [x] App shell: `QMainWindow` with dockable panels (viewport centre, outliner + inspector,
  code editor, console), dark theme.
- [x] Engine bridge: locator (`TRECH_BIN` / `build/**/trech`), `trech run` subprocess runner
  (QProcess, streamed stdout), real-time `trech lab` bridge (JSONL stdin ↔ snapshot stdout).
- [x] Output parsing: provenance / scores / hook-emits / viz-scene / trajectories → typed objects.
- [x] Scene model + loader (`trech_viz_scene.json` → editable `SceneModel`).
- [x] Camera (orbit / pan / dolly, perspective, fit-to-bounds), CPU mesh generation. Tubes now
  preserve outer/inner radii, inner-facing normals and annular end faces; spheres remain modest
  resolution meshes with render-detail controls.
- [~] wgpu viewport: lit volumes (physics-derived colour/opacity + Fresnel specular) + ground
  grid via WGSL; the camera frames the **placed volumes** (not the whole world box) and the grid
  is a subtle plane sunk under them. Falls back to a message widget if wgpu is unavailable. TODO:
  order-independent transparency for intersecting objects, in-viewport MSAA, picking. Object
  depth sorting and per-surface triangle sorting are implemented. (The
  offscreen capture already supersamples + downsamples for clean anti-aliased frames.)
- [~] Code editor: JS syntax highlighting, root-bound Run and local API completion for known
  `ctx.*`/config receivers, `TRECH_VALUE`, globals and direct `TRECH_CONFIG` object keys.
  Ctrl+Space requests suggestions; Enter/Tab accepts and Escape dismisses. The static catalog
  follows executable bindings and common config keys, preserves source drafts and supports undo.
  Focused completion tests cover filtering, comment/string exclusion, keyboard acceptance,
  Unicode cursor offsets and dormant drafts. Inline error markers remain open, along with
  dynamic aliases/computed properties, regex-literal parsing, template interpolation and complete
  config-schema completion. This is local authoring assistance, not an LSP or engine validation.
