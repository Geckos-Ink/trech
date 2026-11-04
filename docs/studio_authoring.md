# Editing JS processes and Studio descriptions

Studio's Scenario editor lists the physics root, its automatically loaded `.ui.js`, `.view.js`
and `.validation.js` companions, and every JS file evaluated through `TRECH_INCLUDE`.
Shipped bundles live in `examples/scenarios/<name>/`; reusable TRECH modules live in `js/`.
See [the bundle contract](scenario_bundles.md). The C++ runtime supplies that inventory via `trech inspect`; Studio does not
parse JS source. Select an included model/helper/solver module to edit it. Drafts survive source
switches; **Run always runs the root scenario**, even with a helper visible. Save writes changed
loaded drafts and rejects overwriting a file changed outside Studio. Changed source names show
`*`, including drafts in modules that are no longer visible. Before replacing a scenario or closing,
Studio offers **Save / Discard / Cancel**, listing every changed source; Cancel is the default.
Save checks every changed file for external edits before writing. A conflict or read/write failure
keeps the workspace open; Cancel also leaves playback and running/export/reference jobs alone.
Discard switches/closes without writing those drafts. Browser, file-open and Chemistry scenario
switches use the same guard, and a failed target open keeps the old drafts.

This guard covers the JS root and loaded-source drafts. It does not persist unsaved typed options
or Chemistry inputs across scenario changes, recover from a crash, or make multiple disk writes
atomic when an IO failure happens mid-save. Those remain explicit roadmap work.

**Save + apply UI** re-inspects the scenario and refreshes typed options and the JS description
without restarting Studio. Removed controls no longer leave stale overrides. Active runs retain
their loaded JS/config; a source change takes effect on the next run. This is not in-flight
replacement of a Geant4 worker, model weights or a lab kernel.

**File → Export scene scenario…** writes the loaded transport scene as a separate, readable
`.js` draft. It combines `SceneModel` edits with the run's complete provenance config, retaining
beam origins/spreads, isotope/element composition, physical conditions and unedited settings
that the viewport does not represent. Recorded optics/appearance remain results. The export
keeps the current editor and running jobs in place, and refuses to overwrite loaded source
files or retained drafts. Open the new file separately to review, inspect and run it.

This bounded export requires matching scene/config geometry and run identity. Missing provenance,
registered JS callbacks and external model dependencies require editing the original scenario;
the exporter cannot recover callback source, typed parameter declarations or companions from
run output. It also rejects unsupported edited shapes and numeric values that JS cannot retain
exactly. Dependency packaging and complete source round-trip remain M2 work. Export does not validate geometry overlaps or physical behaviour; TRECH owns
those checks. Python clients can author new transport drafts using the pure
`trech_studio.scene.scene_to_config` / `scene_to_js` functions without Qt or the engine.
The **Inspector** edits exportable transport runs: world size/material, box/sphere/tube/cylinder
shape dimensions, volume position/rotation/material and a single or named beam's particle/energy,
direction/origin, disk spot radius (mm), divergence cone half-angle (degrees) and energy sigma
as a fraction of energy. Source controls use the recorded config, including fields absent from
viz output; untouched defaults stay omitted. Editing one field preserves the others exactly,
including energy, spectral lines and polarization. Direction must be finite and nonzero;
spreads must be finite/nonnegative, with cone half-angle at most 180 degrees.
Coordinates are comma-separated x,y,z triples; numeric fields accept scientific notation. Select
a node in Outliner, change fields, then **Apply scene draft**. Invalid dimensions/nonfinite values
leave the scene unchanged. Materials are selected from the current scene; TRECH validates particle
names, materials, geometry overlaps and physics when the exported scenario is run.

