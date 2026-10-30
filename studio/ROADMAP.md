# ROADMAP — TRECH Studio

Short-term execution plan for the desktop UI. Keep it updated as items land or are re-scoped.
The engine's own roadmap is the repo-root `ROADMAP.md`; this file only tracks Studio.

## Shareable native previews and export (2026-10-30)

- [x] Preview menu: asynchronous final-image/full-animation export with fresh names,
  selected material stream, standard camera, annotations and JSON sidecar; cancellation and
  incomplete-video reporting. The Qt UI does not run simulation while exporting.
- [x] Pure shared held-frame phase/clock/HUD/legend text in Processes and optional capture
  footer. NaCl inventories and Euler field ranges/units are emitted by their scenarios.
- [x] Correct bottom tab grouping and bounded initial side docks; inactive Chemistry is hidden.
  Relative engine overrides resolve before scenario cwd changes. A live native UI check found
  and verified that correction.
- [x] NaCl and airflow suite IDs plus gated 360×240, 4 s/10 fps GIFs; retained reference JSON
  sidecars. Root README includes two native windows and both animations, linking renderer PNGs.
  Capture/source/run/media provenance: `../docs/images/studio-processes/manifest.json`.
- [ ] Current-cursor stills, UI timeline excerpts, camera/display-state parity for exports,
  progress and partial-file cleanup on cancel remain. Current image is the final held frame;
  animation spans the full recorded timeline with no interpolation and a standard camera.
- [ ] Text legend/HUD readout is landed; quantitative colour bars, charts, apparatus/grid and
  3D text overlays and multi-stream compositing remain open for complete scenario fidelity.

Validation: Studio pytest 104/104 with Metal, seven real engine reference cases, native image
export exercised via the menu, and both native windows plus GIF start/middle/end inspection.

## JS process editing and comparison scenarios (2026-10-30)

- [x] Engine-inspected root/include source inventory; editor retains per-source drafts,
  rejects overwriting external changes and keeps Run tied to the root scenario. Save + apply UI
  re-inspects typed declarations, removes stale override names and reapplies `TRECH_STUDIO`
  titles, panel visibility and process descriptions without restarting Studio.
- [x] Processes displays configured model paths/scales and declared transport/training/inference
  roles. These are descriptions; actual execution/trust remains the engine's run/scale trace.
- [x] Generic material stream selector, explicit comparison step-clock units, and optional
  `show_geant4_scene:false` to hide unrelated transport probes without changing their physics.
  Precision/capture metadata reports scene visibility. NaCl and Euler-airflow comparison
  scenarios use existing frame/sphere/vector playback and normal output inspection.
- [ ] All-scenario render parity remains incomplete: moving apparatus meshes, grid/class
  surfaces, legends/scalar colour bars, chart/text overlays and simultaneous streams need
  generic implementations plus an all-family engine/capture matrix. The stream selector
  chooses one recorded stream; it does not composite them or implement those missing families.
- [ ] Live authoring extensions: asynchronous inspection, dirty draft guard on scenario switch/
  close, source-content provenance, arbitrary JS widget layout, workflow job execution with
  progress/cancellation and validated model/kernel hot swap. Current Save affects the next run;
  active Geant4/model workers are unchanged. Offline trainers remain outside the UI process.
- [ ] V8 is a pinned optional source/standalone probe foundation, not Studio's or TRECH's host
  backend. Upstream build, runtime/API/replay parity and performance validation remain root-roadmap
  work. No training or Geant4 logic moves into Studio's viewer/render layer.

Contracts: `../docs/studio_authoring.md`, `../docs/process_references.md`, `../docs/v8.md`.
Behavioural tests: `tests/test_authoring.py` (real-engine reinspection plus Qt editor/stream checks).
Full Studio pytest passes 99/99 with local Metal access, including the five GPU playback cases.
Fresh NaCl/airflow run captures were rendered with Studio's wgpu path and visually inspected;
quantitative comparison physics remains unvalidated as recorded in the root roadmap.


## Interactive probability fields and phase (2026-10-28)

