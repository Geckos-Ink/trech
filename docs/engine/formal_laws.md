# Formal laws with Lean

[Engine contracts](README.md) · [Documentation index](../README.md)

TRECH has started a route to describe the laws and the mathematics it relies on in
[Lean 4](https://lean-lang.org). Lean is a programming language and a proof assistant: a
statement written in Lean (a *theorem*) is accepted only with a proof that Lean's kernel checks.
[Mathlib](https://github.com/leanprover-community/mathlib4) is the community library of
mathematics written in Lean, from real analysis to linear algebra and probability.

**Status (2026-11-23): fourteen law pairs exist and their 49 Lean theorems are verified.** The
classic code of each pair is checked against its Lean statement by an ordinary test, without
Lean. The Lean files compile with Lean `v4.37.0-rc1` and the pinned Mathlib, and every theorem
rests only on Lean's three standard axioms. The transition count proof uses mathematical
integers. Other proofs that use real numbers carry a separate floating-point conformance test
where applicable. TRECH runs the classic implementations and records their runtime checks.
The engine checks the lattice theorems' hypotheses each time it builds a lattice. The
`analytic_compton_transfer` validation companion checks its Compton reference. Both checks
appear in the run's outputs and provenance
([below](#law-checks-in-run-outputs)). The open work is in the
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
| Energy balance of a recorded step | `Trech.Laws.EnergyBalance`: a step conserves energy when `E_pre + Q = E_post + ΣT_i + d` (its residual is zero); with no rest mass released (`Q = 0`) the outgoing particle and every secondary carry at most `E_pre`, and balanced steps telescope along a track | `include/trech/sim/EnergyBalance.hpp`, read in `src/sim/SteppingAction.cpp` | 410 Compton steps formed as Geant4's free-electron model forms them, a gamma conversion with `Q = −2 m_e c²` and a 41-step track close within `1e-12` relative; a step that drops its electron fails on purpose. In a Geant4 run the engine records the same check on every first Compton scatter |
| Compton from four-momentum | `Trech.Laws.TwoBody`: if a photon scatters off an electron at rest and energy and momentum are both conserved (the electron ending on its mass shell), then `m(E − E′) = E E′ − k·k′`, which is the Compton relation `E′(m + E(1 − cos θ)) = m E` | `include/trech/sim/KleinNishina.hpp` (the relation), `include/trech/sim/EnergyBalance.hpp` (momentum balance) | 410 scatters whose electron is built the way Geant4's model builds it (direction from the photon momenta, magnitude from its energy) conserve momentum within `1e-12`; a scattered energy 1% off fails on purpose. In a Geant4 run the engine records the momentum balance as the theorem's hypothesis check |
| Beer–Lambert attenuation | `Trech.Laws.Attenuation`: survival `exp(-μx)` multiplies over consecutive paths, stays in (0, 1] and decreases with path length | `src/sim/AnalyticCrossCheck.cpp`, `js/trech_formal_laws.js` | `S(x+y)` against `S(x)·S(y)` on 20 path pairs, within a stated float tolerance |
| Lattice mass conservation | `Trech.Methods.Lattice`: the collision keeps a cell's mass if the equilibrium does, a zero-sum source keeps it, streaming along a bijection keeps the total | `src/core/LatticeKinetic.cpp` | the theorems' hypotheses (velocity-set moments, opposite-direction table, streaming map) and the total mass over 300 forced steps on a periodic lattice |
| Scalar lattice conservation | `Trech.Methods.Lattice.advectedEquilibrium_sum`: the advection-diffusion equilibrium carries the cell's value, so with the same collision and streaming theorems a scalar lattice with closed (zero-flux) walls keeps its total | `src/core/LatticeKinetic.cpp`, `src/core/LatticeContinuum.cpp` | the engine's own hypothesis checks on a walled lattice with an obstacle, and the scalar total over 400 advected steps; a Dirichlet wall (which adds scalar by design) is the counter-example |
| Reaction step probabilities (`ctx.react`) | `Trech.Methods.Transition`: the engine's two-stage draw fires channel `c` with probability `h·s_c/S`; these are nonnegative and add up to the event hazard `h ≤ 1`, leaving `1 − h` for "no transition" | `selectTransitionChannel` in `src/ml/DiscreteTransition.cpp` | the engine's draw function swept over 2²⁰ evenly spaced draws for four hazard/score cases; each outcome's share matches its probability within 2/2²⁰ |
| Reaction count conservation (`ctx.react`) | `Trech.Methods.Transition.applyChannel_conserves` and `applyChannel_nonnegative` preserve declared weighted totals and the valid count range when applying or rejecting a channel | `src/ml/DiscreteTransition.cpp` | exact integer counts after accepted, unbalanced, insufficient and overflowing changes, including the signed 64-bit limit |
| Antisymmetric exchange (`ctx.interact`) | `Trech.Methods.PairInteraction.exchange_preserves_sum` conserves the real-valued total when each member receives opposite rates and increments and the resulting state stays within its bounds | `src/ml/PairInteraction.cpp` | two links sharing a member exchange a field within `1e-15` relative tolerance on the total. Forcing a bound to clip the state demonstrates the conservation check detects the change |
| Bounded explicit step (`ctx.evolve`, `ctx.interact`) | `Trech.Methods.Evolve`: the engine's step `x + r·dt`, clamped to the field's declared bounds `lo ≤ hi`, always lands in `[lo, hi]` and is left untouched when it already lies inside (the clamp is Mathlib's projection onto the interval); the unclamped increment is linear in `dt` and two steps at one rate equal one step of the summed length | `include/trech/ml/BoundedStep.hpp`, called by `src/ml/StateEvolution.cpp` and `src/ml/PairInteraction.cpp` | a constant-rate stage drives 41 elements across a two-sided and a one-sided bound through `StateEvolution::evolve`: every result is in bounds and equal to the clamp, the 62 unclipped steps are exact, scaling `dt` by 0.25, 2 and 3 scales the increment within `1e-15` absolute plus `1e-14` relative (4.4e-16 seen), and two steps of `dt` equal one of `2dt`. Unordered or NaN bounds (`min: 1, max: 0`, `min: NaN`) are rejected by `ctx.evolve` and `ctx.interact` with a `RangeError`; with them, the clamp breaks the lower bound, which a negative control shows |
| Set-network order independence (`ctx.lift`, set operators) | `Trech.Methods.SetPool`: the sum, mean and max pools over the present elements, a DeepSets readout and (as *equivariance*: permuting the inputs permutes the outputs) each message-passing round do not depend on element order, and an absent element that stays absent does not change the pool. The hypothesis is that every element slot shares its feature's input standardisation | `src/ml/GenericSurrogate.cpp` (`predictSet`; the loader enforces the hypothesis) | the committed DeepSets and message-passing fixtures and four variants (sum, mean and max pools; sum and mean aggregation), 11 rows under all 24 orders of their four element blocks: max pooling is exact, sums agree within `1e-12` relative (4.4e-16 seen); moving an absent element's features changes nothing, exactly. A model whose slot statistics differ fails to load |
| Group assembly (`ctx.lift`) | `Trech.Methods.Group`: one lifting level puts every element in exactly one group, the group weights add up to the total weight, and (when no group weighs zero) weight times centroid summed over the groups equals the elements' weighted first moment, so total weight and centre of weight are the same at every level | `src/ml/GroupHierarchy.cpp` | the three-level lift fixtures with unequal weights, plus an explicit first level, 18 levels in all: every element has one parent, weights agree within `1e-14` relative (2.8e-14 absolute seen) and moments within `1e-13`; a zero-weight group, whose centroid is NaN, fails on purpose |
| Domain-learner split score (`ctx.learnDomains`) | `Trech.Methods.LeastSquares`: for any coefficients β, the weighted squared error equals `c − 2β·b + β·Aβ` computed from the rows' summed statistics (`A = Σ w φφᵀ`, `b = Σ w φ y`, `c = Σ w y²`); statistics of disjoint row sets add, so prefix sums score every cut; and two separately fitted sides never do worse than one shared fit, which is why splits need a penalty | `include/trech/ml/LeastSquaresStatistics.hpp`, called by `src/ml/DomainLearner.cpp` | 240 weighted rows, a quadratic basis and two targets, 9 cuts: the statistic score matches the direct error within `1e-12·c` (6.5e-16 seen; the form cancels `c` against `2β·b`, so the bound is relative to `c`), left plus right statistics match the total, and exact side fits never exceed the parent; a sign error on the cross term fails on purpose |
| Method arbiter scoring | `Trech.Methods.Arbiter`: the squared error is minimised exactly by the mean prediction (a *strictly proper* score), and ranking by `log(error + floor)` keeps the error order | `src/ml/MethodArbiter.cpp` | 40 noisy graded calls with an unbiased method and two biased ones: the unbiased one scores lowest and leads, although the declared fallback is a biased one |

The attenuation row shows why the real-versus-float caveat matters. Over the reals,
`exp(-μ(x+y)) = exp(-μx)·exp(-μy)` exactly. In doubles the two sides differ by about two units
in the last place, so the check states a tolerance of `2e-15` relative, and a second check
that demands exact equality fails on purpose to keep that gap visible.

In the reaction step, `h` is the chance that anything happens in the step and `s_c` is channel `c`'s
score, with total `S`. One random number `u` between 0 and 1 decides: nothing happens when
`u ≥ h`; otherwise `u` is rescaled and the channel whose share of the scores contains it fires.
For example, with `h = 0.3` and scores `0.2, 0.5, 0.3`, the channels fire with probabilities
`0.06, 0.15, 0.09` and nothing happens with probability `0.7`. The theorem proves this always
gives a valid probability vector; the test confirms the engine's actual function produces it.

For a channel that exchanges one whole unit for two half units, the count change is `[-1, 2]`
and the conservation weights are `[2, 1]`. The weighted change is zero. If both updated counts
fit in `[0, INT64_MAX]`, TRECH applies the channel and the weighted total is preserved exactly.
If either count falls outside the range, both counts retain their original values.

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
lattice listing each check, and every run records them in `law_checks` (below). A failed check is always printed as a warning. A lattice with
moving walls or fixed-value (Dirichlet) walls still passes, with a note that it adds mass or
scalar by design, so the conservation theorems do not apply to it.

Run the checks (both are part of the normal CTest suite):

```bash
ctest --test-dir build/rel -R trech_formal
```

The output lists each check with its Lean declaration, sample count, largest error and verdict.
Checks named `negative_control` are meant to fail: they prove each check can catch a violation.

A validation companion can use the same classic references and record their verdicts in the
run (next section):

```js
TRECH_INCLUDE("../../../js/trech_formal_laws.js");
const checks = TRECH_FORMAL_LAWS.checkComptonBounds([0.5, 1.3], [-1, 0, 1], 1e-15);
// each record: {law, lean_declaration, lean_status: "not_checked_by_this_check", role: "validation", passed, ...}
TRECH_FORMAL_LAWS.record(checks);  // into this run's law_checks; returns how many were recorded
```

`TRECH_FORMAL_LAWS.record` accepts only records made by the library's own check functions
(`checkWithinBounds`, `checkConservedTotal`, `checkAgreement`, `checkProbabilityVector`,
`checkComptonBounds`, `checkAttenuationMemoryless`) and throws on anything else. Call it only
from a `.validation.js` companion, never from the physics script. Outside TRECH (Node, a
browser) it records nothing and returns 0.

## Law checks in run outputs

A run that performs at least one law check records it in two places. Runs without checks write
neither, so their files keep the same bytes as before.

- **`law_checks`** in the `run_end` record of `trech_scores.jsonl`: one record per check, with
  `origin` saying who ran it. `engine` checks come from the engine itself (each lattice it builds
  checks its velocity set, opposite-direction table and streaming table). `validation` checks come
  from a companion through `TRECH_FORMAL_LAWS.record`. Identical checks are merged, and `count`
  says how many were merged.
- **`formal`** in the `run_end` provenance record: which law sources the binary was built with
  (hashes of `formal/laws.json` and of every Lean file), which Lean theorems the checks cite, how
  many checks failed, and `lean_status`.

`lean_status` says how much the run can claim about the Lean side. By default it is
`not_checked_by_this_run`: the run checked its classic code, but did not look at any proof. To
attach a proof audit, write one and pass it to the run:

```bash
python3 scripts/check_lean_laws.py --report build/lean_audit.json
trech run examples/scenarios/analytic_compton_transfer/analytic_compton_transfer.js \
  --events 200 --formal-audit build/lean_audit.json --output build/out_compton
```

The run copies the report's Lean version, toolchain and Mathlib revision. If the report was made
from the same law sources as the binary and lists every cited theorem with standard axioms only,
`lean_status` becomes `audited`. A report made from other sources gives `audit_mismatch`, and a
report that misses a cited theorem gives `audit_incomplete`. The run never starts Lean, and the
option changes no result: on 2026-11-22 the scores of this run were byte-identical with and
without `--formal-audit`, and identical between QuickJS and V8. `audited` covers the theorems as
statements about real numbers, not the floating-point code (see above).

The Compton scenario's family gate grades the recorded checks too: `formal_laws_recorded` needs
at least two `validation` records and `formal_laws_hold` needs all of them to pass.

**Energy balance from Geant4's own steps.** In a run with a `compton_energy_transfer` analytic
check, the engine reads each primary photon's first Compton scatter from Geant4's step record:
the photon's energy before and after, the kinetic energy of every secondary the step created,
and the energy deposited on the spot. It records how far `E − E′ − ΣT − deposit` is from zero,
divided by the largest of those energies, as the engine check `energy.step_balance` (tolerance
`1e-12`) and as `measured_max_energy_balance_residual` in the analytic check. Nothing else in
the run changes: on 2026-11-22 a 20,000-event run differed from the previous build's output only
in these new fields and the new engine record in `law_checks`. That run read 16,423 scatters with a largest residual of `4.2e-17`, so
Geant4's sampled Compton steps close to rounding.

The same scatters also check momentum, `k = k′ + p`: the photon's momentum before equals the
photon's after plus the electron's. That is the hypothesis from which `Trech.Laws.TwoBody` proves
the Compton relation, so the record says `kind: "hypothesis"`. It is checked only on scatters
whose products are all tracks, because an electron absorbed on the spot takes momentum the step
record does not list. The tolerance is stated per scatter: the electron's momentum is computed
from `T = E − E′`, which loses digits when the transfer is small, so the bound grows like
`√(m / 2T)`. A flat `1e-12` fails at `ε = 10⁻⁴` (2.7e-12), and the conformance test keeps that
failure as a negative control. On 2026-11-22, 16,420 of 16,423 scatters were checked (three
deposited their electron), with a largest residual of `3.7e-15`. The family gate adds
`energy_balance_measured`, `energy_balance_closure`, `momentum_balance_measured`,
`engine_laws_recorded` (at least two) and `engine_laws_hold`. To see it:

```bash
trech run examples/scenarios/analytic_compton_transfer/analytic_compton_transfer.js \
  --events 2000 --output build/out_compton
grep run_end build/out_compton/trech_scores.jsonl | python3 -c \
  "import json,sys; print([c for c in json.load(sys.stdin)['law_checks'] if c['origin']=='engine'])"
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
ending with `49/49 theorems proved from standard axioms only`. An unfinished proof (`sorry`) or
an added axiom makes it fail. Add `--report build/lean_audit.json` to also save the audit
as JSON: the Lean version, toolchain and Mathlib revision, the SHA-256 hash of `laws.json` and
of every Lean file, one combined hash of all of them, and each theorem's axioms. A run reads it
through `--formal-audit` ([law checks in run outputs](#law-checks-in-run-outputs)). Configuring TRECH with
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
it changes nothing. The first observation does not need a derived class: the energy balance of
Compton scatters is read from the step record that Geant4 already hands to TRECH (see
[law checks in run outputs](#law-checks-in-run-outputs)). Contract: [formal-laws handbook](../../AGENTS/engine/formal/AGENTS.md#geant4-secondary-track).