Apply updates the viewport and Outliner as an authored draft. Recorded trajectories/frames and
precision are hidden because they belong to the old geometry; Run summary, Emits and Scale ladder
still describe the recorded run. Open JS drafts and active workers are unchanged. **Run** keeps its
open-source target, so export the scene to a new file and open that file to run these edits. Draft
preview capture is disabled until there are new recorded results. Before replacing an unsaved
scene or closing, Save exports it, Discard restores recorded geometry, and Cancel (the default)
keeps it open. Failed/cancelled exports also keep the draft. Reload the run to restore playback
after Discard. Opening an output directory without `trech_viz_scene.json` leaves the current run
and scene together. Live lab patches, gizmos, undo/redo and arbitrary source reconstruction remain open.

Named beams preserve their source origins/spreads across reorder or nonprimary deletion.
Changing beam identities, removing the primary or editing multiple unnamed sources requires
the original scenario so source fields are never reassigned by list position.

An optional JSON-compatible global describes the UI and internal process roles:

```js
globalThis.TRECH_STUDIO = {
  schema: "trech_studio_v1",
  title: "My experiment",
  description: "How this scenario connects transport, learning and observation",
  panels: { options: true, processes: true, emits: true },
  processes: [
    { id: "transport", label: "Particle transport", kind: "Geant4",
      description: "Transport and composition facts consumed by the scale lift" },
    { id: "fit", label: "Offline model fitting", kind: "offline training",
      description: "Describe the actual tools/torch command and its data split here" },
    { id: "lift", label: "Higher-scale response", kind: "inference",
      description: "Describe the actual ctx.cascade / ctx.evolve call and its validation limits" }
  ]
};
```

Supported panel identifiers are `options`, `scenario`, `processes`, `emits` and `scale_ladder`.
Values are booleans. Descriptors contain at most 64 process rows; all row fields are text.
Processes also lists actual configured models and their scale/path. Descriptions document
execution; they do not launch a trainer, import a solver into Studio, register arbitrary Qt
callbacks or prove that a model loaded. Run provenance and Scale ladder remain the evidence.
Typed controls come from companion `TRECH_PARAMETERS` factories read through `TRECH_PARAMETER`
(or legacy inline `TRECH_VALUE`), so engine validation owns their values.

`trech inspect` adds `authoring: {sources: [...], studio?: {...}, validation: {...}}` alongside `config` and
`parameters`. The descriptor is inspection metadata, outside serialized simulation config; its
title/panel edits do not alter the config hash. Any physics-relevant process parameters must go
in config/`hooks.inputs` rather than only in the descriptor. As with existing hook source,
source contents are not captured by a new source-content hash in this change.

The Processes stream selector can replay any recorded `material_frame.stream`, including when
trajectories would otherwise win automatic preview. It holds emitted frames and preserves native
axis/length/clock choices. Comparison frames may use `time` + `time_unit:"step"` and explicitly
set `show_geant4_scene:false` to separate their display geometry from unrelated transport probes.
The latter is a rendering choice and appears in precision/capture metadata.

Processes also follows the timeline's held phase, clock, `hud_lines` and display-legend labels.
**Preview → Export image…** writes the final recorded frame; **Export animation (GIF + MP4)…**
writes the full recorded horizon. Choose a directory: a separate cancellable capture process
uses the selected material stream and a standard fixed camera, with the same frame annotations
and a JSON provenance sidecar. Exporting does not rerun the engine. Install healthy ffmpeg for
animation; missing GIFs are reported as incomplete. Manually orbited cameras, current-cursor
stills/excerpts and all probability/field settings are not yet mirrored by export.
The CLI exposes `--stream`, `--annotations` and `--supersample` for reproducible captures.
Compact references retain their own JSON sidecars after promotion.

Arbitrary JS widget composition, workflow execution/training jobs, validated model hot-swap,
asynchronous inspection and complete parity for moving apparatus/chart/text outputs remain
tracked in [the project roadmap](../AGENTS/studio/ROADMAP.md#studio-desktop-ui). Existing offline training
entry points remain in `tools/torch`; the engine continues to execute inference with its strict-mode gate.