- [x] Generic C++ scalar-field integrals, signed positive/negative components and 1–99%
  finite-grid absolute-mass thresholds, with exact tie inclusion. JS recomputes imported-grid
  diagnostics; source arrays stay unchanged. No learned-inference/RNG calls are introduced.
- [x] Optional solver exports signed real MO point amplitudes and independent joint-minus-
  isolated-fragment density. Geometry/unit/source/role validation rejects malformed phase
  arrays and unlabeled negative densities. Explicit Chemistry emit cap grows to 8 MiB.
- [x] Interactive Field explorer: gradient ray-marched volume, quantitative movable sections,
  enclosed-mass slider/contours, phase lobes/nodes and recorded orbital overlays on joint or
  difference fields. Legends/hover values and projected owner-labelled nuclei provide context.
  Controls preserve the source arrays and current clock; same-clock field switches retain cursor.
- [x] Correct outward contour winding and separate field-display lighting avoid random back-face
  triangle artifacts and material-optics shading. GPU ray marching uses scaled float16 textures,
  linear display sampling and 128 steps; original scalar values remain inspectable.
- [x] Nonuniform occupied-energy contributions: solver-evaluated diameter curves and spherical
  radial electron distributions for every occupied state, grouped by computed eigenvalues and
  occupation; engine validates geometry/membership and recomputes totals. Complete small-system
  grids expose energy-color contributions and cut faces. Ne-20 reference resolves core/outer
  distributions with computed 2/2/6 occupations, without fixed shell radii or linear fades.
- [x] Verification: Release CTest 27/27; Studio pytest 94 passed / 1 skipped; optional rotated-H2
  CLI and actual QProcess ethanol service gates pass. Eight paired Geant4 runs are byte-identical,
  preserve transport and drop no emits. Native Metal volume/phase/section/profile QA is recorded
  with the deliberately refreshed README screenshot manifest.
- [ ] Profile angular/radial and grid/image convergence studies, correlated basis benchmarks,
  energy decomposition for larger systems with omitted 3D orbital grids, and more than eight
  nucleus-centred profiles remain open. Basis-character labels are not exact atomic quantum
  numbers. Finite-radius molecular profiles include the whole joint wavefunction.
- [ ] Complex/spinor phases, adiabatic state matching, correlated/time-dependent quantum states,
  independently validated bond/entanglement measures and charge-transfer accuracy remain open.
  Own-basis closed-shell RHF fragment differences are comparisons, not proof of a shared bond.
- [ ] Field/texture streaming beyond in-memory scenes, scientific image-convergence gates, and
  richer camera/occlusion handling for transparent overlapping fields remain open. Sampling,
  log ranges and alpha are representation choices, not improved physics precision.


## Readable quantum states and nuclear grouping (2026-10-28)

- [x] States & particles tab: engine-emitted electron/proton/neutron inventory, discrete orbital
  energies and occupations, selectable recorded |ψ|² surfaces/points, total energy and dipole.
  Cursor changes update diagnostics; virtual orbitals visibly contain zero electrons.
- [x] One-nucleus labels, red/blue species counts, recorded RMS distances and radial-count plot;
  larger nucleon glyphs and separate sample-extent guides improve grouping without moving samples.
- [x] Optional electronic-reference action delegates to the shared engine tool (QProcess),
  validates through TRECH before/after calculation, then runs the ordinary scenario. No PySCF
  dependency in Studio; set TRECH_QUANTUM_PYTHON externally. Failed/stale jobs preserve drafts.
- [x] Complete large-scene restore from provenance, fresh batch output directories and compact
  numeric JSON rows prevent duplicate emits/stale-run mixing/excessive Qt text blocks.
- [x] Verification: 90 Studio pytest tests pass, one GPU animation test skips in the restricted
  runner; separate native Metal captures show orbital/nuclear views. Real QProcess/PySCF ethanol
  calculation preserves the venv executable and returns a TRECH-validated 26-electron scene.
- [ ] Multiple simultaneous orbital overlays, graphical nucleus picking and
  state tracking across geometries remain open. Energy eigenstates must not become guessed
  circular trajectories, imposed radial shells or persistent electron identities.
