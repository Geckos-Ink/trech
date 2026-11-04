# Coverage, uncertainty and trust — context and contracts

[Root principles](../../../../AGENTS.md) · [Root roadmap](../../../../ROADMAP.md) · [Parent](../AGENTS.md) · [Roadmap](ROADMAP.md)

Related owners: [Multi-scale inference](../AGENTS.md) · [Training tools, model data and feature schemas](../../../tooling/training/AGENTS.md) · [Panels, run reports and resource controls](../../../studio/workspace/AGENTS.md).

Read the root principles and the parent handbook first; then open only the subcategory relevant to the task. Source paths and shell commands in code spans/blocks are repository-relative unless stated otherwise; Markdown links resolve from this file.

This branch covers coverage, uncertainty and trust. Use the linked parent and related owners for implementation contracts and source maps; the paired roadmap records its delivery and validation requirements.

## Cascade dependency trust

`ScaleCascade::run` tracks out-of-domain ancestry separately from each model's numeric hull check.
The stage trace carries effective `inDomain`, numeric-only `localInDomain`, and sorted
`upstreamOutOfDomainInputs`. An out-of-domain producer marks its published keys; consumers retain
that evidence even if their numeric inputs fit their own hull. Independent branches stay independent,
clean successful overwrites replace lineage, skipped stages do not, and each run starts fresh.
`stagesExtrapolating` includes inherited failures, so the existing hook OOD counter and resim routing
act on them. Local distances/hull metadata are never replaced with another model's sigma units.
`tests/test_scale_cascade.cpp` exercises these cases; `tests/test_js_runtime.cpp` checks the JS fields
and inherited hook accounting.

Density and trained-band evidence use independent per-key lineage in the same call. Cascade
`starved` includes `localStarved` (local `starvedInputs` or `jointStarved`) and sorted
`upstreamStarvedInputs`. Effective `scaleMismatch` includes `localScaleMismatch` and sorted
`upstreamScaleMismatchedInputs`; `trainedScale` always describes the current model. The matching
stage counters include inherited evidence. Local density measurements stay local, and neither
cause changes hull-domain trust, hook OOD counts or OOD resim routing. Independent branches,
clean/skipped overwrites, per-feature/joint/combined causes, sorted multi-key dependencies and
per-call reset have C++ regression coverage; the JS test checks serialization and unchanged OOD
accounting/strict gating. Lineage across separate calls and persistent operator state remains
open in the paired roadmap; matching numeric values do not establish ancestry.

## Event resimulation policies

`stratify.resimOnLowConfidence` remains hull-only. Independent false-default
`resimOnStarvation` and `resimOnScaleMismatch` opt into sparse-training and off-trained-band
evidence. All five inference APIs contribute successful evaluation counts to their
`HookDispatchReport`; cascade counts include inherited causes, while operators retain local
checks and count the feature/joint starvation union once per evaluation. Point predictions
compare declared and trained scales only when both are known; result payloads are unchanged.
Strict mode, missing inputs and unloaded stages contribute no evaluations.

`RunAction::DispatchHook` returns separate `HookInferenceCounts`; `EventAction` uses only the
current event's `onEventEnd` report. `stratify.enable` gates routing/accounting and
`dumpResimQueue` gates queue writing. Qualifying events increment `stratify_low_confidence_count`
once across enabled causes, including when queue writing is disabled. Feature-exceptional
reasons retain precedence; otherwise the first hull/starvation/band cause becomes the reason.
When either new policy is enabled, event/queue records add exact cause counts and
`inference_resim_reasons` in policy order; otherwise legacy fields/bytes remain unchanged. OOD
counts remain hull-only. Candidates are recorded, never automatically rerun or used to retrain a model.

The [manual Geant4 gate](../../../../scripts/validate_inference_resim.py) checks point/cascade
routing, legacy bytes/hashes, strict gating, combined causes, feature precedence, disabled
queue/stratification, dispatch isolation and replay. Operator cause counts are checked in C++
and at the JS boundary. See [`docs/scenario_hooks.md`](../../../../docs/scenario_hooks.md)
and the [output schema](../../../../docs/output_schema.md) for field contracts.
