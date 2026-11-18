# Lattice methods and field-evolution arbitration — context and contracts

[Root principles](../../../AGENTS.md) · [Root roadmap](../../../ROADMAP.md) · [Parent](../AGENTS.md) · [Roadmap](ROADMAP.md)

Related owners: [Learned state and pair operators](../operators/AGENTS.md) · [JavaScript host and live lab](../runtime/AGENTS.md) · [Water and fluid comparisons](../../scenarios/fluids/AGENTS.md) · [Lava lamp thermofluid](../../scenarios/fluids/lava/AGENTS.md).

Read the root principles and the parent handbook first; then open only the subcategory relevant to the task. Source paths and shell commands in code spans/blocks are repository-relative unless stated otherwise; Markdown links resolve from this file.

## Goal

The engine must find out, by itself and from evidence, where lattice Boltzmann methods (LBM)
predict the internal evolution of declared systems better than its other methods. Scenarios
declare systems; they never choose, import or wire a method (root principle
[*Scenarios declare systems*](../../../AGENTS.md#scenarios-declare-systems-prediction-methods-emerge-from-the-engine)).
LBM is a mesoscale kinetic method, and its relaxation times come from properties the cascade
lifts from the Geant4 base. It is a candidate for the meso rung of the engine thesis, but it is
one candidate among the engine's methods, and it is used where the statistics favour it.

## Points to keep stable

1. **Engine-owned methods only.** The lattice method lives in
   [`LatticeContinuum`](../../../include/trech/core/LatticeContinuum.hpp) with its kernel
   [`LatticeKinetic`](../../../include/trech/core/LatticeKinetic.hpp). It names no material,
   scenario or domain. No scenario or `js/` module may contain or construct a lattice. There is
   no JavaScript lattice module and no lattice global.
2. **Scenarios declare, the engine selects.** A scenario reaches the method only through
   `ctx.evolveField`. It declares the region, its own cells and values, the transport properties
   and their source, the exchanges and an optional reference. Options carry method numerics
   (cell size, Mach target, twin ratio), never a method choice.
3. **Selection is statistical and prequential.** Every method is advanced and graded against
   the reference per cell. A `DomainLearner` over lattice-local context (Mach, cell Reynolds,
   cell Péclet, scalar step, velocity curvature, wall distance) predicts each method's error
   *before* learning the call, and the lowest predicted error wins per cell. Fallback before
   anything is learned: the method with the lowest realized error so far, else persistence. No
   textbook threshold decides.
4. **Same start, same horizon.** After grading, the lattices are nudged to the reference cell
   means, which keeps their sub-cell structure and flow. Every method therefore competes one
   interval ahead from the same state. Never compare a free-running method with a one-step
   method: persistence would always win.
5. **Failures are evidence.** A diverging lattice is marked `failed` with a reason and then
   predicts its last valid state, so the arbitration routes away from it. Nothing is clipped,
   and the scenario never aborts.
6. **Self-consistency without a reference.** A coarser twin of the convective lattice
   (`twin_ratio`) gives local error evidence. A second learner predicts it prequentially; this
   is reported, and is the signal available when no reference exists.
7. **No feedback by default.** `ctx.evolveField` writes nothing back. A scenario that adopts the
   returned `field` must say so in code and handbook, behind a documented switch. The lava lamp
   does not adopt it, and its normal-path emits are byte-identical with `engine_field_evolution`
   on or off; re-check this whenever either side changes.
8. **Verification before arbitration.** `trech_lattice_continuum` must pass:
   - Taylor–Green, Kolmogorov and advection–diffusion converge at second order;
   - Poiseuille (TRT Λ = 3/16), Couette and Dirichlet conduction are exact;
   - closed-box mass and scalar are conserved;
   - the de Vahl Davis Ra = 10³ cavity is within 1 %;
   - the staggered-mode guard holds (the scalar's even modes relax at τ⁺ = 1);
   - wall distances follow the lattice.

   `trech_field_evolution` must show the choice following the evidence: a conducting reference
   makes a lattice emerge, and a frozen reference makes persistence emerge where the methods
   differ. Never loosen a tolerance to absorb a regression.
9. **Deterministic, no contraction.** The lattice and arbitration sources are built with
   `-ffp-contract=off`. The only perturbation is a seed-derived horizontal tilt (10⁻⁵ of the
   field span) that breaks mirror symmetry.

## Source map

| Piece | File | Notes |
| --- | --- | --- |
| Kernel | [`LatticeKinetic.hpp`](../../../include/trech/core/LatticeKinetic.hpp) · [`.cpp`](../../../src/core/LatticeKinetic.cpp) | TRT collide-and-stream with Guo forcing; scalar advection–diffusion with a relaxation source; per-cell force fields; scalar-only advance. |
| Lattice method | [`LatticeContinuum.hpp`](../../../include/trech/core/LatticeContinuum.hpp) · [`.cpp`](../../../src/core/LatticeContinuum.cpp) | D2Q9/D3Q19 flow and D2Q5/D3Q7 scalar; domain compaction, bounce-back and moving walls, Dirichlet links, Boussinesq coupling (mean reference), `addScalar`, sampling, local descriptors, staggered fraction. |
| Arbitration | [`FieldEvolution.hpp`](../../../include/trech/ml/FieldEvolution.hpp) · [`.cpp`](../../../src/ml/FieldEvolution.cpp) | Methods `lattice_convective`, `lattice_conductive`, `persistence`; overlap mapping between lattice and declared cells; arbitration and self-consistency learners; run summary. |
| Hook | `jsHookEvolveField` in [`JsRuntime.cpp`](../../../src/js/JsRuntime.cpp) | `ctx.evolveField`, predictive only, persistent by name. Contract in [scenario hooks](../../../docs/scenario_hooks.md#engine-field-evolution); emits in [output schema](../../../docs/output_schema.md#engine-field-evolution-emits). |
| Tests | [`test_lattice_continuum.cpp`](../../../tests/test_lattice_continuum.cpp) · [`test_field_evolution.cpp`](../../../tests/test_field_evolution.cpp) | Pure C++, a few seconds each in Release. |
| Declaration example | `declareCarrierField` in [`lava_lamp.js`](../../../examples/scenarios/lava_lamp/lava_lamp.js) | Declares only. The authored column is passed as the validation `reference`. |

## Recorded arbitration on the lava lamp (default 600 s, 2026-11-18)

The lamp declares its 24-cell carrier column (cylinder R = 30 mm, H = 180 mm). Properties come
from the cascade: ν = 258 mm²/s from the effective dynamic viscosity and the Geant4 density,
κ = 18.1 mm²/s, β = 3.04·10⁻⁴ K⁻¹. Exchanges are the heater and top relaxations and the replayed
wax load. The engine built a 6 mm convective lattice (τ = 0.579, dt = 3.7 ms), a 6 mm conductive
lattice (dt = 0.25 s) and a 9 mm twin. None failed.

| Method | RMSE vs reference (K) | Share of cells selected |
| --- | --- | --- |
| `lattice_conductive` | **0.127** (best single) | 0.49 |
| `lattice_convective` | 0.292 | 0.21 |
| `persistence` | 0.358 | 0.30 |
| arbitrated (learned selections, 98 % of cells) | 0.164 | — |
| oracle (best per cell) | 0.094 | — |

How the selection moved:

| Frames | Phase | Selection | Per-phase RMSE (K): convective / conductive / persistence |
| --- | --- | --- | --- |
| 1–29 | rapid heating | convective 42 %, conductive 35 % | 0.22 / 0.18 / 0.52 |
| 30–89 | | conduction dominant (52–65 %) | |
| 90–120 | column near steady state | persistence 52 % | 0.47 / 0.09 / 0.05 |

The convective lattice drifts late because it convects where the reference column does not.

Normal-path emits are byte-identical with the declaration on or off. Wall time is 105 s with it
and 17 s without it (Release); 3.9·10⁸ of the cell-steps are the convective lattice's.

Reading:

- With these properties the lamp's authored column behaves like conduction, and the engine
  found that unaided.
- Convection helps only in the fast early phase. It degrades the prediction once the lattice
  convects where the reference does not.
- Learned arbitration does not yet beat the best single method; the oracle shows the gain still
  available.
- The reference is the authored column, so this grades agreement with a teacher, not
  experimental accuracy.

Earlier development findings (the free-running confrontation, 4/6 mm spatial convergence and the
staggered-mode defect) are in the [roadmap history](ROADMAP.md#2026-11-18--lattice-module-native-kernel-and-lava-lamp-companion).

## Common mistakes

- **Wiring a method in a scenario.** The first lattice companion (commit `916a60d`) imported the
  JavaScript lattice into `lava_lamp.js` and decided there where it ran. Move the method into the
  engine and declare the system instead.
- **Comparing free-running methods with one-step methods.** Persistence of the last reference
  then wins everywhere. Synchronise every method to the same observed state.
- **Lambda = 1/4 for a weakly diffusive scalar.** It makes τ⁺ ≈ 0.25/(τ⁻ − ½) huge, and the
  scalar's period-2 modes then pump the flow's staggered momentum invariant, which no viscosity
  damps. The result is cell-alternating u_z with *negative* buoyancy power. Keep τ⁺ = 1; an
  energy budget is the fastest check.
- **Choosing dt from viscosity alone** for a buoyant flow. The free-fall velocity bound sets
  the Mach number.
- **A fixed buoyancy reference in a warming closed region.** It launches acoustic pulses; use
  the mean reference.
- **Mapping declared cells onto lattice layers without overlap weights.** The exchange power
  then changes with the cell size.