- [ ] PySCF service accuracy/coverage limits and general learned electronic/nuclear/reaction
  dynamics belong to engine/model work; see root roadmap and docs/chemistry_probability.md.


## Chemistry workspace — initial implementation

- [x] Four native-window Chemistry screenshots in the root README and linked from Studio's
  README, with source/clock captions, capture instructions and SHA-256 manifest. Covers structure
  editing, JSON/density surfaces, electron samples and Geant4 nuclear ensembles.
- [ ] Engine bridge: prefer a compatible build when dev/release binaries differ and normalize
  explicit engine paths before changing subprocess cwd. Captures currently use an absolute
  release-engine override; ordinary default discovery can select an older dev binary.

- [x] Multi-entity JSON scenes with placements/rotations/links and recorded density frames;
  import/export, append current structure, restore and content-addressed large-file overrides.
- [x] Direct scalar-grid density surfaces beside authored structures, supplied probability points,
  field view selector and source labels. Missing fields clear the last density; camera fitting
  uses visible threshold extents while preserving the full grid. Density transparency is an
  unlit display overlay, separate from the material optics pipeline.
- [x] Separate fm Geant4 proton/neutron ensemble views (both or either particle type), with
  parameter/ensemble clocks explicitly marked nonphysical. No individual electron trajectories
  or nucleus exaggeration into molecular units. Headless capture supports `--quantum-view`.
- [ ] Picking an individual nucleus/molecule, editable graphical placements and multiple simultaneous field overlays remain open. Nuclear samples are per-nuclide
  ensemble pools; current selector does not claim correlated nuclear evolution across a molecule.
- [ ] Streaming/chunking for large grids: fields cap at 131072 density samples/8192 points, but
  aggregate JSON scenes and 8 MiB Chemistry emits can still exceed memory/payload budgets. Density
  source metadata is displayed as supplied, not authenticated by Studio. Full correlated quantum
  dynamics and learned reaction paths require engine/model work.

- [x] Chemistry menu/dock opens `chemistry_mode.js`; explicit atom/isotope/Å-coordinate table,
  net charge and declared bond-order editor; six engine-evaluated starting scaffolds.
- [x] Typed string overrides pass to engine inspection/run; authored graphs/plans enter config
  hash/provenance. Native-unit held spheres/bonds use the existing renderer. Edited drafts are
  labelled pending a new run. Saved run structures/plans can be restored as drafts.
- [x] Engine results show isotope facts, electron bookkeeping, live particle probes, learned
  atomic/nano response/traces and unavailable capabilities. Optional supplied reaction plans
  show last recorded discrete inventory and operator trace; all steps remain in Emits.
- [x] Ten Chemistry tests cover authoring/restore/index bookkeeping, invalid edits, native-unit
  frames, JSON staging and actual engine inspection/run argument wiring. Seven probability tests
  cover recorded grids, missing fields, samples, nuclear units/clocks and file round trips.
  All 12 Studio test modules pass;
  Metal-rendered molecular structure capture was visually checked.
- [x] Chemistry layout leaves room for the viewport and a scrollable atom table, with zero-based
  atom row labels. The source header shows the filename with full path in its tooltip.
- [ ] Direct 3D atom/bond picking/dragging, bond-order glyphs, import/export formats and dedicated
  chemistry project persistence (source Save does not save transient controls; provenance does).
- [ ] Reaction timeline/species views and product geometry playback after the engine emits
  validated atomistic dynamics. No atomistic path is synthesized from species counts.
- [ ] Transferable electronic/stability/polarization and isotope-conditioned models require engine
  training/holdout/independent-validation work. UI currently reports them unavailable; supplied
  hazard attachment alone never establishes scientific coverage or a calibrated physical clock.
- [ ] Large plan/output streaming and payload-cap feedback; large graphs/plans can exceed hook
  payload limits and emits/frames remain in memory. Studio keeps its existing dependency surface;
  the optional offline electronic-reference service requires PySCF in its own runtime.
