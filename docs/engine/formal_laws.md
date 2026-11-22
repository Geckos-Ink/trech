# Formal laws with Lean

[Engine contracts](README.md) · [Documentation index](../README.md)

TRECH has started a route to describe the laws and the mathematics it relies on in
[Lean 4](https://lean-lang.org). Lean is a programming language and a proof assistant: a
statement written in Lean (a *theorem*) is accepted only with a proof that Lean's kernel checks.
[Mathlib](https://github.com/leanprover-community/mathlib4) is the community library of
mathematics written in Lean, from real analysis to linear algebra and probability.

**Status (2026-11-22): six law pairs exist and their 19 Lean theorems are verified.** The
classic code of each pair is checked against its Lean statement by an ordinary test, without
Lean. The Lean files compile with Lean `v4.37.0-rc1` and the pinned Mathlib, and every theorem
rests only on Lean's three standard axioms, so no step is assumed. The proofs are about real
numbers: they do not by themselves prove the floating-point code correct (see below). TRECH
does not link or run Lean. The engine itself now checks the lattice theorems' hypotheses each
time it builds a lattice and reports them in the [engine trace](engine_trace.md), but no run
output or provenance record carries a law check yet. The open work is in the
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

## The first law pairs

[`formal/laws.json`](../../formal/laws.json) lists each pair: an id, a plain statement, the
Lean file and theorems, and the classic sources.

| Pair | Lean (`formal/`) | Classic code | What is checked without Lean |
| --- | --- | --- | --- |
| Compton kinematics | `Trech.Laws.Compton`: the electron's share `T/E` lies between 0 and the Compton edge `2ε/(1+2ε)`, and equals the edge at back-scatter | `include/trech/sim/KleinNishina.hpp`, `js/trech_formal_laws.js` | 410 (energy, angle) samples respect the bound; the C++ and JavaScript values are bit-identical |
| Beer–Lambert attenuation | `Trech.Laws.Attenuation`: survival `exp(-μx)` multiplies over consecutive paths, stays in (0, 1] and decreases with path length | `src/sim/AnalyticCrossCheck.cpp`, `js/trech_formal_laws.js` | `S(x+y)` against `S(x)·S(y)` on 20 path pairs, within a stated float tolerance |
| Lattice mass conservation | `Trech.Methods.Lattice`: the collision keeps a cell's mass if the equilibrium does, a zero-sum source keeps it, streaming along a bijection keeps the total | `src/core/LatticeKinetic.cpp` | the theorems' hypotheses (velocity-set moments, opposite-direction table, streaming map) and the total mass over 300 forced steps on a periodic lattice |
| Scalar lattice conservation | `Trech.Methods.Lattice.advectedEquilibrium_sum`: the advection-diffusion equilibrium carries the cell's value, so with the same collision and streaming theorems a scalar lattice with closed (zero-flux) walls keeps its total | `src/core/LatticeKinetic.cpp`, `src/core/LatticeContinuum.cpp` | the engine's own hypothesis checks on a walled lattice with an obstacle, and the scalar total over 400 advected steps; a Dirichlet wall (which adds scalar by design) is the counter-example |
| Reaction step probabilities (`ctx.react`) | `Trech.Methods.Transition`: the engine's two-stage draw fires channel `c` with probability `h·s_c/S`; these are nonnegative and add up to the event hazard `h ≤ 1`, leaving `1 − h` for "no transition" | `selectTransitionChannel` in `src/ml/DiscreteTransition.cpp` | the engine's draw function swept over 2²⁰ evenly spaced draws for four hazard/score cases; each outcome's share matches its probability within 2/2²⁰ |
| Method arbiter scoring | `Trech.Methods.Arbiter`: the squared error is minimised exactly by the mean prediction (a *strictly proper* score), and ranking by `log(error + floor)` keeps the error order | `src/ml/MethodArbiter.cpp` | 40 noisy graded calls with an unbiased method and two biased ones: the unbiased one scores lowest and leads, although the declared fallback is a biased one |

The attenuation row shows why the real-versus-float caveat matters. Over the reals,
`exp(-μ(x+y)) = exp(-μx)·exp(-μy)` exactly. In doubles the two sides differ by about two units
in the last place, so the check states a tolerance of `2e-15` relative, and a second check
that demands exact equality fails on purpose to keep that gap visible.

Two of the new pairs state properties of engine methods rather than physical laws. In the
reaction step, `h` is the chance that anything happens in the step and `s_c` is channel `c`'s
score, with total `S`. One random number `u` between 0 and 1 decides: nothing happens when
`u ≥ h`; otherwise `u` is rescaled and the channel whose share of the scores contains it fires.
For example, with `h = 0.3` and scores `0.2, 0.5, 0.3`, the channels fire with probabilities
`0.06, 0.15, 0.09` and nothing happens with probability `0.7`. The theorem proves this always
gives a valid probability vector; the test confirms the engine's actual function produces it.

A scoring rule is *proper* when a method scores best, on average, by predicting the true
expected value instead of a shifted one. The arbiter grades methods by squared error, and the
theorem proves that over any weighted set of references the mean prediction beats every
other value by exactly `(total weight)·(shift)²`. So the arbiter cannot reward a biased
method that happens to look stable. The theorem covers one weighted set of references; the
arbiter's leader ranks by an average of log errors across calls, which it does not cover.

The engine also runs the lattice hypothesis checks itself. Each time it builds a lattice for
field evolution it checks the velocity set's moments, the opposite-direction table and the
streaming table, once, without touching the populations. With tracing on
(`--trace info:formal`), the [engine trace](engine_trace.md) gets one `formal` record per
lattice listing each check. A failed check is always printed as a warning. A lattice with
moving walls or fixed-value (Dirichlet) walls still passes, with a note that it adds mass or
scalar by design, so the conservation theorems do not apply to it.

Run the checks (both are part of the normal CTest suite):

```bash
ctest --test-dir build/rel -R trech_formal
```

The output lists each check with its Lean declaration, sample count, largest error and verdict.
Checks named `negative_control` are meant to fail: they prove each check can catch a violation.

A validation companion can use the same classic references:

```js
TRECH_INCLUDE("../../../js/trech_formal_laws.js");
const checks = TRECH_FORMAL_LAWS.checkComptonBounds([0.5, 1.3], [-1, 0, 1], 1e-15);
// each record: {law, lean_declaration, lean_status: "not_checked_by_this_check", role: "validation", passed, ...}
```

To check the proofs yourself you need Lean and Mathlib's prebuilt files (a one-time download
of about 7 GB):

```bash
brew install elan-init
scripts/pull_lean.sh
(cd formal && lake exe cache get)
python3 scripts/check_lean_laws.py
```

The last command builds the package and prints one line per theorem with the axioms it uses,
ending with `19/19 theorems proved from standard axioms only`. An unfinished proof (`sorry`) or
an added axiom makes it fail. Add `--report build/lean_audit.json` to also save the audit
as JSON: the Lean version, toolchain and Mathlib revision, the SHA-256 hash of `laws.json` and
of every Lean file, and each theorem's axioms. This is the identity a run would record once
law checks reach the run outputs; nothing reads it yet. Configuring TRECH with
`-DTRECH_ENABLE_LEAN_CHECK=ON` runs the same check as the CTest entry `trech_formal_lean_build`. More detail:
[`formal/README.md`](../../formal/README.md).

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
nothing. After it moves Mathlib, copy `thirds/mathlib4/lean-toolchain` to
`formal/lean-toolchain` and fetch the matching cache again (`lake update` and
`lake exe cache get` in `formal/`). Building Lean itself or all of Mathlib from source takes a
long time and needs an explicit go-ahead.

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
