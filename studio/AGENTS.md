# TRECH Studio — AI Agent Reference (nested handbook)

Scoped instructions for agents working inside [`studio/`](.) (the desktop UI). **Read the repo-root
[`AGENTS.md`](../AGENTS.md) first** — the engine thesis, honesty discipline, determinism rules, and
output-schema contracts inherit from it and are not repeated here. This file adds only Studio-local
ownership, layering, commands, and constraints.

TRECH Studio is the **observer-scale window** onto the engine: a real-time 3D scenario editor, a
simulation viewer, and a scenario code editor in one PySide6 desktop app. It is the human end of
the multi-scale cascade — pose a macroscopic question, watch the answer the engine *inferred from
the microscopic Geant4 base*, and edit the scenario that produced it. Status: **basis/skeleton +
faithful viewer** (landed from 2026-07-11); scaffolds are labelled below and tracked in
[`ROADMAP.md`](ROADMAP.md).

> ## ⭐ What Studio is (and what it is NOT)
>
> **Studio is a client, never a second physics engine.** Every number it shows comes from a TRECH
> run (`trech run …`) or a live lab session (`trech lab`); Studio parses the documented JSONL/JSON
> outputs and draws them. It MUST **never** invent physics, re-derive a quantity the engine emits,
> or present an interpolated/eye-candy value as if it were simulated. When Studio shows something
> the engine did not emit (a placeholder mesh, a smoothed camera path, a guessed colour, a
> render-surface splat), it is a **rendering choice** and MUST be labelled as such — the same
> "physics for comparison" discipline the scenarios use.

## Read order and sources of truth

1. Root [`AGENTS.md`](../AGENTS.md) — engine thesis, honesty rules, determinism, the output
   contracts Studio consumes.
2. [`../docs/output_schema.md`](../docs/output_schema.md) — the authoritative schema for every file
   Studio parses. If a field changes there, `engine/outputs.py` / `scene/loader.py` change in the
   same commit.
3. This file — Studio layering, ownership, and local contracts.
4. [`README.md`](README.md) — user-facing overview. [`ROADMAP.md`](ROADMAP.md) — stack decision +
   milestone status (the editable source of truth for what is scaffolded vs done).
5. [`tests/reference/README.md`](tests/reference/README.md) — the committed reference-GIF policy.

## Collaboration and maintenance rules

- **Update markdowns as you go** (root directive): this `AGENTS.md` and [`ROADMAP.md`](ROADMAP.md)
  whenever Studio gains a capability. Treat "implementation" as Python source under
  [`trech_studio/`](trech_studio/).
- **Track every unfinished edge in [`ROADMAP.md`](ROADMAP.md)** in the same change — a residual,
  scaffold, missing render-precision feature, untested output family, or TODO. Never leave
  incomplete work only in a comment or handoff prose.
- **Reference GIFs are gated & committed.** `tests/reference/*.gif` are binary and regenerate only
  under `--update-refs` / `TRECH_STUDIO_UPDATE_REFS=1` for a curated id set. Never regenerate them
  on an ordinary capture run — churning them wastes repo space. See
  [`tests/reference/README.md`](tests/reference/README.md).
- **Keep the dependency surface small.** Anything heavier than PySide6 + wgpu + numpy needs a line
  in [`ROADMAP.md`](ROADMAP.md) justifying it (`pyproject.toml` optional-deps note enforces this).

## Essential principles (Studio-local)

### Keep it a viewer, not an oracle

Any pixel not backed by an engine emit is labelled a rendering choice (grid, placeholder box,
camera easing, ribbon width, metaball/necking splats). No hidden interpolation presented as data.
Positions/times/colours are engine output on the engine clock.

### Determinism is visible

Show the run's seed / determinism mode / physics list from provenance. Never let the UI imply a
`predictive`-mode result is a strict Geant4 tally.

### Graceful degradation

wgpu or the engine binary may be absent on a fresh checkout. The app MUST still launch, name what
is missing, and stay usable (code editor, output inspection). `engine/locator.py` finds the
binary; the viewport falls back to a message widget when wgpu is unavailable; capture degrades to
sidecar-only (no GPU) or a still PNG (no healthy ffmpeg).

### Cross-platform from day one

