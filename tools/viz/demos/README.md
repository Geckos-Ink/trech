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

## h2o\_bulk\_water\_gr.mp4 — bulk MD vs measured liquid structure

[`render_bulk_water.py`](render_bulk_water.py) replays the Sputnik
[`h2o_bulk_water`](../../../examples/experiments/h2o_bulk_water.js) periodic
box (108 rigid **SPC/E** molecules, SHAKE/RATTLE constraints, minimum-image +
DSF Coulomb, classical MD in the deterministic hook layer with Geant4 as the
per-tick clock) next to the engine's own accumulating O-O radial distribution
function:

- **experiment** (amber) — the measured liquid-water first peak at
  **2.80 Å** (the hydrogen-bond distance) and the **~4.5 Å** tetrahedral
  second shell (X-ray/neutron diffraction), drawn as reference markers only;
  they never feed the simulation.
- **TRECH simulated** (green) — the g(r) histogram the scenario itself
  accumulates after equilibration, normalised exactly as in the JS, growing
  a first peak at **2.74 Å** and a second shell at **~4.4 Å**.

The end card shows how close the rigid SPC/E model now lands: the inter-shell
minimum (g(r) ≈0.78) sits essentially on the measured ≈0.75 at ≈3.4 Å, and
the coordination number (≈4.7) is in the measured ~4.3–4.7 band — no longer
the over-count the earlier flexible model produced. The remaining gap is the
second-shell height (the short-cutoff DSF electrostatics), stated not tuned
away.

The same run also measures the **self-diffusion coefficient** (the first
*dynamic* observable) from the production-phase O-atom mean-squared
displacement via the Einstein relation (MSD = 6 D t). It is reported on the
end card and saved as a standalone comparison plot,
`h2o_self_diffusion.png` (MSD vs time + the Einstein-relation fit + D against
the SPC/E literature and experiment): **D ≈ 2.6×10⁻⁹ m²/s**, on the SPC/E
literature ~2.5×10⁻⁹ and within ~12 % of experiment 2.3×10⁻⁹ (the run sits
at ≈305 K vs the 298 K reference; water's D rises with T). Caveats stated:
single-origin MSD, N=108, 7 Å cutoff.

## h2o\_vacf\_diffusion.png — the second route to D (Green-Kubo)

The same bulk run also computes the molecular center-of-mass **velocity
autocorrelation function** and integrates it for the Green-Kubo
self-diffusion, D = (1/3)∫⟨v(0)·v(t)⟩dt — an *independent* route to D from
the same trajectory. The plot shows the normalized VACF: a fast decay, then
the **negative cage-backscattering region** (min ≈−0.09 at ~300 fs) where
molecules rebound off their hydrogen-bond cage — the textbook signature of a
dense liquid (a gas VACF would decay monotonically without going negative).
The two routes agree: **D = 2.57 (Einstein) vs 2.79 (Green-Kubo) ×10⁻⁹ m²/s**,
both near experiment 2.3. Written by `render_bulk_water.py` alongside the MSD
plot.

## h2o\_diffusion\_temperature.png — does the model track D(T)?

A single state point can be lucky; a *trend* cannot.
[`render_diffusion_temperature.py`](render_diffusion_temperature.py) plots the
self-diffusion coefficient that
[`h2o_diffusion_temperature.js`](../../../examples/experiments/h2o_diffusion_temperature.js)
measures at three temperatures (one deterministic anneal: melt once, then per
block equilibrate + measure with a multi-time-origin MSD) against the measured
temperature dependence of liquid-water self-diffusion (Holz, Heil & Sacco,
PCCP 2000, amber):

- **experiment** (amber) — water's D roughly triples between 278 and 318 K.
- **TRECH simulated** (green squares) — D at each block's measured mean T.

TRECH reproduces the trend: **1.24 / 2.66 / 4.64 ×10⁻⁹ m²/s at 281 / 297 /
313 K** vs measured **1.43 / 2.27 / 3.26** — absolute values within ~15–45 %,
the rise a touch steeper than experiment (×3.74 vs ×2.28), which is the known
SPC/E behaviour. Caveats on the plot: constant-density sweep, N=108. The run
is slow (~20 min, ``SKIP_DIFFUSION_T``-gated in the suite).

### Regenerate

```bash
trech run examples/experiments/h2o_diffusion_temperature.js \
    --events 8100 --output build/dev/out_h2o_diffusion_T

cd tools/viz
source .venv/bin/activate
python demos/render_diffusion_temperature.py
```

Input is the run's `trech_hook_emits.jsonl`: the scenario emits a
deterministic `md_snapshot` every 10 ticks (wrapped per-molecule positions +
the running histogram) as a visualization sideband; physics is unchanged.

### Regenerate

```bash
trech run examples/experiments/h2o_bulk_water.js \
    --events 2500 --output build/dev/out_h2o_bulk

cd tools/viz
source .venv/bin/activate
python demos/render_bulk_water.py     # writes demos/h2o_bulk_water_gr.mp4
```

Useful flags: `--run`, `--out`, `--fps`, `--hold-seconds`, `--width`,
`--height`, `--keep-frames`.
