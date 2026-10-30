# Editing JS processes and Studio descriptions

Studio's Scenario editor lists the physics root, its automatically loaded `.ui.js`, `.view.js`
and `.validation.js` companions, and every JS file evaluated through `TRECH_INCLUDE`.
Shipped bundles live in `examples/scenarios/<name>/`; reusable TRECH modules live in `js/`.
See [the bundle contract](scenario_bundles.md). The C++ runtime supplies that inventory via `trech inspect`; Studio does not
parse JS source. Select an included model/helper/solver module to edit it. Drafts survive source
switches; **Run always runs the root scenario**, even with a helper visible. Save writes changed
loaded drafts and rejects overwriting a file changed outside Studio. Changing to another scenario
still replaces the editor workspace; save drafts first.

**Save + apply UI** re-inspects the scenario and refreshes typed options and the JS description
without restarting Studio. Removed controls no longer leave stale overrides. Active runs retain
their loaded JS/config; a source change takes effect on the next run. This is not in-flight
replacement of a Geant4 worker, model weights or a lab kernel.

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
asynchronous inspection and complete parity for moving apparatus/chart/grid/text outputs remain
tracked in [Studio's roadmap](../studio/ROADMAP.md). The existing offline training entry points
remain in `tools/torch`; the engine continues to execute inference with its strict-mode gate.
