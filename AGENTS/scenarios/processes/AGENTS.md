# Reusable solution and material processes — context and contracts

[Root principles](../../../AGENTS.md) · [Root roadmap](../../../ROADMAP.md) · [Parent](../AGENTS.md) · [Roadmap](ROADMAP.md)

Related owners: [Learned state and pair operators](../../engine/operators/AGENTS.md) · [Independent process references](../references/AGENTS.md) · [Recorded process and scalar views](../../studio/processes/AGENTS.md).

Read the root principles and the parent handbook first; then open only the subcategory relevant to the task. Source paths and shell commands in code spans/blocks are repository-relative unless stated otherwise; Markdown links resolve from this file.

**Reusable process authoring:** `trech_process_runtime.js` owns generic validated sequencing;
`trech_process_operators.js` binds unit-declared continuous/discrete process contracts to engine
operators, isolates auxiliary arrays and commits only valid proposals. C++ `ctx.operatorCatalog()`
exposes detached role/kind/IO/load/training metadata without inference or RNG, including strict mode;
catalog presence is not proof of compatible inputs or physical validity. Solution plans record
their operator contracts in `hooks.inputs`; bound reports retain the raw report under `engine`.
Loaded catalog `content_id` values fingerprint the exact loader bytes once (FNV-1a-64,
noncryptographic); file replacement cannot relabel already-loaded weights. Optional shared
`model_artifacts` pins require the complete loaded role/kind group before inference and report
observed identities. Mismatches block without state/clock/RNG changes; unpinned bindings keep
engine contextual selection. The same loader snapshot now also carries SHA-256 and byte size;
process pins accept `sha256:<64 lowercase hex digits>` alongside legacy FNV IDs. A name-sorted
`trech_model_artifacts_v1` registry manifest enters both provenance phases and run-end scores,
including failed loads and point/cascade models; Studio displays recorded identities/load failures.
The optional sorted `loaders` array also records separate optics/stratifier snapshots, failures
and intentional strict/disabled statuses. Stratifier workers load isolated classifiers from one
captured byte snapshot; run-boundary legacy hashes use it too. Strict mode prevents the optics
surrogate override. No-model runs omit the manifest and config hashes retain FNV. Artifact
signatures and physical-validation requirements remain roadmap work.
Optional JSON model `feature_units` carries complete named input/output unit labels from the
loaded snapshot; malformed declarations fail loading and legacy metadata stays unknown/null.
Process `model_units` checks the entire loaded role/kind group's IO union before inference,
including intermediate labels and overlapping state/aux/context declarations. Missing/mismatched
units block without state/clock/RNG changes; labels are exact strings, not dimensional analysis,
conversion or physical-validation proofs. Unchecked bindings retain prior behavior.
Bindings may instead declare `element_kinds: {field, allowed}` to read a detached per-element
kind array from process state on each call. Pins cover the union of all declared kinds; unit
IO unions must match separately for every kind, including inactive declarations. These calls
enable C++ `require_complete_selection`: missing/ambiguous active-kind selection blocks the
batch before inference or reaction sequence allocation. This gate checks selection, not model
input completeness; raw operators retain partial execution by default. Kind fields are never
committed by numeric bindings. Spatial neighbour `interact` bindings declare read-only x/y/z
arrays, a common coordinate unit/cutoff, optional pair budget and explicit field symmetry.
Pins/units cover canonical material-combination groups; C++ complete-selection gating precedes
pair inference. Supplied raw positions require complete finite x/y/z arrays, with no zero-filled
missing axes. Truncated neighbour proposals reject state/clock commits and retain engine counts.
An empty neighbourhood blocks by default; `spatial.empty_neighbourhood: "complete"` turns only
the engine's explicit `no_pairs` verdict (complete selection, untruncated, zero inference) into
a `no_op` report that `TRECH_PROCESS_RUNTIME` commits with unchanged state and an advanced clock.
Scalar-kind `evolve`/`react` bindings may likewise declare `empty_population: "complete"`
(default `"block"`, where zero-element arrays stay `invalid_binding`): an empty step then asks
the engine with `report_empty_population` and `require_complete_selection`, and only its
`no_elements` verdict (selected, zero inference/draws) becomes `no_op:"empty_population"`.
Spatial and per-element-kind bindings reject the declaration. Test:
[`tests/test_process_empty_population.cpp`](../../../tests/test_process_empty_population.cpp).
Persistent-link/pair-state bindings, coupled processes and validated cross-material laws remain open.
`tests/test_process_operators.cpp` exercises catalog metadata and synthetic continuous/discrete
bindings through the real host, including strict gating, proposal rollback and exact replay.
`tests/test_process_spatial.cpp` adds synthetic 3D neighbour selection and material-pair dispatch,
geometry/aux isolation, pin/unit/selection gates, truncation rollback and replay; no transport
response is physically validated by these fixtures.
`trech_solution_processes.js` owns H2O/NaCl units, inventories, atom conservation, process roles
and operator specifications. `water_salt_recipe.js` declares mix/heat/evaporate/crystallize intent.
It currently blocks on missing operators, emits no invented spatial motion, and records its plan
in `hooks.inputs`. The old NaCl display trays are retired from active playback; inventory emits remain diagnostics.
C++ `TRECH_INTERFACE_SEQUENCE` validates calibrated external measured mesh recordings and rejects
missing units/uncertainty/time/triangle/source/validation declarations. Inspection verifies format,
never experimental accuracy. Native-um held triangle replay needs supplied data; none is bundled.
The microscope photograph in `hooks.inputs.visual_reference` is attributed appearance only.

**Author-notes foundations:** `nacl_dehydration_reference.js` +
`trech_crystallization_reference.js` and `aerodynamics_reference.js` +
`trech_euler_reference.js` are explicitly independent comparison fixtures, not particle-trained
phase-change/aerodynamic predictions. They preserve serial execution and snapshot comparison assumptions in `hooks.inputs`. Scope/tests:
[`docs/process_references.md`](../../../docs/process_references.md). Do not promote illustrative salt
capacity/attachment or ideal-gas Euler laws into Geant4 truth or claim metal temper/fracture.
`JsRuntime::authoringMetadataJson` supplies inspected source inventories and optional
`TRECH_STUDIO` descriptions outside the physics config; Studio edits included modules and applies
these declarative panels/process descriptions on Save. [`docs/studio_authoring.md`](../../../docs/studio_authoring.md).
