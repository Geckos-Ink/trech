# Preview export and native media — roadmap

[Root principles](../../../AGENTS.md) · [Root roadmap](../../../ROADMAP.md) · [Parent](../ROADMAP.md) · [Handbook](AGENTS.md)

Related owners: [Classic and Studio media refresh](../../tooling/media/ROADMAP.md) · [Rendering, appearance and playback](../rendering/ROADMAP.md).

Maintain work in its owning branch. Dated results apply to the recorded checkout; they do not validate subsequent changes.

## Studio preview export and comparison media (2026-10-30)

- [x] Preview menu exports final PNG or full-timeline GIF+MP4 through the existing Studio
  capture renderer in a separate cancellable process, preserving material-stream selection.
  Fresh names avoid ordinary UI overwrites; failures/missing video are visible in Console.
- [x] Generic held-frame phase/clock/HUD/legend text is shared between Processes and optional
  capture footers. NaCl reports conserved parcel inventories on a step clock; airflow reports
  recorded gas temperature/pressure/density range with units and its actual CFL/SI clock.
- [x] NaCl/airflow enter the reproducible suite and gated compact GIF set. Two native Studio
  window PNGs, two annotated renderer stills and two 360×240/40-frame GIFs enter the root README;
  source/run/media hashes and refresh commands live in `docs/images/studio-processes/`.
  Existing committed GIFs and Chemistry screenshots are unchanged.
- [x] Compact reference JSON sidecars survive promotion/temporary cleanup. Tests caught the
  old dotted temporary-prefix/suffix collision; separate temporary stems now retain metadata.
  Relative engine overrides are resolved before inspection changes the working directory.
  Bounded side docks, one bottom tab group and hidden inactive Chemistry controls improve
  the default viewport without changing any engine state.
- [ ] Export parity: copy manually orbited cameras and every quantum/density display selection,
  select arbitrary timeline excerpts/current still cursor from UI, report progress, and remove
  cancelled partial files. Current exports use a standard camera and final/full recorded span.
- [ ] Generic scalar colour bars, chart/3D-text/apparatus overlays and simultaneous streams
  remain open; text HUD/legend readout does not complete all-scenario rendering parity.
- [ ] Physical accuracy remains unchanged: independent NaCl/Euler comparisons still need the
  quantitative anchors/convergence and learned lifts in the phase-change/airflow workstream.

Verification: Release CTest 29/29; Studio pytest 104/104 with Metal; all seven real-Geant4
reference cases pass conservation/replay with no dropped emits/inferences. Both native windows
and start/middle/end GIF frames were visually checked; Preview → Export image was exercised
through the native UI. Native and capture images remain distinct, labelled artifacts.

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
  Capture/source/run/media provenance: `docs/images/studio-processes/manifest.json`.
- [ ] Current-cursor stills, UI timeline excerpts, camera/display-state parity for exports,
  progress and partial-file cleanup on cancel remain. Current image is the final held frame;
  animation spans the full recorded timeline with no interpolation and a standard camera.
- [ ] Text legend/HUD readout and class-grid surfaces are landed; quantitative colour bars, charts, apparatus and
  3D text overlays and multi-stream compositing remain open for complete scenario fidelity.

Validation: Studio pytest 104/104 with Metal, seven real engine reference cases, native image
export exercised via the menu, and both native windows plus GIF start/middle/end inspection.

## Milestone 4 — authoring & polish

- [~] Scenario gallery: browse `examples/**/*.js` (landed as the `Scenarios` tree in M1).
  **[search/filter landed 2026-11-11]** the tree's filter box ANDs whitespace tokens over the file
  name, its folder under the root and the scenario's leading comment block (case-insensitive,
  e.g. `chirality` → the two CNT scenarios, `mri brain` → the brain phantom), hides empty folders,
  shows "k of N" and opens the scenario on Enter when exactly one matches; covered by
  `test_scenario_browser_filter_matches_name_folder_and_description`. Remaining — thumbnails from a
  cached scene (the reference-capture PNGs are not yet indexed per scenario), filtering by
  validation status/family, and matching on description text past the first 8 KiB/120 lines.
- [ ] Material editor tied to the composition surface (element/SMILES) + PubChem lookups.
- [ ] Undo/redo on the scene model; project/session persistence.
- [x] Screenshot / turntable export: `studio/trech_studio/capture.py` renders a run offscreen to a
  still PNG + MP4/GIF (turntable, timeline playback), and `studio/run_examples_suite.sh` runs the
  example scenarios + captures each into a `manifest.json`/`index.md` for AI/human validation.
- [x] Reference GIFs (**landed 2026-07-13**): `capture_reference()` / `--reference` writes a
  compact committed GIF; the suite promotes a curated subset into `studio/tests/reference/` only
  under `--update-refs` (`TRECH_STUDIO_UPDATE_REFS=1`) so refs aren't churned every run.
  `studio/tests/test_animation_capture.py` asserts the renderer produces *different* frames over the
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
