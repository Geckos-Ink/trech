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
