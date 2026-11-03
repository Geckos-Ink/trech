# Rendering, appearance and playback — roadmap

[Root principles](../../../AGENTS.md) · [Root roadmap](../../../ROADMAP.md) · [Parent](../ROADMAP.md) · [Handbook](AGENTS.md)

Related owners: [Recorded process and scalar views](../processes/ROADMAP.md) · [Chemistry workspace and field inspection](../chemistry/ROADMAP.md) · [Classic and Studio media refresh](../../tooling/media/ROADMAP.md).

Maintain work in its owning branch. Dated results apply to the recorded checkout; they do not validate subsequent changes.

## Grouped bulk material rendering (2026-10-31)

- [x] Visible particle sampling and merging controls: shaken-water spatial multiplier plus
  display grid spacing; beaker representation-only particle multiplier; furnace N³ cell label.
  Shaken-water mass stays fixed across its actual integer lattice counts. Studio exposes separate
  surface detail and 0.5–2× Gaussian merge radius; Preview exports carry the selected values.
  Both material capture CLIs accept matching detail/radius options and record display overrides.
  Grid frames disable the radius control. Small detail changes invalidate Gaussian extraction
  caches even when sphere tessellation rounds to the same integer.
  Checks: 142 Studio tests, 20 classic-renderer tests and 34 CTest entries pass. Fresh startup
  counts are 4301/8841 at 1×/2× with identical total water mass; the 880-representative beaker
  passes its existing 11/11 checks. These are startup/representation checks, not convergence proof.
- [ ] Full-horizon convergence/performance checks across new shaken-water particle counts remain
  open. Startup checks prove sizing/mass invariance only; beaker sampling does not train/improve
  the model. Classic high-detail working-memory limits and persisted Studio control preferences
  remain future work; current Studio resource limits are estimates, not hard memory guarantees.

- [x] Studio consumes recorded phase grids as separate continuous class boundaries, with
  anisotropic spacing, closed outer faces, axis remapping and `replaces_points` support.
  The glass furnace now draws translucent sand/melt/glass bodies, rather than per-cell balls.
- [x] Explicit disjoint `material_groups` fuse unchanged liquid/gas representatives separately
  in Studio and classic replay. Water/pentane declares two liquids and a vapor envelope; kernels
  and opacity are display choices, preserving the existing illustrative-motion limitations.
- [x] Combined class/group triangles sort by view depth, translucent surfaces disable depth
  writes, existing single-fluid surfaces sort their triangles, and scene volumes sort by depth.
  Render detail controls display sampling; metadata distinguishes it from simulation precision.
  Pure membership/boundary tests and GPU held-frame/reverse-scrub checks cover live/export paths.
  Clear-shell shading uses the view angle on both faces; liquid clip boundaries close correctly,
  and classic cylinder clipping retains its declared world centre throughout Gaussian splatting.
- [x] Focused furnace/beaker classic and Studio previews plus the beaker reference were refreshed
  with hashes/manifests. Validation: 34 CTest, 138 Studio and 19 classic-renderer tests pass;
  fresh furnace/beaker physics gates pass 21/21 and 11/11. All 150/61 recorded position frames
  match their previous default runs; display reconstruction is not additional physical validation.
- [ ] Audit remaining observer-scale bulk emitters and migrate any point-only representations
  using explicit material identity/support. Molecular diagnostics must keep their particle view.
  Never reconstruct missing NaCl growth/liquid morphology from inventory counts; calibrated
  spatial data or validated spatial operators are still required.
- [ ] Order-independent transparency across intersecting separate scene objects, physical
  liquid refraction/gas volume optics, streamed/worker extraction and measured GPU memory bounds
  remain open. Current gas envelopes are Gaussian display contours, not measured density fields.
  Parcel-group kernels currently require mm frames; native-unit bulk groups need an explicit
  unit-bearing kernel contract.

## Milestone 1 — view any run faithfully

- [x] `--open <output_dir>` loads scene + trajectories + emits and populates every panel
  (scene → viewport/outliner, scores → run summary, trajectories/emits → timeline playback).