- [ ] Local Qt `offscreen` cannot host the native Metal widget (process crash at surface creation).
  Chemistry glue tests stub the viewport; headless 3D captures use rendercanvas's separate
  offscreen backend. Native Cocoa launch/layout and separate Metal rendering were checked.
  Detecting unsupported Qt surface platforms before widget construction remains open.

> ## ⭐ Studio's north star
>
> Make the multi-scale cascade **observable and editable by a human**. A user should open
> Studio, load or author a scenario, press Run, and *watch* the macroscopic answer the engine
> inferred from the Geant4 base — then reach into the scene, change it, and re-run, all without
> hand-editing JSONL. Studio succeeds when the distance between "a question about the world" and
> "a running TRECH scenario" is a few clicks, and when nothing on screen lies about what the
> engine actually computed.

## Adaptive precision and resources

- [x] Precision and resources dock: continuous scenario refinement, predictive soft time limits,
  independent render detail/target FPS/memory allowance. Engine remains the only physics owner.
- [x] Interactive CPU frame-cost feedback with hysteresis, viewport/particle complexity bounds,
  dynamic sphere/tube tessellation and surface-grid spacing, and estimated GPU cache budgets.
- [x] Configurable track/segment loading budgets; fixed capture overrides (including all recorded
  samples), representation metadata, engine stop reasons and limited-stage ladder badges.
- [ ] Residual: GPU timestamps and measured available VRAM are unavailable; CPU submission timing
  and RAM-based defaults are scheduling estimates, not a measured GPU throughput or hard memory cap.
- [ ] Residual: hook emits/particle frames still load in memory. Streaming/out-of-core loading and
  worker-thread surface extraction are needed for very large runs; surface neck construction can
  still require quadratic temporary memory. Trajectory budget changes apply on reopening output.
- [ ] Residual: automatic simulation accuracy/convergence control needs engine/scenario error
  estimates; Studio currently submits continuous factors and event/time budgets. It never invents
  missing models or claims a render refinement improves simulation accuracy.

## Stack decision (settled — do not relitigate without a reason here)

| Concern | Choice | Why |
| --- | --- | --- |
| 3D API | **wgpu-py (WebGPU)** | WGSL → Vulkan (Lin/Win) / Metal (mac) via `naga`, automatically. OpenGL is deprecated on macOS; raw Vulkan means hand-managing MoltenVK. |
| Shading language | **WGSL** | One shader source, cross-compiled to SPIR-V / MSL. Compute shaders available for future particle/fluid overlays. |
| UI toolkit | **PySide6 (Qt 6)** | Industry-standard dockable editor shell (outliner/inspector/viewport), native `wgpu` Qt canvas integration. |
| Math | **numpy** | Matrices + mesh gen without pulling a math lib. |

**Alternative considered and declined:** Godot 4 + GDExtension (`godot-python`). Batteries-included
(scene graph, gizmos, UI all free) and Vulkan-native, but it makes Studio a Godot app embedding
Python rather than a Python app — heavier to ship alongside the engine, and it couples our UI to
Godot's release cadence. Revisit only if hand-writing the render/gizmo layer becomes the bottleneck.

## Status legend

`[x]` done · `[~]` scaffolded (runs, minimal, has TODOs) · `[ ]` not started

## Milestone 0 — the basis (this scaffold, landed 2026-07-11)

- [x] Package skeleton (`trech_studio/`), `pyproject.toml`, entry point `python -m trech_studio`.
- [x] App shell: `QMainWindow` with dockable panels (viewport centre, outliner + inspector,
  code editor, console), dark theme.
- [x] Engine bridge: locator (`TRECH_BIN` / `build/**/trech`), `trech run` subprocess runner
  (QProcess, streamed stdout), real-time `trech lab` bridge (JSONL stdin ↔ snapshot stdout).
- [x] Output parsing: provenance / scores / hook-emits / viz-scene / trajectories → typed objects.
- [x] Scene model + loader (`trech_viz_scene.json` → editable `SceneModel`).
- [x] Camera (orbit / pan / dolly, perspective, fit-to-bounds), CPU mesh generation. Tubes now
  preserve outer/inner radii, inner-facing normals and annular end faces; spheres remain modest
  fixed-resolution meshes.
