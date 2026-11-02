# Classic and Studio media refresh — context and contracts

[Root principles](../../../AGENTS.md) · [Root roadmap](../../../ROADMAP.md) · [Parent](../AGENTS.md) · [Roadmap](ROADMAP.md)

Read the root principles and the parent handbook first; then open only the subcategory relevant to the task. Source paths and shell commands in code spans/blocks are repository-relative unless stated otherwise; Markdown links resolve from this file.

**All-experiment media refresh:** `scripts/update_experiment_media.sh` drives the canonical classic
capture registry and the runnable JS Studio inventory, including slow runs. Source/engine identity,
per-case status, assets/hashes and logs are recorded under a fresh `build/media_refresh` session;
`--resume` reuses matching completed work. Successful GIFs/PNGs are staged before promotion.
`studio/previews/` is committed generated documentation with an index/manifest. Missing-model or
static-only scenarios must not receive invented motion. Script invocation deliberately authorizes
updating the gated Studio GIF set. Native Chemistry/process screenshots are separate historical
captures and are not automatically regenerated or composited.

- **Studio Chemistry README screenshots** live in `docs/images/studio-chemistry/` with a
  capture guide and SHA-256 manifest. They are unmodified native-window captures, including
  the Metal viewport, distinct from the gated animation references under `studio/tests/reference/`.
  Refresh deliberately; preserve captions separating authored structures, independent quantum
  density comparisons and Geant4 nuclear initial-state ensembles. Capture the real app window
  including its GPU viewport; Qt widget grabs alone omit the native Metal surface.

- **Reference GIFs are gated & committed.** `studio/tests/reference/*.gif` regenerate only
  under `--update-refs` / `TRECH_STUDIO_UPDATE_REFS=1` for a curated ID set, or through the
  explicitly authorized all-experiment media refresh. Never regenerate them on an ordinary capture.
  See [`studio/tests/reference/README.md`](../../../studio/tests/reference/README.md).

- **[`tools/viz/trech_viz/`](../../../tools/viz)** — PyVista 3D viewer (console script `trech-viz`).
  [`animate.py`](../../../tools/viz/trech_viz/animate.py) owns held `material_frame` replay incl. the 3D
  observer extensions (`render_material_animation`; radii/bonds/vectors/apparatus meshes +
  `vertex_rgba`/legend/HUD/streams/labels/phase `grid` surfaces) and the shared GIF/text helpers
  (Unicode font, boxed text, `draw_caption`); [`tracks_view.py`](../../../tools/viz/trech_viz/tracks_view.py)
  owns recorded-Geant4-track replay (`render_tracks`: fading trails, history colouring,
  process-marked vertices, `find_reactions` nuclide labels, `bundle_optical`, composition glyphs,
  split panes); [`charts.py`](../../../tools/viz/trech_viz/charts.py) is the side chart panel (frame
  `samples`/`charts`/`curves`) and [`track_charts.py`](../../../tools/viz/trech_viz/track_charts.py) the
  recorded-track statistics (Kaplan–Meier attenuation, Bragg, dispersion, reaction timeline, …).
  [`demos/render_readme_3d.py`](../../../tools/viz/demos/render_readme_3d.py) regenerates every README GIF
  from real runs — **no scripted 2D renderer remains; do not add one** (a figure that cannot come
  from emitted state is a gap in the scenario's emits, not a job for a drawing script).

**Unified media refresh:** `scripts/update_experiment_media.sh` includes every runnable JS
scenario and all classic README capture families. Studio captures share fresh classic runs where
possible, use normal `trech_studio.capture`, and publish `studio/previews/` with audit metadata. Static
geometry is a still, blocked recipes publish their missing-model status, and unsupported motion is
never fabricated. The command explicitly updates the curated reference GIFs; native screenshots
remain deliberate, historical window captures. Preserve virtual-environment interpreter symlinks
when launching subprocesses (resolving them can lose installed graphics packages).

- **Scripted/planar animations.** Symptom: a README GIF shows motion no solver produced (targeted
  packets, a prescribed lobe pattern, a textbook curve being drawn) or a planar solver orbited in
  3D. Fix: emit the solver's own state as `material_frame` (or capture Geant4 tracks with
  `--viz-all`) and lift the solver to 3D; label any remaining representation kinematics.
- **Chart statistics revealed over playback must censor, not truncate.** Symptom: a survival
  curve dips far below the formula mid-GIF and recovers at the end. Cause: interacted photons are
  "known" early while survivors are only known when they exit. Fix: Kaplan–Meier with in-flight
  photons censored at the depth they have reached (`track_charts.attenuation_charts`); fractions
  of the whole population, never of the outcomes seen so far.
- **Classic-viewer axis for y-up geometry frames.** A frame emitted in a y-up Geant4 geometry frame
  must declare `up_axis: "y"`, or the z-up relabel lays it on the floor (glass_from_sand did).

- **Hook-emit file is append-mode.** `trech_hook_emits.jsonl` appends; clean the `--output` dir
  between reruns or renderers read stale emits.
- **PyVista offscreen renders repeat frame 0.** Call `plotter.render()` before each `screenshot()`.
