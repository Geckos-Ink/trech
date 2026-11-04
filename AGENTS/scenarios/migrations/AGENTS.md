# Scenario law migration ledger — context and contracts

[Root principles](../../../AGENTS.md) · [Root roadmap](../../../ROADMAP.md) · [Parent](../AGENTS.md) · [Roadmap](ROADMAP.md)

Related owners: [Operator migration contract](../../engine/operators/migration/AGENTS.md) · [Operator migration prerequisites](../../engine/operators/prerequisites/AGENTS.md).

Read the root principles and the parent handbook first; then open only the subcategory relevant to the task. Source paths and shell commands in code spans/blocks are repository-relative unless stated otherwise; Markdown links resolve from this file.

This branch covers scenario law migration ledger. Use the linked parent and related owners for implementation contracts and source maps; the paired roadmap records its delivery and validation requirements.

The hook inventory includes `particle_observer_cascade` as `no_active_material_law`: it predicts
properties through learned inference without an authored material-state evolution law. Its bounded
observer validation is a separate capability and does not close any remaining dynamics migration.
