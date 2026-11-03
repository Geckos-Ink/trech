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
