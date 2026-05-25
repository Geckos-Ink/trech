# trech-viz demos

Reproducible, scripted illustrations of TRECH scenarios, captured as mp4.

The interactive `trech-viz` CLI (one level up) renders TRECH output
faithfully — actual `trech_viz_trajectories.jsonl` polylines, derived
optical constants for tinting, etc. The scripts in this directory are
*illustrations*: they read the scene to recover geometry, but may
synthesise the photon path or override material colours to make the
underlying physics easy to see in a six-second clip suitable for docs /
talks / PRs.

## Prerequisites

- `tools/viz` installed in a venv — see [`../README.md`](../README.md).
- `ffmpeg` on `$PATH`.
- A TRECH run for the relevant scenario, so the script has a scene file
  to read geometry from.

## glass\_of\_water\_beam.mp4

[`render_glass_of_water.py`](render_glass_of_water.py) animates a single
photon traversing the
[`validation_glass_of_water`](../../../examples/experiments/validation_glass_of_water.js)
cup. The script:

- reads geometry (glass cup + water bulk + emitter + beam direction)
  from `trech_viz_scene.json`,
- synthesises the refracted ray by applying Snell's law at each
  axis-aligned interface using the **handbook indices** that the scenario
  records under `optics.derive.validate.references`
  (`n_air = 1.000`, `n_glass = 1.46`, `n_water = 1.333`),
- advances the photon along that path at `c / n` per medium, drawing
  the wavelength-coloured trail behind a small "head" sphere,
- overrides the glass/water display colours (light blue / azure)
  because the derived `display_rgb` for this run collapses to the same
  brown for every material at 2.25 eV.

Why synthesise instead of replaying the trajectory file? In this run
the MolecularOptics derivation at 2.25 eV returns
`n_glass ≈ 1.006` and `n_water ≈ 1.001`, so Geant4's optical photon
transport correctly draws straight lines with no measurable refraction.
The video would be uninformative. The synthesis shows the *expected*
behaviour that `scripts/validate_glass_of_water.py` solves for via the
inverse problem. Use the interactive `trech-viz` CLI if you want to
inspect the actual simulated trajectories.

Regenerate the scene input if it is missing:

```bash
trech run examples/experiments/validation_glass_of_water.js \
    --events 4000 --output build/dev/out_validation_gow
```

Render the video (defaults to 6 s @ 30 fps, writes
`glass_of_water_beam.mp4` next to the script):

```bash
cd tools/viz
source .venv/bin/activate
python demos/render_glass_of_water.py
```

Useful flags: `--duration`, `--fps`, `--width`, `--height`, `--out`,
`--energy-ev`, `--keep-frames` (preserve the PNG sequence).
