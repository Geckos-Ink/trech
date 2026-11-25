# Formal laws and Lean verification — context and contracts

[Root principles](../../../AGENTS.md) · [Root roadmap](../../../ROADMAP.md) · [Parent](../AGENTS.md) · [Roadmap](ROADMAP.md)

Related owners: [Builds and dependencies](../../tooling/dependencies/AGENTS.md) · [Geant4 transport and diagnostics](../simulation/AGENTS.md) · [Lattice methods](../lattice/AGENTS.md) · [Scenario bundles](../../scenarios/bundles/AGENTS.md).

Read the root principles and the parent handbook first; then open only the subcategory relevant to the task. Source paths and shell commands in code spans/blocks are repository-relative unless stated otherwise; Markdown links resolve from this file.

**Maturity (2026-11-25): nineteen law pairs, 84 proofs verified. Lean stays optional.** The pairs
([`formal/laws.json`](../../../formal/laws.json)) are Compton kinematics, the Compton relation
from four-momentum conservation, the energy balance of a recorded step, Beer–Lambert attenuation, lattice mass conservation, scalar-lattice conservation, `ctx.react` step
probabilities and declared count conservation, antisymmetric `ctx.interact` exchange, the bounded explicit step of `ctx.evolve` and `ctx.interact`, the order independence of set networks, `ctx.lift` group assembly, the domain learner's split score, the
method arbiter's proper squared score and its decayed prequential scores, stage order inside a `ctx.evolve` band, `ctx.learnDomains` routing the registration order of `ctx.cascade` and the pruned joint-coverage scan of learned models. Their classic C++/JS code is
checked against each Lean statement by `trech_formal_laws`, and the pair links by
`trech_formal_law_pairs` (both in the normal suite, no Lean needed). The 84 Lean theorems
compile with Lean `v4.37.0-rc1` and Mathlib `348837d` and depend only on the standard
axioms (`propext`, `Classical.choice`, `Quot.sound`), checked by the opt-in
`trech_formal_lean_build`. The count proof uses mathematical integers. The exchange proof uses
reals, with classic conformance tested before bound clipping at `1e-15` relative. The
engine runs four classic checks itself: `Lattice` checks its pair's hypotheses once per build
(`lawChecks()`, trace category `formal`), a run with a `beer_lambert` analytic check records
`attenuation.memoryless` at Geant4's own attenuation coefficient (`sim/AttenuationLaw.hpp`,
2e-15 relative), and a run with a `compton_energy_transfer` analytic
check records `energy.step_balance` over every first Compton scatter and
`compton.momentum_balance` (the `Trech.Laws.TwoBody` hypothesis) over those whose products are all
tracks, read from Geant4's step record in `SteppingAction` (`sim/EnergyBalance.hpp`; relative
tolerance `1e-12`, plus the stated `momentumRoundingBound` for momentum). Runs record their checks (2026-11-22): `law_checks`
in the `run_end` scores (origins `engine` and `validation`) and a provenance `formal` object
with the build-embedded law-source hashes and, with `--formal-audit`, the Lean audit identity.
No config field. One bundled companion records checks (`analytic_compton_transfer`).
Classic C++/JavaScript implementations stay the running path (see the first rule). The plan and
every open item are in the [roadmap](ROADMAP.md#priority-queue). User guide:
[`docs/engine/formal_laws.md`](../../../docs/engine/formal_laws.md).

## Purpose

Describe the laws and the mathematics TRECH relies on in [Lean 4](https://lean-lang.org), a
programming language and proof assistant, so that a statement (a conservation law, an
invariant, a kinematic identity, a method's property) carries a machine-checked proof instead
of a comment. The aim is more reinforcement for the validation math the engine and the
scenarios already contain: a Lean theorem says exactly what holds, under which hypotheses.

## Sources

| Checkout | Upstream | Role |
| --- | --- | --- |
| [`thirds/lean4`](../../../thirds/lean4) | [leanprover/lean4](https://github.com/leanprover/lean4) | Compiler, kernel, runtime and the C FFI headers (`src/include/lean/lean.h`). Reference source and the from-source toolchain. |
| [`thirds/mathlib4`](../../../thirds/mathlib4) | [leanprover-community/mathlib4](https://github.com/leanprover-community/mathlib4) | The community mathematics library. **Check it before declaring any theorem**, so TRECH never restates what Mathlib already proves. |

Both are shallow submodules (`shallow = true`, `branch = master` in [`.gitmodules`](../../../.gitmodules)).

## Rules

- **Lean is optional for now: implement every law twice.** Until the owner decides otherwise,
  no build, CTest entry, scenario run or Studio path may require Lean, `lake` or Mathlib. Each
  law or method that gets a Lean description keeps its **classic implementation** (C++ in the
  engine, JavaScript in the scenario or its `.validation.js` companion), and that classic
  implementation is the one that runs. The **Lean definition** sits next to it, for validation:
  1. a proof that the stated law or invariant holds under its hypotheses;
  2. conformance: the classic implementation's results, on sampled or recorded inputs, agree
     with the Lean reference evaluator within a stated tolerance;
  3. a hypothesis check: the classic code's preconditions (units, domains, signs, limits) match
     the theorem's.
  Without the Lean toolchain, Lean-backed checks skip with a recorded reason and the classic
  path is unchanged. A classic implementation is never deleted because a Lean one exists, and a
  Lean definition never replaces the engine's method selection. Name the pair so each side
  finds the other: the classic source cites the Lean declaration in a comment, and the Lean
  docstring cites the classic source path.
- **Pull before use.** Every task that reads, searches or builds either checkout first runs
  [`scripts/pull_lean.sh`](../../../scripts/pull_lean.sh). It fast-forwards both to upstream
  `master` (`git pull --ff-only`, deepening the shallow clone as needed), prints the new
  heads and the toolchain Mathlib expects (`thirds/mathlib4/lean-toolchain`), and warns when
  `thirds/lean4` is not at that release. Commit the moved submodule pointers in the same change
  as the work that needed them, and update the pins below.
- **Mathlib first.** Before writing a `theorem`, `lemma` or `def`, search Mathlib for it:
  `python3 scripts/lean_mathlib_search.py <regex>` greps declaration headers under
  `thirds/mathlib4/Mathlib`. Grep finds names and statement text, not equivalent statements, so
  after the toolchain gate also try `exact?`/`apply?` in Lean. Reuse or specialise a Mathlib
  result; a new declaration states only what Mathlib lacks, and its docstring names the
  Mathlib results it builds on.
- **Building is heavy and gated.** Pulling is light; building is not. Compiling `thirds/lean4`
  (CMake, tens of minutes) or all of Mathlib from source needs an explicit go-ahead, like
  Geant4 and V8. The toolchain of record is Mathlib's `lean-toolchain`, installed through
  `elan` (Homebrew `elan-init`, done 2026-11-22 on macOS arm64) or built from `thirds/lean4`
  at that tag. Mathlib's prebuilt cache (`lake exe cache get` in `formal/`, about 9,100 files
  and 6.9 GB under `thirds/mathlib4/.lake`, ignored by Mathlib's `.gitignore`) is fetched
  again after each Mathlib pull; the TRECH package itself then builds in seconds.
- **After a Mathlib pull:** copy `thirds/mathlib4/lean-toolchain` to `formal/lean-toolchain`
  (`trech_formal_law_pairs` fails until they match), run `lake update` and
  `lake exe cache get` in `formal/`, then `python3 scripts/check_lean_laws.py`; fix any proof a
  Mathlib rename breaks, and commit `formal/lake-manifest.json` with the new pointer.
- **Lean states and checks; it never becomes a classical-formula engine.** A Lean-stated law
  follows the root principles: a closed-form physical law stays a validation or comparison
  reference (`reference`, `validation` roles), fed from Geant4's own particle-level data, and
  stays off the decision path. What Lean may prove for the engine itself is the correctness of
  engine methods and invariants (for example that a lattice collision conserves mass and
  momentum, that a probability vector stays normalised, that the arbiter's prequential score is
  a proper scoring rule). A scenario may cite a Lean law only from its `.validation.js`
  companion.
- **Hardware acceleration stays on the hot path.** Lean compiles to single-threaded scalar C
  with reference counting; it has no SIMD, GPU or Torch backend. Large computations stay in the
  engine's accelerated kernels (C++, LibTorch, Metal/WebGPU in Studio). Lean contributes the
  specification and proofs, and at most a slow reference evaluator used to check an
  accelerated kernel on sampled inputs (conformance), never per step in a production run. A
  Lean check must not change physics, RNG consumption or emitted fields, and its cost is
  measured and budgeted.
- **Reals are not floats.** Mathlib proves over `ℝ`; the engine computes in IEEE-754 doubles.
  A theorem over `ℝ` does not certify the floating-point kernel. Bridge the two explicitly
  (stated error bounds, interval arithmetic, or a proof over the rounding model) and label the
  gap otherwise.
- **Provenance.** A run that performs a law check records it: every check goes through
  `formal::recordRunCheck` (engine code with origin `engine`; companions through
  `TRECH_FORMAL_LAWS.record`, origin `validation`), the CLI drains it at each run end into
  `law_checks` and the provenance `formal` object, and a run without checks writes neither.
  The law-source identity (`formal::manifestSha256`, `formal::sourcesSha256`) is embedded by
  CMake; the Lean identity (version, toolchain, Mathlib revision) comes only from a
  `check_lean_laws.py --report` file named by `--formal-audit`/`TRECH_FORMAL_AUDIT`, and
  `lean_status: "audited"` requires that report to match the embedded hashes. Law checks never
  enter the config or its hash, and never feed back into a run.

## Geant4 secondary track

Secondary objective: express Geant4's own basic physical laws in Lean, starting from the
simplest (relativistic two-body kinematics, the Compton relation from four-momentum
conservation, exponential attenuation from a constant interaction rate, energy conservation in
`SampleSecondaries`), then attach those statements to the Geant4 models that implement them.

- **C++ inheritance is preferred.** Derive from the Geant4 class (for example
  `G4KleinNishinaCompton`, `G4BetheBlochModel`, a `G4VEmModel`), delegate to the base, and
  check or compare the result against the Lean statement in shadow mode. Register the derived
  model through the physics list or `G4EmConfigurator`, never by editing `thirds/geant4`.
- **A git patch only when inheritance cannot reach the code** (a non-virtual or private
  method). Patches live under `patches/geant4/` with the reason, the upstream revision they
  apply to and the build step that applies them. The submodule checkout stays pristine.
- **Geant4 stays the base of truth.** A derived model first observes. It may replace a Geant4
  computation only with byte parity (strict mode) or a validated, documented tolerance, a
  regression run against the unpatched build, and the owner's go-ahead. Any rebuild of Geant4
  for a patch is a heavy, gated build.

## Points to keep stable

- **Float tolerances are stated, not hidden.** `attenuation.memoryless` holds exactly over `ℝ`
  but `exp(-μ(x+y))` and `exp(-μx)·exp(-μy)` differ by about 2 ulp in doubles (2.3e-16
  relative seen on macOS arm64), so the check allows 2e-15 relative and an exact-equality
  negative control shows the gap. The lattice check allows 1e-13 relative over 300 steps (2.1e-14
  seen). Tighten a tolerance only with evidence; never loosen one to make a check pass.
- **Run the conformance test in an optimised build too.** A Debug build never fuses
  multiply-add, so it cannot show a source that does. Every source that calls a proved function
  (`BoundedStep.hpp`, `DecayedScore.hpp`, the lattice kernels, the arbiter) is compiled with
  `-ffp-contract=off` (`CMakeLists.txt`); `StateEvolution.cpp` and `PairInteraction.cpp` were
  missing until 2026-11-23, and in Release a fused `x + r·dt` broke the bounded-step checks by
  1 ulp and turned `inf − inf` into `inf`.
- **Engine methods route through the proved function.** `ctx.react` draws only through
  `selectTransitionChannel`, `ctx.evolve` and `ctx.interact` step and clamp only through
  `boundedEulerStep`/`clampToBounds` (`ml/BoundedStep.hpp`) and count steps outside the
  theorems (non-finite increment or NaN result) as `nonFiniteSteps` without repairing them, the arbiter grades by squared
  error ranked through `log(error + floor)`, and every decayed arbiter score advances only
  through `decayedUpdate` (`ml/DecayedScore.hpp`). Changing either changes what `Trech.Methods.Transition`,
  `Trech.Methods.Evolve`, `Trech.Methods.Arbiter` or `Trech.Methods.Decay` covers: update the Lean pair and its conformance check in the same change.
- **`ctx.cascade` order is covered only for producer-first bands.** `Trech.Methods.Cascade`
  assumes each fact has one writer per band and that no stage runs before an in-band producer
  of its inputs. `ScaleCascade::run`'s ready-stage choice meets this unless a fact an in-band
  stage writes is already present at band start (a stale read); changing readiness or the band
  sort changes what the pair covers: update it and `cascadePairs` in the same change.
- **Engine-side checks observe only.** `Lattice::checkLaws` runs once per build, touches no
  population, RNG stream, emit or output, and reports through the trace; a failed check is a
  warning, never an exception. Moving walls and Dirichlet links pass the bijection check with a
  "not conservative by design" detail; they are not failures. The Compton energy balance reads
  `GetSecondaryInCurrentStep` and `GetTotalEnergyDeposit` without touching the track; its
  accumulables merge by sum and maximum, and it writes only when a `compton_energy_transfer`
  check is configured, so other runs keep their bytes. Its `max_abs_error` is relative to the
  step's largest energy term. The momentum check's tolerance is per scatter
  (`momentumRoundingBound`, growing like `√(m / 2T)` for a small transfer `T`); the record
  reports the largest bound used.
- **One law-source hash, two implementations.** CMake (`TRECH_FORMAL_SOURCES_SHA256`) and
  `check_lean_laws.py` (`sources_sha256`) hash the same files the same way; `trech_formal_laws`
  recomputes it from the tree. Adding a Lean file outside `formal/Trech.lean` or
  `formal/Trech/**.lean` needs all three updated.
- **Hypothesis checks matter as much as invariants.** `relaxTRT_sum_eq` assumes `∑ feq = ∑ f`,
  which the classic kernel gets from the velocity-set moments; `stream_sum_eq` assumes `src` is a
  bijection, which moving-wall and anti-bounce-back links break (they are not conservative by
  design). A new lattice configuration that should conserve mass must pass these checks.

## Current pins

The TRECH git tree records the revisions (`git submodule status thirds/lean4 thirds/mathlib4`).
Current checkout (2026-11-25): lean4 `451d44e` (`master`), mathlib4 `348837d` (`master`),
whose `lean-toolchain` is `leanprover/lean4:v4.37.0-rc1`. The lean4 `master` tip is newer than
that release candidate, so a from-source toolchain build must check out the tag first.

## Source map

| Path | Contents |
| --- | --- |
| [`scripts/pull_lean.sh`](../../../scripts/pull_lean.sh) | Fast-forward both checkouts, print heads, check the toolchain Mathlib expects. |
| [`scripts/lean_mathlib_search.py`](../../../scripts/lean_mathlib_search.py) | Grep Mathlib declaration headers (`theorem`, `lemma`, `def`, `structure`, …) by regex. |
| [`docs/engine/formal_laws.md`](../../../docs/engine/formal_laws.md) | User guide: what the route is for, how to pull and search, what is not done yet. |
| [`formal/`](../../../formal) | Lake package `trech_formal` (Mathlib by path from `thirds/mathlib4`, with the same toolchain). The [module index](../../../formal/README.md) links each proof to the running C++ or JavaScript implementation. |
| [`formal/laws.json`](../../../formal/laws.json) | `trech_formal_laws_v1` pair manifest: id, role, statement, Lean file + declarations, classic sources and the namespace each cites, conformance checks. |
| [`include/trech/core/FormalLaws.hpp`](../../../include/trech/core/FormalLaws.hpp) · [`src/core/FormalLaws.cpp`](../../../src/core/FormalLaws.cpp) | `trech::formal::LawCheck` and the physics-agnostic classic checks: `checkConservedTotal` (Neumaier sums), `checkWithinBounds`, `checkProbabilityVector`, `checkAgreement`, and the hypothesis checks `checkPermutation`, `checkInvolution`, `checkVelocityMoments`. `toJson()` records `lean_status: "not_checked_by_this_check"`. In `trech_core`; the engine calls the three hypothesis checks from `Lattice::checkLaws` ([`LatticeContinuum.cpp`](../../../src/core/LatticeContinuum.cpp)). |
| [`DiscreteTransition.hpp`](../../../include/trech/ml/DiscreteTransition.hpp) · [`MethodArbiter.cpp`](../../../src/ml/MethodArbiter.cpp) | `selectTransitionChannel` (the `ctx.react` draw, pair `Trech.Methods.Transition`) and the arbiter's squared-error grading (pair `Trech.Methods.Arbiter`); its decayed scores advance through [`DecayedScore.hpp`](../../../include/trech/ml/DecayedScore.hpp) (pair `Trech.Methods.Decay`). |
| [`GenericSurrogate.cpp`](../../../src/ml/GenericSurrogate.cpp) | `predictSet` (DeepSets and message passing behind `ctx.lift` and set operators), pair `Trech.Methods.SetPool`. A `generic_surrogate_v3` set network whose element slots do not share their feature's `input_mean`/`input_std` fails to load (the theorems' hypothesis); every committed set model ties them exactly. |
| [`GroupHierarchy.cpp`](../../../src/ml/GroupHierarchy.cpp) | `partition` and the per-group weight and weighted centroid of `ctx.lift`, pair `Trech.Methods.Group`. |
| [`LeastSquaresStatistics.hpp`](../../../include/trech/ml/LeastSquaresStatistics.hpp) | `sseFromStatistics` (the batched `c − 2β·b + β·Aβ` that `DomainLearner`'s `scoreCuts` uses to score candidate splits) and `bicSplitAccepted` (its BIC gate), pair `Trech.Methods.LeastSquares`. |
| [`BoundedStep.hpp`](../../../include/trech/ml/BoundedStep.hpp) | `boundedEulerStep`, `clampToBounds` and `boundsOrdered`: the explicit step and declared-bounds clamp of `ctx.evolve` (`StateEvolution.cpp`) and `ctx.interact` (`PairInteraction.cpp`), pair `Trech.Methods.Evolve`. `JsRuntime.cpp` throws a `RangeError` for a field whose bounds fail `boundsOrdered` (the theorems' hypothesis). |
| [`js/trech_formal_laws.js`](../../../js/trech_formal_laws.js) | `TRECH_FORMAL_LAWS` (QuickJS, V8, Node): classic `compton` and `attenuation` references for validation companions, each naming its Lean declaration, the same check contract as C++ (`role: "validation"`), and `checkComptonBounds`/`checkAttenuationMemoryless`. Calls are reported as authored laws in the engine trace. |
| [`tests/test_formal_laws.cpp`](../../../tests/test_formal_laws.cpp) | CTest `trech_formal_laws`: classic C++ and JS against each statement, hypothesis checks on a periodic D2Q9 lattice driven through `advanceLattice` with a body force, the engine's own `lawChecks()` on a walled scalar lattice (400 advected steps) and a walled D3Q19 flow lattice, `selectTransitionChannel` over 2^20 draws, the arbiter on noisy references with biased rivals, the arbiter's decayed scores against their closed form and its leader under dominance and under abstention, bit-identical C++/JS Compton values (`-ffp-contract=off`), the run record (merging, provenance grading of missing/stale/partial/matching audits, JS recording and rejection), and a negative control per check kind. |
| [`tests/test_formal_law_pairs.py`](../../../tests/test_formal_law_pairs.py) | CTest `trech_formal_law_pairs`: each Lean file declares its listed theorems, has no `sorry`, cites its classic sources; each classic source cites the Lean namespace; `formal/lean-toolchain` equals Mathlib's. |
| Run record | `formal::recordRunCheck`/`takeRunChecks`/`provenanceBlock` ([`FormalLaws.cpp`](../../../src/core/FormalLaws.cpp)); drained in `TrechRunAction::EndOfRunAction` ([`RunAction.cpp`](../../../src/sim/RunAction.cpp)) after `onRunEnd`; `--formal-audit` in [`RunOptions.cpp`](../../../src/core/RunOptions.cpp); `__TRECH_FORMAL_RECORD` in [`JsRuntime.cpp`](../../../src/js/JsRuntime.cpp) (QuickJS and V8); law-source hashes embedded by [`CMakeLists.txt`](../../../CMakeLists.txt). |
| [`scripts/check_lean_laws.py`](../../../scripts/check_lean_laws.py) | `lake build` of `formal/`, then `#print axioms` for every declaration in `laws.json`; fails on a build error, a missing report or any axiom beyond `propext`, `Classical.choice`, `Quot.sound` (so `sorryAx` fails). Shared theorems are audited once. `--report PATH` writes `trech_lean_audit_v1` JSON (Lean version, toolchain, Mathlib revision, SHA-256 of `laws.json` and each module, `sources_sha256` computed exactly as CMake embeds it, per-declaration laws and axioms). |
| `TRECH_ENABLE_LEAN_CHECK` | Opt-in (OFF) CMake option registering `trech_formal_lean_build`, which runs `check_lean_laws.py` (needs `lake` and the Mathlib cache; about 12 s once cached). |
| [`formal/lake-manifest.json`](../../../formal/lake-manifest.json) | Lake's pins of Mathlib's own dependencies (batteries, aesop, Qq, ProofWidgets, plausible, …), cloned into ignored `formal/.lake/packages`. |
