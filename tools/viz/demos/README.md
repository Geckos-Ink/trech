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

## glass\_of\_water\_beam.mp4 — physics target vs TRECH simulation

[`render_glass_of_water.py`](render_glass_of_water.py) animates a 2.25 eV
(green) photon crossing the
[`validation_glass_of_water`](../../../examples/experiments/validation_glass_of_water.js)
cup **two ways at once**, so the gap between them is honest and obvious:

- **physics target** (amber) — where the photon *should* go, from classical
  Snell refraction using the **handbook indices** the scenario records under
  `optics.derive.validate.references` (`n_air = 1.000`, `n_glass = 1.46`,
  `n_water = 1.333`). This is a well-known-physical-law reference, not a
  TRECH output.
- **TRECH simulated** (green) — where the photon *actually* went, replayed
  verbatim from `trech_viz_trajectories.jsonl`. TRECH derives each
  material's refractive index from Geant4 *nanoscale* cross sections
  (photoelectric + Compton + Rayleigh → Kramers-Kronig dispersion) plus an
  f-sum-rule valence oscillator — the valence-electron oscillator strength
  the atomic tables miss below ~100 eV — with no hard-coded optics.

Both rays start from the same emission point in the air above the cup and
advance in lockstep along their own arc length. The HUD reports, for water
and glass, the handbook index, the index TRECH derived (`n_glass ≈ 1.47`,
`n_water ≈ 1.33`), and the **fraction of the real refraction TRECH recovers
(~100 %)**. A red connector measures the resulting ray gap at the world
boundary (now well under 1 mm).

TRECH's ray refracts at every interface and tracks the textbook Snell angles
(air 30° → glass 19.9° → water 22.1° → glass → air 30°) from physics-derived
indices, so the green and amber rays essentially coincide. The remaining
residual (glass over-recovers by ~3 %, water under by ~1 %) is the
material-specific dispersion a single global oscillator energy can't resolve;
the surrogate training track is meant to close it
(see [`../../../docs/viz_refraction.md`](../../../docs/viz_refraction.md)).
This video is the regression artefact that tracks that residual toward the
ROADMAP "realistic *and* TRECH-based" goal.

The glass/water display colours (light blue / azure) are a visualization-only
override: the derived `display_rgb` for this run collapses to the same brown
for every material at 2.25 eV.

### Modes

| `--mode`            | shows                                              | file written by default            |
|---------------------|----------------------------------------------------|------------------------------------|
| `compare` (default) | both rays + the gap HUD (headline)                 | `glass_of_water_beam.mp4`          |
| `physics`           | the Snell target only (illustrative)               | use `--out glass_of_water_physics.mp4` |
| `trech`             | the faithful engine replay only (refracting)       | use `--out glass_of_water_trech.mp4`   |

`glass_of_water_physics.mp4` and `glass_of_water_trech.mp4` are committed
alongside the comparison so each story is also viewable on its own.

### Regenerate

Regenerate the scene + trajectory input if missing:

```bash
trech run examples/experiments/validation_glass_of_water.js \
    --events 4000 --output build/dev/out_validation_gow
```

Render (defaults to 7 s @ 30 fps, writes `glass_of_water_beam.mp4` next to
the script):

```bash
cd tools/viz
source .venv/bin/activate
python demos/render_glass_of_water.py                 # compare (headline)
python demos/render_glass_of_water.py --mode physics --out demos/glass_of_water_physics.mp4
python demos/render_glass_of_water.py --mode trech   --out demos/glass_of_water_trech.mp4
```

Useful flags: `--mode`, `--duration`, `--fps`, `--width`, `--height`,
`--out`, `--trajectories`, `--energy-ev`, `--keep-frames` (preserve the PNG
sequence).

Use the interactive `trech-viz` CLI (one level up) if you want to inspect the
full per-event trajectory set rather than a single representative ray.
