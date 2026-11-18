# Lattice Boltzmann development track — context and contracts

[Root principles](../../../AGENTS.md) · [Root roadmap](../../../ROADMAP.md) · [Parent](../AGENTS.md) · [Roadmap](ROADMAP.md)

Related owners: [Water and fluid comparisons](../../scenarios/fluids/AGENTS.md) · [Lava lamp thermofluid](../../scenarios/fluids/lava/AGENTS.md) · [Learned state and pair operators](../operators/AGENTS.md) · [JavaScript host and live lab](../runtime/AGENTS.md).

Read the root principles and the parent handbook first; then open only the subcategory relevant to the task. Source paths and shell commands in code spans/blocks are repository-relative unless stated otherwise; Markdown links resolve from this file.

## Goal

Evaluate whether lattice Boltzmann methods (LBM) can **predict the internal evolution** of the
systems TRECH already simulates, using the **same geometry and the same (cascade-inferred)
properties**, where the method applies. LBM is a mesoscale kinetic scheme, so it is a natural
candidate for the meso rung of the [engine thesis](../../../AGENTS.md#multi-scale-inference-cascade-the-core-thesis).
Its relaxation times can come from properties the cascade lifts from the Geant4 base, and its
dynamics can replace authored kinematics such as a prescribed circulation basis. Until a
companion passes the promotion gates in the [roadmap](ROADMAP.md#promotion-gates), the track is
**development only**. Every applicable run executes **both** paths and records the confrontation.

## Points to keep stable

These hold for the whole development roadmap. Change one only with a recorded owner decision and
a matching roadmap entry.

1. **Dual run, no feedback.** The normal path is computed exactly as without the companion. The
   default lava lamp emits are byte-identical with `lbm_companion=compare` and `off`; check this
   whenever the companion changes. Companion state is read from the scenario only through
   read-only taps (the lamp's wax heat accumulator) and never written back.
2. **Always on; applicability is found by running.** A scenario with a companion defaults to
   `compare`; `off` exists only for timing and identity checks. No textbook rule stops a lattice
   from running. Only a lattice that cannot be constructed (τ ≤ ½) is skipped. A lattice that
   diverges is caught, recorded as `failure` (observed evidence of non-applicability) and
   stopped, and the scenario continues.
3. **Same system, same properties.** The companion uses the scenario's geometry, its boundary laws
   on the same regions (overlap-weighted when lattice and scenario cells differ) and its
   cascade-inferred properties, each with its recorded source. It never hand-tunes a property to
   improve agreement. A property the cascade does not supply is named in `limitations`, never
   silently substituted.
4. **Comparison physics labels.** The module stays a `*_reference.js` file, and scenario glue
   lives in functions named `…Comparison…`. The purity audit therefore excludes them from
   normal-path law counts, and they do not dilute the coefficient density, which counts
   normal-path lines only. Records carry `scope`, `track: "development"`, `feeds_back: false`.
   They are never Geant4 results or learned predictions.
5. **Verification before confrontation.** `trech_lbm_accuracy` (CTest) must pass: Taylor–Green,
   Kolmogorov and advection–diffusion at second order; Poiseuille (TRT Λ = 3/16), Couette and
   Dirichlet conduction exact; closed-box mass/scalar conservation; the de Vahl Davis Ra = 10³
   cavity within 1 %; and native ↔ JavaScript **bit identity**. Never loosen a tolerance to absorb
   a regression.
6. **Applicability is learned on the fly, never assumed.** The engine decides where the lattice
   holds from evidence gathered in the run:
   - **Evidence:** a twin lattice (cell × `lbm_twin_ratio`) on the same clock. Its local
     discrepancy is each cell's observed error; no convergence order is assumed.
   - **Context:** lattice-intrinsic local descriptors: Mach, cell Reynolds, cell Péclet, scalar
     step, velocity curvature and wall distance.
   - **Learning:** `ctx.learnDomains` grows error-response domains online and predicts every
     cell's error *before* learning that frame (prequential).
   - **Decision:** each frame's `applicability` is the learned share of cells meeting the
     declared accuracy demand. The summary verdict (`applicable` / `intermittent` /
     `not_applicable`) requires that share to meet the coverage demand on every learned frame
     after the warm-up. `trusted` follows the learned verdict.
   - **Reference only:** the textbook envelope (τ, Mach, cells across, maximum principle,
     staggered share) is reported as `reference_assessment`, with its agreement with the learned
     verdict. It never decides.
   - **Declared numbers:** the only declared numbers are the scenario's accuracy demand
     (`LBM_COMPARISON_DEMAND`, coverage, warm-up). They say how accurate the comparison must
     be, not where the method works.
7. **Stable schema.** `trech_lbm_comparison_v1` (frame and summary fields in
   [output schema](../../../docs/output_schema.md#lattice-boltzmann-comparison-emits)) changes only
   additively; a breaking change bumps the schema name.
8. **Physics-agnostic native kernel.** `TRECH_LATTICE_ADVANCE` /
   [`LatticeKinetic.cpp`](../../../src/core/LatticeKinetic.cpp) names no lattice, fluid or material.
   Velocity sets, rates, couplings and sources come from JavaScript, and the kernel stays
   bit-identical to the JS loop, which has no FP contraction.
9. **Deterministic.** There is no RNG. The symmetry-breaking tilt (1 mK in the lamp) is derived
   from the scenario's own seeded microstate and declared in source.

## Source map

| Piece | File | Notes |
| --- | --- | --- |
| Lattice module | [`js/trech_lbm_reference.js`](../../../js/trech_lbm_reference.js) | D2Q9/D3Q19 TRT flow with Guo forcing, link-wise half-way bounce-back (moving walls); D2Q5/D3Q7 TRT advection–diffusion with zero-flux or anti-bounce-back Dirichlet walls; `createThermalFlow` (Boussinesq, fixed or per-step `"mean"` reference, declarative relaxation source); `units`, `assess`, `sample`, `compareProfiles`, `compareVectors`, `scoreCard`. |
| Native hot loop | [`LatticeKinetic.hpp`](../../../include/trech/core/LatticeKinetic.hpp) · [`LatticeKinetic.cpp`](../../../src/core/LatticeKinetic.cpp) · `jsTrechLatticeAdvance` in [`JsRuntime.cpp`](../../../src/js/JsRuntime.cpp) | Zero-copy on JS typed arrays after constructor, size and index checks; `-ffp-contract=off`. Documented in [scenario hooks](../../../docs/scenario_hooks.md#native-lattice-advance). |
| Verification | [`tests/fixtures/js/lbm_accuracy.js`](../../../tests/fixtures/js/lbm_accuracy.js) · [`tests/test_lbm_accuracy.cpp`](../../../tests/test_lbm_accuracy.cpp) | About 95 s Debug, 17 s Release (11 anchors). |
| On-the-fly applicability | `neighbours`, `localDescriptors`, `twinDiscrepancy`, `learnApplicability`, `applicabilityVerdict` in the lattice module | Generic: any companion supplies a main and a twin lattice, its accuracy demand and a learner name. |
| Lava-lamp companion | `buildLbmComparisonLattice`, `createLbmComparison` … `lbmComparisonSummary` in [`lava_lamp.js`](../../../examples/scenarios/lava_lamp/lava_lamp.js) | Parameters `lbm_companion`, `lbm_cell_mm` (6), `lbm_mach_target` (0.15), `lbm_twin_ratio` (1.5), development knob `lbm_scalar_magic` (0 = engine default). |

## Applicability matrix

These are **prior hypotheses**, not verdicts. They come from textbook reasoning with each
scenario's defaults (2026-11-18) and say only where a companion is worth building first. A
scenario's applicability is established solely by a learned run (point 6). A prior that a learned
run contradicts is corrected here with the run as evidence.

| Scenario | Status | Reason |
| --- | --- | --- |
| `lava_lamp` (carrier) | **dual run active; learned verdict recorded below** | Closed, laminar Boussinesq convection (Ra ≈ 1.4·10⁵, Pr ≈ 14). The authored carrier basis (`carrierFlowAt`) and the 1-D diffusion column are exactly what the lattice predicts. |
| `glass_from_sand` (melt) | candidate | Thermal conduction and melt convection in a closed charge; needs phase-dependent viscosity and the cell-material map as lattice solids. |
| `testscenario_osmotic`, `testscenario_efflux` | candidate (scalar only) | Solute transport is D3Q7 advection–diffusion; membranes need partial-bounce-back or interface-flux links. |
| `nacl_dehydration_reference` | candidate (scalar only) | Concentration field under evaporation; needs a moving free boundary. |
| `aerodynamics_reference` | not applicable | Default Mach 1.5 is outside the isothermal weakly-compressible model. At Mach ≤ 0.3, air's viscosity on the 16.7 mm grid needs τ − ½ ≈ 10⁻⁵, which is unstable without a subgrid (LES) or entropic collision. |
| `glass_of_water_shaken`, `h2o_fluid` (PBF) | not applicable | Free surface (pour, slosh, splash) needs a mass-tracking or volume-of-fluid LBM extension. |
| MD / molecular scenarios (`h2o_*`, `water_box`, `testscenario_pascal`) | not applicable | Molecular scale; LBM is a continuum-kinetic (meso) method. Pascal's particle bath is the comparison target itself. |

## Recorded confrontation (lava lamp, default 600 s, 2026-11-18)

Settings: 6 mm D3Q19/D3Q7 TRT lattice, 2400 fluid cells, τ = 0.579, scalar τ⁻ = 0.507 (τ⁺ = 1),
dt = 3.7 ms, 162 733 steps (3.9·10⁸ cell-steps), native kernel. Wall time was 65 s with the
companion versus 16.5 s without it (Release), and is 107 s since the twin lattice and learner were added; normal-path emits are byte-identical.

- **Carrier temperature:** the lattice reproduces the stratified 1-D column throughout. The score
  is 0.96–0.99 (RMS 0.3 K up to 300 s, at most 1.4 K later), and the mean score is 0.98. The
  column's pure-diffusion assumption is therefore consistent with the weak convection the lattice
  predicts for these properties.
- **Carrier flow:** the lattice is still until ≈ 150 s, then convects weakly. Its RMS speed is 0.5–0.9 mm/s, the same order as the authored basis at the
  parcels (0.24–0.34 mm/s; cascade circulation 0.67 mm/s); the end speed ratio is 0.88. The
  direction disagrees and varies (mean cosine −0.48 to +0.65 over the run), so the authored
  basis's *pattern* is what the lattice contradicts, not its magnitude.
- **Scores and self-assessment:** mean overall 0.49 (`diverge`), driven by direction and the
  still early phase. The verdict is `applicable` and `trusted: true`: peak lattice Mach 0.0026,
  temperatures inside [ambient, heater] and a staggered share ≤ 0.03 %.
- **Spatial refinement (4 mm, 7965 cells, τ = 0.619, 1.9·10⁹ cell-steps):** the result converges.
  The carrier RMS speed agrees within 3 % (0.589 vs 0.606 mm/s at 600 s) and the lattice
  temperature profiles within 0.16 K (0.4 % of the span) at every frame. Direction cosines are
  identical frame by frame, and the mean scores are 0.98 / 0.55 / 0.42 (temperature / direction /
  speed) at both resolutions. Onset (≈ 150 s) is resolution-independent. The earlier
  resolution-dependent onset came from the staggered-mode defect, not from near-criticality.
  Temporal (Mach-target) refinement has not been repeated since the fix.
- **Cost note:** the a-priori free-fall timestep bound (Mach target 0.15 at 141 mm/s) is ≈ 50×
  more conservative than the observed flow needs.

Reading: with the cascade's effective properties and the lamp's own heater and top laws, the
lattice supports the lamp's stratified carrier column and a sub-mm/s circulation magnitude. It
contradicts the authored basis's spatial pattern. This is a development finding, not a validated
macro result; see the [roadmap](ROADMAP.md) for what must close first.

## Learned applicability on the real scenario (lava lamp, 600 s, 2026-11-18)

The demand is twin error ≤ 2 % of the span (temperature) and ≤ 25 % of the frame's RMS speed
(velocity), on ≥ 90 % of cells, every frame after 3 warm-up frames. The twin uses 1.5× cells,
learner `lbm_applicability`, 2400 rows per frame. The learned share is predicted before each
frame is learned and tracks the measured share closely (mean difference ≤ 0.03 in A and C).
In all three runs the normal-path emits are identical with the companion on and off.

| Run | Textbook reference | Learned verdict (temperature / velocity) | What the engine found on the fly |
| --- | --- | --- | --- |
| A: default 6 mm | applicable | `intermittent` / `not_applicable` (mean shares 0.91 / 0.70; measured 0.91 / 0.74) | Temperature holds except at convective onset; velocity fails the 25 % local demand from frame 23 (≈ 115 s), at onset |
| B: defect re-injected (`lbm_scalar_magic=0.25`) | not_applicable from frame 7 (staggered rule) | `not_applicable` / `not_applicable` from **frame 5** | Caught the staggered-mode defect two frames before the hand-written rule, without knowing staggered modes exist; one domain at Mach ≈ 0.2 and high velocity curvature holds all cells |
| C: coarse 10 mm (6 cells across) | applicable | `not_applicable` / `not_applicable` (0.26 / 0.29) | **Overturned the textbook rule:** "≥ 6 cells across" is not enough here |

Reading:

- The temperature agreement the confrontation reports is established on the fly at 6 mm. The
  velocity comparison is not yet established at a 25 % local demand.
- The twin is coarser than the main lattice, so its discrepancy bounds the main error from
  above. A finer twin, or a looser velocity demand, may restore velocity applicability; both are
  queued.
- Verdicts are only as good as the declared demand and the twin evidence. They are never an
  experimental validation.

## Common mistakes

- **Lambda = 1/4 for a weakly diffusive scalar.** It makes τ⁺ ≈ 0.25/(τ⁻ − ½) huge, so the
  scalar's period-2 modes survive and, through buoyancy, pump the flow's staggered momentum
  invariant, which no viscosity damps. The lamp then showed 0.1–0.2 m/s of cell-alternating u_z
  with *negative* buoyancy power. Keep scalar τ⁺ = 1 and watch `staggered_fraction`. An energy
  budget (buoyancy power versus kinetic energy) is the fastest check when speeds look too high.
- **Choosing dt from viscosity alone.** Buoyancy-driven velocities set the Mach number. Hold the
  free-fall bound at the Mach target, then check the observed Mach number every frame.
- **A fixed buoyancy reference in a warming closed vessel.** Each jump of the reference at a frame
  boundary launches an acoustic pulse; use `reference: "mean"`.
- **Applying a slab law to whole lattice layers.** Weight by height overlap, or the heater power
  changes with `lbm_cell_mm`.
- **Deciding applicability from a textbook rule.** Case C met every envelope threshold and was
  still wrong. Let the learned verdict decide, and keep the envelope as a reference to compare
  against.
- **Comparing a still lattice with a prescribed basis and calling it disagreement in physics.**
  Read the time series: the onset phase and the convecting phase answer different questions.
