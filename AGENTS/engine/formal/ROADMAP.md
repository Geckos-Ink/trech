# Formal laws and Lean verification — roadmap

[Root principles](../../../AGENTS.md) · [Root roadmap](../../../ROADMAP.md) · [Parent](../ROADMAP.md) · [Handbook](AGENTS.md)

Related owners: [Builds and dependencies](../../tooling/dependencies/ROADMAP.md) · [Geant4 transport and diagnostics](../simulation/ROADMAP.md) · [Lattice methods](../lattice/ROADMAP.md) · [Scenario bundles](../../scenarios/bundles/ROADMAP.md).

Maintain work in its owning branch. Dated results apply to the recorded checkout; they do not validate subsequent changes.

## Priority queue

Every open item of this branch, highest priority first. The dated records below are delivery
history: the "Residual" and "Next" notes inside them are tracked here, and this queue wins
where they disagree. Keys and route steps: [priority keys](../../ROADMAP.md#priority-keys) ·
[implementation route](../../ROADMAP.md#implementation-route). When an item lands, delete it here, add a
dated record below, and queue its residuals in the same change.

Standing constraint for every item: Lean stays optional. Each law keeps its classic C++/JS
implementation as the running path, with the Lean definition beside it for validation
([rule](AGENTS.md#rules)).

- **P1** · R8 · Law inventory, continued. Done: Compton kinematics, Beer–Lambert attenuation, lattice mass conservation, scalar-lattice conservation, `ctx.react` step probabilities, the arbiter's proper squared score. Added declared `ctx.react` count conservation, antisymmetric `ctx.interact` exchange, the energy balance of recorded Geant4 Compton steps, the Compton relation from four-momentum conservation (momentum balance checked on recorded steps) and the bounded explicit step of `ctx.evolve`/`ctx.interact` (ordered bounds enforced at the JS boundary). Also added the order independence of set networks (`ctx.lift`, set operators) with its slot-standardisation hypothesis enforced at load. Also added `ctx.lift` group assembly (one parent per element; total weight and weighted first moment kept per level). Also added the domain learner's split score (error from summed statistics, additive statistics, a split never raises training error). Also added the learner's BIC gate as a threshold and the ridge split bound. Also added the arbiter's decayed prequential scores (closed form, monotone ranking on shared calls, counterexample without them), which `ctx.evolveField` selects by. Also added stage order inside a `ctx.evolve` band (disjoint commuting stages, order-free rate-only bands, the order dependence of a read assignment). Also added `ctx.learnDomains` routing (a partition of the input; splits and merges move only their own rows). Also added `ScaleCascade` registration order (producer-first band orders agree; permuting registration permutes bands only; rivals and stale reads are order-dependent). Also added the pruned joint-coverage scan of `GenericSurrogate` (same verdict as a full scan; exact starved distance). Also added its per-feature domain verdict and occupancy bin (extrapolation is 0 exactly in domain; the corrected bin is the unique containing bin, so training values are never starved; a non-finite input is out of domain), which fixed the engine's bin rule to match `numpy.histogram`. Also added the `ctx.lift` level recursion (any depth equals one grouping of the base elements by their composed ancestor; positive weights leave no zero-weight group). Also added `ctx.lift` lineage flags (a flagged element flags its ancestors at every depth; with quiet levels a group is flagged exactly when an element under it is), which found blocked groups dropping their members' out-of-domain flags. Next: the absent slots of a set model (`ctx.lift` and set operators fill them with the input means, so they standardise to zero and never trip coverage, as the inference handbook claims). Search Mathlib first. ([detail](#lift-lineage-and-weights-2026-11-26))
- **P2** · R8 · Energy balance on every recorded step: today `energy.step_balance` reads only a primary photon's first Compton scatter. Extend it to every process and generation with the rest-mass term `Q` (gamma conversion `−2 m_e c²`, positron annihilation, nuclear reactions from Geant4's mass table), behind the same observe-only contract and only in runs that ask for it. ([detail](#geant4-step-energy-balance-2026-11-22))
- **P2** · R8 · Conformance harness: a Lean reference evaluator (`@[export]` C symbols linked behind an opt-in `TRECH_ENABLE_LEAN`, default OFF, or a separate `lake exe` fed JSON) that checks the classic kernel on sampled or recorded inputs offline. Measure its cost; it never runs per step in production and never changes physics, RNG or emits. ([detail](#route-opened--2026-11-22))
- **P2** · R8 · Hardware acceleration contract: Lean compiles to scalar CPU code, so accelerated kernels (C++ SIMD, LibTorch, GPU) stay the compute path. Define how a proof about an algorithm's model transfers to its accelerated implementation (shared algorithm spec, sampled conformance, documented reduction-order and fused-operation differences). ([detail](#route-opened--2026-11-22))
- **P3** · R8 · More runs recording law checks: `analytic_compton_transfer` (validation and engine) and `analytic_beer_lambert` (engine, `attenuation.memoryless` at Geant4's own coefficient) record verdicts. Next: companions of `ctx.react` scenarios checking recorded per-cell probabilities with `checkProbabilityVector`, and an engine `ctx.lift` check of conserved weight per level from the recorded groups. Always observe-only and off the decision path; a companion check runs under the `validation` role. ([detail](#attenuation-at-geant4s-coefficient-2026-11-23))
- **P3** · R3 · Stale reads in a `ctx.cascade` band: the ready-stage choice treats a fact as available as soon as it is present, so when a seed or a lower band already holds a fact that an in-band stage replaces, a consumer registered before that producer reads the old value (`stale_read_order_matters`, reproduced on the engine). Measure whether any committed scenario's cascade has such a fact, and decide whether readiness should also wait for every unrun in-band producer of an input (then the chosen order is producer-first and `cascade_perm` covers it), with a regression on the cascade scenarios either way. ([detail](#cascade-registration-order-2026-11-25))
- **P3** · R3 · Non-finite steps beyond the per-call count: `nonFiniteSteps` is returned to the calling scenario only. Decide whether a run-level counter belongs in provenance (beside the hook/predict counters) and whether the engine trace should warn on the first such step, conditionally serialized so unaffected configs keep their hashes. ([detail](#non-finite-steps-counted-2026-11-23))
- **P3** · R8 · Split inequality under the affine fallback: `split_le_parent` and `split_le_parent_ridge` cover full-basis (ridge) minimisers, but `DomainLearner` fits a side with fewer than four rows per quadratic coefficient on the affine part only, a minimiser over a subspace, so that side's error may exceed the parent's full-basis fit. Measure how often it happens on recorded learner calls and decide whether the gate should compare like with like. ([detail](#learner-gate-and-ridge-split-2026-11-23))
- **P3** · R3 · Covered joint distance: a covered input reports the first covering centre's distance, not the nearest (`covered_distance_not_min`; 0.20 apart in the conformance grid). The hooks guide documents this, but stage records and the Studio show `jointDistance` with no such label; decide whether a covered record should carry it as an upper bound or compute it in full (measure the cost first). ([detail](#joint-coverage-scan-2026-11-25))
- **P3** · R8 · Reals vs floats: bridge Mathlib's `ℝ` theorems to IEEE-754 kernels with stated error bounds, interval arithmetic or a rounding-model proof; until then label every Lean verdict as covering the real-valued statement only. ([detail](#route-opened--2026-11-22))
- **P3** · R3 · Leader ranking on shared calls: `decayedMean_needs_common_calls` shows that the leader (decayed mean log error over the calls each method predicted in) can rank a method that abstains on easy calls behind one it beats on every shared call; `decay.needs_common_calls` reproduces it on the engine. Measure how often methods abstain on recorded `ctx.evolveField` and operator runs, and decide whether the leader should rank on calls (or rows) every candidate predicted, as `rmse_common` already does, with a regression on the lamp and furnace either way. ([detail](#decayed-prequential-scores-2026-11-23))
- **P3** · R8 · Lean CI beyond this machine: the toolchain, cache and `trech_formal_lean_build` are verified on macOS arm64 only; check Linux and decide whether CI runs the Lean check. ([detail](#proofs-compiled-and-audited--2026-11-22))
- **P3** · R8 · Better Mathlib search now that Mathlib is built: `exact?`/`apply?`/Loogle-style queries in place of the grep, so equivalent statements under other names are found. ([detail](#route-opened--2026-11-22))
- **P3** · R5 · Geant4 secondary track: Lean statements of Geant4's basic laws (two-body kinematics, the Compton relation from four-momentum conservation, exponential attenuation, energy conservation in `SampleSecondaries`), attached through derived classes in shadow mode (inheritance preferred; `patches/geant4/` only for non-virtual code). Observation first; any replacement needs byte parity or a validated tolerance, a regression against the unpatched build and the owner's go-ahead. ([detail](AGENTS.md#geant4-secondary-track))
- **gated** · R8 · Owner decision: whether to add a physics-specific Lean library (for example PhysLean) as a further reference checkout, so physical laws are also checked against it before being declared.
- **gated** · R8 · Owner decision: when (if ever) Lean stops being optional for a given path.

## Lift lineage and weights (2026-11-26)

- [x] `Trech.Methods.Group` (law `group.lift_lineage`): `raise` (one level's flag rule: the
  group's own check or any flagged member), `liftFlag` (any depth), `liftFlag_iff` (a flag at
  any depth is a flagged base element under the group or a level's own flag),
  `flag_of_descendant`, `not_flag_no_descendant`, `liftFlag_false` and `liftFlag_no_local`.
  The same rule covers `valid`, `inDomain` and `starved`. Audit 109/109.
- [x] Classic side fixed: a group blocked by overflow or a blocked member skipped its lineage
  flags and reported `inDomain: true`, `starved: false` even with an out-of-domain or starved
  member. `GroupHierarchy::run` now sets both flags before blocking; inference counters still
  count evaluated groups only.
- [x] Weights (closes the P3 queued by the recursion record): `GroupHierarchy::run` refuses a
  non-finite or non-positive weight (`stopReason` and every level's `skipReason`
  `invalid_weight`), `ctx.lift` throws a `RangeError` naming the element, and
  `trech_torch.hierarchy.build_structure` raises `ValueError`. Measured first: no committed
  scenario passes `weight` to `ctx.lift` (`particle_observer_cascade` uses the default 1).
- [x] Conformance (`trech_formal_laws`): 3 fixture cases × 5 variants (three outliers, one
  overflowing cell, overflow plus an outlier in the same block): 4,560 element–ancestor pairs,
  129 flagged, none lost; 18 top checks with quiet upper levels exact. Reverting the engine fix
  fails three checks (3 blocked groups read in domain). Zero, negative and NaN weights refused.
  Regressions: `trech_js_runtime` (the `RangeError`), `trech_group_hierarchy_py` (the trainer).
- [x] Docs: the group-lifting contract and the inference handbook said no scenario uses
  `ctx.lift`; `particle_observer_cascade` does, corrected.

## Lift recursion to any depth (2026-11-26)

- [x] `Trech.Methods.Group` (law `group.lift_recursion`): `sum_members_comp` (two levels group
  a base element by its composed key, from Mathlib's `Finset.sum_fiberwise_eq_sum_filter`),
  `groupWeight_comp`, `groupMoment_comp` and `centroid_comp` (non-negative weights: a group of
  zero weight then has zero moment, so no nonzero-weight hypothesis is needed under Lean's
  `x / 0 = 0`). Any depth, as a list of keys over the base index type (the engine numbers a
  level's groups below its element count): `ancestor_unique`, `liftWeight_eq`,
  `sum_liftWeight`, `liftMoment_eq`, `liftPos_eq_centroid`, `sum_liftMoment` and
  `liftWeight_pos` (positive base weights leave no occurring group of zero weight, so the
  classic code never writes its NaN centroid). Audit 104/104.
- [x] Classic side unchanged; `GroupHierarchy.cpp` cites the theorems at the level loop.
- [x] Conformance (`trech_formal_laws`): the three-level fixtures and the explicit first level,
  268 groups over 18 levels. Each base element's ancestor is composed from the recorded
  parents; level weights equal the ancestor sums (2.8e-14 absolute), centroids from the
  second level up equal the base centroids (1.8e-15), all 804 position components are finite.
  Negative control: the unweighted mean of the lower centroids misses by up to 0.33.
- Not covered: zero or negative weights (refused since the lineage record above), and floating-point rounding (the
  recursion re-rounds every level; the checks bound it empirically).

## Per-feature domain and occupancy bins (2026-11-26)

- [x] `Trech.Methods.Domain`: `extrap_nonneg`, `extrap_eq_zero_iff` (with a non-negative
  tolerance, `extrapolation` is 0 exactly when every excess `|z| - radius` is within it, the
  `inDomain` verdict), `le_extrap`, `extrap_attained`, `extrap_mono`; `correct_spec` (numpy's
  one-bin correction of a guess at most one bin off gives a containing bin; no monotonicity
  needed), `bin_unique` (monotone edges) and `training_value_not_starved`.
- [x] Classic side fixed: the engine indexed bins by `(x - lo) / (hi - lo) * n` alone, which lands
  one bin up within about one ulp below an edge, while training counts with `numpy.histogram`
  (which corrects against its linspace edges). A training value there read as the next bin and,
  when that bin was empty, as starved. `GenericSurrogate::occupancyBin` now applies numpy's
  correction; `ArchitectureGenerator` (C++ trainer counts) and `validate_model.occupancy_bins`
  use the same rule. Exported models need no change.
- [x] Conformance (`trech_formal_laws`): 4,000 four-input samples, verdict, named inputs and
  extrapolation exact, scaling out never lowers it; 129,243 edge-adjacent and interior values
  over 3,000 ranges all in a containing bin, guesses never more than one off, the uncorrected
  index outside its bin on 13,393 (negative control); training values beside edges never
  starved, both empty bins flagged. `trech_occupancy_bins_numpy`: the engine's and validator's
  bins equal `numpy.histogram`'s on every sampled value.
- [x] Non-finite inputs (same day): a NaN input's excess never compared above the tolerance, so
  it read as in domain. The engine now names a non-finite input out of domain with infinite
  `extrapolation` and `maxStandardizedDeviation`; `nonfinite_out_of_domain` and
  `extrapN_eq_zero_iff` cover it (`Option ℝ` excesses, `WithTop ℝ` extrapolation). Conformance
  `domain.nonfinite`: NaN, `+∞` and `−∞` in each of four slots. Audit 94/94. The validator
  already treated NaN as outside the hull.

## Joint coverage scan (2026-11-25)

- [x] `Trech.Methods.Coverage`: `partialBreak_spec` (with non-negative terms the pruned sum is
  the full sum or lies between the best so far and it), `pruned_lt_iff`, `foldl_step_covered`,
  `scan_spec` (from a best above the radius the early-stopping scan is covered exactly when
  some centre's full distance is within it, and a starved scan's best is the minimum) and
  `covered_distance_not_min`. Audit 84/84.
- [x] Classic side unchanged; `GenericSurrogate.cpp` cites the pair at the joint check.
- [x] Conformance (`trech_formal_laws`, Debug and Release): 48 centres in 3D, 1,183 grid inputs
  (276 covered, 907 starved) against a full scan: verdicts identical, starved distances bit
  identical; covered distances differ from the minimum (negative control, 0.20 at worst).
- Not covered: a non-finite input's joint distance (a NaN distance never compares below the
  best, so the input reads as starved with an infinite distance). Since 2026-11-26 such an input
  is also out of domain per feature, so the verdicts agree.

## Cascade registration order (2026-11-25)

- [x] `Trech.Methods.Cascade`: a context maps fact names to optional values; a stage reads and
  writes declared facts and predicts only from what it reads (readiness included).
  `run_of_notMem`, `run_of_mem`, `run_comm` (disjoint writes, neither reads the other's),
  `runAll_move_front`, `runAll_perm` (two producer-first orders of a band agree, by moving the
  first stage of one order to the front of the other), `cascade_perm` (a permuted registration
  permutes each band's stages only, via `List.Perm.filter`), `rivals_order_matters` and
  `stale_read_order_matters`. No real arithmetic: every order evaluates the same models on the
  same inputs, so the agreement is exact in doubles too. Audit 79/79.
- [x] Classic side unchanged; `ScaleCascade.cpp` cites the pair at the band sort and states when
  the ready-stage choice is producer-first.
- [x] Conformance (`trech_formal_laws`, Debug and Release): nine `tanh` stages over nano, micro
  and meso with in-band and cross-band dependencies, registered in 240 orders: facts bit
  identical (2,640 values), every stage after its producers (2,160 checks); a seeded fact
  replaced in-band (stale read) and two rival writers each change the result (negative
  controls).
- Mathlib advanced to `348837d` and lean4 to `451d44e` in the same change (cache fetched; the
  earlier files compile unchanged).
- Not covered: that the greedy choice is producer-first (checked, not proved; it is not under a
  stale read, queued); rival arbitration at band end; `maxStages`/`targetOutputs` limits, which
  depend on order by design.

## Domain routing (2026-11-23)

- [x] `Trech.Methods.Route`: a routing tree of Boolean tests; `route_mem_ids`, `mem_region_iff`,
  `regions_disjoint`, `regions_cover`, `card_routed` (via `Finset.card_eq_sum_card_fiberwise`),
  `route_replace`, `split_keeps_other_rows` and `merge_keeps_other_rows`. Audit 71/71.
- [x] Classic side: `route` and the split's redistribution of buffered rows now call one
  non-inlined `goesLeft`, so a buffered row sits in the leaf a fresh copy of it is routed to
  (before, two loops computed the same dot product; the compiler was free to round them
  differently in an optimised build).
- [x] Conformance (`trech_formal_laws`, Debug and Release): 80 calls, 9 splits, 5 merges, 32,000
  rows; every check passes, and a negative control requiring every row to keep its domain fails
  on the 1,149 rerouted rows.
- Verification: Debug CTest 80/80; Release formal and learner tests 6/6. `glass_from_sand`
  (Release, budget pinned) emits and scores byte-identical before and after.
- Not covered (the reals-vs-floats item tracks it): the floating-point test itself (`direction · x ≤ threshold`), modelled as an
  arbitrary Boolean predicate; rows with a non-finite feature are not routed (domain `-1`).

## Relative tolerance in law records (2026-11-23)

- [x] `LawCheck.relativeTolerance` (C++) and `relative_tolerance` (JS records, read back by
  `__TRECH_FORMAL_RECORD`): set by `checkAgreement`, merged by maximum, written to `law_checks`
  only when nonzero so every other record keeps its bytes. Records of agreement checks with a
  relative bound (the Compton companion's `compton.edge_at_backscatter`,
  `attenuation.memoryless`) gain the field.
- [x] `trech_formal_laws` run-record section: two engine agreements merge to the larger bound, a
  bounds check has no field, and a JS Compton record carries `1e-15` through the runtime.
- Verification: Debug CTest 80/80.

## Attenuation at Geant4's coefficient (2026-11-23)

- [x] `memorylessAtCoefficients` (`include/trech/sim/AttenuationLaw.hpp`): survival memorylessness
  at each available `beer_lambert` check's Geant4 `μ` over ten cuts of its path; `RunAction`
  records it as the engine check `attenuation.memoryless` at run end. Observe-only; runs without
  a `beer_lambert` check keep their bytes.
- [x] Why the engine and not the companion: the companion runs before Geant4 builds its tables,
  so it cannot know `μ`.
- [x] `analytic_beer_lambert` family gate adds `engine_laws_recorded` and `engine_laws_hold`; a
  real Release run (μ = 0.01704/mm, 50 mm) passes 6/6 with a largest error of 5.6e-17;
  `trech_scenario_contracts` covers pass, a failed record and a missing record.
- Tests: `trech_formal_laws` (two coefficients, a split-sum negative control), Debug CTest.
- Known at landing: `checkAgreement` stored only the absolute tolerance; fixed the same day
  (record below).

## Band order (2026-11-23)

- [x] `Trech.Methods.Band`: a stage writes a set of working slots and adds rates, both computed
  from the working vector it reads. `apply_comm` (disjoint writes, neither reads the other's
  writes), `rateOnly_comm`, `foldRateOnly` (a rate-only band adds the sum of its rates),
  `rateOnly_perm` (any reordering, via `List.Perm.sum_eq`) and `order_matters` (a concrete
  assignment read by a rate). Audit 63/63.
- [x] Classic side unchanged; `StateEvolution.cpp` cites the pair at the band sort.
- [x] Conformance (`trech_formal_laws`, Debug and Release): two rate stages swapped are bit
  identical; three in four orders within `1e-15` (4.4e-16 seen, the float order of a
  three-term sum); two disjoint assigners swapped bit identical; an assignment read by a rate
  stage moves the result by up to 0.27 when swapped (negative control).
- Not covered: assignments across *different* bands (ordered by scale, not registration) and
  intermediates shared between bands, which the cascade item takes up.

## Non-finite steps counted (2026-11-23)

- [x] Decision for the P3 non-finite-rate item: count and report, never reject or repair. A NaN
  rate still yields a NaN state and an overflowing increment still lands on its bound (no
  behaviour change); `nonFiniteStep` (`ml/BoundedStep.hpp`) marks a step whose increment is not
  finite or whose result is NaN, and `ctx.evolve` and `ctx.interact` return the count as
  `nonFiniteSteps`. Rejecting would abort runs whose learned operator extrapolates; repairing
  would hide it.
- [x] Tests: `evolve.non_finite_steps_counted` (rate `1e308`, `dt` 10: both elements land on the
  upper bound of `[0, 1]`, the unbounded field goes to `-inf` and to NaN from `+inf`, count 4)
  and `pair.non_finite_steps_counted` (two links: count 2, the shared element's opposite rates
  cancel exactly before `dt` and it keeps its value) in `trech_formal_laws`; a finite
  `ctx.evolve` call reports `nonFiniteSteps: 0` at the JS boundary (`trech_js_runtime`).
- Verification: Debug CTest 80/80.
- Found in a Release (V8) build: `StateEvolution.cpp` and `PairInteraction.cpp` were not
  compiled with `-ffp-contract=off`, so `x + r·dt` fused into one FMA. That broke
  `evolve.bounded_step_within_bounds` and `evolve.unclipped_step_exact` by 1 ulp (failing in
  every optimised build since the bounded-step change; the Debug runs could not show it) and
  turned `inf − inf` into `inf`. Both sources are now pinned like the other engine ML sources.
  Release CTest 80/80, V8 focused set 4/4. Effect on `glass_from_sand` (Release, budget
  pinned): the physical state moved by at most 1 ulp (`mean_temperature_k`, once in 150
  frames); only the validation companion's field-evolution grading emits shifted further, as
  they already do between two runs of one binary. `lava_lamp` unchanged. No reference media
  regenerated.
- Queued: a run-level counter and trace warning.

## Decayed prequential scores (2026-11-23)

- [x] `Trech.Methods.Decay`: `decayed_eq_sum` (the fold of `s ← λs + x` is `Σ λ^(T−1−t) x_t`, by
  `Finset.sum_range_succ`), `decayed_mono`/`decayed_nonneg` (`λ ≥ 0`), `decayedMean_le` and
  `decayedMean_lt` (on shared calls a method no worse on every call ranks no worse, strictly
  with one strictly better weighted call and `λ > 0`, via `Finset.sum_lt_sum`), and
  `decayedMean_needs_common_calls` (a concrete inversion when the call sets differ). Mathlib has
  no moving-average statement. Audit 58/58.
- [x] Classic side routed through one function: `decayedUpdate` (`include/trech/ml/DecayedScore.hpp`)
  now advances every decayed `MethodArbiter` score (`ew_sq`, `ew_n`, `ew_log`, `ew_calls`, the
  policy score and totals, the error learners' uncertainty), with the same operations under
  `-ffp-contract=off`. `ctx.evolveField` selects its methods through this arbiter.
- [x] Conformance (`trech_formal_laws`): the fold over 120 values at four forgetting factors
  against the closed form (1.8e-14 seen); the arbiter's exported `ew_log`/`ew_calls` against the
  closed form of its recorded call RMSEs, exactly; a dominant method leads although the fallback
  is its rival; the abstaining case does not lead; an undecayed fold fails on purpose.
- Verification: Debug CTest 80/80; Lean audit 58/58; law pairs 15/15. `lava_lamp` and
  `glass_from_sand` (both select `ctx.evolveField` methods through the arbiter) byte-identical
  before and after with `TRECH_COMPUTE_BUDGET` pinned, apart from output paths and the formal
  source hashes.
- Closes the P3 "arbiter ranking across calls" item: the ranking preserves dominance on shared
  calls and nothing more. Queued: whether the leader should rank on shared calls.

## Learner gate and ridge split (2026-11-23)

- [x] `Trech.Methods.LeastSquares.split_le_parent_ridge`: with per-side ridge terms the split's
  error exceeds the parent's at a shared `β` by at most `(λL + λR)‖β‖²`.
- [x] `bicGate_iff` (`Real.log_lt_iff_lt_exp`) and `bicGate_rejects` (`Real.log_nonneg`): the
  gate is the threshold `S < S₀ exp(−pen/n)` and never accepts a split that does not lower the
  error. The gate moved into `bicSplitAccepted` (`ml/LeastSquaresStatistics.hpp`), the same
  expression. Audit 52/52.
- [x] Conformance: ridge bound on 9 cuts with the learner's per-side scale; the gate against the
  threshold on 60 grid cases (three exact-boundary cases skipped for rounding) and rejecting all
  15 non-improving ones.
- Verification: Debug CTest 80/80; Lean audit 52/52.
- Residual narrowed: the affine fallback for small sides (queued).

## Domain-learner split score (2026-11-23)

- [x] `Trech.Methods.LeastSquares`: `sse_eq_stat` (weighted error from `A`, `b`, `c` for any β,
  by `Finset.sum_comm` and `Finset.mul_sum`), `gram_union`, `moment_union`, `yy_union`
  (`Finset.sum_union`) and `split_le_parent`. Audit 49/49.
- [x] Classic side: the batched score moved from a lambda in `scoreCuts` to
  `sseFromStatistics` (`include/trech/ml/LeastSquaresStatistics.hpp`), same tensor operations.
- [x] Conformance (`trech_formal_laws`): 240 weighted rows, quadratic basis, two targets, 9 cuts
  scored in the learner's batched prefix/total form; statistic score within `1e-12·c` of the
  direct error (6.5e-16 seen), statistics additive within `1e-12 + 1e-13` relative, exact side
  fits never above the parent; a sign error fails on purpose.
- Mathlib advanced to `90e6eec` in the same change (cache fetched, no renames, manifest
  unchanged).
- Residual queued: the inequality under the learner's per-side ridge and affine fallback.

## Group assembly (2026-11-23)

- [x] `Trech.Methods.Group`: `mem_group_unique` (each element lies in the fibre of its key and no
  other), `sum_groupWeight` (Mathlib's `Finset.sum_fiberwise_of_maps_to`),
  `groupWeight_mul_centroid` and `sum_weight_centroid` (the weighted first moment carries over
  when no group weighs zero). Audit 44/44.
- [x] Conformance (`trech_formal_laws`) on `GroupHierarchy::run`: the three-level lift fixtures
  with unequal member weights, and with an explicit first level (groups of four by index), 18
  levels: parents unique and matching `memberCount`, weights within `1e-14` relative (2.8e-14
  absolute seen), moments within `1e-13` (2.3e-13 absolute on moments of order 10). A
  zero-weight group (NaN centroid, the excluded case) fails on purpose.
- Verification: Debug CTest 80/80; Lean audit 44/44. No engine behaviour changed (a citing
  comment only).
- The engine does not check these at run time; `ctx.lift` results carry the weights and
  positions, so a companion could record them (see the P3 companions item).

## Set-network order independence (2026-11-23)

- [x] `Trech.Methods.SetPool`: `sumPool_perm`, `presentCount_perm` and `meanPool_perm` (from
  Mathlib's `Equiv.sum_comp`), `presentImage_perm` (the set of present images, which a max pool
  reduces), `sumPool_update_absent`, `deepSets_perm` and `mpnnRound_perm` (one message-passing
  round is permutation equivariant; the state may carry the raw features, covering relative
  features). Presence is a predicate on each element's own features, as the engine reads it from
  the raw mask. Audit 40/40.
- [x] Hypothesis enforced: `GenericSurrogate` now fails closed on a `generic_surrogate_v3` set
  network whose element slots differ in `input_mean`/`input_std`. All nine committed set models
  (three furnace conduction models, three group-hierarchy and two set-network fixtures) tie
  them exactly.
- [x] Conformance (`trech_formal_laws`): the DeepSets and MPNN fixtures and four pool/aggregate
  variants, 11 rows under all 24 orders of four element blocks (264 samples each): DeepSets max
  exact, sums within `1e-12` relative (4.4e-16 seen); moving an absent element's features
  changes nothing, bit for bit; the untied-slot model is refused with its note.
- Verification: Debug CTest 80/80; Lean audit 40/40.
- Not covered by the proof: the float rounding of a sum pool in a different order, which the
  theorems (over a commutative monoid) leave aside; tracked by the reals-vs-floats queue item.

## Bounded explicit step (2026-11-23)

- [x] `Trech.Methods.Evolve`: `clampBounds_eq_projIcc` (the classic lower-then-upper clamp is
  Mathlib's `Set.projIcc` for `lo ≤ hi`), `boundedStep_mem` (the step lands in `[lo, hi]` from
  any start and rate), `boundedStep_of_mem` (an inside step is not clipped, from
  `Set.projIcc_of_mem`), `eulerStep_smul_dt` (the increment is linear in `dt`) and
  `eulerStep_add_dt` (two steps at one rate equal one of the summed length). Audit 33/33.
- [x] Classic side routed through one function: `boundedEulerStep`/`clampToBounds`
  (`include/trech/ml/BoundedStep.hpp`) now carry the `ctx.evolve` field step and the
  `ctx.interact` link and element clamps, with the same operations as before.
- [x] Hypothesis enforced: `ctx.evolve` fields and `ctx.interact` `fields`/`pair_fields` throw a
  `RangeError` when `min <= max` fails (inverted or NaN), tested in `trech_js_runtime`.
- [x] Conformance (`trech_formal_laws`): 41 elements driven across a two-sided and a one-sided
  bound; all in bounds and equal to the clamp, 62 unclipped steps exact, `dt` scaling within
  `1e-15` absolute plus `1e-14` relative (4.4e-16 seen), two steps of `dt` equal to one of `2dt`
  bit for bit here; a negative control shows unordered bounds breaking the lower bound.
- Verification: Debug CTest 80/80; Lean audit 33/33 at landing. `glass_from_sand` (domain and
  declared grouping) byte-identical before and after with `TRECH_COMPUTE_BUDGET` pinned (unpinned,
  only its `field_evolution` emits vary, as between two runs of one binary); `polyurethane_foam`
  and `testscenario_efflux` run without a bounds rejection.
- Residuals queued: non-finite rates, and the Mathlib pin advance whose cache refresh was not
  run.

## Compton from four-momentum (2026-11-22)

- [x] `Trech.Laws.TwoBody`: `compton_invariant` (`m(E − E′) = E E′ − ⟪k, k′⟫` from energy and
  momentum conservation and the electron's mass shell, over any real inner-product space) and
  `compton_relation` (the angle form). No Compton or four-momentum statement in Mathlib;
  `norm_sub_sq_real` does the vector step. Audit 28/28.
- [x] Classic side: `scatteredEnergyRatio` (`KleinNishina.hpp`) is the relation; the new
  `relativeMomentumResidual` (`EnergyBalance.hpp`) checks the theorem's momentum hypothesis on
  each first Compton scatter whose products are all tracks (photon survives, nothing deposited)
  and records the engine check `compton.momentum_balance` (`kind: hypothesis`).
- [x] Stated float bound `momentumRoundingBound`: the electron momentum comes from `T = E − E′`,
  so its rounding grows like `√(m / 2T)`. At `ε = 10⁻⁴` the flat `1e-12` misses (2.7e-12
  measured, 1.6e-12 predicted by the model); a negative control keeps that visible.
- Verification: Debug CTest 80/80. A 20,000-event Geant4 run checked 16,420 of 16,423 scatters
  (three deposited their electron on the spot) with a largest residual of 3.7e-15 against a
  largest bound of 1.09e-12, output otherwise unchanged. Family gate 25/25.
- Found while landing it: the previous change's new Compton family checks were not reflected in
  the `trech_scenario_contracts` fixture (the CTest run preceded the companion edit). The fixture
  now carries the fields and covers each new failure.

## Geant4 step energy balance (2026-11-22)

- [x] `Trech.Laws.EnergyBalance` states `E_pre + Q = E_post + ΣT_i + d` as a zero residual, bounds
  the outgoing particle and each secondary by `E_pre` when `Q = 0`, and proves that balanced
  steps telescope along a track (`Finset.sum_range_sub'`). Four theorems listed; the audit
  passes 26/26 with standard axioms only.
- [x] Classic side `sim/EnergyBalance.hpp` (`relativeResidual`, Neumaier sum, NaN on non-finite
  input). `SteppingAction` reads it on each primary photon's first Compton scatter; `RunAction`
  records the engine check `energy.step_balance` and two analytic-check fields only when a
  `compton_energy_transfer` check is configured.
- [x] Conformance: 410 modelled Compton steps, a gamma conversion with `Q = −2 m_e c²`, a
  41-step telescoping track, a dropped-electron negative control and non-finite input.
- Verification: Debug CTest 80/80; Lean audit 26/26. A 20,000-event Geant4 Compton run read
  16,423 scatters, largest relative residual `4.2e-17`, no violations, and differed from the
  previous build's 20,000-event output only in the new fields. The family gate passes 24/24 and
  fails the pre-change output on the six law-check entries.

## Operator conservation (2026-11-22)

- [x] Added Lean statements for declared integer conservation and atomic count bounds in
  `ctx.react`, plus exchange of equal-and-opposite rates and increments in `ctx.interact`.
  Checked all 22 theorems against the standard axioms on the pinned Mathlib toolchain.
- [x] Classic conformance covers acceptance, availability and signed 64-bit overflow, early
  rejection of an unbalanced channel, and two antisymmetric links sharing a member. Pair
  conformance uses `1e-15` relative tolerance and verifies that clipping changes the total.
- Verification: Debug CTest 80/80 and the focused V8 set 3/3. The Geant4 Compton smoke accepted
  the new audit identity for all recorded checks and kept 200-event scores byte-identical with
  and without the audit.

## Route opened — 2026-11-22

- [x] `thirds/lean4` (`5ec4e0be17`) and `thirds/mathlib4` (`6ebcce3733`) added as shallow
  submodules tracking `master`. Mathlib expects `leanprover/lean4:v4.37.0-rc1`.
- [x] [`scripts/pull_lean.sh`](../../../scripts/pull_lean.sh): pull-before-use for both checkouts
  plus the toolchain check; [`scripts/lean_mathlib_search.py`](../../../scripts/lean_mathlib_search.py):
  grep of Mathlib declaration headers.
- [x] Handbook rules: Lean optional, classic + Lean pairs, Mathlib first, building gated, Lean
  off the decision path and off the hot path, reals vs floats, Geant4 secondary track.
- [ ] Nothing is built, linked or run; every item above is open.

## First law pairs — 2026-11-22

- [x] `formal/` Lake package (Mathlib by path, `lean-toolchain` = Mathlib's `v4.37.0-rc1`) with
  `Trech.Laws.Compton` (T/E within [0, edge], equality at back-scatter), `Trech.Laws.Attenuation`
  (survival multiplicative, in (0, 1], decreasing) and `Trech.Methods.Lattice` (TRT collision,
  zero-sum source and bijective streaming conserve the total). Mathlib lemma names were checked
  against `thirds/mathlib4` `6ebcce3733`; compiled the same day (record below).
- [x] Classic side: `trech::formal` checks in `trech_core`, `js/trech_formal_laws.js`, Lean
  citations in `KleinNishina.hpp`, `AnalyticCrossCheck.cpp` and `LatticeKinetic.cpp` (comments
  only; no behaviour change), `formal/laws.json`.
- [x] Tests: `trech_formal_laws` (all pairs pass; negative controls fail as intended; C++ and
  QuickJS Compton values bit-identical) and `trech_formal_law_pairs`. Opt-in
  `TRECH_ENABLE_LEAN_CHECK` registers `trech_formal_lean_build`.
- [x] Finding: the attenuation identity is exact over `ℝ` but off by ~2 ulp in doubles; the
  check states a 2e-15 relative tolerance and an exact-equality negative control records the gap.
- [ ] Open: provenance fields, engine call sites and the
  next inventory items, all queued above.

## Proofs compiled and audited — 2026-11-22

- [x] Owner go-ahead for the toolchain gate. `brew install elan-init` (elan 4.4.0),
  `elan toolchain install leanprover/lean4:v4.37.0-rc1` (commit `0b77e12952`, the tag the pull
  script resolves), `lake exe cache get` in `formal/` (9,135 Mathlib files, 6.9 GB in ignored
  `thirds/mathlib4/.lake`; Mathlib's dependencies in ignored `formal/.lake/packages`, pinned
  by the committed `formal/lake-manifest.json`).
- [x] `lake build`: 3,197 jobs. The only failure on first build was `relaxTRT`, which divides
  reals and had to be `noncomputable`; every proof compiled as written. The files then moved
  to the module system and off the deprecated `Mathlib.Data.Real.Basic` import
  (`Mathlib.Basic.Real.Basic`); the build has no errors and no warnings.
- [x] Axiom audit (`scripts/check_lean_laws.py`): all nine declarations in `laws.json` depend
  only on `propext`, `Classical.choice`, `Quot.sound`. The opt-in CTest
  `trech_formal_lean_build` (`TRECH_ENABLE_LEAN_CHECK=ON`) passed in `build/rel` (12 s); the
  option was then set back OFF there.
- [ ] Verified on macOS arm64 only; other platforms, and the audit after the next Mathlib pull,
  are untested. The proofs cover the real-valued statements, not the float kernels (queued above).

## More law pairs and the first engine check — 2026-11-22

- [x] Pulled both Lean checkouts first (`scripts/pull_lean.sh`: no movement, lean4 `5ec4e0be17`,
  mathlib4 `6ebcce3733`). Mathlib searched for each statement: it has `Real.log_lt_log_iff` and
  the measure-theoretic `ProbabilityTheory.variance` lemmas, but no finite weighted
  "mean minimises the squared score" and nothing on the two-stage draw, so both are stated here.
- [x] `Trech.Methods.Transition` (5 theorems): `stepProbability h s c = h·s c/∑ s` is
  nonnegative, sums to `h`, leaves `1 − h ≥ 0`, equals `s c` in direct mode, and
  `channelDraw_lt_iff` is the inverse-CDF step. Classic side: the draw in
  `DiscreteTransition::react` moved verbatim into `selectTransitionChannel` (same operations in
  the same order, so RNG and results are unchanged; every CTest passed after it).
- [x] `Trech.Methods.Arbiter` (4 theorems): bias–variance split of the weighted squared score,
  the mean minimises it (strictly for positive weight), `log(error + floor)` keeps the order.
- [x] `Trech.Methods.Lattice.advectedEquilibrium_sum`: the scalar equilibrium carries the cell
  value; with the existing collision and streaming theorems it gives the scalar-lattice pair.
- [x] Engine call site: `Lattice::checkLaws` (end of `build()`), stored in `lawChecks()` and
  traced at info under `formal` (warn when a check fails). Moving walls and Dirichlet links
  record "not conservative by design".
- [x] Conformance (`trech_formal_laws`): `selectTransitionChannel` over 2^20 grid draws in four
  hazard/score cases matches `h·s_c/S` within 2/2^20 (8.7e-7 seen); the arbiter with a biased
  fallback ends with the unbiased method leading and lowest in `rmse_common`; a walled D2Q5
  lattice with an obstacle and prescribed advection keeps its total over 400 steps (1.6e-14
  relative seen, 1e-13 allowed) while a Dirichlet copy does not (negative control).
- [x] Audit: 19 distinct theorems (shared ones now audited once), all on the standard axioms;
  `--report` writes `trech_lean_audit_v1`. Full CTest in `build/rel`: 80/80 passed.
- [ ] Open: the provenance and output location (draft below), the next inventory items, and
  the arbiter's cross-call ranking, all queued above. Verified on macOS arm64 only.

## Provenance design draft — 2026-11-22

Approved by the owner and implemented the same day (record below); kept as the design of record. It answers the P1 item: what a run records
when it performs a law check, and where the records go.

1. **Run outputs.** A run that performs at least one law check writes a `law_checks` array in
   its `run_end` record of `trech_scores.jsonl`: one `LawCheck` JSON each (the current
   `toJson()` shape plus `origin`: `engine` for `Lattice::checkLaws`, `validation` for a
   companion's `TRECH_FORMAL_LAWS` call). A run without checks writes no key, so existing
   outputs keep their bytes. Lattices built several times in a run record each distinct check
   once, with a count.
2. **Provenance.** The same run adds a `formal` object to its provenance record, again only when
   a check ran: the SHA-256 of `formal/laws.json`, the declarations cited by its checks and,
   when an audit report is supplied (`--formal-audit PATH` or `TRECH_FORMAL_AUDIT`), that
   report's `lean_version`, `toolchain`, `mathlib_revision`, module hashes and `passed`. Without
   a report, `lean_status` stays `not_checked_by_this_check`; the run never invokes Lean.
3. **Config.** No config field: law checks are not a scenario choice and must not change the
   config hash. A companion's checks are part of the validation companion, which already sits
   off the decision path.
4. **Companion output.** A validation companion that wants recorded verdicts gets an
   executable hook (for example `onValidate(ctx)` beside its JSON contract) whose returned
   `LawCheck` records land in `law_checks` with `origin: "validation"`. It runs under the
   `validation` trace role and cannot emit physical fields.
5. **Tests.** Round-trip: a scenario without checks keeps its config hash and output bytes; a
   lattice scenario gains only `law_checks` and `formal`; strict replay stays byte-identical.

## Law checks in run outputs — 2026-11-22

- [x] Owner approved the design draft above. `formal::recordRunCheck`/`takeRunChecks` keep a
  thread-safe run record, merged by (origin, law, declaration) so the result does not depend on
  thread order; `TrechRunAction::EndOfRunAction` drains it after `onRunEnd` into `law_checks`
  (run_end scores) and `formal` (run_end provenance, `trech_formal_provenance_v1`). Both are
  written only when a check ran; no config field.
- [x] Identity: CMake embeds the SHA-256 of `formal/laws.json` and one hash over it and every
  Lean module (`sources_sha256`, also computed by `check_lean_laws.py`). `--formal-audit` /
  `TRECH_FORMAL_AUDIT` attach a `--report` file; `lean_status` is `audited` only when it matches
  both hashes, passed and lists every cited declaration on standard axioms
  (`audit_mismatch`, `audit_incomplete`, `audit_unreadable`, `not_checked_by_this_run` otherwise).
- [x] Sources: `Lattice::checkLaws` reports with origin `engine`; `TRECH_FORMAL_LAWS.record`
  (QuickJS and V8, `__TRECH_FORMAL_RECORD`) with origin `validation`, accepting only the
  library's own records. `analytic_compton_transfer.validation.js` records its Compton checks
  (eps grid including 662 keV) under the `validation` role; its family gate adds
  `formal_laws_recorded` and `formal_laws_hold`. The companion still loads on a binary without
  `TRECH_TRACE` (the stale `build/dev` one), where recording is a no-op.
- [x] Verified: `trech_formal_laws` (merging, provenance grading of missing, unreadable,
  stale, partial and matching audits, JS recording and rejection, embedded hash recomputed from
  the tree) and `trech_scenario_contracts` (gate passes, fails on a failing or missing record).
  A 200-event Compton run: `law_checks` has 2 validation records, `lean_status` `audited` with
  the report and `not_checked_by_this_run` without, scores byte-identical either way, and
  identical `law_checks` under V8. CTest: `build/rel` 80/80, `build/v8` 89/89 (`TRECH_JS_ENGINE=v8`).
- [ ] Open: more companions recording checks (queued above). `audited` covers the real-valued
  statements only (the reals-vs-floats item). macOS arm64 only.