- [x] Trajectory rendering: **glowing camera-facing beam ribbons** (wavelength→RGB for optical
  photons, per-particle palette otherwise; additive, `trajectory.wgsl`) so a run's photon paths
  read as a bright beam through clear glass, not thin 1-px scribbles a milky volume hides.
  **Time slider** drives a playback cursor from the engine's per-step `time_ns` (segments sorted
  by end-time → a growing beam). `studio/trech_studio/render/playback.py` + `studio/trech_studio/ui/timeline.py`.
  Fixed 2026-07-13: clear dielectrics now render genuinely see-through (`surface.wgsl` suppresses
  the flat fill for low-alpha media, Fresnel rim carries the shape) + a `viz_shell` hint forces a
  clear glass shell — the optics scenes were unreadable milky blocks before.
- [x] **Medium/process-exact optics playback (2026-07-15):** each segment consumes engine-emitted
  `material`, `process`, and `interaction`. Air is named in the playback/precision UI and drawn
  0.58× as wide / 0.72× as opaque as condensed media; a scatter halo is applied only when Geant4
  recorded `interaction:"scatter"`, never from a bend. Ribbon width and opacity follow sampled
  optical-track count (one photon stays tight/translucent, overlapping photons build brightness).
  Tests cover weak-vs-strong and air-vs-water paths.
