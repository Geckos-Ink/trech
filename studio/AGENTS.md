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
   trech inspect exp.js ────────────────────►  engine/parameters.py → Options controls
   trech lab (stdin JSONL @ 60 Hz)  ◄────────►  engine/lab.py (real-time)
                                                    │
   trech_viz_scene.json ───────────────────►  scene/   → SceneModel (editable)
   trech_viz_trajectories.jsonl ───────────►  render/  → wgpu viewport
   trech_hook_emits.jsonl / scores ────────►  ui/console, ui/timeline
```

- `trech_studio/engine/` — the **only** code that talks to the engine binary. Locator,
  subprocess runner (`trech run`), typed scenario inspection (`trech inspect` in
  `parameters.py`), real-time lab bridge (`trech lab`), output-dir parser.
  Nothing else in Studio shells out or reads engine files directly.
- `trech_studio/scene/` — the editable scenario model. `SceneModel` is the in-memory truth;
  `loader.py` builds it from a `trech_viz_scene.json`. `appearance.py` turns a material's
  engine-emitted `derived_optics` (refractive index + absorption/scatter spectra) into an
  **honest look** — transparency from Beer–Lambert over the volume thickness, reflectivity from
  Fresnel(n), a transmission tint from the visible spectrum — the "understand the object from
  the physics" surface (see *Material appearance* below). It is a pure module (numpy only, no
  Qt/wgpu/engine import) so it is unit-testable in isolation. Serialising a `SceneModel` back to
  a runnable `.js` scenario is a **standing goal, not yet done** (see ROADMAP): today Studio
  edits the `.js` text directly and re-runs.
- `trech_studio/render/` — the wgpu viewport. Camera, CPU mesh generation, pipelines, WGSL
  shaders, and `playback.py` (time-indexed, medium/process-labelled trajectory ribbons plus
  fluid/material particle frames the viewport draws at a cursor). Tube meshes preserve both
  radii, inner walls and annular faces; a Geant4 beaker must not become a solid display cylinder.
  Pure rendering: it receives a `SceneModel` + a `Playback` and draws; it
  never reads engine files or computes physics. To honour the layering, `playback.py` builds
  from **duck-typed** inputs (objects exposing `.points`/`.times_ns` or `.tag`/`.payload`), so
  it needs no `engine` import while still consuming the real `engine.outputs` types at runtime.
- `trech_studio/ui/` — PySide6 panels (main window, outliner, inspector, code editor, console,
  typed `scenario_options`, the `scenarios` browser tree, and the `timeline` playback bar). Glue only; no physics, no
  direct file IO into engine outputs.

Respect the layering: `ui → scene/engine/render`, never the reverse; `render` and `scene`
do not import `engine`; nothing imports `ui` except `app.py`.

The **scenario browser** (`ui/scenarios.py`) is a filesystem tree rooted at `examples/` by
default — the shipped scenarios double as Studio's own test suite for opening/rendering complex
runs. The **timeline** (`ui/timeline.py`) drives one scalar cursor (engine-native `time_ns`/
`time_s`) that the viewport reads to grow trajectory polylines or select a particle frame; it
never invents a clock. A `material_frame` may additionally declare `playback_time_s` while
retaining `physical_time_s` + `time_scale`; Studio follows that emitted acceleration and shows
both clocks in the timeline/sidecar. See `docs/output_schema.md` for the fields it replays.

`trech_studio/capture.py` is the **headless** counterpart of the viewport: it drives the same
`SceneRenderer` offscreen (via `rendercanvas.offscreen`) to render a run's scene + playback to
a still PNG and an MP4/GIF (encoded with `ffmpeg`), writing a `<prefix>.json` provenance sidecar
next to the pixels. It is an app-level orchestrator (imports `engine`/`scene`/`render`, never
`ui`), the basis of `run_examples_suite.sh` — which runs the example scenarios and captures each
for AI/human validation (`manifest.json` + `index.md`). Because captures go through Studio's own
renderer, they *test the real viewport path*, not a parallel one. Keep it degrading gracefully:
no GPU → sidecar only; no healthy ffmpeg → still PNG via the built-in encoder. `TRECH_FFMPEG`
may name an explicit encoder; merely finding a broken executable on `PATH` must not crash capture.

`capture_reference()` (CLI `--reference <path.gif>`) writes a **compact** animation GIF
(default 320×220 px · 10 fps · 3 s, either dimension capped at 360 px, 128-colour palette) for committing as a repo visual
reference under `studio/tests/reference/`. Frames render supersampled and are box-downsampled for
anti-aliasing, and the GIF is built from **lossless raw frames** with `dither=none` (never the old
MP4→GIF + `bayer` path, which quantised h264 flat-area noise and the grid into speckle). This is
**gated**: the suite only writes references when run
with `--update-refs` (or `TRECH_STUDIO_UPDATE_REFS=1`), for a curated small id set
(`STUDIO_REF_IDS`). Never regenerate references on an ordinary capture run — they are binary and
committed, so churning them wastes repo space. See `studio/tests/reference/README.md`.

## Material appearance & render hints (how objects get their look)

Studio derives a material's *look from the physics*, the same "understand the object from the
Geant4 base" discipline the engine uses — never an invented colour. `scene/appearance.py`
reads the run's `derived_optics` and answers the observer-scale questions honestly:

- **"Is the glass transparent?"** → Beer–Lambert transmittance `exp(-thickness / attenuation)`
  through the volume's *own* thickness (`VolumeNode.path_length_mm`). Clear media render
  barely-there (a floored display alpha) and are seen mainly by their edges — like real glass.
- **"How does it reflect photons?"** → the Fresnel reflectance `R0 = ((n-1)/(n+1))²` from the
  derived refractive index drives a specular highlight in `surface.wgsl` (glass n≈1.47 → ~3.6%
  and glossy; water n≈1.33 → ~2% and matte). The shader also has the camera eye position now,
  so the highlight and a grazing-angle Fresnel edge are real view-dependent terms.
- **"Does water tend to be blue?"** → integrate the per-wavelength transmittance against the CIE
  colour-matching functions, **normalised so a flat spectrum is neutral**. A tint appears only
  when the physics resolves differential absorption. For the shipped pure-water/glass runs the
  EM optical base does *not* (it models refraction + photoelectric/Compton/Rayleigh, not the
  molecular vibrational overtones behind water's faint blue), so the honest result is a
  colourless clear medium — and the inspector's note says exactly that. Grade the gap; don't
  fake the blue.

**Scenarios can make a volume more visible for rendering** via authored `viz_*` tags (they
already flow JS → `trech_viz_scene.json` → Studio, exactly like the existing `viz_forced_white`
/ `viz_emitter`). Parsed by `scene.model.RenderHint`, applied *over* the physics look and
**labelled as a rendering choice, not physics** (inspector shows it as an authored override):

| tag | effect |
| --- | --- |
| `viz_hidden` | do not draw the volume |
| `viz_solid` | force an opaque body (alpha ~1) |
| `viz_shell` / `viz_wireframe` | force a clear glass **shell** (near-zero fill, edges/Fresnel only) so a beam/contents inside read through it — the optics legibility lever |
| `viz_emissive` / `viz_glow` | self-lit (skips shading) — beacons, collectors |
| `viz_opacity=<0..1>` | force display alpha |
| `viz_color=<#rgb\|#rrggbb\|r,g,b>` | replace the base colour |
| `viz_tint=<colour>` | multiply the derived colour by a tint |

