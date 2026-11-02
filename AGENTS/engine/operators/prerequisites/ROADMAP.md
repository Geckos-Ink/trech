# Operator migration prerequisites — roadmap

[Root principles](../../../../AGENTS.md) · [Root roadmap](../../../../ROADMAP.md) · [Parent](../ROADMAP.md) · [Handbook](AGENTS.md)

Related owners: [Operator migration contract](../migration/ROADMAP.md) · [Scenario law migration ledger](../../../scenarios/migrations/ROADMAP.md).

Maintain work in its owning branch. Dated results apply to the recorded checkout; they do not validate subsequent changes.

These entries preserve the original prerequisite landings. Later pair-model and per-kind process adoption is recorded in the [process workstream](../../../scenarios/processes/ROADMAP.md); current contracts are in the [operator handbook](../AGENTS.md).

## Engine prerequisites — land in this order

- [x] **General paired-run support. [landed 2026-07-26]** The validation runner now has one
  declarative `OperatorReferencePairSpec`/`OperatorReferencePairCase`: a migration declares its
  operator/reference run aliases, summary emit, comparison block, observer fields and trust
  thresholds once. The scenario's shared `trech_operator_reference_pair_v1` payload owns the
  absolute/relative tolerances and normalized trust record. The reusable evaluator checks identical
  comparison keys/teachers/tolerances, source and fidelity labels, every observer gap, contextual
  selection, measured hull/band/holdout, missing/starved/OOD state, and exact run-level inference +
  OOD accounting. Polyurethane now uses this path; its bespoke Python validator was removed.
  `tests/test_validation_pairs.py` covers the passing contract plus comparison-key, tolerance and
  inference-accounting failures and runs in CTest.
- [x] **Named operator roles and contextual selection. [landed 2026-07-26]** `models[]` now has
  conditionally serialized `operator_role`, `element_kind` and `required_context_keys` metadata.
  With no explicit `models` list, `ctx.evolve` matches loaded stages against the requested role/
  element kind and the ambient Geant4/material + caller context, then scale-orders the one
  compatible operator group. Point/cascade models (no role) are never swept into evolution.
  `result.selection` records mode/status/selected models and a per-model compatibility trace.
  Multiple compatible groups report `ambiguous`; zero report `no_compatible`; both return
  `ran:false` and leave every state array untouched. An explicit model list remains the override.
  Polyurethane now exercises the contextual default (`reaction_state` + `foam_parcel`) instead of
  naming its model in every call. Config round-trip and JS-boundary tests cover metadata,
  successful selection and ambiguous/no-compatible no-mutation.
- [x] **Discrete stochastic transitions. [landed 2026-07-26]** The new physics-agnostic
  `DiscreteTransition` + `ctx.react` sibling keeps stochastic state changes out of scenario JS.
  Callers declare named integer inventories over N elements, stoichiometric channels, and linear
  conservation vectors (atoms, charge, packet identity); learned scale-tagged operator stages emit
  either competing `hazard_<channel>` values or one `hazard` plus `weight_<channel>` values.
  The engine clamps learned hazards/weights to [0,1], deterministically renormalizes competing
  hazards above unity, owns the per-hook/per-call seeded draw, attempts at most one channel per
  element, rejects unavailable reactants without a partial update, and applies an accepted
  integer delta atomically. A malformed/duplicate/non-conserving topology stops before inference,
  draw, or mutation; mixed direct/weighted hazard schemas count the inference but never draw.
  Reports separate N×K `inferenceCount`, RNG `drawCount`, attempted/accepted/rejected transition
  counts, per-channel conservation/availability trace, contextual model-selection trace and the
  full model trust profile. Strict mode returns `null` before incrementing the react-call RNG
  sequence and leaves all arrays untouched. `tests/test_discrete_transition.cpp` covers direct and
  weighted hazards, clamping, seeded repeatability, both sampled channels, atomic availability,
  exact H/O/charge-style conservation and invalid/mixed-schema no-mutation;
  `tests/test_js_runtime.cpp` covers the JS boundary, contextual selection, N×K accounting and
  strict no-draw/no-mutation. This unblocks the electrolysis/combustion and membrane-crossing
  ledger rows without a chemistry or biology switch in C++.
