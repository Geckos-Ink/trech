# Formal laws and Lean verification — context and contracts

[Root principles](../../../AGENTS.md) · [Root roadmap](../../../ROADMAP.md) · [Parent](../AGENTS.md) · [Roadmap](ROADMAP.md)

Related owners: [Builds and dependencies](../../tooling/dependencies/AGENTS.md) · [Geant4 transport and diagnostics](../simulation/AGENTS.md) · [Lattice methods](../lattice/AGENTS.md) · [Scenario bundles](../../scenarios/bundles/AGENTS.md).

Read the root principles and the parent handbook first; then open only the subcategory relevant to the task. Source paths and shell commands in code spans/blocks are repository-relative unless stated otherwise; Markdown links resolve from this file.

**Maturity: route opened 2026-11-22, nothing implemented in the engine; Lean is optional.**
Only the two source checkouts, the pull script and the Mathlib declaration search exist. No
Lean code is built, linked or run by TRECH, no config field exists, and no result is
Lean-checked. Classic C++/JavaScript implementations stay the running path (see the first rule). The plan and
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
  (CMake, tens of minutes) or Mathlib (thousands of files, or several GB of prebuilt
  `lake exe cache get` downloads) needs an explicit go-ahead, like Geant4 and V8. The toolchain
  of record is Mathlib's `lean-toolchain`, installed through `elan` or built from `thirds/lean4`
  checked out at that tag.
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
- **Provenance.** Once a law is checked by a run, the run records the Lean declaration name,
  the module source hash, the Lean toolchain and the Mathlib revision. New config fields are
  conditionally serialized (root principles).

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

## Current pins

The TRECH git tree records the revisions (`git submodule status thirds/lean4 thirds/mathlib4`).
First checkout (2026-11-22): lean4 `5ec4e0be17` (`master`), mathlib4 `6ebcce3733` (`master`),
whose `lean-toolchain` is `leanprover/lean4:v4.37.0-rc1`. The lean4 `master` tip is newer than
that release candidate, so a from-source toolchain build must check out the tag first.

## Source map

| Path | Contents |
| --- | --- |
| [`scripts/pull_lean.sh`](../../../scripts/pull_lean.sh) | Fast-forward both checkouts, print heads, check the toolchain Mathlib expects. |
| [`scripts/lean_mathlib_search.py`](../../../scripts/lean_mathlib_search.py) | Grep Mathlib declaration headers (`theorem`, `lemma`, `def`, `structure`, …) by regex. |
| [`docs/engine/formal_laws.md`](../../../docs/engine/formal_laws.md) | User guide: what the route is for, how to pull and search, what is not done yet. |