- [~] wgpu viewport: lit volumes (physics-derived colour/opacity + Fresnel specular) + ground
  grid via WGSL; the camera frames the **placed volumes** (not the whole world box) and the grid
  is a subtle plane sunk under them. Falls back to a message widget if wgpu is unavailable. TODO:
  back-to-front transparency *sorting* of translucent volumes, in-viewport MSAA, picking. (The
  offscreen capture already supersamples + downsamples for clean anti-aliased frames.)
- [~] Code editor: JS scenario editor with syntax highlighting + a Run button wired to the runner.
  TODO: LSP-less autocomplete for the `ctx.*`/config surface, inline error markers.

## Milestone 1 — view any run faithfully

- [x] `--open <output_dir>` loads scene + trajectories + emits and populates every panel
  (scene → viewport/outliner, scores → run summary, trajectories/emits → timeline playback).
- [x] Trajectory rendering: **glowing camera-facing beam ribbons** (wavelength→RGB for optical
  photons, per-particle palette otherwise; additive, `trajectory.wgsl`) so a run's photon paths
  read as a bright beam through clear glass, not thin 1-px scribbles a milky volume hides.
  **Time slider** drives a playback cursor from the engine's per-step `time_ns` (segments sorted
  by end-time → a growing beam). `render/playback.py` + `ui/timeline.py`.
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
  suite), activate to open + auto-load a prior run. `ui/scenarios.py`. (Was the M4 gallery seed.)
- [x] Run summary panel (**landed 2026-08-15**): a dedicated dock (tabbed with Console/Emits) over
  a new pure `trech_studio/run_summary.py` builder. Five labelled sections — determinism &
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
  of counts the engine already emitted. Tests in `tests/test_ui_panels.py` cover the section
  contents, the predictive-mode caution, the analytic gap text, the out-of-domain share and an
  empty output directory.
- [x] Precision profile in the preview (**landed 2026-08-15**): the engine now resolves a
  physics-agnostic precision profile per run (root `ROADMAP.md`), and Studio reads it rather than
  inventing a quality level. `precision.py` carries `precision_profile` + the scenario-mapped
  `precision_axes` into the preview status line and every capture sidecar; the Run-summary panel
  adds a **Precision profile** section listing each axis with its role, unit, resolved value,
  `balanced` reference, whether an explicit control overrode it, and a REPRESENTATION ONLY label
  for display-only axes. A `custom` rung is explained rather than shown as a named level. Tests:
  `tests/test_ui_panels.py::test_run_summary_reports_precision_axes_not_one_quality_number`.
  *Remaining:* only `lava_lamp.js` declares a profile so far, and Studio cannot yet **set** it —
  it appears as a normal typed option in the Options panel (`precision_profile`), which is enough
  to re-run at another rung but is not a dedicated preview-quality control.
- [x] Emit inspector (**landed 2026-08-15**): `ui/emits.py` filters `trech_hook_emits.jsonl` by tag
  (with per-tag counts) and by free-text payload match, pretty-prints the selected payload with
  **disclosed** display truncation of long arrays (the file is untouched), and jumps a played frame
  tag onto the timeline. The jump is honest by construction: the n-th emit of the tag the timeline
  is playing is the n-th emitted frame, and the cursor becomes that frame's own engine-emitted
  time — `Timeline.set_cursor` refuses a time outside the run's playable span instead of
  fabricating one, and the button is disabled for a tag the timeline is not playing. Tests cover
  filtering, truncation disclosure, the frame mapping and the disabled non-played tag.
