# Studio desktop client — context and contracts

[Root principles](../../AGENTS.md) · [Root roadmap](../../ROADMAP.md) · [Parent](../AGENTS.md) · [Roadmap](ROADMAP.md)

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

Read the root principles and the parent handbook first; then open only the subcategory relevant to the task. Source paths and shell commands in code spans/blocks are repository-relative unless stated otherwise; Markdown links resolve from this file.

- **Keep Studio dependencies small.** Anything heavier than PySide6 + wgpu + numpy needs a
  justification in the [Studio roadmap](ROADMAP.md), as required by
  [`studio/pyproject.toml`](../../studio/pyproject.toml).

### Desktop UI — [`studio/`](../../studio)

The PySide6 + wgpu client uses the same engine and project contracts. Its
[shared viewer and layering contracts](#studio-desktop-ui) apply across the client. Source maps
are split between [panels](workspace/AGENTS.md), [engine IO](engine/AGENTS.md),
[rendering](rendering/AGENTS.md), [authoring](authoring/AGENTS.md) and [capture](capture/AGENTS.md);
[desktop milestones and remaining gaps](ROADMAP.md#studio-desktop-ui) belong to the paired roadmap.

## Studio desktop UI

The desktop client is part of the same TRECH project. The [root principles](../../AGENTS.md)
and [project maintenance rules](../project/AGENTS.md#collaboration-and-maintenance-rules) apply;
this handbook records shared viewer contracts and development commands. The [desktop workstream](ROADMAP.md#studio-desktop-ui) tracks its milestones.
Module paths in the flow diagram are relative to `studio/trech_studio/`; source links and
other paths are relative to the repository root. Commands that start with `cd studio` run there.

TRECH Studio is the **observer-scale window** onto the engine: a real-time 3D scenario editor, a
simulation viewer, and a scenario code editor in one PySide6 desktop app. It is the human end of
the multi-scale cascade — pose a macroscopic question, watch the answer the engine *inferred from
the microscopic Geant4 base*, and edit the scenario that produced it. Status: **basis/skeleton +
faithful viewer** (landed from 2026-07-11); scaffolds are labelled in
[features and recurring pitfalls](#features-and-recurring-pitfalls) and tracked in
[`ROADMAP.md`](ROADMAP.md#studio-desktop-ui).

> ### ⭐ What Studio is (and what it is NOT)
>
> **Studio is a client, never a second physics engine.** Every number it shows comes from a TRECH
> run (`trech run …`) or a live lab session (`trech lab`); Studio parses the documented JSONL/JSON
> outputs and draws them. It MUST **never** invent physics, re-derive a quantity the engine emits,
> or present an interpolated/eye-candy value as if it were simulated. When Studio shows something
> the engine did not emit (a placeholder mesh, a smoothed camera path, a guessed colour, a
> render-surface splat), it is a **rendering choice** and MUST be labelled as such — the same
> "physics for comparison" discipline the scenarios use.

### Viewer principles

#### Keep it a viewer, not an oracle

Any pixel not backed by an engine emit is labelled a rendering choice (grid, placeholder box,
camera easing, ribbon width, metaball/necking splats). No hidden interpolation presented as data.
Positions/times/colours are engine output on the engine clock.

#### Determinism is visible

Show the run's seed / determinism mode / physics list from provenance. Never let the UI imply a
`predictive`-mode result is a strict Geant4 tally.

#### Graceful degradation

wgpu or the engine binary may be absent on a fresh checkout. The app MUST still launch, name what
is missing, and stay usable (code editor, output inspection). `studio/trech_studio/engine/locator.py` finds the
binary; the viewport falls back to a message widget when wgpu is unavailable; capture degrades to
sidecar-only (no GPU) or a still PNG (no healthy ffmpeg).

#### Cross-platform from day one

WGSL + wgpu keep the shader path portable (Vulkan on Linux/Windows, Metal on macOS via `naga`).
Do not add a platform-specific graphics branch; test paths, not `os.name`. No absolute paths — the
engine is located via `TRECH_BIN` or repo-relative `build/**/trech`.

### Critical layering contract (the one rule)

```
        TRECH engine (C++/Geant4)                 Studio (desktop client)
   trech run exp.js --output <dir> ─────────►  engine/  → parses outputs
   trech inspect exp.js ────────────────────►  engine/parameters.py → Options controls
   trech lab (stdin JSONL @ 60 Hz)  ◄────────►  engine/lab.py (real-time)
                                                    │
   trech_viz_scene.json ───────────────────►  scene/   → SceneModel (editable)
   trech_viz_trajectories.jsonl ───────────►  render/  → wgpu viewport
   trech_hook_emits.jsonl / scores ────────►  ui/console, ui/timeline
```

- **`ui → scene / engine / render`, never the reverse.** `render` and `scene` do **not** import
  `engine`; nothing imports `ui` except [`app.py`](../../studio/trech_studio/app.py).
- **Only `studio/trech_studio/engine/` talks to the binary.** Run-file parsing belongs to
  `studio/trech_studio/engine/outputs.py`, with the existing scene-file adapter in
  `studio/trech_studio/scene/loader.py` reading `trech_viz_scene.json`. UI and rendering layers
  consume parsed data; they must not read run files or launch engine processes directly.
- **Rendering data/geometry helpers and `studio/trech_studio/scene/appearance.py` are pure** (numpy only, no
  Qt/wgpu/engine import) so they are unit-testable in isolation. The renderer/viewport own
  GPU/Qt integration; this purity rule applies to helpers such as playback, materials and meshes.
  `studio/trech_studio/render/playback.py` builds from **duck-typed** inputs (objects
  exposing `.points`/`.times_ns` or `.tag`/`.payload`), so it consumes the real `engine.outputs`
  types at runtime without importing `engine`.

### Architecture and data/control flow

`trech run` → output dir → `studio/trech_studio/engine/outputs.py` parses (+ `studio/trech_studio/scene/loader.py` builds the `SceneModel`,
`studio/trech_studio/scene/appearance.py` derives the look) → `studio/trech_studio/render/playback.py` builds a time-indexed `Playback` →
`studio/trech_studio/render/renderer.py` (`SceneRenderer`) draws it in the wgpu `viewport.py` (or offscreen via
`capture.py`) → `studio/trech_studio/ui/` panels bind it. The timeline drives one engine-native scalar cursor
(`time_ns`/`time_s`) that grows trajectory polylines or selects a particle/material frame; it never
invents a clock.

### Linked source tree and file reference

#### App shell & orchestration

##### [`studio/trech_studio/__main__.py`](../../studio/trech_studio/__main__.py) · [`app.py`](../../studio/trech_studio/app.py)

Entry point (`python -m trech_studio` / console script `trech-studio`) and the **only** importer of
`ui`. `app.py` wires the panels and owns app-level lifetime.

### Features and recurring pitfalls

- **Faithful viewer — Shipped.** Scene + physics-derived appearance + trajectory/particle/material
  playback + typed Options + timeline + headless capture + gated reference GIFs.

- **Scaffolded — Known gaps:** property-driven scene editor, gizmos, and `SceneModel → .js`
  serialisation (today Studio edits `.js` text and re-runs). Generic `fluid_frame`/material frames
  without a surface contract remain soft billboards; trajectory/sprite overlays draw depth-test-off
  (legible, not occluded). Live kernel-bound geometry/beam/physics/scoring patches over `trech lab`
  are rejected until safe reinitialization lands (shared gap with the engine).
- **Pitfalls:** fluid clouds are z-up (remap via `_to_yup`); the hook-emit file is append-mode
  (clean `--output` between reruns or frames are stale — shared output-directory pitfall); never let render-surface
  splats alter centres or join components; never regenerate reference GIFs on an ordinary run.

### Interface, build, and test

- **Panels/interfaces** follow the [workspace source map](workspace/AGENTS.md);
  `studio/trech_studio/engine/` owns the [engine boundary](engine/AGENTS.md) entirely.
- **Run / develop:**

```bash
cd studio
python -m venv .venv && source .venv/bin/activate
pip install -e .            # PySide6 + wgpu + numpy
python -m trech_studio      # or: trech-studio
python -m trech_studio --open ../build/dev/out_viz_refraction   # view an existing run
```

  If `TRECH_BIN` is unset, the locator tries newest executable builds, then PATH, with a bounded
  inspection-protocol check before selection.

- **Tests** (pytest, headless): [`studio/tests/test_appearance.py`](../../studio/tests/test_appearance.py) (physics
  look), [`studio/tests/test_mesh.py`](../../studio/tests/test_mesh.py) + [`studio/tests/test_metaballs.py`](../../studio/tests/test_metaballs.py)
  (meshing), [`studio/tests/test_playback.py`](../../studio/tests/test_playback.py) (timeline/remap),
  [`studio/tests/test_cascade_ladder.py`](../../studio/tests/test_cascade_ladder.py) (scale ladder),
  [`studio/tests/test_capture.py`](../../studio/tests/test_capture.py) + [`studio/tests/test_animation_capture.py`](../../studio/tests/test_animation_capture.py)
  (headless render path), [`studio/tests/test_precision.py`](../../studio/tests/test_precision.py),
  [`studio/tests/test_ui_panels.py`](../../studio/tests/test_ui_panels.py). Committed reference GIFs under
  [`studio/tests/reference/`](../../studio/tests/reference).

### Data & compatibility boundaries

- Studio owns **no canonical physics data** — engine outputs remain the source of recorded
  results. Studio edits authored JS/scene drafts and exports captures (PNG/MP4/GIF + `.json`
  sidecars) plus gated `studio/tests/reference/*.gif`; it does not turn display choices into physics facts.
- The parsing contract is the compatibility surface: it must track
  [`docs/output_schema.md`](../../docs/output_schema.md). A `material_frame` may declare an
  accelerated `playback_time_s` only while retaining `physical_time_s` + `time_scale`; Studio shows
  both clocks and never fabricates acceleration.