These authored `viz_*` tags are the **"forced parameters, easy to disable"** channel: they make a
run legible (a clear glass shell for a beam, a bright emitter, a bumped opacity) without touching
the physics, and switch off by dropping the tag. Studio's *default* already reads optics well —
trajectories draw as glowing beam ribbons and clear dielectrics render see-through — so the tags
are for emphasis, not to paper over an unreadable default.

Precedence in `SceneModel.volume_color`: physics-derived appearance → engine viz tags
(`viz_forced_white`/`viz_emitter` = a bright opaque marker) → scenario `viz_*` hints (win last).
`volume_surface` additionally returns `(reflectance R0, gloss, emissive)` for the shader.

## Output contracts Studio depends on (do not silently break)

Studio reads these engine outputs — their schemas live in `docs/output_schema.md` at the repo
root. If you change a field there, update the parser in `engine/outputs.py` / `scene/loader.py`
in the same change:

| File | Studio consumer | What Studio uses |
| --- | --- | --- |
| `trech_viz_scene.json` | `scene/loader.py` → `scene/appearance.py` | world/medium, volumes (shape, pose, tags), materials, `derived_optics` (mean n + `mean_absorption_length_mm`/`mean_scatter_length_mm` + visible-band `samples[]`) → derived look, beams |
| `trech_viz_trajectories.jsonl` | `engine/outputs.py` → `render/playback.py` | sampled polylines + per-step `time_ns`, `material`, `process`, `interaction` → timeline-scrubbed beam; air is labelled/thinner and only a Geant4 scatter process receives the scatter emphasis |
| `trech_hook_emits.jsonl` | `ui/console`, `render/playback.py` (timeline) | scenario sideband emits; `fluid_frame` (metres) and `material_frame` (mm + per-particle RGBA) become scrubbable held frames |
| `trech_scores.jsonl` / `trech_provenance.jsonl` | `ui/console`, run summary, `precision.py` | run-level tallies, determinism/seed provenance, event/trajectory counts and caps for the simulation-precision report |

