# Precision profiles and runtime budgets — context and contracts

[Root principles](../../../AGENTS.md) · [Root roadmap](../../../ROADMAP.md) · [Parent](../AGENTS.md) · [Roadmap](ROADMAP.md)

Related owners: [Panels, run reports and resource controls](../../studio/workspace/AGENTS.md) · [Scenario bundles and shared helpers](../../scenarios/bundles/AGENTS.md).

Read the root principles and the parent handbook first; then open only the subcategory relevant to the task. Source paths and shell commands in code spans/blocks are repository-relative unless stated otherwise; Markdown links resolve from this file.

- **Precision is a profile mapped onto scenario axes, never one global "quality" number.**
  `config.precision` carries a rung (`preview`/`balanced`/`high`/`convergence`, or `custom` when a
  control overrode it) plus the axes the scenario mapped onto it, each with a physics-agnostic role
  (`spatial`/`temporal`/`output`/`statistical`/`representation`), its control, unit, resolved value
  and `balanced` reference. C++ owns the vocabulary + uniform reporting
  ([`src/core/Config.cpp`](../../../src/core/Config.cpp), `precision_profile`/`precision_axes` in scores,
  `precision_profile`/`precision_axis_count` in provenance); the *ladder* lives in
  `helpers.precision` ([`js/trech_helpers.js`](../../../js/trech_helpers.js))
  because only the scenario knows what refining its own axis means. A `representation` axis is
  forced display-only by the parser, so a render knob can never read as improved physics.
- **Continuous precision and budgets:** `--refinement` injects `TRECH_REFINEMENT` for
  `helpers.precision.resolve` (or use JS `factor`); scenario bounds/overrides remain authoritative.
  `run.timeBudgetSeconds`/`--time-budget` are predictive batch-only soft event-boundary budgets,
  using `src/core/SimulationBudget.cpp` and a serial Geant4 manager. Run-end `n_events` is actual;
  `requested_events`, budget, wall time and stop reason are conditional metadata. Strict rejects
  timing budgets. `ScaleCascade` chooses dependency-ready stages within a band, with registration
  order breaking ties; optional third-argument `ctx.cascade` limits (`maxStages`, `targetOutputs`)
  disclose every omitted stage. No three-stage cap. Full contract: [`docs/adaptive_precision.md`](../../../docs/adaptive_precision.md).
