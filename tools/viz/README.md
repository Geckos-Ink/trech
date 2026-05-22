# trech-viz

Accessible 3D viewer for TRECH scenes. Reads the artefacts written by `trech run` when `viz.enable = true`:

- `trech_viz_scene.json` — world / volumes / beams / per-material derived optical constants.
- `trech_viz_trajectories.jsonl` — sampled photon polylines (one JSON object per trajectory).

The viewer renders the volumes as transparent meshes (transparency and tint come from the **derived** optical constants the engine computed from Geant4 atomic cross sections, *not* from any handbook tables) and the photon paths as wavelength-coloured polylines. Volumes tagged `viz_forced_white` or `viz_emitter` get a forced visual look — those are non-physical viz hints (light sources, frames of reference).

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

Useful flags:

- `--screenshot path.png` — render off-screen and save instead of opening a window.
- `--background dark|light` — background colour.
- `--trajectory-limit N` — render at most N trajectories (default: render all).
- `--no-volumes` / `--no-trajectories` — toggle layers.

## Notes

The viewer is intentionally simple — it is a debug / demo surface, not a production renderer. If you need photoreal output use the JSONL artefacts as input to whatever pipeline you prefer; the data layer is documented in `docs/output_schema.md` (sections `trech_viz_scene.json` and `trech_viz_trajectories.jsonl`).