The **real-time** path is `trech lab`: a persistent process reading `{"action":…}` JSONL on
stdin (`patch`/`simulate`/`snapshot`/`quit`) and writing snapshot JSON on stdout at
`lab.targetHz`. `engine/lab.py` owns that protocol; bootstrap config lives at
`examples/lab/realtime_lab_bootstrap.json` in the repo. An omitted `simulate.events` uses the
engine's measured seconds/round EWMA to choose the next count; positive `lab.roundsPerTick` or
an explicit command count overrides selection. `phase:"lab_round_plan"` telemetry is routed to
the bridge's `round_plan` signal so a future live-loop panel can show actual throughput. The CLI
initializes Geant4 on the first batch and reuses the kernel for compatible later batches. Event
count, seed, and planner settings may change live; a kernel-bound geometry/beam/physics/scoring
patch is rejected with a restart-required error until safe reinitialization lands. That handshake
and arbitrary live-edit support remain tracked in both ROADMAPs.

## Directives for agents (Studio-specific)

- **Keep it a viewer, not an oracle.** Any pixel that isn't backed by an engine emit is
  labelled a rendering choice (grid, placeholder box, camera easing). No hidden interpolation
  presented as data.
- **Determinism is visible.** Show the run's seed / determinism mode / physics list from
  provenance. Never let the UI imply a predictive-mode result is a strict Geant4 tally.
- **Update markdowns as you go** (root directive): this `AGENTS.md`, `ROADMAP.md`, and the
  root references when Studio gains a capability. Treat "implementation" as Python source under
  `trech_studio/`.
