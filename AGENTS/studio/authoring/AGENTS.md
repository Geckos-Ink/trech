# Scenario and process editing — context and contracts

[Root principles](../../../AGENTS.md) · [Root roadmap](../../../ROADMAP.md) · [Parent](../AGENTS.md) · [Roadmap](ROADMAP.md)

Read the root principles and the parent handbook first; then open only the subcategory relevant to the task. Source paths and shell commands in code spans/blocks are repository-relative unless stated otherwise; Markdown links resolve from this file.

**Scenario bundles:** `examples/scenarios/<name>/` holds physics plus `.view.js`,
`.validation.js` and `.ui.js`. The C++ loader inventories all companions; the source editor can
edit/save/re-inspect them while Run stays bound to the root. Built-in Chemistry/atomic-reference actions resolve the bundled physics entry points.
Browser discovery hides companions
and shared `trech_*.js` modules. Typed parameter factories work identically outside Studio.
Contract: [`docs/scenario_bundles.md`](../../../docs/scenario_bundles.md).

**JS process authoring:** `studio/trech_studio/ui/code_editor.py` switches between engine-inventoried included
sources, retains drafts and keeps Run bound to the root scenario. Save rejects external edits
and re-inspects typed declarations plus `TRECH_STUDIO` without restarting; already-running
workers are unchanged. `CodeEditor.dirty_paths()` includes visible and dormant root/include drafts;
source names show `*`. Scenario replacement and close offer Save/Discard/Cancel with Cancel as
default. Cancellation/failed Save precedes playback clearing or job shutdown, including browser
and Chemistry switch paths. This protects JS sources; typed-option/Chemistry persistence, crash
recovery and atomic multi-file disk writes remain roadmap work.
`studio/trech_studio/engine/parameters.py` validates the data-only `trech_studio_v1` descriptor;
`studio/trech_studio/ui/processes.py` displays declared process roles and configured models, never starts training.
It also selects recorded material streams. Material comparison streams may declare step-index
clocks and hide unrelated Geant4 probe geometry via `show_geant4_scene:false`, reported in capture
metadata. Full contract: [`docs/studio_authoring.md`](../../../docs/studio_authoring.md).

**Transport-scene export:** `studio/trech_studio/scene/writer.py` exposes pure
`scene_to_config` / `scene_to_js`. Loaded scenes require the full provenance config;
unchanged canonical fields remain intact, including source origin/spread, isotope/element
composition, unused materials, physics options and an independent primary beam. Only authored
model edits are overlaid; derived optics/appearance never become physics inputs. The writer
checks geometry/source and run identity against the recorded snapshot, rejecting callbacks,
external models, unsupported edited shapes, nonfinite values and JS values that cannot round-trip.
Named beams retain their source fields across reorder/nonprimary deletion; primary deletion,
identity changes and edits among multiple unnamed sources require the original scenario.
`File → Export scene scenario…` saves a separate transport draft without changing the open
source workspace or workers; it refuses to overwrite inventoried sources or retained drafts.
**Transport Inspector drafts:** `ui/inspector.py` exposes world size/material, primitive
box/sphere/tube/cylinder dimensions, volume pose/material and single or named beam particle/energy.
Apply builds a detached candidate, validates it through the same lossless writer, and only then
updates the scene/Outliner/viewport. Callback/model-bearing or mismatched runs remain read-only.
Recorded playback and precision are hidden for the draft; original config/score/emit reports retain
their recorded meaning. Applying leaves JS source drafts and active jobs untouched. Export saves a
separate JS file; Run still targets the open source. Unsaved scene replacement/close offers
Save(export)/Discard/Cancel, with Cancel as default; failed/cancelled export preserves the draft.
Discard restores recorded geometry; reload the run to restore its playback. Draft preview capture
is disabled until its exported scenario is run. Opening an output directory without a viz scene
is refused before replacing any scene/results, preserving their pairing. Gizmos, live patches, companions and typed
declarations are not reconstructed.
Tests: `studio/tests/test_scene_editing.py` (atomic Apply validation, draft/recorded isolation,
source/job preservation and scene-draft guard) and `studio/tests/test_scene_writer.py` (exact unchanged config + edit isolation through real
`trech inspect`, canonical source/material preservation, lossy-export guards and File export).
