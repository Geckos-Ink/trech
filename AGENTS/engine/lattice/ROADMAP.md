# Lattice methods and field-evolution arbitration — roadmap

[Root principles](../../../AGENTS.md) · [Root roadmap](../../../ROADMAP.md) · [Parent](../ROADMAP.md) · [Handbook](AGENTS.md)

Related owners: [Learned state and pair operators](../operators/ROADMAP.md) · [Water and fluid comparisons](../../scenarios/fluids/ROADMAP.md) · [Lava lamp thermofluid](../../scenarios/fluids/lava/ROADMAP.md) · [Scenario law migration ledger](../../scenarios/migrations/ROADMAP.md).

Maintain work in its owning branch. Dated results apply to the recorded checkout; they do not validate subsequent changes.

## Priority queue

Every open item of this branch, highest priority first. The dated records below are delivery
history: the "Residual" and "Next" notes inside them are tracked here, and this queue wins
where they disagree. Keys and route steps: [priority keys](../../ROADMAP.md#priority-keys) ·
[implementation route](../../ROADMAP.md#implementation-route). When an item lands, delete it here, add a
dated record below, and queue its residuals in the same change.

- **P1** · R3 · Make the arbitration beat the best full-coverage single method in every phase, not only overall. The lamp now wins overall (0.100 vs 0.127 K) and in its first and last windows, but only ties conduction in the middle window (0.099 vs 0.100 K, oracle 0.020 K). The furnace's heating window only ties persistence (48.8 vs 49.0 K, oracle 24.0 K). Candidates: per-domain policies instead of one global policy; the learned operator's abstention (it covers 49 % of furnace cells while heating); and the blind first informative call, where only the median prior is possible. ([detail](AGENTS.md#recorded-arbitration-on-the-lava-lamp-default-600-s-2026-11-19))
- **P2** · R4 · Held-out grading of the arbitration. Freeze the arbiter and the learned operator (export/restore) and run another condition (lamp heater 318 K, furnace 1820 K) as the gate-2 evidence. Phase windows are later in-run time only. ([detail](#promotion-gates))
- **P2** · R4 · Teacher-only grading. On the lamp and the furnace, the reference is the scenario's own authored column or operator output. The `learned_operator`'s wins (0.067 K lamp, 2.3 K furnace on its cells) therefore measure how well it distils that teacher, not physical accuracy. Label teacher-graded results as such in the `field_evolution` summary (a `reference_kind` the arbiter reports per run). Add a teacher-free score next to them: twin self-consistency for every method, or a Geant4/measured anchor where one exists. Gate 4 (independent anchor) still blocks adoption until then. ([detail](AGENTS.md#recorded-arbitration-on-the-lava-lamp-default-600-s-2026-11-19))
- **P2** · R4 · Twin evidence is biased high. The self-consistency twin is coarser than the main lattice (`twin_ratio` default 1.5, `FieldMethods.hpp`), so the twin-vs-main difference overstates the main lattice's own error. Where no reference exists, that biases the arbiter against the lattice methods. Estimate the main lattice's error instead, for example with a Richardson-style correction from two twin ratios or a finer twin on a sub-window, and check on the lamp that the corrected estimate tracks the reference-graded error. ([detail](AGENTS.md#recorded-arbitration-on-the-lava-lamp-default-600-s-2026-11-19))
- **P2** · R2 · The furnace's declared diffusivity, the cascade `conduction_coefficient` (0.0185 s⁻¹ per face) times pitch², makes the conductive lattice 74–85 K off in every window. The run's own illustrative pair law is 0.004 s⁻¹ for batch|batch. Either the cascade output or the declaration mapping is wrong; the engine's verdict says the declared property does not describe the charge. Reconcile them, and the floor/roof coupling declared at the same coefficient. ([detail](AGENTS.md#recorded-arbitration-on-the-glass-furnace-default-150-ticks-2026-11-19))
- **P2** · R3 · More registered methods: a lattice with Dirichlet walls from declared boundary values, a free-surface lattice, a set-network learned operator over each cell's neighbours, and offline-trained surrogate checkpoints registered as field methods. The registry takes each as one `registerFieldMethod` call. ([detail](AGENTS.md#points-to-keep-stable))
- **P2** · R3 · Declare continuum fields in more scenarios:
  - solute transport in `testscenario_osmotic`/`testscenario_efflux`, a particle-count field that needs a `sphere` region and noise-aware grading;
  - the `aerodynamics_reference` gas, which is strict-only today and needs a predictive switch; its compressible flow is outside every current method, so persistence or the learned operator should emerge;
  - the `glass_of_water_shaken` free surface.

  ([detail](AGENTS.md#goal))
- **P2** · R4 · Deterministic learner capacity. `hostComputeBudget()` times the host, so unpinned predictive arbitration varies run to run (furnace middle window 0.39–0.70 K). Recorded runs pin `TRECH_COMPUTE_BUDGET` and the summary records it. Decide whether engine-internal learners should take a declared capacity by default. ([detail](AGENTS.md#points-to-keep-stable))
- **P2** · R5 · Automate the invariants: validation cases run the lamp and the furnace with `engine_field_evolution` on and off and require identical normal-path emits, and the suite gates on `trech_lattice_continuum` and `trech_field_evolution`. ([detail](AGENTS.md#points-to-keep-stable))
- **P2** · R2 · A cascade output for the carrier's own viscosity: the lamp's declaration borrows the effective dynamic viscosity that drives wax drag. ([detail](AGENTS.md#recorded-arbitration-on-the-lava-lamp-default-600-s-2026-11-19))
- **P2** · R7 · Cost: the convective lattice dominates (3.9·10⁸ cell-steps on the lamp) yet is selected for 1–3 % of cells. Its free-fall timestep bound is ≈50× more conservative than the observed flow (Mach 0.0026). Add a deterministic, observed-Mach-controlled dt and kernel speed-ups (loop fusion, deterministic threading). Consider letting the arbiter's evidence pause a method that has not been selected for many calls, with a periodic probe. ([detail](AGENTS.md#recorded-arbitration-on-the-lava-lamp-default-600-s-2026-11-19))
- **P2** · R5 · Temporal convergence of the convective lattice (Mach target 0.15 → 0.075) since the staggered-mode fix, and an independent 3D convection anchor with uncertainty at the lamp's aspect ratio. ([detail](#promotion-gates))
- **P3** · R6 · Studio: show the per-cell selection, method fields, coverage, policies and per-method error domains from the `field_evolution` emits. ([detail](AGENTS.md#source-map))
- **gated** · Adoption (owner): once the gates below pass, decide whether a scenario such as the lamp adopts the engine's arbitrated `field` instead of its authored column, retiring the column to a validation reference through the [migration ledger](../../scenarios/migrations/ROADMAP.md). ([detail](#promotion-gates))

## Promotion gates

A scenario may adopt the engine's arbitrated field only when all of these hold on the recorded
checkout:

1. **Verification:** `trech_lattice_continuum` and `trech_field_evolution` pass.
2. **Arbitration gain:** the arbitration beats the best full-coverage single method and
   persistence on held-out time (another condition with frozen learners), not only in later
   windows of the same run.
3. **Convergence:** halving the lattice cell or the Mach target changes the arbitrated field by
   less than 5 % of its span.
4. **Independent anchor:** the reference used for adoption is a measurement or an external
   benchmark with stated uncertainty, not only the scenario's own authored law.
5. **Property provenance:** every declared property comes from a recorded cascade output or a
   Geant4 fact, with held-out error metadata.
6. **Owner decision:** the gated item above, recorded here with the scores that justified it.

## 2026-11-18 · Lattice module, native kernel and lava-lamp companion

- [x] `js/trech_lbm_reference.js` (since removed; see below): D2Q9/D3Q19 TRT flow (Guo
  forcing, link-wise bounce-back, moving walls); D2Q5/D3Q7 TRT scalar (zero-flux or
  anti-bounce-back Dirichlet walls, relaxation source); Boussinesq coupling with a per-step mean
  reference; units, applicability assessment (stability envelope, observed Mach number, maximum
  principle, staggered-mode share), sampling and dual-run scoring (`trech_lbm_comparison_v1`).
- [x] Native `TRECH_LATTICE_ADVANCE` (physics-agnostic `LatticeKinetic.cpp`, no FP contraction),
  bit-identical to the JS loop.
- [x] `trech_lbm_accuracy` CTest with ten anchors: Taylor–Green, Kolmogorov and
  advection–diffusion at second order; Poiseuille, Couette and conduction exact to ≤ 10⁻¹¹;
  closed-box conservation ≤ 10⁻¹³; de Vahl Davis Ra = 10³ Nu = 1.1195 (benchmark 1.118); native
  parity; staggered-mode guard. Development-only check: the Ra = 10⁵ cavity on 64² gives
  Nu = 4.539 (4.519) and u_max = 34.38 (34.73).
- [x] Lava-lamp dual run on by default (`lbm_companion`, `lbm_cell_mm`, `lbm_mach_target`). The
  normal path is byte-identical on/off.
- [x] Purity audit counts only normal-path lines for coefficient density, so comparison modules
  no longer dilute it. This regenerated the report for `lava_lamp`, `polyurethane_foam`,
  `testscenario_efflux` and `testscenario_h2o_electrolysis_combustion`.
- **Defect found and fixed during the confrontation:** the first scalar default (TRT Λ = 1/4)
  gave τ⁺ ≈ 36 at τ⁻ = 0.507. The scalar's staggered modes then pumped the flow lattice's
  staggered momentum invariant through buoyancy. The 6 mm lamp showed 0.1–0.2 m/s of
  non-decaying, cell-alternating u_z with negative buoyancy power. The scalar now relaxes even
  modes at τ⁺ = 1, `assess` rejects a staggered share above 5 %, and anchor 10 locks both in.
- Spatial convergence for the lava lamp (4 vs 6 mm) passes the gate-3 bands: speed within 3 %,
  temperature within 0.4 % of the span.
- Free-running lamp confrontation (600 s, 6 mm): the lattice reproduced the stratified carrier
  column (temperature score 0.96–0.99, RMS ≤ 1.4 K) and sub-mm/s circulation (0.5–0.9 mm/s
  against the authored basis's 0.24–0.34 mm/s), with flow direction disagreeing.

## 2026-11-18 · On-the-fly (learned) applicability

- [x] Applicability is learned during the run, not decided by a textbook envelope. A twin
  lattice gives each cell's observed error; lattice-intrinsic descriptors give its context;
  `ctx.learnDomains` (`lbm_applicability`) learns error domains prequentially. The verdict is the
  learned share meeting the declared demand, per target and per run. The envelope is kept as
  `reference_assessment`. Divergence is caught and recorded as `failure`.
- [x] Generic module API: `localDescriptors`, `twinDiscrepancy`, `learnApplicability`,
  `applicabilityVerdict`. Fixture anchor 11 checks the evidence half: an identical twin gives zero
  error, plus coarse-twin evidence and wall distances.
- [x] Validated on the lava lamp (A default, B defect re-injected, C coarse). B was caught two
  frames before the staggered rule; C overturned the "≥ 6 cells across" rule; A establishes the
  temperature comparison and not the velocity one. Default run: 107 s with the companion and its
  twin and learner (16.5 s without).

## 2026-11-18 · Lattice and method selection moved into the engine

- [x] The scenario-side lattice was the wrong design: the lamp imported and wired the method, so
  the scenario decided where LBM ran. Removed: `js/trech_lbm_reference.js`, its fixture and
  `test_lbm_accuracy`, the `TRECH_LATTICE_ADVANCE` global, and every `lbm_*` lamp parameter and
  function.
- [x] Engine: `trech::lattice::LatticeContinuum` (the method) and
  `trech::ml::FieldEvolution` (statistical, prequential method selection by context domain).
  Exposed only through `ctx.evolveField`, where a scenario declares the system and passes an
  optional reference.
- [x] `trech_lattice_continuum` reproduces every earlier anchor in C++ with identical values.
  `trech_field_evolution` shows the selection following the evidence: lattice share 0.75 under a
  conducting reference; under a frozen one the arbitrated RMSE is 0.0047 against 1.11 for the
  best lattice.
- [x] The lamp only declares its carrier field (normal path byte-identical on/off). The engine
  chose conduction overall, convection in the early heating and persistence near steady state
  ([superseded record](#2026-11-19--method-registry-engine-wide-arbiter-learned-operator-and-the-glass-furnace)).
- [x] The root principle *Scenarios declare systems; prediction methods emerge from the engine*
  and the scenario pitfall note now prevent the same mistake with other features.


## 2026-11-19 · Method registry, engine-wide arbiter, learned operator and the glass furnace

- [x] **Registry.** `FieldMethod` interface and `registerFieldMethod`. `FieldEvolution` builds
  every registered method for the declared system, excludes those that cannot represent it
  (with the reason) and never names a method. A method added later joins without code changes;
  `trech_field_evolution` registers a test method and checks that it emerges.
- [x] **Domain-free `MethodArbiter`**, shared by every future multi-method path:
  - one error learner per method, learning log errors from the elements that method predicted;
  - learned-domain and recent-leader policies, scored by decayed log-ratio and total squared
    error;
  - evidence-set hysteresis toward the leader, and the median prior;
  - common-element RMSE, coverage and phase windows in the summary.

  Its test learns complementary methods per context domain (100 % correct late selections).
- [x] **`learned_operator`**, the first learned (non-lattice) field method. It is a
  `DomainLearner` with affine laws over the method-independent context, predicts each cell's
  increment per interval, and abstains where it is remote from its support.
  `DomainLearner::predict` (no side effects, with remoteness) supports it.
- [x] **Fixed:** an inapplicable method used to empty every arbitration row, because rows needed
  all methods. Now one learner per method, and exclusion at build time.
- [x] **`glass_from_sand` declares its charge temperature** (216 cells, box, no flow property).
  Normal-path emits are byte-identical on and off, and no emits are dropped. The engine
  excluded the convective lattice (no viscosity declared) and rejected the conductive lattice
  built from the cascade conduction coefficient ([record](AGENTS.md#recorded-arbitration-on-the-glass-furnace-default-150-ticks-2026-11-19)).
- [x] **Lava lamp re-recorded** under a pinned budget: the arbitration now beats the best
  full-coverage single method over the run (0.100 vs 0.127 K; it was 0.164 vs 0.127 K)
  ([record](AGENTS.md#recorded-arbitration-on-the-lava-lamp-default-600-s-2026-11-19)).
- **Superseded record (2026-11-18, three methods, one joint learner):** conductive 0.127,
  convective 0.292 and persistence 0.358 K; arbitrated 0.164 K, oracle 0.094 K. The selection
  moved from convection (early heating) to conduction to persistence (near steady state).
- **Development findings,** each now a common mistake in the handbook:
  - absolute-error regression gave negative predicted errors;
  - squared-sum policies froze after a transient;
  - a quadratic basis made the learned increment jump 55×;
  - abstaining methods looked best on their own cells;
  - the unpinned budget changed results under load.