WGSL + wgpu keep the shader path portable (Vulkan on Linux/Windows, Metal on macOS via `naga`).
Do not add a platform-specific graphics branch; test paths, not `os.name`. No absolute paths — the
engine is located via `TRECH_BIN` or repo-relative `build/**/trech`.

## Critical layering contract (the one rule)

```
        TRECH engine (C++/Geant4)                 Studio (this package)
   trech run exp.js --output <dir> ─────────►  engine/  → parses outputs
   trech inspect exp.js ────────────────────►  engine/parameters.py → Options controls
   trech lab (stdin JSONL @ 60 Hz)  ◄────────►  engine/lab.py (real-time)
                                                    │
   trech_viz_scene.json ───────────────────►  scene/   → SceneModel (editable)
   trech_viz_trajectories.jsonl ───────────►  render/  → wgpu viewport
   trech_hook_emits.jsonl / scores ────────►  ui/console, ui/timeline
```

- **`ui → scene / engine / render`, never the reverse.** `render` and `scene` do **not** import
  `engine`; nothing imports `ui` except [`app.py`](trech_studio/app.py).
- **Only `engine/` talks to the binary or reads engine files.** Nothing else in Studio shells out
  or reads run outputs directly.
- **`render/` and `scene/appearance.py` are pure** (numpy only, no Qt/wgpu/engine import) so they
  are unit-testable in isolation. `render/playback.py` builds from **duck-typed** inputs (objects
  exposing `.points`/`.times_ns` or `.tag`/`.payload`), so it consumes the real `engine.outputs`
  types at runtime without importing `engine`.

## Architecture and data/control flow

`trech run` → output dir → `engine/outputs.py` parses (+ `scene/loader.py` builds the `SceneModel`,
`scene/appearance.py` derives the look) → `render/playback.py` builds a time-indexed `Playback` →
`render/renderer.py` (`SceneRenderer`) draws it in the wgpu `viewport.py` (or offscreen via
`capture.py`) → `ui/` panels bind it. The timeline drives one engine-native scalar cursor
(`time_ns`/`time_s`) that grows trajectory polylines or selects a particle/material frame; it never
invents a clock.

## Linked source tree and file reference

### App shell & orchestration

#### [`trech_studio/__main__.py`](trech_studio/__main__.py) · [`app.py`](trech_studio/app.py)

Entry point (`python -m trech_studio` / console script `trech-studio`) and the **only** importer of
`ui`. `app.py` wires the panels and owns app-level lifetime.

#### [`trech_studio/capture.py`](trech_studio/capture.py)

**Headless** counterpart of the viewport: drives the same `SceneRenderer` offscreen (via
`rendercanvas.offscreen`) to render a run's scene + playback to a still PNG and an MP4/GIF (ffmpeg),
writing a `<prefix>.json` provenance sidecar. App-level orchestrator (imports `engine`/`scene`/
`render`, never `ui`); basis of [`run_examples_suite.sh`](run_examples_suite.sh).

- **Key symbols:** `capture_run` (still + animation), `capture_reference` (CLI `--reference` — a
  compact committed GIF: ~320×220 · 10 fps · 3 s, box-downsampled supersampled frames, lossless
  raw frames with `dither=none`, **gated** on `--update-refs`), `CaptureResult`, `main`.
- **Common mistakes:** `TRECH_FFMPEG` may name an explicit encoder; a broken executable merely on
  `PATH` must not crash capture. Never write references on an ordinary run.

#### [`trech_studio/precision.py`](trech_studio/precision.py) · [`run_summary.py`](trech_studio/run_summary.py) · [`settings.py`](trech_studio/settings.py)

