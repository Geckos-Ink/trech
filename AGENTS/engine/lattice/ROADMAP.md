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

- **P1** · R3 · Make learned arbitration beat the best single method on the lamp: its arbitrated RMSE (0.164 K) is above the best single method's (0.127 K) and the oracle's (0.094 K). Candidates: more context (field-cell gradient and time since an exchange change), a per-domain switch with hysteresis, and forgetting tuned to the phase changes the selection already shows. ([detail](AGENTS.md#recorded-arbitration-on-the-lava-lamp-default-600-s-2026-11-18))
- **P2** · R3 · More engine methods for declared fields: learned operators (`ctx.evolve` surrogates trained on the arbitration rows), a lattice with Dirichlet walls from declared boundary values, and a free-surface lattice. The arbitration decides among them; no scenario names one. ([detail](AGENTS.md#points-to-keep-stable))
- **P2** · R3 · Declare continuum fields in more scenarios (`glass_from_sand` melt; solute transport in `testscenario_osmotic` / `testscenario_efflux`; the `aerodynamics_reference` gas) and let the engine's verdicts replace the textbook priors that used to sit in this handbook. ([detail](AGENTS.md#goal))
- **P2** · R5 · Automate the invariants: a validation case runs the lamp with `engine_field_evolution` on and off and requires identical normal-path emits, and the suite gates on `trech_lattice_continuum` and `trech_field_evolution`. ([detail](AGENTS.md#points-to-keep-stable))
- **P2** · R2 · A cascade output for the carrier's own viscosity: the declaration borrows the effective dynamic viscosity that drives wax drag. ([detail](AGENTS.md#recorded-arbitration-on-the-lava-lamp-default-600-s-2026-11-18))
- **P2** · R7 · Cost: the convective lattice dominates (3.9·10⁸ cell-steps, ≈6× the lamp's wall time). Its free-fall timestep bound is ≈50× more conservative than the observed flow (Mach 0.0026). Add a deterministic, observed-Mach-controlled dt and kernel speed-ups (loop fusion, deterministic threading). ([detail](AGENTS.md#recorded-arbitration-on-the-lava-lamp-default-600-s-2026-11-18))
- **P2** · R5 · Temporal convergence of the convective lattice (Mach target 0.15 → 0.075) since the staggered-mode fix, and an independent 3D convection anchor with uncertainty at the lamp's aspect ratio. ([detail](#promotion-gates))
- **P3** · R6 · Studio: show the per-cell selection, method fields and arbitration domains from the `field_evolution` emits. ([detail](AGENTS.md#source-map))
- **gated** · Adoption (owner): once the gates below pass, decide whether a scenario such as the lamp adopts the engine's arbitrated `field` instead of its authored column, retiring the column to a validation reference through the [migration ledger](../../scenarios/migrations/ROADMAP.md). ([detail](#promotion-gates))

## Promotion gates

A scenario may adopt the engine's arbitrated field only when all of these hold on the recorded
checkout:

1. **Verification:** `trech_lattice_continuum` and `trech_field_evolution` pass.
2. **Arbitration gain:** over the run, the learned arbitration beats the best single method and
   persistence on held-out time (a later window or another condition), not only in-run.
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
  ([record](AGENTS.md#recorded-arbitration-on-the-lava-lamp-default-600-s-2026-11-18)).
- [x] The root principle *Scenarios declare systems; prediction methods emerge from the engine*
  and the scenario pitfall note now prevent the same mistake with other features.