- [x] Particle-frame playback: `fluid_frame` emits (metres→mm) scrubbed as **camera-facing sprite
  billboards** (world-sized from the cloud's own spacing) — the shaken glass of water previews as
  an upright body of water in the viewport (M3 upgrades sprites → a true metaball isosurface).
  Fixed 2026-07-13: `fluid_frame` is z-up but the viewport is y-up, so frames are remapped
  z-up→y-up (`playback._to_yup`) — the water stood on its side before.
- [x] Material-resolved playback: `material_frame` emits preserve engine positions in mm and
  per-particle RGBA. The water/n-pentane beaker uses 61 held (never interpolated) frames for empty
  beaker → sequential pours → intermix/separate → moving plume. When frames declare an accelerated
  `playback_time_s`, Studio retains/discloses their physical time and scale in the timeline and
  capture sidecar; it never derives the mapping. **Lava-lamp coverage landed 2026-07-16:**
  `lava_lamp.js` emits stable ordered `particle_ids` with heat/phase/density/velocity state from a
  bounded persistent solver. Its default emits 121 states over a configurable 600 s horizon;
  duration is not scenario identity. Studio replays the emitted state and never creates parcels.
  Cascade-inferred 3D carrier circulation/vorticity, lateral-plume strength, and interfacial
  velocity coupling now drive volumetric blob collisions in the solver. Initial thermal
  fluctuations select the horizontal axis and handedness. Frames expose stable-ID surface
  lineage plus centroid x/y/path/azimuth metrics, so the viewer cannot substitute cosmetic
  overlap, camera orbit, or axis-locked vertical motion for simulated 3D transport.
  Camera fitting now unions rotation-aware apparatus bounds with particle bounds, so the real
  lamp cap/base stay visible instead of being cropped by a cloud-only fit.
- [x] Scenario-declared fused particle surfaces (**landed 2026-07-16**): `material_frame` may carry
  a labelled Gaussian `render_surface` hint. Lava frames use it to turn unchanged parcel centres
  into an interpolated marching-tetrahedra mesh, depth-tested and shaded by Studio's existing
  WGSL surface pipeline. Classic TRECH consumes the same contract with PyVista contouring. An
  eight-frame GPU-resource LRU keeps scrubbing bounded; frames without the hint still use sprites.
  Capture/preview precision reports disclose grid spacing, sigma, iso-level and the no-position-
  interpolation invariant. Remaining scaling work: move density splatting/extraction to compute
  when materially larger interactive particle fields require it.
- [x] Fluid-interface neck growth/rupture (**landed 2026-07-16**): the optional
  `render_surface.fluid_necking` contract adds smoothstep-faded Gaussian density between parcel
  pairs already inside the emitted observer-interface connection radius. Studio and classic
  TRECH share the same parser/splat semantics. It changes neither parcel centres nor component
  topology, and precision metadata discloses mode, distances, sample count, weight, and the
  topology-preservation assertion. The earlier fine parcel lineage remains separate (README:
  19 merges / 18 splits / 43 merged frames); the smoother interface records 8 / 10 / 90.
- [x] **Simulation + representation precision (2026-07-15):** `precision.py` reports actual MC
  events, trajectory counts/caps/drops, medium/process-label coverage, binomial standard errors,
  native mean segment step, beam display strength/width/opacity, emitted frame count, raster size
  and supersampling. Preview shows it in status/console + the world inspector; headless rendering
  writes the same structured report to its provenance sidecar. Loaded-vs-recorded trajectories
  and exact segment-budget truncation are explicit rather than silently dropping render samples.
  **Extended 2026-07-16:** lava exposes spatial parcel count at fixed inventory, temporal maximum
  step, output ticks, and representation-only surface grid separately; a 480-parcel/0.2 s run
  validates aggregate convergence against the 240-parcel/0.4 s baseline. Studio reports the
  fused-surface parameters rather than presenting one ambiguous “quality” level.
- [x] Scenario browser: left-sidebar tree over `examples/` (the shipped scenarios as a test
  suite), activate to open + auto-load a prior run. `studio/trech_studio/ui/scenarios.py`. (Was the M4 gallery seed.)
- [x] Run summary panel (**landed 2026-08-15**): a dedicated dock (tabbed with Console/Emits) over
  a new pure `studio/trech_studio/run_summary.py` builder. Five labelled sections — determinism &
  provenance (seed, mode, physics list, Geant4 version, RNG engine, config hash, registered hooks;
  a `predictive` run is flagged *"inferred results are not strict Geant4 tallies"*), primaries &
  transport (Geant4's own tallies, each fraction carrying an explicitly labelled binomial standard
  error), analytic cross-checks (classical prediction vs this run's measurement with the **gap**,
  relative error and tolerance, cautioned when out of tolerance, and stated as a self-consistency
  check rather than an external calibration), learned inference (`hook_predict_count`, the
  out-of-domain subset with its share, resim-routed low-confidence events, feature-based
  exceptional events) and the hook sideband (emit counts/drops, per-tag counts). The Console is now
  the log stream only, so there is one run header instead of two divergent ones. Studio derives
  nothing physical here: the only computed values are the labelled sampling error and percentages
  of counts the engine already emitted. Tests in `studio/tests/test_ui_panels.py` cover the section
  contents, the predictive-mode caution, the analytic gap text, the out-of-domain share and an
  empty output directory.
- [x] Precision profile in the preview (**landed 2026-08-15**): the engine now resolves a
  physics-agnostic precision profile per run (see [adaptive precision](../../engine/precision/ROADMAP.md#adaptive-precision-inference-depth-and-resource-scheduling)), and Studio reads it rather than
  inventing a quality level. `precision.py` carries `precision_profile` + the scenario-mapped
  `precision_axes` into the preview status line and every capture sidecar; the Run-summary panel
  adds a **Precision profile** section listing each axis with its role, unit, resolved value,
  `balanced` reference, whether an explicit control overrode it, and a REPRESENTATION ONLY label
  for display-only axes. A `custom` rung is explained rather than shown as a named level. Tests:
  `studio/tests/test_ui_panels.py::test_run_summary_reports_precision_axes_not_one_quality_number`.
  Profiles now also cover the furnace, shaken water and beaker (see the shared precision/bulk
  workstreams). Profile rungs remain typed Options where declared; continuous refinement and
  separate display detail are available in Precision and resources. A dedicated rung selector
  remains open.
- [x] Emit inspector (**landed 2026-08-15**): `studio/trech_studio/ui/emits.py` filters `trech_hook_emits.jsonl` by tag
  (with per-tag counts) and by free-text payload match, pretty-prints the selected payload with
  **disclosed** display truncation of long arrays (the file is untouched), and jumps a played frame
  tag onto the timeline. The jump is honest by construction: the n-th emit of the tag the timeline
  is playing is the n-th emitted frame, and the cursor becomes that frame's own engine-emitted
  time — `Timeline.set_cursor` refuses a time outside the run's playable span instead of
  fabricating one, and the button is disabled for a tag the timeline is not playing. Tests cover
  filtering, truncation disclosure, the frame mapping and the disabled non-played tag.
- [x] Volume opacity/colour from `derived_optics` (**landed 2026-07-13**, `studio/trech_studio/scene/appearance.py`):
  transparency from Beer–Lambert over the volume thickness, reflectivity from Fresnel(n) as a
  real specular in `surface.wgsl`, and a CIE transmission tint from the visible spectrum. Glass
  renders transparent+glossy, water transparent+matte; the tint stays neutral where the EM base
  does not resolve differential absorption (honest — water's vibrational blue is out of scope).
  Plus an authored `viz_*` render-hint channel (`RenderHint`) so scenarios can bump opacity /
  tint / hide / glow a volume for legibility, labelled as a rendering choice. The inspector shows
  the derived optics breakdown + any hint. Tests: `studio/tests/test_appearance.py`.

## Known scaffolds to finish (the gap, stated honestly)

- Renderer draws **physics-shaded volumes** (Beer–Lambert opacity + Fresnel specular from the
  derived optics) + a grid + **playback overlays** (coloured trajectory polylines, particle sprite
  billboards, plus scenario-declared fused material surfaces). Object depth sorting and material
  triangle sorting are implemented; intersecting separate translucent objects can still composite
  out of order. Frames without a surface/grid/group declaration remain soft camera-facing quads drawn with depth off;
  lava's declared surface is now a depth-tested isosurface. GPU compute extraction is a future
  scaling improvement, not missing correctness for the current 240/480-parcel case.
- Capture precision is machine-readable in the JSON sidecar but not yet optionally burned into
  image/video pixels; add a labelled overlay only if users need standalone media without sidecars.
- The lava-lamp macro response and parcel discretisation are illustrative. Wider measured training
  coverage remains engine/model work in the [lava-lamp workstream](../../scenarios/fluids/lava/ROADMAP.md). The engine precision-profile schema is
  landed; automatic accuracy/convergence control remains open. A fused display surface must
  never be described as improving the underlying thermofluid model.
- The Inspector edits bounded transport drafts and hides the old recorded playback; the pure
  `SceneModel → .js` writer exports them with the canonical config. Live-session patching,
  gizmos and complete source reconstruction remain [M2 work](../authoring/ROADMAP.md#milestone-2--real-time-scenario-editing).
- Sphere tessellation now follows render detail and resource bounds; picking remains
  M1 polish. Tube/cylinder topology is now geometry-faithful.
- Lab bridge protocol is implemented but not yet wired to inspector edits (M2).
- **3D observer contract parity with classic `trech-viz` (2026-09-29).** Studio now accepts the
  `positions` alias of non-mm frames and a frame's own `up_axis`. The Processes selector now chooses
  one recorded `stream` at a time (`studio/tests/test_playback.py`). **Radius/bond parity landed 2026-10-18:** instanced sphere meshes
  use each emitted radius; bonds join emitted centres with a rendering-choice line width. Native
  non-mm streams exclude the mm scene and its camera bounds; bounds include radii, GPU caches keep
  at most eight frames per representation, and capture discloses units/representation/bond count.
  Pure tests cover unit/axis/bond/radius validation and held-frame buffers; the GPU test checks
  changing radii and deterministic reverse scrubbing. **Vector parity landed 2026-10-19:**
  arrows retain emitted origin, magnitude and direction, with the same axis remapping as points.
  Zero vectors draw nothing; malformed arrays are ignored. Bounds include all vector frames;
  caches keep eight frames and capture reports vector counts and the cyan tint / 15%-length,
  6%-half-width arrowheads as representation choices. Pure tests and five GPU capture tests pass,
  including changing directions and pixel-identical reverse scrubbing; a real MR capture was
  inspected. Still to draw: moving
  `apparatus` (boxes/cylinders/spheres/segments/triangle
  meshes — the osmotic membrane, Pascal walls, the shaken glass), in-viewport frame
  `legend`/`hud_lines`/`clock_text` and a `length_unit`-aware scale bar. Held text readouts in
  Processes/capture and a single-stream selector are landed; simultaneous streams remain open.
  Moving apparatus is still absent from these replays; Studio must not invent it.

- **[partial] Chart/label/grid contract (2026-09-29).** The classic viewer draws frame `samples` +
  `charts` + `curves` as a side chart panel, `labels` as 3D text, a phase `grid` as per-class
  surfaces (with `replaces_points`) and mesh `vertex_rgba`. Studio now consumes phase grids and
  suppresses their point glyphs as declared. Studio still needs chart/3D-label support and
  authored-mesh `vertex_rgba`, beyond its existing class/group RGBA. Plot the same emitted series
  in its dock, and read the trajectory `boundary` field (reflection/refraction) for ray styling.
- **[open] Radius/bond rendering polish.** Transparent spheres use depth testing without
  back-to-front instance sorting. Bond lines have a fixed display width rather than tubes;
  sphere meshes use the existing bounded tessellation. Native-unit scale bars and simultaneous
  stream compositing still need UI work; no physics or motion may be inferred to fill these gaps.
