# Formal laws with Lean

[Engine contracts](README.md) · [Documentation index](../README.md)

TRECH has started a route to describe the laws and the mathematics it relies on in
[Lean 4](https://lean-lang.org). Lean is a programming language and a proof assistant: a
statement written in Lean (a *theorem*) is accepted only with a proof that Lean's kernel checks.
[Mathlib](https://github.com/leanprover-community/mathlib4) is the community library of
mathematics written in Lean, from real analysis to linear algebra and probability.

**Status (2026-11-22): the route is open, nothing runs yet.** The repository holds the two
source checkouts and two helper scripts. TRECH does not build, link or run Lean, no scenario
uses it, and no result is Lean-checked. The open work is in the
[formal-laws roadmap](../../AGENTS/engine/formal/ROADMAP.md#priority-queue).

## What it is for

Several parts of TRECH already compute laws and invariants with ordinary code: a lattice method
should conserve mass and momentum, a reaction step should keep probabilities normalised, an
analytic cross-check applies a closed-form formula to Geant4's particle data. A Lean definition
next to such code states exactly what must hold and under which hypotheses, and proves it. It
reinforces the validation math; it does not replace the code.

## Lean is optional: classic code and Lean side by side

For now, Lean is never required. Every law that gets a Lean description keeps its classic
implementation (C++ in the engine, JavaScript in a scenario's `.validation.js` companion), and
the classic implementation is the one that runs. The Lean definition is used to validate it:

- the Lean proof shows the law or invariant holds;
- a conformance check compares the classic results with a Lean reference evaluation on sampled
  or recorded inputs, within a stated tolerance;
- the classic code's preconditions (units, domains, limits) are compared with the theorem's
  hypotheses.

Without Lean installed, these checks are skipped with a recorded reason and nothing else
changes. Example: the lattice collision step in the engine stays C++; a Lean theorem would
state that the collision conserves the summed density, and a conformance check would replay a
few recorded lattice cells through the Lean definition and compare them with the C++ output.

Two further limits keep Lean in its place:

- **Speed.** Lean compiles to plain single-threaded CPU code. Large computations stay in
  TRECH's accelerated kernels (vectorised C++, LibTorch, GPU rendering). Lean checks run
  offline or on samples, never at every step of a production run.
- **Real numbers versus floating point.** Mathlib proves statements about real numbers (`ℝ`).
  The engine computes with 64-bit floating-point numbers, which round. A theorem about `ℝ` does
  not by itself prove the floating-point code correct; the gap is stated explicitly.

Lean-stated physical laws follow the same rule as any closed-form law in TRECH: they are
validation references, fed from Geant4's own data, and never decide how a system is predicted.

## Get and update the sources

The checkouts are shallow submodules that track upstream `master`:

| Path | Contents |
| --- | --- |
| `thirds/lean4` | The Lean compiler, kernel and runtime sources. |
| `thirds/mathlib4` | Mathlib. Its `lean-toolchain` file names the Lean release it needs. |

Pull both before using them:

```bash
scripts/pull_lean.sh
```

The script fast-forwards both checkouts, prints their heads and reports whether `thirds/lean4`
is at the release Mathlib expects. On 2026-11-22 Mathlib expected `v4.37.0-rc1`, while the
Lean checkout was a newer `master` commit; the script prints how to fetch that tag. It builds
nothing. Building Lean or Mathlib downloads several GB or compiles for a long time, so it is a
separate step that needs an explicit go-ahead (see the
[dependency roadmap](../../AGENTS/tooling/dependencies/ROADMAP.md#priority-queue)).

## Search Mathlib before declaring a theorem

Do not restate a result Mathlib already proves. Search its declarations first:

```bash
python3 scripts/lean_mathlib_search.py 'exp_add'
```

The output lists each matching declaration as `path:line: header`, for example
`Mathlib/Analysis/Complex/Exponential.lean:110: theorem exp_add : exp (x + y) = exp x * exp y`.
Use `--kind theorem` to restrict the kind, `--path Analysis/SpecialFunctions` to restrict the
folder and `-i` to ignore case. The search matches names and statement text only; a result
stated differently or under another name is not found. Once Lean is built, Lean's own
`exact?` search closes that gap.

## Geant4 laws (secondary objective)

A later track expresses Geant4's own basic laws in Lean (two-body kinematics, the Compton
relation, exponential attenuation, energy conservation when a process produces secondaries) and
attaches them to the Geant4 models that compute them. TRECH would do this by deriving its own
C++ classes from the Geant4 model classes, which call the original and compare its result with
the Lean statement. A patch to the Geant4 sources is the fallback only where a method cannot be
overridden. Geant4 stays the base of truth: such a class only observes until a regression shows
it changes nothing. Contract: [formal-laws handbook](../../AGENTS/engine/formal/AGENTS.md#geant4-secondary-track).