- [x] Volume opacity/colour from `derived_optics` (**landed 2026-07-13**, `scene/appearance.py`):
  transparency from Beer–Lambert over the volume thickness, reflectivity from Fresnel(n) as a
  real specular in `surface.wgsl`, and a CIE transmission tint from the visible spectrum. Glass
  renders transparent+glossy, water transparent+matte; the tint stays neutral where the EM base
  does not resolve differential absorption (honest — water's vibrational blue is out of scope).
  Plus an authored `viz_*` render-hint channel (`RenderHint`) so scenarios can bump opacity /
  tint / hide / glow a volume for legibility, labelled as a rendering choice. The inspector shows
  the derived optics breakdown + any hint. Tests: `tests/test_appearance.py`.

## Milestone 2 — real-time scenario editing

- [x] **Typed scenario Options (2026-07-15):** `TRECH_VALUE` declarations are evaluated by the
  engine through Geant4-free `trech inspect` (never regex-parsed by Studio), mapped to grouped
  number/integer/boolean/choice/text controls in the right sidebar, preserved across compatible
  source refreshes, and sent back as validated JSON `--param` values on batch Run. Refraction,
  H2O-fluid, and CNT-fluid examples exercise sizes/levels, temperatures, source and sampling.
- [ ] Inspector drives the `SceneModel`: edit world size, a volume's pose/shape/material, beam
  particle/energy; changes reflect live in the viewport.
- [ ] **Real-time lab loop:** inspector edits become `{"action":"patch",…}` commands to a live
  `trech lab` session; `simulate` streams snapshots back into the viewport (the 60 Hz path).
  The engine-side adaptive round planner is landed: omitted counts learn seconds/round online and
  fit the next batch to `targetHz`; `engine/lab.py` routes `lab_round_plan` telemetry separately.
  Compatible batches now reuse one initialized Geant4 kernel, with per-batch config provenance;
  event count, seed and planner changes are live. Remaining work is wiring inspector edits and
  live snapshots/precision into the viewport, plus a restart/reinitialize handshake for
  kernel-bound geometry/beam/physics/scoring edits (currently rejected explicitly).
- [ ] Transform gizmos (translate/rotate/scale) on the selected volume.
- [ ] `SceneModel → scenario .js` serialisation — the round-trip that lets the visual editor
  emit a runnable, reviewable scenario (mirrors `scene/loader.py` in reverse). **Core deliverable.**

## Milestone 3 — the cascade, made legible

- [x] Scale ladder widget (**landed 2026-08-15**): a `Scale ladder` dock (tabbed with Console / Run
  summary / Emits) over a new pure `trech_studio/cascade.py` builder. It reads every recorded
  inference pass out of `trech_hook_emits.jsonl` — a `ctx.cascade` **property** pass or a
  `ctx.evolve`/`ctx.react`/`ctx.interact` **operator** pass — and shows: the bands the run bridged
  (`bands_bridged`, the root ROADMAP's headline cascade metric — a narrow point-predictor bridges
  one, `polyurethane_foam.js` bridges nano → meso → macro), which `seedKeys` came from the **Geant4
  base** (per-event tallies + `material.*` probes) rather than from the scenario, and per stage its
  band, what it predicted, and the engine's own trust flags rendered as badges: `EXTRAPOLATING`,
  `STARVED REGION`, `STARVED REGION (JOINT)` (in range on every axis yet far from any training
  point), `OFF TRAINED BAND`, `HEURISTIC DOMAIN` (an unmeasured hull) and `NO MEASURED
  ACCURACY`, alongside the stage's held-out R² and its **measured per-output error** (the engine's
  new `outputAccuracy`, whose `rmse` is a measured 1-σ residual). Honesty by construction: Studio
  sets no flag of its own — every badge names a boolean the engine decided — a counter a scenario
  renamed is reported as unrecorded rather than guessed, and a model with no metrics is described in
  words ("an illustrative map, not a trained-and-validated stage") instead of being shown with a
  flattering blank or a 0. The joint density check keeps **three** outcomes — covered, starved, and
  *not checked* — so a model carrying no joint reference can never read as one that passed. Detection keys on the **stage record's shape**, not the container name,
  because scenarios nest these traces under their own keys (`cascade`, `cascade_trace`,
  `chemistry_inference.stage_trace`). Verified against real runs: `glass_from_sand.js` (two
  illustrative maps, both badged) and `polyurethane_foam.js` (the same two maps plus its trained
  meso operator, badge-free, reporting `d_gel_dt` R²=0.99959 σ=8.25e-5). Tests:
  `tests/test_cascade_ladder.py` (6 cases). *Remaining:* it is a read-only report — no click-through
  from a stage to the emit that produced it, no per-event scrub of how a stage's coverage changed
  over the run, and `trech_resim_queue.jsonl` (which events the coverage flag routed to resim) is
  still not read by Studio at all.
  **Engine signal (2026-07-24):** each `__cascade.trace[i]` carries a per-stage **trust
  profile** — training-domain coverage (`inDomain`, `domainMeasured`, `extrapolation`,
  `outOfDomainInputs`), in-hull starvation (`starvedInputs`), off-trained-band use (`scaleMismatch`,
  `trainedScale`), and held-out accuracy (`holdoutR2`/`holdoutSamples`, null for untrained maps) —
  plus run-level `stagesExtrapolating` + `stagesScaleMismatched` + `stagesStarved` and the run's
  `hook_predict_out_of_domain_count` / `stratify_low_confidence_count` in scores/provenance. The
  widget can badge an *extrapolating / starved / off-band / low-confidence* stage, show its held-out
  R², distinguish a trained-domain guarantee (`domainMeasured:true`) from a heuristic fallback, and
  even surface which events the coverage flag routed to resim (`trech_resim_queue.jsonl` with
  `source:"cascade_coverage"`) — the same honesty discipline as the determinism/gap-to-truth labels.
  Scenarios expose the trace via hook emits (e.g. `cascade_multiscale_demo.js`).
