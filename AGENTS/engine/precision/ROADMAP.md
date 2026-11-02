# Precision profiles and runtime budgets — roadmap

[Root principles](../../../AGENTS.md) · [Root roadmap](../../../ROADMAP.md) · [Parent](../ROADMAP.md) · [Handbook](AGENTS.md)

Related owners: [Panels, run reports and resource controls](../../studio/workspace/ROADMAP.md) · [Scenario bundles and shared helpers](../../scenarios/bundles/ROADMAP.md).

Maintain work in its owning branch. Dated results apply to the recorded checkout; they do not validate subsequent changes.

## Adaptive precision, inference depth and resource scheduling

- [x] Continuous scenario refinement (`--refinement`, JS `factor`) within authored axis bounds;
  explicit unsupported-scenario failures and actual-axis reporting.
- [x] C++ `SimulationBudget`: predictive serial runs stop at whole event boundaries using measured
  EWMA event cost; actual/requested counts and stop reason agree across scores/provenance/scene.
  Strict runs reject time-based scheduling; existing no-budget config serialization is unchanged.
- [x] Arbitrary cascade depth, dependency-ready scheduling within bands, deterministic stage caps
  and target-output early exit with skipped-stage traces. Twelve-stage forward/reverse chains tested.
- [x] Studio continuous refinement/time controls and adaptive representation detail/resources.
- [x] Evolvo pinned in `thirds/evolvo`; optional offline GFSL width/depth search and portable model
  export, with disjoint training/selection/test runs. Ordinary trainer supports `--depth`.
- [ ] Residual: soft deadlines cannot interrupt a long event/hook or bound initialization;
  confidence/error-driven spatial/time-step refinement requires validated scenario-specific error
  estimates. No automatic accuracy claim follows from a resource budget.
- [ ] Residual: batched evolve/react/interact calls remain atomic; cascade caps are per property
  call, not a shared per-run inference budget. Model discovery/training/deployment remain explicit.
- [ ] Residual: evolutionary search currently varies uniform MLP width/depth, not arbitrary DAGs,
  activations or cross-family model discovery. Candidate training is atomic under its time budget.
  Broader learned-physics benchmarks and search-quality comparisons remain to be measured.
