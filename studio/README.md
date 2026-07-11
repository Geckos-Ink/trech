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
    shaders/surface.wgsl shaders/lines.wgsl
  ui/                # PySide6 panels (glue only)
    main_window.py outliner.py inspector.py code_editor.py console.py theme.py
```

Layering rule: `ui → scene/engine/render`, never the reverse. See [`AGENTS.md`](AGENTS.md).

## Status

Basis / skeleton (2026-07-11): app shell, panels, engine locator/runner/lab bridge, output
parsing, scene model + loader, camera, mesh gen, and a wgpu viewport that draws lit volumes +
a grid are implemented. Trajectory playback, the property-driven visual editor, gizmos, and
`SceneModel → .js` serialisation are scaffolded — tracked in [`ROADMAP.md`](ROADMAP.md).