- [x] **Pair/neighbour inference. [landed 2026-08-15]** `src/ml/PairInteraction.cpp` +
  `include/trech/ml/PairInteraction.hpp` add the batched interaction operator, exposed as
  `ctx.interact(spec)`. The caller declares positions, per-element fields that RECEIVE pair
  contributions (each with its declared `antisymmetric`/`symmetric` invariant and bounds), a
  neighbour `cutoff` and/or a persistent link list with its own per-pair state fields; the engine
  builds a uniform cell list, enumerates canonical `(a,b)` pairs (`a < b`) **in ascending index
  order**, and evaluates the contextually selected scale-tagged stages over each. Ordering is
  invariant under cell-map details by construction (the enumeration is index-driven, not
  bucket-driven), so a cell size or hash layout change cannot reorder the floating-point
  accumulation; a `maxPairs` budget truncates a canonical prefix and reports
  `neighborPairsSkipped`/`neighborPairsTruncated` instead of hiding it. Naming convention:
  `d_<field>_dt` is a rate contribution to both members (integrated once over `dt`), `add_<field>`
  a direct neighbourhood-sum increment, `d_<pair field>_dt`/`set_<pair field>` drive the pair's own
  persistent state (bond rest length, damage), anything else is an intermediate a higher-scale
  stage consumes; members are read as `a_<name>`/`b_<name>` and the geometry through reserved
  `r`, `dx/dy/dz`, `ux/uy/uz`, `dt`. An antisymmetric field's contribution applies the *same
  double* to both members, so a pair exchange cancels exactly; contributions accumulate and apply
  once, so no member sees a half-updated neighbour; a declared bond is always evaluated (a
  stretched bond is the interesting case) and never double-counted against the cutoff search;
  `set_<element field>`, undeclared-field outputs, invalid/duplicate links and missing inputs are
  all reported rather than silently dropped. Honest accounting: **pairs × stages** inferences feed
  `hook_predict_count`, with per-pair-aggregated trust coverage (`pairsOutOfDomain`,
  `pairsStarved`, `maxExtrapolation`, `scaleMismatch`, `holdoutR2`) exactly like `ctx.evolve`.
  Strict mode returns `null` and mutates neither element nor pair state. Guarded by
  `tests/test_pair_interaction.cpp` (12 groups, Geant4-free: cell-list pair discovery,
  equal-and-opposite conservation, symmetric sums without `dt`, out-of-cutoff bonds with bounded
  pair state, link/neighbour de-duplication, invalid/duplicate topology reporting, scale-ordered
  chaining through a pair intermediate, missing/unapplied reporting, reserved `dt`+shared context,
  aggregated coverage, the bounded search, unloaded-stage degradation, purity) plus a
  `ctx.interact` JS-boundary case in `tests/test_js_runtime.cpp` (in-place element AND pair-state
  mutation, pairs × stages counting, contextual selection, strict-mode no-mutation).
  `ctest --preset dev` 16/16. **Honest status: mechanism only — no scenario has been migrated onto
  it and no pair model is committed yet**; foam bonds, PBF, molecular water and collision baths are
  [migration ledger rows 1 and 8](../../../scenarios/migrations/ROADMAP.md#scenario-migration-ledger--exact-authored-laws-and-learned-targets).
- [x] **Batched inference core: allocation-free, vectorisable, optimization-level reproducible.
  [landed 2026-08-15]** The operators made inference the inner loop of the engine — a single
  `polyurethane_foam.js` run performs 2,812,320 model evaluations, `glass_from_sand.js` 73,848 — but
  every one of them ran through `predictVector`, which allocated one `std::vector<double>` per layer
  per call and walked a `vector<vector<double>>` weight matrix. Three changes, none of which touch
  what the arithmetic computes:
  - **`GenericSurrogate::predictInto(inputs, n, out, m, Workspace&)`** evaluates into caller-owned
    storage and ping-pongs two reusable scratch buffers, so a per-step operator over N elements
    allocates **nothing** after the first call. `StateEvolution`, `DiscreteTransition` and
    `PairInteraction` each hold one `Workspace` per call; `predictVector` now delegates to the same
    function, so the convenience and batched forms *cannot* drift apart.
  - **Input-major weights** (`weights[i * rows + o]`): the loop runs inputs-outside /
    neurons-inside, giving every neuron its own accumulator. Each accumulator still sums bias, then
    input 0, 1, 2 … in declared order — no reassociation — but the inner loop is now a contiguous
    scaled-add a compiler can vectorise, which a per-neuron dot-product reduction can never be.
  - **Rounding pinned, not left to the optimiser:** the accumulation uses an explicit `std::fma` and
    the translation unit is compiled `-ffp-contract=off`. This fixed a **latent determinism bug**:
    the old scalar reduction was contracted differently at different optimization levels, so the
    same committed model produced different last bits under `dev` (Debug) and `rel` (Release) — a
    measured 74,908/80,000 differing outputs for the efflux transport operator between `-O0` and
    `-O2`. The new core is bit-identical at `-O0`/`-O2`/`-O3`/`-Os` by construction.

  **Honest scope of the win.** Measured on the committed operator models with an `-O2` A/B harness
  against a faithful copy of the previous implementation
  (`c++ -std=c++17 -O2 -I include -I thirds/json/single_include bench.cpp src/ml/GenericSurrogate.cpp`):
  **×1.11–×1.65** for the wide trained operators (efflux transport 17→4 ×1.65, polyurethane meso
  27→8 ×1.48, efflux crossing ×1.43, H2O cycle 16→2 ×1.11) and **×3.7–×4.7** for the narrow glass
  furnace operators (3→2, 3→3), where per-call overhead dominated. This is the inference core only —
  the end-to-end share depends on how much of a scenario's time is model evaluation. **No physics
  changed:** a full `glass_from_sand.js` run (73,848 inferences through three trained operators)
  is byte-identical to the pre-change build in `trech_scores.jsonl`, `trech_hook_emits.jsonl` and
  `trech_viz_trajectories.jsonl`, and the three committed operator models reproduce the old `-O0`
  outputs exactly over 20,000 random input points each. Guarded by `tests/test_generic_surrogate.cpp`
  (batched == convenience form bitwise over 64 points, with a reused AND a fresh workspace; a
  workspace is shape-agnostic across models; mismatched input/output widths are refused rather than
  overrunning the caller's buffer). **Remaining:** the inner loop is only *vectorisable* — no
  explicit SIMD or blocking is written, and a genuinely batched `predictBatch` over many elements
  (one weight traversal for a whole element block) is the next step if a scenario's profile shows
  inference still dominating. `.pt` TorchScript models keep the old per-call path (LibTorch owns
  its own allocation).
- [ ] **Reusable bounded integrator/projection.** Move the repeated Euler/Verlet/OU thermostat and
  boundary/contact loops into a physics-agnostic array operator driven by inferred rates/impulses
  and declarative bounds. Keep integrator choice and tolerances in config/provenance. Learned
  models predict response; the integrator enforces numerical and conservation invariants.
- [ ] **Measured-data replacement path.** Generalise manifests to name dataset DOI/source,
  acquisition/simulation version and fidelity tier (`distilled`, `ab_initio`, `Geant4`,
  `measured`). Promotion across tiers requires the same independent paired gate. Start with the
  deferred foam-rise/temperature/gas-retention/fracture panel.
