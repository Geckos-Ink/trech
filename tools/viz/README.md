# trech-viz

Accessible 3D viewer for TRECH scenes. Reads the artefacts written by `trech run` when `viz.enable = true`
(or when a run is captured with `trech run … --viz` / `--viz-all`):

- `trech_viz_scene.json` — world / medium / volumes / beams / per-material derived optical constants.
- `trech_viz_trajectories.jsonl` — sampled Geant4 polylines (optical photons, or every particle
  with `--viz-all`), each point with its Geant4 time, energy, process and interaction class.
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

Generate a real ten-minute/100-tick run, then render its 100 post-tick states as a ten-second GIF:

```bash
build/dev/trech run examples/scenarios/lava_lamp/lava_lamp.js \
  --param duration_s=600 --param playback_duration_s=10 \
  --param simulation_ticks=100 --output build/dev/out_lava_lamp_readme_10m
trech-viz \
  --scene build/dev/out_lava_lamp_readme_10m/trech_viz_scene.json \
  --emits build/dev/out_lava_lamp_readme_10m/trech_hook_emits.jsonl \
  --gif tools/viz/demos/lava_lamp_trech_viz.gif \
  --width 260 --height 360 --seconds 10 --fps 10 --no-beams
```

The run emits 101 unique states of the same ordered parcels over physical 0–600 s at the default
333.15 K heater condition. With 100 output frames, the viewer maps
post-tick states 1–100 directly rather than stretching sparse frames or interpolating motion.
The frame-emitted Gaussian surface contract is contoured into connected wax bodies; it changes no
parcel centre or clock and falls back to spherical points for scenarios without that contract.
For lava, the optional pair-Gaussian neck samples fade smoothly to zero at the emitted interface
connection radius. They make coalescence and fission continuous in the surface while preserving
the independently reported fine parcel lineage and the observer-interface component graph.
Three-dimensional carrier circulation/vorticity, lateral-plume strength, and interfacial coupling
are cascade-inferred and applied inside the scenario. The README centroid spans 38.73 × 36.52 mm,
travels 123.41 mm laterally, and occupies 10/12 azimuth sectors; the viewer only reveals that
motion and the emitted persistent-ID merge/split lineage (19/18 events in this run).
Camera orbit, ground grid, text, and spherical point glyphs are representation choices; point
IDs/positions/RGBA and held timing are the same data Studio consumes. The viewer never generates
or regenerates simulation particles.
The GIF writer records per-frame delays in milliseconds, so `--seconds 10 --fps 10` produces an
actual 100-frame, 10.0-second animation rather than relying on player-specific default timing. It
then quantizes every frame onto one shared adaptive palette so inter-frame diffs stay small — a
file-size optimisation only; frame content is the same replayed data.

The same `--emits … --gif …` path replays any `material_frame` scenario. The reactive-foam pair
uses it unchanged — and since the polyurethane scenario integrates a bonded-parcel network under
gravity, its replay shows the bun leaning, cracking and dropping pieces that land on the table, all
from the emitted parcel state:

```bash
TRECH_PUBCHEM_CACHE_DIR=build/pubchem_cache build/dev/trech run \
  examples/scenarios/polyurethane_foam/polyurethane_foam.js --output build/dev/out_polyurethane_foam
trech-viz \
  --scene build/dev/out_polyurethane_foam/trech_viz_scene.json \
  --emits build/dev/out_polyurethane_foam/trech_hook_emits.jsonl \
  --gif tools/viz/demos/polyurethane_foam.gif \
  --width 300 --height 420 --seconds 10 --fps 14 --no-beams
```

For those runs the material extent grows past the apparatus (a foam that rises well above the cup
rim), so the animation camera frames the union of the scene bounds and the full replayed parcel
extent, at a distance derived from the actual vertical field of view, the window aspect, and the
turntable's worst-case footprint circle. The frame keeps the whole emitted material visible without
moving any position.

## Geant4 trajectory GIFs

Any scenario can record its real Geant4 tracks without editing it: `trech run … --viz` (optical
photons) or `--viz-all` (every particle), with `--viz-max-trajectories N`. `--gif` without
`--emits` then replays the recorded polylines on their own Geant4 clock — each event overlaid from
its own t=0, a head marker on the recorded step each particle is on, discrete interaction vertices
of neutral quanta marked where Geant4 recorded them (white: scatter, red: other):

```bash
build/rel/trech run examples/scenarios/analytic_csda_range/analytic_csda_range.js --viz-all   --viz-max-trajectories 400 --output build/dev/out_csda
trech-viz --scene build/dev/out_csda/trech_viz_scene.json   --trajectories build/dev/out_csda/trech_viz_trajectories.jsonl   --scores build/dev/out_csda/trech_scores.jsonl --color-by energy   --gif csda.gif --title "20 MeV protons stopping in water"
```

- `--clock activity|linear` — playback maps frames to quantiles of the recorded step times (default,
  so picosecond ionisation and microsecond neutron diffusion both get frames) or uniform time; the
  HUD always prints the true Geant4 time.
