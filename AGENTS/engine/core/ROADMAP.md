# Configuration, CLI and provenance — roadmap

[Root principles](../../../AGENTS.md) · [Root roadmap](../../../ROADMAP.md) · [Parent](../ROADMAP.md) · [Handbook](AGENTS.md)

Related owners: [Precision profiles and runtime budgets](../precision/ROADMAP.md) · [JavaScript host and live lab](../runtime/ROADMAP.md) · [Tests and validation ownership](../../tooling/validation/ROADMAP.md).

Maintain work in its owning branch. Dated results apply to the recorded checkout; they do not validate subsequent changes.

For config serialization and reporting changes, follow [precision profiles and runtime budgets](../precision/ROADMAP.md). CLI, inspected metadata and live-session changes belong to the [runtime workstream](../runtime/ROADMAP.md); regression and schema gates belong to [validation](../../tooling/validation/ROADMAP.md). Add new core-only gaps here when they do not belong to one of those workstreams.

- [x] Independent `stratify.resimOnStarvation` / `resimOnScaleMismatch` opt-ins round-trip
  without changing absent/false legacy config bytes or hashes. Routing and remaining gaps are
  tracked in the [trust roadmap](../inference/trust/ROADMAP.md).