- [ ] Overlay inferred macro quantities (rest density, cohesion, viscosity for the glass-of-water)
  next to their measured nano base, with the gap-to-truth shown (honesty rule). The per-stage
  `extrapolation` (training-σ past the trained hull) is the natural low-confidence marker here.
- [ ] Compute-shader particle/fluid overlay for `fluid_frame` emits (WGSL compute → instanced
  points/metaballs) so a shaken glass renders in the viewport, not only in the offline MP4.

## Milestone 4 — authoring & polish

- [~] Scenario gallery: browse `examples/**/*.js` (landed as the `Scenarios` tree in M1);
  remaining — thumbnails from a cached scene, search/filter.
- [ ] Material editor tied to the composition surface (element/SMILES) + PubChem lookups.
- [ ] Undo/redo on the scene model; project/session persistence.
- [x] Screenshot / turntable export: `trech_studio/capture.py` renders a run offscreen to a
  still PNG + MP4/GIF (turntable, timeline playback), and `run_examples_suite.sh` runs the
  example scenarios + captures each into a `manifest.json`/`index.md` for AI/human validation.
- [x] Reference GIFs (**landed 2026-07-13**): `capture_reference()` / `--reference` writes a
  compact committed GIF; the suite promotes a curated subset into `studio/tests/reference/` only
  under `--update-refs` (`TRECH_STUDIO_UPDATE_REFS=1`) so refs aren't churned every run.
  `tests/test_animation_capture.py` asserts the renderer produces *different* frames over the
  timeline (in-program animation preview) and that references stay small. **Refreshed
  2026-07-15:** all three existing GIFs were rerendered after the medium/process and precision
  work. The corrected `beaker_water_pentane.gif` covers the full sequential pour/intermix/separate/
  moving-plume timeline at 30 °C with explicitly labelled representation-only phase tints.
  **Corrected 2026-07-16:** the lava scenario covers the persistent thermofluid material-frame contract, while
  `lava_lamp.gif` and its paired classic-viewer GIF are generated from the same dedicated README
  run, not parallel motion sources. **Corrected:**
  README media comes from a dedicated typed ten-minute simulation at the default 333.15 K heater
  condition with 100 Geant4 ticks and 101 unique state frames; capture maps post-tick states 1–100
  to the 100 GIF frames over ten display seconds. The rejected seven-frame held excerpt,
  cadence-only scripted replay, and one-minute warm-up excerpt are gone; no optical flow or
  temporal interpolation replaces them. A 60 s duration-horizon comparison and a 310 K low-heater
  control validate state continuity and condition response outside the renderer. **Surface refresh
  2026-07-16:** both GIFs now merge nearby wax parcels through the shared emitted Gaussian-density
  contract; Studio's lava reference is portrait 260×360 so the new surface detail remains visible.
  The refreshed README run retains its former fine-interface 19 coalescences, 18 fissions, and
  43/101 merged states, while the new fluid interface records 8 merges, 10 splits, and 90/101
  merged states with visible neck growth/rupture. Its centroid spans 38.73 × 36.52 mm, traverses 123.41 mm laterally, and occupies
  10/12 azimuth sectors; both renderers show the same volumetric lineage rather than independent
  or centreline-confined bubble motion.