- `--color-by species|energy` — species palette, or each recorded point's kinetic energy.
- `--scores trech_scores.jsonl` — the engine's analytic / nuclear-cycle checks join the HUD.
- `--events-with PARTICLE [--context-events N]` — show only whole events containing a rare product
  (stated in the HUD); tracks are never edited.
- `--compare-trajectories other.jsonl --labels "a|b"` — overlay a second run's recorded tracks (one
  changed condition) in a contrasting colour; `--compare-scene`/`--derived-n MAT` and
  `--compare-scores`/`--edep VOLUME_PREFIX` add each run's engine-derived n or Geant4-scored edep.
- When the apparatus dwarfs the tracks (a 4 mm proton range in a 20 cm medium) the camera frames
  the tracks and omits volumes enclosing the whole view (named in the HUD).

Legibility layers ([`trech_viz/tracks_view.py`](trech_viz/tracks_view.py)); none moves a recorded
point or invents a track:

- `--color-by history` (default): a primary photon is bright until its first recorded discrete
  interaction and orange afterwards; vertices are marked by the recorded process (photoelectric
  red, Compton white, Rayleigh blue, neutron reaction magenta, radioactive decay green) and flash
  when they happen.
- `--trail F`: recorded points dim with playback age (e-folding `F` of the clip; `0` = full trails).
- `--bundle`: optical photons with the same wavelength band and the same recorded
  `G4OpBoundaryProcess` history are drawn as one width-weighted mean path; recorded reflections are
  marked.
- `--nuclides`: ions are drawn as labelled nuclei; nuclide-changing vertices are labelled from the
  recorded products (`n + ¹⁴N → ¹⁴C + p`, target inferred by baryon/charge conservation).
- `--glyphs`: sparse ball-and-stick composition glyphs of each Geant4 material (H₂O, N₂, a NaCl
  lattice …) — representation, not to scale, and the legend says so.
- `--split`: the `--compare-trajectories` run in its own pane on the shared clock.
- `--display-events N`: draw only the first N recorded events (charts still use all of them);
  `--frame scene` frames the apparatus instead of the recorded extent.
- `--charts attenuation,bragg,optical,sampling,nuclear,deposit,refraction,tissues`: a side panel of
  statistics of the recorded tracks ([`trech_viz/track_charts.py`](trech_viz/track_charts.py)) —
  Kaplan–Meier uncollided survival vs `exp(−μx)`, first-interaction split vs `σᵢ/σ`, Bragg curve
  and range straggling vs `R_CSDA`, boundary outcomes and measured dispersion vs the engine's
  `n(λ)`, sampled spot/divergence/spectrum, reaction timeline on the Geant4 clock, per-volume
  electron deposits, and per-tissue detected signal vs ¹H density. Each sample appears at the
  Geant4 time it happened; formula lines come from `trech_scores.jsonl` and are dashed.
- `--caption "line|line"`: explanatory text drawn lower-left.

## material_frame contract extensions

Beyond positions/RGBA/clocks/`render_surface`, a frame may carry (all optional, see
`docs/output_schema.md`): `length_unit` (+ `positions` alias) for Å/nm/solver-unit frames,
`up_axis`, per-point `radii` (true-size spheres), `bonds` (index pairs → ball-and-stick),
`vectors` (arrows), `apparatus` (moving boxes/cylinders/spheres/segments/triangle `mesh`es),
`legend`, `hud_lines`, `clock_text` for non-SI solver clocks, and `stream` to keep several
timelines in one run (`--stream NAME`). Frames may also carry `samples` + `charts` + `curves` (the
side chart panel: time series of emitted observables, per-frame curve snapshots, labelled reference
data), `labels` (3D text), a `grid` of solver cells drawn as one smooth surface per material class
(`grains`/`liquid`/`solid`), and mesh `vertex_rgba` (a wall coloured by its own displacement). `--reframe` re-frames the camera per frame for streams
whose frames are different objects. Every README animation is produced this way by
[`demos/render_readme_3d.py`](demos/render_readme_3d.py).

Useful flags:

- `--screenshot path.png` — render off-screen and save instead of opening a window.
- `--background dark|light` — background colour.
- `--trajectory-limit N` — render at most N trajectories (default: render all).
- `--no-volumes` / `--no-trajectories` — toggle layers.
- `--emits … --gif …` — replay `material_frame` observer output; tune with
  `--width`, `--height`, `--seconds`, `--fps`, `--orbit`, `--physical-start`, and
  `--physical-duration`.
- `--no-world` / `--no-beams` — hide debug context layers.
- `--title`, `--elevation`, `--colors` — HUD title, camera elevation and GIF palette size.
- `--chart-width PX`, `--caption` — side chart panel width, explanatory caption.
- `--scene` is optional for `--gif` (frames in non-mm units never draw the mm apparatus scene).

## Notes

The viewer is intentionally simple — it is a debug / demo surface, not a production renderer. If you need photoreal output use the JSONL artefacts as input to whatever pipeline you prefer; the data layer is documented in `docs/output_schema.md` (sections `trech_viz_scene.json`, `trech_viz_trajectories.jsonl`, and `trech_hook_emits.jsonl`).
