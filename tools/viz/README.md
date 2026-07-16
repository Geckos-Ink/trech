# trech-viz

Accessible 3D viewer for TRECH scenes. Reads the artefacts written by `trech run` when `viz.enable = true`:

- `trech_viz_scene.json` — world / volumes / beams / per-material derived optical constants.
- `trech_viz_trajectories.jsonl` — sampled photon polylines (one JSON object per trajectory).
- `trech_hook_emits.jsonl` — optional held `material_frame` observer playback with per-particle
  RGBA plus retained physical and accelerated playback clocks.

The viewer renders the volumes as transparent meshes (transparency and tint come from the **derived** optical constants the engine computed from Geant4 atomic cross sections, *not* from any handbook tables) and the photon paths as wavelength-coloured polylines. Volumes tagged `viz_forced_white` or `viz_emitter` get a forced visual look — those are non-physical viz hints (light sources, frames of reference).
It shares Studio's labelled `viz_*` hint vocabulary, applies actual placed-volume rotations and
parent transforms, and can replay material frames as spherical points without inventing motion.

## Install

```bash
cd tools/viz
python -m venv .venv
source .venv/bin/activate
pip install -e .
```

PyVista pulls VTK. On macOS first time it can take a minute.

## Run

```bash
trech-viz \
  --scene build/dev/out_viz_refraction/trech_viz_scene.json \
  --trajectories build/dev/out_viz_refraction/trech_viz_trajectories.jsonl
```

Generate a real one-minute/100-tick run, then render its 100 post-tick states as a ten-second GIF:

```bash
build/dev/trech run examples/experiments/lava_lamp_10_minutes.js \
  --param duration_s=60 --param playback_duration_s=10 \
  --param simulation_ticks=100 --output build/dev/out_lava_lamp_readme_1m
trech-viz \
  --scene build/dev/out_lava_lamp_readme_1m/trech_viz_scene.json \
  --emits build/dev/out_lava_lamp_readme_1m/trech_hook_emits.jsonl \
  --gif tools/viz/demos/lava_lamp_trech_viz.gif \
  --width 260 --height 360 --seconds 10 --fps 10 --no-beams
```

The run emits 101 unique states over physical 0–60 s. With 100 output frames, the viewer maps
post-tick states 1–100 directly rather than stretching sparse frames or interpolating motion.
Camera orbit, ground grid, text, and spherical point glyphs are representation choices; point
positions/RGBA and held timing are the same data Studio consumes.
The GIF writer records per-frame delays in milliseconds, so `--seconds 10 --fps 10` produces an
actual 100-frame, 10.0-second animation rather than relying on player-specific default timing.

Useful flags:

- `--screenshot path.png` — render off-screen and save instead of opening a window.
- `--background dark|light` — background colour.
- `--trajectory-limit N` — render at most N trajectories (default: render all).
- `--no-volumes` / `--no-trajectories` — toggle layers.
- `--emits … --gif …` — replay `material_frame` observer output; tune with
  `--width`, `--height`, `--seconds`, `--fps`, `--orbit`, `--physical-start`, and
  `--physical-duration`.
- `--no-world` / `--no-beams` — hide debug context layers.

## Notes

The viewer is intentionally simple — it is a debug / demo surface, not a production renderer. If you need photoreal output use the JSONL artefacts as input to whatever pipeline you prefer; the data layer is documented in `docs/output_schema.md` (sections `trech_viz_scene.json`, `trech_viz_trajectories.jsonl`, and `trech_hook_emits.jsonl`).