`precision.py` builds the multidimensional simulation-precision report (events, trajectory
counts/caps, medium/process coverage, Monte-Carlo proportion standard errors, representation
settings) shown in the UI and embedded in every capture sidecar. `run_summary.py` builds the
**honest run header** the Run-summary panel renders — determinism/seed/physics list (flagging that
a `predictive` run's inferred results are not strict Geant4 tallies), Geant4's primary tallies with
a labelled binomial sampling error, the analytic cross-check **gaps**, the learned-inference
counters (`hook_predict_count` + how many ran out of trained domain) and the hook sideband. Both
are pure (no Qt) and unit-tested headless. `settings.py` holds app settings.

### `engine/` — the only code that talks to the binary

#### [`trech_studio/engine/locator.py`](trech_studio/engine/locator.py) · [`runner.py`](trech_studio/engine/runner.py)

`locator.py` (`EngineLocation`, `locate`) finds the binary via `TRECH_BIN` then `build/**/trech`.
`runner.py` (`EngineRunner`, `RunResult`) runs `trech run` and returns the output dir.

#### [`trech_studio/engine/outputs.py`](trech_studio/engine/outputs.py) · [`parameters.py`](trech_studio/engine/parameters.py) · [`lab.py`](trech_studio/engine/lab.py)

`outputs.py` parses an output dir into typed objects (`Trajectory`, `HookEmit`, scores/provenance).
`parameters.py` (`ScenarioInspection`, `ScenarioParameter`) asks `trech inspect` for real
`TRECH_VALUE` declarations and passes JSON-typed `--param` back on Run — **never** regex-parses
scenario source or computes physics. `lab.py` (`LabSession`) owns the real-time protocol
(`patch`/`simulate`/`snapshot`/`quit`, snapshot JSON at `lab.targetHz`, `round_plan` telemetry).

### `scene/` — the editable scenario model (pure)

#### [`trech_studio/scene/model.py`](trech_studio/scene/model.py) · [`loader.py`](trech_studio/scene/loader.py)

`SceneModel` is the in-memory truth; `loader.py` builds it from `trech_viz_scene.json`. Key types:
`VolumeNode` (`path_length_mm` = the volume's own thickness), `RenderHint` (parsed `viz_*` tags).
Precedence in `SceneModel.volume_color`: physics-derived appearance → engine viz tags
(`viz_forced_white`/`viz_emitter`) → scenario `viz_*` hints (win last); `volume_surface` returns
`(reflectance R0, gloss, emissive)` for the shader.

#### [`trech_studio/scene/appearance.py`](trech_studio/scene/appearance.py)

Turns a material's engine-emitted `derived_optics` into an **honest look** (numpy only). Answers
the observer questions from the physics: transparency via Beer–Lambert `exp(-thickness/attenuation)`
(`_mu_per_mm`, `_transmittance_grid`), reflectivity via Fresnel `R0=((n-1)/(n+1))²` (`_fresnel_r`),
colour via CIE integration of visible-band transmittance **normalised so a flat spectrum is neutral**
(`_cie_xyz`, `derive_appearance`, `rgba`). Where the EM base doesn't resolve differential absorption
(pure water/glass), the honest result is colourless and the inspector says so. **Grade the gap;
don't fake the blue.**

- **Tests:** [`tests/test_appearance.py`](tests/test_appearance.py).

### `render/` — the wgpu viewport (pure rendering)

#### [`trech_studio/render/renderer.py`](trech_studio/render/renderer.py) · [`viewport.py`](trech_studio/render/viewport.py) · [`camera.py`](trech_studio/render/camera.py)

`SceneRenderer` receives a `SceneModel` + `Playback` and draws; it never reads engine files or
computes physics. `viewport.py` is the wgpu Qt canvas (falls back to a message widget if wgpu is
absent). The camera frames the **placed volumes** (not the whole world box) incl. rotated apparatus
+ particle bounds.

#### [`trech_studio/render/mesh.py`](trech_studio/render/mesh.py) · [`metaballs.py`](trech_studio/render/metaballs.py)

`mesh.py` CPU mesh generation — **true annular tube meshes** (both radii, inner walls, annular
faces) so a Geant4 beaker stays hollow, not a solid display cylinder. `metaballs.py` extracts the
interpolated marching-tetrahedra surface for the fused-lava `render_surface` contract.

- **Tests:** [`tests/test_mesh.py`](tests/test_mesh.py), [`tests/test_metaballs.py`](tests/test_metaballs.py).

#### [`trech_studio/render/playback.py`](trech_studio/render/playback.py)

Builds the time-indexed `Playback` (trajectory ribbons + fluid/material particle frames). Key
symbols: `build_playback`, `build_trajectory_playback`, `build_material_frame_playback`,
`build_particle_playback`, `count_at`, `frame_count`, and the **z-up→y-up remap** `_to_yup` /
`_surface_to_yup` (fluid clouds are z-up but the viewport is y-up — without this the shaken glass
lies on its side). Air is labelled/thinner; scatter emphasis requires a recorded `scatter` process.

- **Common mistakes:** don't emphasise a bend as scattering; don't apply the render-surface mode to
  frames that didn't request it, and never let necking/surface splats move centres or join graph
  components (representation-only, identical semantics to classic `trech-viz`).
- **Tests:** [`tests/test_playback.py`](tests/test_playback.py).

#### [`trech_studio/render/shaders/`](trech_studio/render/shaders/)

WGSL shaders: [`surface.wgsl`](trech_studio/render/shaders/surface.wgsl) (Fresnel specular +
grazing-angle rim; suppresses flat fill for low-alpha media so beams read through clear glass),
[`trajectory.wgsl`](trech_studio/render/shaders/trajectory.wgsl) (additive wavelength-coloured beam
ribbons), [`particles.wgsl`](trech_studio/render/shaders/particles.wgsl) (camera-facing sprite
billboards), [`lines.wgsl`](trech_studio/render/shaders/lines.wgsl).

### `ui/` — PySide6 panels (glue only; no physics, no direct engine IO)

#### [`trech_studio/ui/main_window.py`](trech_studio/ui/main_window.py) + panels

[`outliner.py`](trech_studio/ui/outliner.py), [`inspector.py`](trech_studio/ui/inspector.py),
[`code_editor.py`](trech_studio/ui/code_editor.py) (JS editor + Run), [`console.py`](trech_studio/ui/console.py)
(log stream only), [`run_summary.py`](trech_studio/ui/run_summary.py) (sectioned run header from
`../run_summary.py`), [`emits.py`](trech_studio/ui/emits.py) (tag-filtered hook-emit browser;
payload arrays are truncated for **display** with a note, and "Show on timeline" maps the n-th emit
of the played tag to the n-th emitted frame's own time — the timeline stays the only clock),
[`scenario_options.py`](trech_studio/ui/scenario_options.py) (typed controls from `trech inspect`),
[`scenarios.py`](trech_studio/ui/scenarios.py) (filesystem tree rooted at `../examples/`),
[`timeline.py`](trech_studio/ui/timeline.py) (the one scalar cursor; follows an emitted accelerated
`playback_time_s` only when `physical_time_s` is retained, showing both clocks), and
[`theme.py`](trech_studio/ui/theme.py).

- **Tests:** [`tests/test_ui_panels.py`](tests/test_ui_panels.py) (browser, typed options,
  timeline scrub/`set_cursor` rejection, run-summary sections/labels, emit filtering + frame jump).

## Material appearance & render hints

Studio's default already reads optics well (glowing beam ribbons, see-through dielectrics), so the
authored `viz_*` tags are the **"forced parameters, easy to disable"** emphasis channel — applied
*over* the physics look and labelled a rendering choice (the inspector shows them as authored
overrides). Parsed by `scene.model.RenderHint`:

| tag | effect |
| --- | --- |
| `viz_hidden` | do not draw the volume |
| `viz_solid` | force an opaque body (alpha ~1) |
| `viz_shell` / `viz_wireframe` | force a clear glass **shell** (edges/Fresnel only) so contents read through |
| `viz_emissive` / `viz_glow` | self-lit (skips shading) |
| `viz_opacity=<0..1>` | force display alpha |
| `viz_color=<#rgb\|#rrggbb\|r,g,b>` | replace the base colour |
| `viz_tint=<colour>` | multiply the derived colour by a tint |

## Output contracts Studio depends on (do not silently break)

Schemas live in [`../docs/output_schema.md`](../docs/output_schema.md). Change a field there →
update the parser here in the same change.

| File | Studio consumer | What Studio uses |
| --- | --- | --- |
| `trech_viz_scene.json` | `scene/loader.py` → `scene/appearance.py` | world/medium, volumes (shape/pose/tags), materials, `derived_optics` (mean n + absorption/scatter lengths + visible-band `samples[]`), beams |
| `trech_viz_trajectories.jsonl` | `engine/outputs.py` → `render/playback.py` | sampled polylines + per-step `time_ns`, `material`, `process`, `interaction` → timeline-scrubbed beam |
| `trech_hook_emits.jsonl` | `ui/console`, `render/playback.py` | scenario emits; `fluid_frame` (m) and `material_frame` (mm + per-particle RGBA, optional `render_surface`) become scrubbable held frames |
| `trech_scores.jsonl` / `trech_provenance.jsonl` | `ui/console`, run summary, `precision.py` | tallies, determinism/seed provenance, event/trajectory counts and caps |

## Features and recurring pitfalls

- **Faithful viewer — Shipped.** Scene + physics-derived appearance + trajectory/particle/material
  playback + typed Options + timeline + headless capture + gated reference GIFs.
- **Run summary + emit inspector — Shipped (2026-08-15).** A dedicated Run-summary panel replaces
  the old Console "Run" tab: grouped provenance/tallies/analytic gaps/inference counters, each row
  carrying its honesty label (predictive mode flagged; the only Studio-computed numbers are a
  labelled binomial standard error and percentages). The Emits panel filters
  `trech_hook_emits.jsonl` by tag, pretty-prints payloads with disclosed display truncation, and
  jumps a played frame tag onto the timeline cursor.
- **Fused lava surface — Shipped (representation-only).** `render_surface` contract → Gaussian
  splat → marching-tetrahedra mesh via the same depth-tested `surface.wgsl`; disclosed in precision
  metadata; identical semantics to classic `trech-viz`.
- **Scaffolded — Known gaps:** property-driven scene editor, gizmos, and `SceneModel → .js`
  serialisation (today Studio edits `.js` text and re-runs). Generic `fluid_frame`/material frames
  without a surface contract remain soft billboards; trajectory/sprite overlays draw depth-test-off
  (legible, not occluded). Live kernel-bound geometry/beam/physics/scoring patches over `trech lab`
  are rejected until safe reinitialization lands (shared gap with the engine).
- **Pitfalls:** fluid clouds are z-up (remap via `_to_yup`); the hook-emit file is append-mode
  (clean `--output` between reruns or frames are stale — root pitfall); never let render-surface
  splats alter centres or join components; never regenerate reference GIFs on an ordinary run.

## Interface, build, and test

- **Panels/interfaces** are owned as listed in the `ui/` source map above; the engine boundary is
  owned entirely by `engine/`.
- **Run / develop:**

```bash
cd studio
python -m venv .venv && source .venv/bin/activate
pip install -e .            # PySide6 + wgpu + numpy
python -m trech_studio      # or: trech-studio
python -m trech_studio --open ../build/dev/out_viz_refraction   # view an existing run
```

  If `TRECH_BIN` is unset, the locator searches `build/**/trech`.

- **Tests** (pytest, headless): [`tests/test_appearance.py`](tests/test_appearance.py) (physics
  look), [`tests/test_mesh.py`](tests/test_mesh.py) + [`tests/test_metaballs.py`](tests/test_metaballs.py)
  (meshing), [`tests/test_playback.py`](tests/test_playback.py) (timeline/remap),
  [`tests/test_capture.py`](tests/test_capture.py) + [`tests/test_animation_capture.py`](tests/test_animation_capture.py)
  (headless render path), [`tests/test_precision.py`](tests/test_precision.py),
  [`tests/test_ui_panels.py`](tests/test_ui_panels.py). Committed reference GIFs under
  [`tests/reference/`](tests/reference/).

## Data & compatibility boundaries

- Studio owns **no canonical data** — it reads engine outputs and writes only capture artifacts
  (PNG/MP4/GIF + `.json` sidecar) and the gated `tests/reference/*.gif`.
- The parsing contract is the compatibility surface: it must track
  [`../docs/output_schema.md`](../docs/output_schema.md). A `material_frame` may declare an
  accelerated `playback_time_s` only while retaining `physical_time_s` + `time_scale`; Studio shows
  both clocks and never fabricates acceleration.

## Task start and handoff checklist

**Start:** read root [`AGENTS.md`](../AGENTS.md) + this file; confirm which layer you're in and
respect the import direction; check the output-schema field you depend on actually exists in
[`../docs/output_schema.md`](../docs/output_schema.md).

**Handoff:** update this file + [`ROADMAP.md`](ROADMAP.md) for any capability change or new
scaffold; keep parsers in lock-step with the schema; run the pytest suite; label any pixel not
backed by an emit as a rendering choice; never regenerate reference GIFs unless explicitly updating
them.
