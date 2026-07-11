# AGENTS.md — TRECH Studio

Guidance for agents working inside `studio/` (the desktop UI). Read the **repo-root
`AGENTS.md` first** — the engine thesis and honesty rules below inherit from it.

> ## ⭐ What Studio is (and what it is NOT)
>
> TRECH Studio is the **observer-scale window** onto the engine: a real-time 3D scenario
> editor, a simulation viewer, and a scenario code editor, in one desktop app. It is the
> human end of the multi-scale cascade — the place where a user poses a macroscopic question
> ("what does this glass of water do while I shake it?"), watches the answer that the engine
> *inferred from the microscopic Geant4 base*, and edits the scenario that produced it.
>
> **Studio is a client, never a second physics engine.** Every number it shows comes from a
> TRECH run (`trech run …`) or a live lab session (`trech lab`); Studio parses the documented
> JSONL/JSON outputs and draws them. It must **never** invent physics, re-derive a quantity the
> engine emits, or present an interpolated/eye-candy value as if it were simulated. When Studio
> shows something the engine did not emit (a placeholder mesh, a smoothed camera path, a
> guessed colour), it is a *rendering choice* and must be labelled as such — the same
> "physics for comparison" discipline the scenarios use.

## The stack (decided)

- **UI:** PySide6 (Qt 6) — dockable panels, outliner, inspector, industry-standard editor shell.
- **3D:** `wgpu-py` (WebGPU) — WGSL shaders compiled by `naga` to **Vulkan on Linux/Windows,
  Metal on macOS** automatically. No OpenGL (deprecated on macOS), no hand-managed MoltenVK.
- **Math:** `numpy` (view/projection/model matrices, mesh generation). No extra math dep.
- Rationale and the Godot/GDExtension alternative we deliberately did *not* take: see
  `ROADMAP.md` → "Stack decision".

Keep the dependency surface small. Anything heavier than PySide6 + wgpu + numpy needs a line
in `ROADMAP.md` justifying it.

## Architecture — the one rule

```
        TRECH engine (C++/Geant4)                 Studio (this package)
   trech run exp.js --output <dir> ─────────►  engine/  → parses outputs
   trech lab (stdin JSONL @ 60 Hz)  ◄────────►  engine/lab.py (real-time)
                                                    │
   trech_viz_scene.json ───────────────────►  scene/   → SceneModel (editable)
   trech_viz_trajectories.jsonl ───────────►  render/  → wgpu viewport
   trech_hook_emits.jsonl / scores ────────►  ui/console, ui/timeline
```

- `trech_studio/engine/` — the **only** code that talks to the engine binary. Locator,
  subprocess runner (`trech run`), real-time lab bridge (`trech lab`), output-dir parser.
  Nothing else in Studio shells out or reads engine files directly.
- `trech_studio/scene/` — the editable scenario model. `SceneModel` is the in-memory truth;
  `loader.py` builds it from a `trech_viz_scene.json`. Serialising a `SceneModel` back to a
  runnable `.js` scenario is a **standing goal, not yet done** (see ROADMAP): today Studio
  edits the `.js` text directly and re-runs.
- `trech_studio/render/` — the wgpu viewport. Camera, CPU mesh generation, pipelines, WGSL
  shaders. Pure rendering: it receives a `SceneModel` + trajectories and draws; it never
  reads engine files or computes physics.
- `trech_studio/ui/` — PySide6 panels (main window, outliner, inspector, code editor,
  console). Glue only; no physics, no direct file IO into engine outputs.

Respect the layering: `ui → scene/engine/render`, never the reverse; `render` and `scene`
do not import `engine`; nothing imports `ui` except `app.py`.

## Output contracts Studio depends on (do not silently break)

Studio reads these engine outputs — their schemas live in `docs/output_schema.md` at the repo
root. If you change a field there, update the parser in `engine/outputs.py` / `scene/loader.py`
in the same change:

| File | Studio consumer | What Studio uses |
| --- | --- | --- |
| `trech_viz_scene.json` | `scene/loader.py` | world/medium, volumes (shape, pose, tags), materials, `derived_optics` (colour/opacity), beams |
| `trech_viz_trajectories.jsonl` | `render/` (planned) | sampled polylines + per-step time for playback |
| `trech_hook_emits.jsonl` | `ui/console`, timeline | scenario sideband emits (`fluid_frame`, `md_snapshot`, …) |
| `trech_scores.jsonl` / `trech_provenance.jsonl` | `ui/console`, run summary | run-level tallies, determinism/seed provenance |

The **real-time** path is `trech lab`: a persistent process reading `{"action":…}` JSONL on
stdin (`patch`/`simulate`/`snapshot`/`quit`) and writing snapshot JSON on stdout at
`lab.targetHz`. `engine/lab.py` owns that protocol; bootstrap config lives at
`examples/lab/realtime_lab_bootstrap.json` in the repo.

## Directives for agents (Studio-specific)

- **Keep it a viewer, not an oracle.** Any pixel that isn't backed by an engine emit is
  labelled a rendering choice (grid, placeholder box, camera easing). No hidden interpolation
  presented as data.
- **Determinism is visible.** Show the run's seed / determinism mode / physics list from
  provenance. Never let the UI imply a predictive-mode result is a strict Geant4 tally.
- **Update markdowns as you go** (root directive): this `AGENTS.md`, `ROADMAP.md`, and the
  root references when Studio gains a capability. Treat "implementation" as Python source under
  `trech_studio/`.
- **Graceful degradation.** wgpu or the engine binary may be missing on a fresh checkout. The
  app must still launch, name what's missing, and stay usable (code editor, output inspection).
  `engine/locator.py` finds the binary; the viewport falls back to a message if wgpu is absent.
- **Cross-platform from day one.** WGSL + wgpu keep the shader path portable; do not add a
  platform-specific graphics branch. Test paths, not `os.name`.
- **No absolute paths in-repo** (root directive). Locate the engine via `TRECH_BIN` or the
  repo-relative `build/**/trech`.

## Run / develop

```bash
cd studio
python -m venv .venv && source .venv/bin/activate
pip install -e .            # PySide6 + wgpu + numpy
python -m trech_studio      # launch the app
# or, once installed:
trech-studio
```

Point Studio at an existing run to view it:

```bash
python -m trech_studio --open build/dev/out_viz_refraction
```

If `TRECH_BIN` is unset, the locator searches `build/**/trech` (currently `build/dev/trech`).

## Honest status

This is the **basis / skeleton** (landed 2026-07-11). What is real vs. scaffolded is tracked
per-module in `ROADMAP.md`. In short: the app shell, panel layout, engine locator/runner/lab
bridge, output parsing, scene model + loader, camera, and CPU mesh generation are implemented;
the wgpu pipeline draws lit volumes + a grid; trajectory playback, the property-driven scene
editor, gizmos, and `SceneModel → .js` serialisation are scaffolded with explicit TODOs.
Don't describe a scaffold as finished — grade the gap, like the engine does.
