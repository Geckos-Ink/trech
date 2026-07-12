# TRECH Studio

A desktop app for TRECH: a **real-time 3D scenario editor**, a **simulation viewer**, and a
**scenario code editor** in one window. Studio is the observer-scale window onto the engine —
it runs scenarios, watches the macroscopic answers the engine inferred from the Geant4
particle/nano base, and lets you edit the scene that produced them.

> Studio is a **client, not a second physics engine.** Everything it draws comes from a real
> TRECH run or a live `trech lab` session, parsed from the documented outputs. See
> [`AGENTS.md`](AGENTS.md) for the honesty rules and [`ROADMAP.md`](ROADMAP.md) for status.

## Stack

- **PySide6 (Qt 6)** — dockable editor shell (viewport, outliner, inspector, console, code editor)
- **wgpu-py (WebGPU)** — WGSL shaders → **Vulkan** on Linux/Windows, **Metal** on macOS, via `naga`
- **numpy** — camera + mesh math

No OpenGL (deprecated on macOS), no hand-managed MoltenVK, no per-platform graphics branch.

## Install & run

```bash
cd studio
python -m venv .venv && source .venv/bin/activate
pip install -e .
python -m trech_studio            # launch (or: trech-studio)
```

Open an existing run directly:

```bash
python -m trech_studio --open ../build/dev/out_viz_refraction
```

Studio finds the engine binary via `$TRECH_BIN`, else the repo-relative `build/**/trech`
(currently `build/dev/trech`). If wgpu can't initialise a GPU, the app still launches with a
message in place of the viewport so you can edit code and inspect outputs.

## Layout

```
trech_studio/
  __main__.py        # entry: python -m trech_studio
  app.py             # QApplication + main window bootstrap
  capture.py         # headless offscreen capture: run -> PNG + MP4/GIF (python -m trech_studio.capture)
  settings.py        # engine path, viewport defaults
  engine/            # the ONLY code that talks to the engine binary
    locator.py       #   find build/**/trech (or $TRECH_BIN)
    runner.py        #   `trech run exp.js --output dir` (QProcess, streamed)
    lab.py           #   `trech lab` real-time bridge (JSONL stdin ↔ snapshot stdout)
    outputs.py       #   parse an output dir → typed run results
  scene/             # the editable scenario model
    model.py         #   SceneModel (world, volumes, materials, beams, run)
    loader.py        #   trech_viz_scene.json → SceneModel
  render/            # wgpu real-time viewport (pure rendering)
    camera.py mesh.py viewport.py renderer.py
    playback.py      #   time-indexed trajectories / particle frames for the timeline
    shaders/surface.wgsl shaders/lines.wgsl shaders/vertex_color.wgsl
  ui/                # PySide6 panels (glue only)
    main_window.py outliner.py inspector.py code_editor.py console.py theme.py
    scenarios.py     #   left-sidebar scenario tree (defaults to examples/)
    timeline.py      #   playback bar scrubbing the animation preview
tests/               # headless unit tests (playback logic + offscreen Qt panels + capture)
run_examples_suite.sh # run the example scenarios + capture PNG/MP4/GIF for validation
```

Layering rule: `ui → scene/engine/render`, never the reverse. See [`AGENTS.md`](AGENTS.md).

## Scenario tree + timeline

The left sidebar has a **Scenarios** tree rooted at `examples/` — the shipped experiment
scenarios double as Studio's test suite for opening and rendering complex runs. Double-click a
scenario to open it in the code editor; if it has a previous Studio run, that run loads too.
"Add folder…" adds your own scenario folders.

The bottom **Timeline** bar plays back a loaded run's animation preview in the viewport: for
trajectory runs it grows the sampled photon/particle polylines along the engine's per-step
`time_ns`; for particle-family runs (e.g. the shaken glass of water's `fluid_frame` emits) it
scrubs the emitted frames. Everything shown is engine output replayed on the engine's own
clock — the colours (wavelength→RGB, fluid tint) are the only rendering choice.

## Examples capture suite (for AI / human validation)

`run_examples_suite.sh` runs the example scenarios through the engine, then renders **each
run's Studio viewport** (scene + timeline playback) offscreen to a still **PNG** and an
**MP4 + GIF**, and writes a `manifest.json` + `index.md` so a human or an AI can check that
Studio handles each complex scenario and renders it correctly. It uses Studio's own wgpu
renderer (`trech_studio.capture`) — the real viewport path — and `ffmpeg` for encoding.

```bash
studio/run_examples_suite.sh --list                     # show the scenario table
studio/run_examples_suite.sh                            # default set (fast+medium), PNG+MP4+GIF
studio/run_examples_suite.sh --still viz_refraction glass_shaken   # only these, PNG only
studio/run_examples_suite.sh --all                      # add the slow MD/fluid scenarios
studio/run_examples_suite.sh --no-run cnt_band          # re-render an existing run only
```

Output lands in `build/studio/examples_suite/` (`captures/<id>.{png,mp4,gif,json}` +
`index.md` + `manifest.json`). Capture a single run directly with
`python -m trech_studio.capture --run <dir> --out <prefix>`. Everything degrades gracefully:
no GPU → JSON sidecar only; no ffmpeg → still PNG via a built-in encoder.

## Status

Basis / skeleton (2026-07-11): app shell, panels, engine locator/runner/lab bridge, output
parsing, scene model + loader, camera, mesh gen, and a wgpu viewport that draws lit volumes +
a grid are implemented. Added 2026-07-12: the **scenario browser**, the **timeline** with
trajectory + particle-frame playback in the viewport, and the **examples capture suite**
(offscreen PNG/MP4/GIF). The property-driven visual editor, gizmos, and `SceneModel → .js`
serialisation remain scaffolded — tracked in [`ROADMAP.md`](ROADMAP.md).