- [x] Capture quality (**fixed 2026-07-13**): frames render at N× (supersample) and are
  box-downsampled for anti-aliasing (removes specular sparkle on translucent glass/water); the
  GIF is built from **lossless raw frames** with `dither=none` (the old MP4→GIF path baked h264
  noise into flats, which the palette quantised into background speckle; `bayer` dithering had
  shredded the grid into dots). References land ~0.35–0.7 MiB — bigger than the earlier
  near-empty frames because the subject now actually fills the frame, still small enough to commit.

## Known scaffolds to finish (the gap, stated honestly)

- Renderer draws **physics-shaded volumes** (Beer–Lambert opacity + Fresnel specular from the
  derived optics) + a grid + **playback overlays** (coloured trajectory polylines, particle sprite
  billboards, plus scenario-declared fused material surfaces). Still missing: back-to-front
  transparency *sorting* of overlapping translucent volumes (they can composite out of order).
  Generic frames without `render_surface` remain soft camera-facing quads drawn with depth off;
  lava's declared surface is now a depth-tested isosurface. GPU compute extraction is a future
  scaling improvement, not missing correctness for the current 240/480-parcel case.
- Capture precision is machine-readable in the JSON sidecar but not yet optionally burned into
  image/video pixels; add a labelled overlay only if users need standalone media without sidecars.
- The lava-lamp macro response and parcel discretisation are illustrative. Wider measured training
  coverage and a general engine precision-profile schema are root ROADMAP items; the fused display
  surface must never be described as improving the underlying thermofluid model.
- The scene-node Inspector is **read-only**; the separate typed scenario Options panel can change
  authored run values, but arbitrary scene mutation and live-session patching remain M2.
- No `SceneModel → .js` writer yet — Studio edits `.js` text, it does not generate it (M2).
- Sphere meshes use modest fixed tessellation; adaptive screen-space tessellation/picking remains
  M1 polish. Tube/cylinder topology is now geometry-faithful.
- Lab bridge protocol is implemented but not yet wired to inspector edits (M2).
- **3D observer contract parity with classic `trech-viz` (2026-09-29).** Studio now accepts the
  `positions` alias of non-mm frames, a frame's own `up_axis`, and plays the first `stream` only
  (`tests/test_playback.py`). **Radius/bond parity landed 2026-10-18:** instanced sphere meshes
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
  meshes — the osmotic membrane, Pascal walls, the shaken glass), frame `legend`/`hud_lines`/
  `clock_text`, a `length_unit`-aware scale bar, and a stream picker. Until then Studio shows those
  runs as sphere/sprite clouds without their emitted moving apparatus — a missing overlay, never an invented one.

- **[open] Chart/label/grid contract (2026-09-29).** The classic viewer now draws frame `samples` +
  `charts` + `curves` as a side chart panel, `labels` as 3D text, a phase `grid` as per-class
  surfaces (with `replaces_points`) and mesh `vertex_rgba`; Studio ignores all of them (it still
  draws a grid scenario's per-cell points, which is correct data). Studio should plot the same
  emitted series in its dock, and read the trajectory `boundary` field (reflection/refraction) for
  its own ray styling.
- **[open] Radius/bond rendering polish.** Transparent spheres use depth testing without
  back-to-front instance sorting. Bond lines have a fixed display width rather than tubes;
  sphere meshes use the existing modest tessellation. Native-unit scale bars and a stream picker
  still need UI work; no physics or motion may be inferred to fill these presentation gaps.
