# Lattice Boltzmann development track — roadmap

[Root principles](../../../AGENTS.md) · [Root roadmap](../../../ROADMAP.md) · [Parent](../ROADMAP.md) · [Handbook](AGENTS.md)

Related owners: [Water and fluid comparisons](../../scenarios/fluids/ROADMAP.md) · [Lava lamp thermofluid](../../scenarios/fluids/lava/ROADMAP.md) · [Scenario law migration ledger](../../scenarios/migrations/ROADMAP.md).

Maintain work in its owning branch. Dated results apply to the recorded checkout; they do not validate subsequent changes.

## Priority queue

Every open item of this branch, highest priority first. The dated records below are delivery
history: the "Residual" and "Next" notes inside them are tracked here, and this queue wins
where they disagree. Keys and route steps: [priority keys](../../ROADMAP.md#priority-keys) ·
[implementation route](../../ROADMAP.md#implementation-route). When an item lands, delete it here, add a
dated record below, and queue its residuals in the same change.

- **P2** · R4 · Sharpen the on-the-fly error evidence: a finer twin, or alternating twins, so the discrepancy estimates the main lattice's error rather than bounding it by the coarser twin's. Then re-grade lamp velocity applicability (run A is `not_applicable` at the 25 % local demand). ([detail](AGENTS.md#learned-applicability-on-the-real-scenario-lava-lamp-600-s-2026-11-18))
- **P2** · R3 · Let the engine confirm or refute the prior matrix: run learned companions (twin evidence plus `ctx.learnDomains`) in the candidate and the "not applicable" scenarios, replacing every prior with a learned verdict. ([detail](AGENTS.md#applicability-matrix))
- **P2** · R5 · Automate the dual-run invariants: a validation case that runs the lava lamp with `lbm_companion` on and off and requires identical normal-path emits, plus `trech_lbm_accuracy` in the suite gate. ([detail](#promotion-gates))
- **P2** · R5 · Lava-lamp temporal convergence: repeat the Mach-target refinement (0.15 → 0.075) after the staggered-mode fix and check gate 3. Spatial refinement (4/6 mm) already passes; also record the onset time's sensitivity to the seeded 1 mK tilt. ([detail](AGENTS.md#recorded-confrontation-lava-lamp-default-600-s-2026-11-18))
- **P2** · R5 · An independent 3D thermal-convection anchor with uncertainty: a cylinder Rayleigh–Bénard onset or Nusselt benchmark at the lamp's aspect ratio, or measured lamp carrier velocities. ([detail](#promotion-gates))
- **P2** · R2 · A cascade output for the carrier's own viscosity. The companion borrows `macro_effective_dynamic_viscosity_pa_s`, which drives wax-parcel drag. ([detail](#promotion-gates))
- **P2** · R7 · Companion cost: ≈125 ns per D3Q19+D3Q7 cell-step with the twin and learner makes the default lamp ≈6.5× slower (16.5 → 107 s). The a-priori free-fall dt bound is ≈50× more conservative than the observed lamp flow (Mach 0.0026), so add a deterministic, observed-Mach-controlled dt (rescaling non-equilibrium populations) and target ≤ 40 ns per cell-step (loop fusion, precomputed velocity products, deterministic threading), keeping bit identity with the JS loop. ([detail](#2026-11-18--lattice-module-native-kernel-and-lava-lamp-companion))
- **P3** · R3 · Two-way wax coupling (parcel momentum and buoyancy into the lattice) so the companion models the whole lamp, not only its carrier. ([detail](#promotion-gates))
- **P3** · R3 · Next companions from the [applicability matrix](AGENTS.md#applicability-matrix): `glass_from_sand` melt convection; D3Q7 solute transport for `testscenario_osmotic` / `testscenario_efflux` (membrane links). ([detail](AGENTS.md#applicability-matrix))
- **P3** · R6 · Studio: show the lattice temperature and velocity sections and the score-card series beside the lamp from the `lbm_comparison` emits. ([detail](AGENTS.md#source-map))
- **P3** · RX · Extensions for the inapplicable families: free-surface (mass-tracking or volume-of-fluid) LBM for `glass_of_water_shaken`; entropic or LES collision for low-Mach `aerodynamics_reference`. ([detail](AGENTS.md#applicability-matrix))
- **gated** · Promotion decision (owner). Once a companion passes every gate below, decide whether the lattice becomes that scenario's normal-path meso evolution (an authored-law migration through the [ledger](../../scenarios/migrations/ROADMAP.md)) or a teacher for a learned meso operator (`ctx.evolve`/`ctx.interact`). Until then it stays a dual-run comparison. ([detail](#promotion-gates))

## Promotion gates

A companion may leave development only when all of these hold on the recorded checkout:

1. **Verification:** `trech_lbm_accuracy` passes (all anchors, native bit identity).
2. **Learned applicability:** the on-the-fly verdict (twin evidence plus `ctx.learnDomains`) is
   `applicable` for every compared quantity at the declared demand, with `trusted: true`. The
   textbook `reference_assessment` is reported but does not count.
3. **Convergence:** halving the lattice cell or the Mach target changes the compared observables
   by less than 5 % of the heater span (temperature RMS) and 20 % (carrier RMS speed) after
   onset.
4. **Independent anchor:** agreement with an external benchmark or measurement within its
   stated uncertainty for the same regime (Rayleigh, Prandtl, aspect ratio).
5. **Property provenance:** every lattice property comes from a recorded cascade output or a
   Geant4 fact, with held-out error metadata; no borrowed proxy remains.
6. **Coupling honesty:** coupling that is still missing (wax momentum) is either implemented or
   shown not to change gate-3 observables beyond its band.
7. **Owner decision:** the gated item above, recorded here with the scores that justified it.

## 2026-11-18 · Lattice module, native kernel and lava-lamp companion

- [x] [`js/trech_lbm_reference.js`](../../../js/trech_lbm_reference.js): D2Q9/D3Q19 TRT flow (Guo
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
- Results and residuals: [handbook record](AGENTS.md#recorded-confrontation-lava-lamp-default-600-s-2026-11-18).

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

