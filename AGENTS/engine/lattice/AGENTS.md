# Lattice methods and field-evolution arbitration — context and contracts

[Root principles](../../../AGENTS.md) · [Root roadmap](../../../ROADMAP.md) · [Parent](../AGENTS.md) · [Roadmap](ROADMAP.md)

Related owners: [Learned state and pair operators](../operators/AGENTS.md) · [JavaScript host and live lab](../runtime/AGENTS.md) · [Water and fluid comparisons](../../scenarios/fluids/AGENTS.md) · [Lava lamp thermofluid](../../scenarios/fluids/lava/AGENTS.md).

Read the root principles and the parent handbook first; then open only the subcategory relevant to the task. Source paths and shell commands in code spans/blocks are repository-relative unless stated otherwise; Markdown links resolve from this file.

## Goal

The engine must find out, by itself and from evidence, which of its methods predicts the
internal evolution of a declared system best, per context domain. Lattice Boltzmann methods
(LBM) are one family of candidates, beside learned operators, baselines and any method
registered later. Scenarios declare systems; they never choose, import or wire a method (root
principle
[*Scenarios declare systems*](../../../AGENTS.md#scenarios-declare-systems-prediction-methods-emerge-from-the-engine)).
LBM is a mesoscale kinetic method whose relaxation times come from properties the cascade lifts
from the Geant4 base. It is a candidate for the meso rung of the engine thesis, used where the
statistics favour it.

## Points to keep stable

1. **Engine-owned methods in a registry.** Field methods implement `FieldMethod` in
   [`FieldMethods.hpp`](../../../include/trech/ml/FieldMethods.hpp) and are registered in
   `fieldMethodRegistry()`. Built-ins:
   - `lattice_convective` and `lattice_conductive`, from
     [`LatticeContinuum`](../../../include/trech/core/LatticeContinuum.hpp) and its kernel
     [`LatticeKinetic`](../../../include/trech/core/LatticeKinetic.hpp);
   - `learned_operator`;
   - `persistence`.

   A new method, whether an algorithm (another lattice, a free-surface or a non-fluid solver)
   or a learned model, is one `registerFieldMethod` call. Arbitration, accounting and reports
   pick it up with no change to `FieldEvolution`, the hook or any scenario. Methods name no
   material, scenario or domain. No scenario or `js/` module may contain or construct a method.
2. **Scenarios declare, the engine selects.** A scenario reaches the methods only through
   `ctx.evolveField`. It declares:
   - the region, its own cells and values;
   - the transport properties and their source;
   - the exchanges and an optional reference.

   Options carry method numerics (cell size, Mach target, twin ratio), never a method choice. A
   method that cannot represent the declared system is excluded, with its reason recorded.
3. **Selection is statistical, prequential and engine-wide.** The domain-free
   [`MethodArbiter`](../../../include/trech/ml/MethodArbiter.hpp) works as follows:
   - **Context.** The method-independent drives (diffusive, exchange and load drives, recent
     change, level, exposure, all in field-span units) plus the descriptors candidates
     contribute (lattice-local Mach, Reynolds and Péclet numbers, scalar step, curvature and
     wall distance; the learned operator's remoteness).
   - **Error learning.** One `DomainLearner` per method learns its log error from the cells it
     predicted, before the call is learned.
   - **Two policies.** The learned per-domain selection leaves the recent leader only when the
     predicted advantage exceeds the error learners' own uncertainty. It is applied while it
     beats the recent leader (lowest decayed log error) on both the decayed log-ratio and the
     decayed total squared error.
   - **Prior.** Before any evidence, the lower median of distinct candidate predictions is used.

   No textbook threshold decides anything.
4. **Same start, same horizon.** After grading, every method observes the reference:
   - lattices are nudged to the reference cell means, keeping their sub-cell structure and flow;
   - the learned operator learns the transition.

   Every method therefore competes one interval ahead from the same state. Never compare a
   free-running method with a one-step method: persistence would always win.
5. **Failures and abstention are evidence.** A diverging lattice is marked `failed` with a
   reason and then predicts its last valid state. The learned operator abstains (NaN) where its
   input is far from the support of its law. Nothing is clipped, the scenario never aborts, and
   the arbiter routes to the methods that do predict.
6. **Self-consistency without a reference.** A coarser twin of the convective lattice
   (`twin_ratio`) gives local error evidence. A second learner predicts it prequentially; this
   is reported, and is the signal available when no reference exists.
7. **No feedback by default.** `ctx.evolveField` writes nothing back. A scenario that adopts the
   returned `field` must say so in code and handbook, behind a documented switch. Neither the
   lava lamp nor the glass furnace adopts it. Their normal-path emits are byte-identical with
   `engine_field_evolution` on or off; re-check this whenever either side changes.
8. **Verification before arbitration.** `trech_lattice_continuum` must pass:
   - Taylor–Green, Kolmogorov and advection–diffusion converge at second order;
   - Poiseuille (TRT Λ = 3/16), Couette and Dirichlet conduction are exact;
   - closed-box mass and scalar are conserved;
   - the de Vahl Davis Ra = 10³ cavity is within 1 %;
   - the staggered-mode guard holds (the scalar's even modes relax at τ⁺ = 1);
   - wall distances follow the lattice.

   `trech_field_evolution` must show that:
   - the domain-free arbiter learns which method wins in which context domain;
   - on a conducting reference an evolving method emerges and later windows match the best
     full-coverage method and stay within 2.5× the oracle;
   - a frozen reference removes most of the lattice error;
   - an inapplicable method is excluded with its reason;
   - a method registered later emerges where it is best.

   Never loosen a tolerance to absorb a regression.
9. **Deterministic numerics, budgeted learners.** The lattice, method and arbitration sources are
   built with `-ffp-contract=off`. The only lattice perturbation is a seed-derived horizontal
   tilt (10⁻⁵ of the field span) that breaks mirror symmetry. Learner capacities come from
   `hostComputeBudget()`, which times the host. Recorded results therefore pin
   `TRECH_COMPUTE_BUDGET`, and the summary carries the `compute_budget` used.

## Source map

| Piece | File | Notes |
| --- | --- | --- |
| Kernel | [`LatticeKinetic.hpp`](../../../include/trech/core/LatticeKinetic.hpp) · [`.cpp`](../../../src/core/LatticeKinetic.cpp) | TRT collide-and-stream with Guo forcing; scalar advection–diffusion with a relaxation source; per-cell force fields; scalar-only advance. |
| Lattice | [`LatticeContinuum.hpp`](../../../include/trech/core/LatticeContinuum.hpp) · [`.cpp`](../../../src/core/LatticeContinuum.cpp) | D2Q9/D3Q19 flow and D2Q5/D3Q7 scalar; domain compaction, bounce-back and moving walls, Dirichlet links, Boussinesq coupling (mean reference), `addScalar`, sampling, local descriptors, staggered fraction. |
| Methods and registry | [`FieldMethods.hpp`](../../../include/trech/ml/FieldMethods.hpp) · [`.cpp`](../../../src/ml/FieldMethods.cpp) | `FieldMethod`, `FieldSystem` (face adjacency, span, context names), `registerFieldMethod`. Built-ins: lattice methods (overlap mapping, twin, descriptors), `learned_operator` (affine domain laws over the context, abstains when remote), `persistence`. |
| Arbiter | [`MethodArbiter.hpp`](../../../include/trech/ml/MethodArbiter.hpp) · [`.cpp`](../../../src/ml/MethodArbiter.cpp) | Domain-free; one error learner per method, policies, prior, phases. Owned with the [inference handbook](../inference/AGENTS.md). |
| Field evolution | [`FieldEvolution.hpp`](../../../include/trech/ml/FieldEvolution.hpp) · [`.cpp`](../../../src/ml/FieldEvolution.cpp) | Builds the system and every registered method, computes the context, runs the arbiter, reports. |
| Hook | `jsHookEvolveField` in [`JsRuntime.cpp`](../../../src/js/JsRuntime.cpp) | `ctx.evolveField`, predictive only, persistent by name. Contract in [scenario hooks](../../../docs/engine/scenario_hooks.md#engine-field-evolution); emits in [output schema](../../../docs/engine/output_schema.md#engine-field-evolution-emits). |
| Tests | [`test_lattice_continuum.cpp`](../../../tests/test_lattice_continuum.cpp) · [`test_field_evolution.cpp`](../../../tests/test_field_evolution.cpp) | Pure C++; about 3 s and 30 s in Release. |
| Declarations | `declareCarrierField` in [`lava_lamp.js`](../../../examples/scenarios/lava_lamp/lava_lamp.js) · `declareChargeField` in [`glass_from_sand.js`](../../../examples/scenarios/glass_from_sand/glass_from_sand.js) | Declare only. The authored column and the furnace's operator temperatures are validation references. |

## Recorded arbitration on the lava lamp (default 600 s, 2026-11-19)

Recorded under a pinned budget: `TRECH_COMPUTE_BUDGET` with 300 GFLOPS, 8 hardware and 6 torch
threads, 16 GiB, memory fraction 0.05 and 0.05 s per call. The lamp declares its 24-cell carrier
column (cylinder R = 30 mm, H = 180 mm). Properties come from the cascade:

- ν = 258 mm²/s, from the effective dynamic viscosity and the Geant4 density;
- κ = 18.1 mm²/s;
- β = 3.04·10⁻⁴ K⁻¹.

Exchanges are the heater and top relaxations and the replayed wax load. The engine built a 6 mm
convective lattice (τ = 0.579, dt = 3.7 ms), a 6 mm conductive lattice and a 9 mm twin. None
failed.

| Method | RMSE vs reference (K) | Coverage | Share selected |
| --- | --- | --- | --- |
| `lattice_conductive` | 0.127 (best full-coverage) | 1.00 | 0.13 |
| `lattice_convective` | 0.292 | 1.00 | 0.01 |
| `learned_operator` | 0.067 on its cells | 0.84 | 0.83 |
| `persistence` | 0.358 | 1.00 | 0.03 |
| **arbitrated** | **0.100** | 1.00 | — |
| oracle (best per cell) | 0.075 | — | — |

By window (RMSE in K):

| Calls | Time (s) | Arbitrated | Oracle | Best full-coverage | Learned operator (coverage) |
| --- | --- | --- | --- | --- | --- |
| 1–40 | 0–195 | **0.143** | 0.128 | conductive 0.174 | 0.054 (0.70) |
| 41–80 | 200–395 | 0.099 | 0.020 | conductive 0.100 | 0.101 (0.90) |
| 81–121 | 400–600 | **0.0085** | 0.0079 | persistence 0.056 | 0.0012 (0.93) |

The learned policy was applied on 65 % of calls. Normal-path emits are byte-identical with the
declaration on or off. Wall time is 103 s with it (17 s without, earlier record). Of the
cell-steps, 3.9·10⁸ belong to the convective lattice, which was selected for 1 % of cells.

Reading:

- The arbitration now beats the best full-coverage single method over the run. Before the
  registry it was 0.164 K against 0.127 K.
- The gain comes from the learned operator, which distils the authored column; the lattices
  keep the cells where the operator is remote from its support.
- The middle window only ties conduction: the oracle (0.020 K) shows the gain still available.
- The reference is the authored column, so this grades agreement with a teacher, not
  experimental accuracy. A learned operator trained on a teacher can at best reproduce it.

## Recorded arbitration on the glass furnace (default 150 ticks, 2026-11-19)

Same pinned budget; two runs gave byte-identical emits. The furnace declares its 6³ = 216-cell
charge (box 120 mm, 20 mm pitch) with:

- κ = c·pitch² = 7.4 mm²/s, from the cascade conduction coefficient c = 0.0185 s⁻¹;
- floor and roof contacts relaxing at c toward the furnace (1750 K) and ambient (300 K)
  temperatures;
- no flow property.

The reference is the run's own per-material operator temperatures. The convective lattice was
excluded ("no positive kinematic viscosity declared").

| Method | RMSE (K) | Coverage | Share selected |
| --- | --- | --- | --- |
| `lattice_conductive` (6 mm, dt = 0.61 s) | 78.4 | 1.00 | 0.003 |
| `learned_operator` | 2.33 on its cells | 0.83 | 0.79 |
| `persistence` | 28.2 (best full-coverage) | 1.00 | 0.21 |
| **arbitrated** | **28.1** | 1.00 | — |
| oracle | 13.8 | — | — |

| Ticks | Time (s) | Arbitrated | Oracle | Persistence | Lattice | Learned operator (coverage) |
| --- | --- | --- | --- | --- | --- | --- |
| 1–50 | 0–2940 | 48.8 | 24.0 | 49.0 | 84.5 | 5.19 (0.49) |
| 51–100 | 3000–5940 | **0.400** | 0.351 | 0.519 | 75.8 | 0.511 (1.00) |
| 101–151 | 6000–9000 | **0.0183** | 0.0134 | 0.030 | 74.6 | 0.0214 (1.00) |

Reading:

- The engine rejected the lattice built from the declared property in every window. The
  cascade coefficient makes conduction about 4.6× faster than the run's own batch|batch pair
  law (0.004 s⁻¹). That is a finding about the declaration or the cascade output, queued in the
  roadmap.
- After the heating front, the arbitration beats every single method.
- While heating, it only ties persistence. The learned operator abstains on half the cells
  there, and the first steep step (448 K in one tick) is a blind call.

Earlier development findings (the free-running confrontation, 4/6 mm spatial convergence, the
staggered-mode defect and the superseded 2026-11-18 record) are in the
[roadmap history](ROADMAP.md#2026-11-18--lattice-module-native-kernel-and-lava-lamp-companion).

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
- **Hard-coding the candidate list.** A method added by name in `FieldEvolution` would need code
  changes for every later method and invites special cases. Register it, and let the arbiter
  treat it like every other method.
- **Regressing absolute errors.** Local error laws go negative near zero, and a negative
  predicted error then wins every selection (persistence once got −0.08 for a true +0.008).
  Learn log errors.
- **One error learner for all methods.** A row then needs every method's prediction. A method
  that abstains at the active cells blinds the arbiter exactly where it matters. Keep one
  learner per method.
- **Squared sums or plain log scores alone for policies.** Squared sums let one early transient
  freeze the choice for many calls. A log-ratio alone trades rare large losses for many small
  wins. Require both.
- **A quadratic basis for learned increments.** On the lamp it turned a 0.01 increment into 0.53
  of the span inside the learned box: the joint support was sparse and the context shifted.
  The drives are linear in the physics, so an affine law per domain is enough; nonlinearity
  enters through domain splits.
- **Ranking an abstaining method by its own cells.** It looks best because it skips the hard
  cells. Compare against full-coverage methods and the oracle (`rmse_common`, `coverage`).
- **Unpinned compute budget.** Learner capacities follow the timed host budget. The same code
  then gives different arbitration under load (glass middle window 0.39–0.70 K across three
  runs). Pin `TRECH_COMPUTE_BUDGET` for recorded results.