- **Track every unfinished edge in `studio/ROADMAP.md`.** A residual, scaffold, missing render
  precision feature, untested output family, or TODO must gain a concrete roadmap item in the
  same change; do not leave incomplete work only in comments or a handoff.
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
the wgpu pipeline draws lit volumes + a grid. **Landed 2026-07-12:** the scenario browser
(left-sidebar tree over `examples/`) and the timeline with **trajectory + particle-frame
playback** in the viewport (colored line-list polylines grown by `time_ns`; `fluid_frame`
particle clouds as a point cloud) — covered by headless tests under `studio/tests/`.
**Landed 2026-07-13:** **physics-derived material appearance** (`scene/appearance.py`) — glass
renders transparent, water clear-but-glossier, colour/opacity/reflectivity read off the engine's
`derived_optics` (Beer–Lambert transparency + Fresnel specular in `surface.wgsl`, CIE
transmission tint); an authored `viz_*` render-hint channel so scenarios can make a volume more
visible without faking physics; and a **gated compact reference-GIF** path
(`capture_reference` / `--update-refs`) writing curated animation references into
`studio/tests/reference/`. Covered by `tests/test_appearance.py` + `tests/test_animation_capture.py`.
**Fixed 2026-07-13 (renderer correctness):** `fluid_frame` clouds are **z-up**, but the viewport
is y-up — frames are now remapped z-up→y-up (`playback._to_yup`), so the shaken glass stands as an
upright body of water instead of lying on its side; particle frames draw as **camera-facing sprite
billboards** (world-sized from the cloud's own spacing) rather than 1-px points; the camera frames
the **placed volumes** (not the whole 200 mm world box, which left the subject tiny); and the
offscreen capture supersamples + downsamples for anti-aliasing and builds the GIF from lossless
frames (killing the background speckle the old lossy MP4→GIF path produced).
**Optics legibility (same day):** the optics scenes were unreadable — thin 1-px photon lines lost
behind a *milky* glass block. Now trajectory segments draw as **glowing camera-facing beam ribbons**
(`trajectory.wgsl`, additive, wavelength-coloured, half-width from the framed scene size), and clear
dielectrics render genuinely **see-through** (`surface.wgsl` suppresses the flat fill for low-alpha
media and lets the Fresnel rim carry the shape) so the beam reads *through* the glass. The `viz_shell`
hint forces a pure clear shell for extra emphasis. All of it stays honest: positions/times/colours
are engine output on the engine clock; ribbon width, glow and the shell are labelled rendering choices.
**Precision + optics provenance landed 2026-07-15:** trajectory vertices now carry the Geant4
medium plus the process/interaction ending each segment. Studio no longer calls an arbitrary bend
"scattering": a scatter emphasis requires the recorded `scatter` class; boundary refraction and
world exit stay labelled boundary events. Air remains visible but is explicitly 0.58× the liquid
width and 0.72× its opacity. Ribbon width/alpha scale with the sampled optical-track count (a
single photon is tight/translucent; overlapping photons build brightness). `precision.py` shows
events, trajectory counts/caps, medium/process coverage and Monte-Carlo proportion standard errors
alongside representation settings; the same report is in every capture sidecar. `material_frame`
adds engine-positioned per-particle RGBA playback for the water/n-pentane beaker. True annular tube
meshes make its glass wall hollow rather than a placeholder solid cylinder.
**Beaker motion correction 2026-07-15:** `material_frame` playback accepts a scenario-emitted
accelerated clock only when physical time is retained and discloses both in the timeline/capture
sidecar. `beaker_water_pentane.gif` now starts empty, shows sequential water/pentane pours,
transient intermixing and phase separation, then a 545× 30 °C evaporation interval with a
continually renewed rising/drifting/fading plume—no stationary targets appearing over time. Its
blue/gold phase tints come only from `beaker_water_n_pentane_studio.js`; inferred layout and
evaporation remain untinted and unchanged.
**Typed scenario Options landed 2026-07-15:** Studio asks `trech inspect` for the declarations
produced by real `TRECH_VALUE` evaluation, builds grouped native controls in the right sidebar,
preserves compatible selections across source refreshes, and passes JSON-typed `--param` values
back on Run. It never regex-parses scenario source or computes physics. The refraction, H2O-fluid,
and CNT-fluid examples expose representative sizes/levels, temperatures, source and sampling knobs.
**Duration-independent lava lamp corrected 2026-07-16:** `lava_lamp.js` is a persistent
thermofluid material-frame case. Geant4 probes water plus a custom reference blend; the cascade
infers thermophysical coefficients, and a bounded-step solver advances the same 240 ordered parcel
IDs through heat, phase, density, buoyancy, velocity, boundaries, and neighbour topology. No cycle
period, authored phase schedule, target trajectory, birth, or regeneration remains. Duration is a
typed horizon, not scenario identity; heater/ambient conditions are independent controls. The
committed README media comes from a separate full-horizon 600 s / 100-Geant4-tick run at the
default 333.15 K heater condition with 101 distinct states; each 10 fps GIF consumes post-tick
states 1–100 directly. Never recreate the rejected seven-frame held excerpt, denser-cadence
scripted replay, or one-minute warm-up excerpt. Camera bounds account for
placed rotations and union apparatus + particle bounds, so tall rotated tubes and their cap/base
remain framed. Display tints are labelled authored; Geant4 does not solve CFD, and the cascade
response/parcel solver remain explicitly illustrative pending wider held-out training.
The macro cascade also infers carrier-circulation/advection and interfacial velocity coupling.
Those values are consumed by the scenario solver, not Studio: they make persistent parcel groups
collide, coalesce, circulate, and fission instead of merely oscillating vertically. Each frame
reports surface-component membership changes from stable parcel IDs; the README run contains 14
coalescences, 16 fissions, and 58/101 states with merged bodies. Treat those lineage fields as the
source of truth for whether a visible merge occurred.
**Fused lava surface + precision split landed 2026-07-16:** lava `material_frame`s now carry a
scenario-emitted `render_surface` contract. Studio splats the unchanged centres into the declared
Gaussian field, extracts an interpolated marching-tetrahedra mesh, and renders it with the same
depth-tested `surface.wgsl` material path as scene volumes; translucent apparatus is drawn over
the wax. This is representation only and is disclosed in preview/capture precision metadata.
Classic `trech-viz` contours the same contract with PyVista. Do not apply the surface mode to
frames that did not request it, and never use it to alter simulation state. Simulation precision
is explicitly multidimensional: fixed-inventory parcel count (spatial), maximum physics step
(temporal), Geant4/output ticks (sampling), and surface grid (display only). The 480-parcel/0.2 s
validation is an aggregate convergence check, not permission to equate “more particles” with all
forms of accuracy.
Still scaffolded: the property-driven scene editor, gizmos, and `SceneModel → .js` serialisation.
Honest gaps in what landed: generic `fluid_frame` and material frames without a surface contract
remain soft billboards, and trajectory/sprite overlays draw with the depth test off (legible, but
not occluded by volumes). Fused lava surfaces are depth-tested meshes; a future GPU compute field
would improve interactive scaling beyond the current CPU/LRU reconstruction. The transmission tint is faithful but the shipped EM optical base does not resolve
water's vibrational blue, so pure water/glass come out honestly colourless (the inspector says
so) — a real tint needs a scenario whose optics resolve differential absorption, or a `viz_tint`
hint. Don't describe a scaffold as finished — grade the gap, like the engine does.
