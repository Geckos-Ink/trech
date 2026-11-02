# Operator migration contract — roadmap

[Root principles](../../../../AGENTS.md) · [Root roadmap](../../../../ROADMAP.md) · [Parent](../ROADMAP.md) · [Handbook](AGENTS.md)

Related owners: [Operator migration prerequisites](../prerequisites/ROADMAP.md) · [Scenario law migration ledger](../../../scenarios/migrations/ROADMAP.md).

Maintain work in its owning branch. Dated results apply to the recorded checkout; they do not validate subsequent changes.

## Scope boundary — what moves and what stays

- **Move out of scenario JS:** material-specific force/rate/relaxation/transport/constitutive laws;
  hand-tuned response curves; per-element or per-bond state transitions; stochastic reaction and
  membrane-crossing hazards; laws which turn a cascade coefficient into motion or chemistry.
  These become trained, scale-tagged model artefacts evaluated by physics-agnostic engine
  operators.
- **Move to reusable engine machinery, but do not train:** array traversal, neighbour search,
  deterministic integration, equal-and-opposite pair accumulation, declared bounds, collision and
  non-penetration projection, and declared reaction conservation. These are numerical/invariant
  operations, not material physics, and must contain no H2O/foam/CNT/MRI domain switch.
- **Keep in scenario JS:** experiment geometry and initial/boundary conditions; species/material
  identity and reaction/circuit topology; units; render-only packet motion, colours and camera
  hints; summary statistics; validation-only analytic comparisons. Boolean truth tables, atom/
  charge/stoichiometric conservation, and MRI reconstruction are specifications or inverse
  algorithms, not learned forward physics.
- **Do not migrate merely because a file uses arithmetic:** `analytic_*.js` deliberately declares
  engine analytic cross-checks; config/optics/beam examples, `hello_world.js`,
  `config_hook_dispatch.js`, `surrogate_generic_demo.js` and `cascade_multiscale_demo.js` do not
  contain an active authored material law. `h2o_fluid.js` is a Geant4 configuration. Studio
  wrappers and renderers are consumers. These remain outside this workstream unless a future audit
  finds a new state law in them.

## Common delivery contract for every migration row

The [scenario migration ledger](../../../scenarios/migrations/ROADMAP.md) owns the family rows; [engine prerequisites](../prerequisites/ROADMAP.md) own shared machinery.

Each migration lands the same evidence chain; a scenario is not promoted on row-wise fit quality
alone.

1. Add a typed `*_source: reference|operator` parameter. Keep the old law isolated as a
   deterministic teacher/audit path until an independent replacement exists; the operator is not
   the default yet.
2. Emit bounded, expanded training rows containing the complete pre-step state, aux/shared
   context, exact `dt`, and reference post-step target/rates. Split validation by **whole run**
   (seed + operating point), not shuffled neighbouring elements.
3. Commit a portable `GenericSurrogate` model plus manifest with `teacher`, `measured`,
   `trained_scale_bands`, measured input hull/occupancy, held-out samples and per-output metrics.
   A distilled JS teacher always remains labelled `measured:false`.
4. Emit a source-independent paired summary with identical seed/config/precision. Add a validation
   case that checks observer-scale gaps, conservation/invariants, holdout quality, missing/starved/
   out-of-domain counts, inference accounting and strict-mode no-mutation.
5. Promote `operator` only after the nominal pair and at least one perturbation/control pair pass.
   Preserve the reference source until measured/Geant4/ab-initio data supersede it; record that
   provenance transition instead of relabelling the distilled model.
6. Remove the reference law from the normal execution path after promotion. JS may retain it only
   behind the explicit audit/harvest switch. Update this ledger and the scenario-family validation
   status in the same commit.

## Completion condition for this workstream

This item may be marked complete only when all ledger rows are promoted, every normal hook path is
free of material-specific state laws, and a repository check prevents regression. Add a static
audit that inventories hook files and requires each allow-listed numeric evolution function to be
classified as `operator call`, `engine invariant/numerics`, `representation`, or
`validation-only`; fail CI on an unclassified new per-step law. The final report must list:
operator-backed scenario families, residual reference-only switches, model fidelity tiers,
independent holdout runs, paired observer gates, inference/out-of-domain counts and the remaining
fraction of authored state transitions. **Zero residual reference-only normal paths** is the exit
criterion; merely having a `ctx.cascade` call in the same file is not.

**[audit scaffold landed 2026-07-26]** `tools/validation/js_law_audit.json` now inventories all
24 hook-bearing experiment files as `operator_backed`, `operator_partial`, `reference_only` or
`no_active_material_law`, naming every residual family. `tests/test_js_law_audit.py` fails CTest
when a new hook experiment is unregistered, an operator claim has no matching call/default, or
the retired H2O/efflux normal-path function names return. This is the repository-level file audit;
function-level classification of every remaining numeric evolution helper is still required before
the workstream itself can be closed.
