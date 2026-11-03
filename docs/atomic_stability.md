# Atomic stability research: first executable stage

This implements the hydrogenic part of Phase A and finite-basis composition primitives from
the [IASF research plan](researches/atomic_stability_research.md). It is an **independent quantum
comparison/research tool**, not a Geant4 result, a trained cascade, or a new fundamental theory.
The numerical core is JavaScript executed by the installed **Node.js/V8** runtime. The optional
C++ launcher supplies the process boundary; atomic equations stay in JS.

## Run experiments

Node.js 18 or newer with V8 is required. No npm packages or network access are needed:

```sh
node tools/atomic/run.cjs
node tools/atomic/run.cjs --input tools/atomic/hydrogenic_requests.json --output build/atomic-results.json
node tools/atomic/run.cjs --composition tools/atomic/composition_request.json
```

The bundled hydrogenic batch contains hydrogen 1s/2s/2p, deuterium 1s, and He-4+ 1s.
He-4+ reports the default numerical-change goal as unmet; an additional 8191-point grid
reduces the mesh change. The runner reports unmet goals without treating them as input errors.
The composition example is a **synthetic two-state matrix**, with no assignment to a real atom.
Create the output's parent directory first. Output is written only after all cases succeed;
input/solver errors exit nonzero without replacing an existing result. Filesystem write failures
can still leave partial output. Without `--output`, a single JSON report goes to stdout.

For the optional C++ entry point, configure a separate lightweight build:

```sh
cmake -S . -B build/atomic-research -G Ninja \
  -DCMAKE_BUILD_TYPE=Release -DTRECH_FETCH_DEPS=OFF \
  -DTRECH_ENABLE_GEANT4=OFF -DTRECH_ENABLE_ATOMIC_RESEARCH=ON
cmake --build build/atomic-research --target trech-atomic
build/atomic-research/trech-atomic --input tools/atomic/hydrogenic_requests.json
```

`TRECH_ENABLE_ATOMIC_RESEARCH` defaults OFF. Configuration finds an installed Node/V8 and
never builds `thirds/v8`. The launcher forwards literal arguments without a shell. It is bound
to the configured Node executable and source-tree script paths; installation/relocation and
Windows execution have not been validated. The main `trech run`/`inspect`/`lab` hook host remains
QuickJS. This separate research command does not change strict/predictive inference semantics.

## Hydrogenic input and supported physics

`--input` accepts one request, or `{"cases":[request,...]}` for 1–32 repeated experiments.
Input files are limited to 1 MiB. Unknown fields and unsupported physics are rejected.

```json
{
  "atomicNumber": 1,
  "neutronCount": 0,
  "electronCount": 1,
  "nuclearMassElectron": 1836.152673426,
  "chargeRadiusFm": 0.84075,
  "state": {"n": 1, "l": 0},
  "grid": {"points": [1023, 2047, 4095], "radius": 40},
  "accuracyGoalEv": 0.002
}
```

Defaults describe hydrogen 1s. Supported ranges are `atomicNumber` 1–10, `neutronCount` 0–30,
exactly one electron, `n` 1–4, and `l` 0–`n-1`. These bounds delimit the prototype, not evidence
that every supplied isotope exists or is stable. Every other isotope requires an explicit
**nuclear mass in electron-mass units**, excluding atomic electrons. Nuclear mass and charge
radius are external inputs, not nuclear predictions. Do not add free nucleon masses to estimate
the nuclear mass without accounting for nuclear binding. An omitted radius for other isotopes
(or explicit `null`) leaves the finite-size correction unknown. Zero explicitly selects zero
leading charge-radius correction. Neutron count labels the isotope; it does not solve its nucleus.

Constants use [CODATA 2022](https://physics.nist.gov/cuu/Constants/). Nuclear mass is restricted
to 1–10⁷ electron masses and radius to 0–10 fm. Input uncertainties are not propagated.

In atomic units, removing center-of-mass motion and setting `rho = mu/me` gives

\[
H_l=-\frac{1}{2\rho}\frac{d^2}{dr^2}
+\frac{l(l+1)}{2\rho r^2}-\frac{Z}{r},\qquad
\rho=\frac{1}{1+1/(m_N/m_e)}.
\]

With `x = rho Z r/a0`, the solver discretizes
`-1/2 d²/dx² + l(l+1)/(2x²) - 1/x` on a uniform radial grid with zero endpoint values.
A tridiagonal Sturm-count bisection solves eigenvalue rank `n-l`, bracketed by matrix row
bounds. Multiplication by `rho Z² Eh` restores energy units. Analytic Coulomb energies do not
assemble, bracket, or solve this eigenproblem; they are recorded as validation comparisons.
The reduced mass already contains nonrelativistic recoil, so no second recoil term is added.

`grid.radius` is the dimensionless endpoint in `x`, defaulting to `40n` (allowed 4–640).
Each grid has 127–8191 interior points; specify 2–6 grids, each at least doubling the previous
interval count. A second calculation doubles the box and its interval count at the finest
spacing, separating box change from mesh change. A small box can destroy binding, and a coarse
mesh can miss requested precision. Both outcomes remain visible.

The leading s-state charge-radius contact correction is computed separately:

\[
\Delta E_{\rm size}=\frac23\rho^3Z^4
  (r_{\rm rms}/a_0)^2 n^{-3}\delta_{l0}\ E_h.
\]

This is first-order perturbation using the analytic point-Coulomb density, consistent with
the leading expression in [CODATA's theory treatment, Eq. (50)](https://physics.nist.gov/cuu/pdf/JPCRD2022CODATA.pdf).
It is positive and does not add the Coulomb attraction again. Zero for `l>0` means only that
this leading contact term vanishes. Higher finite-size terms are omitted. The hydrogen shift
is roughly 4.57×10⁻⁹ eV, much smaller than the default mesh error. Reporting it does not mean
the numerical eigenproblem resolves nuclear structure.

## Finite-basis composition

`--composition` accepts one request or the same batch envelope:

```json
{
  "hamiltonianHartree": [[-0.5, 0.2], [0.2, 1.5]],
  "retainedDimension": 1,
  "projectionEnergyHartree": -0.519803902718557
}
```

Supply a finite, exactly real-symmetric matrix of dimension 1–32 in one consistent Hartree
energy convention. A Jacobi eigensolver returns sorted eigenpairs, residuals, orthogonality
error, and convergence telemetry. The optional paired fields `retainedDimension` and
`projectionEnergyHartree` select the first P coordinates and evaluate

\[
H_{\rm eff}(E)=H_{PP}+H_{PQ}(EI-H_{QQ})^{-1}H_{QP}.
\]

Pivoted linear solves implement the resolvent. Poles and ill-conditioned cases fail explicitly;
no artificial broadening is substituted. The supplied energy is an evaluation point, not an
automatically solved nonlinear eigenvalue. The example evaluates at the lowest full-matrix
eigenvalue to verify the projected identity. Real symmetric closed sectors do not provide
complex resonances, photon/weak open channels, or decay widths.

The pure modules also export `TRECH_ATOMIC_STABILITY.solve(request)` and
`TRECH_ATOMIC_COMPOSITION.{symmetricEigen,feshbachEffective,analyze}` as globals and CommonJS
exports, without filesystem/process dependencies. Supplied matrix elements must come from
an independently justified model. This first stage does **not** generate nuclear/electronic
bases, nuclear forces, matched QED terms, or the reference-subtraction operators needed by IASF.

## Report and uncertainty contract

Reports use schema `trech.atomic_research.v1` with `provenance` and `results`:

- Provenance records Node/V8 versions, platform/architecture/argv flags and `NODE_OPTIONS`, source SHA-256 hashes, raw
  input SHA-256, normalized request hashes, constants, mode, zero inference count, no RNG, and
  `geant4Derived:false` / `learned:false`. There are no timestamps or measured execution times.
  Byte replay is tested on the same host/runtime; cross-platform floating-point identity is not
  established. External `--require`/`--import` preloads are not source-hashed; use a clean host
  environment for controlled experiments. Preserve the report together with the input and source revision.
- Hydrogenic results use `origin:independent_quantum_reference`; energies are in eV relative to
  a separated electron and the same declared nucleus, excluding rest masses. Positive ionization
  separation margins mean electronic binding within this model. Excited states are identified
  by `(n,l)`; their binding does not imply radiative stability.
- `convergence.trace`, `lastGridChangeEv`, and `boxChangeEv` are empirical changes. Even when
  `numericalChangeGoalMet:true`, they are **not** a rigorous error bound or experimental-accuracy
  claim. `accuracyGoalEv` tests observed changes only (allowed 10⁻¹²–1 eV).
  `finiteSizeExceedsObservedChanges` is also only a comparison to observed changes;
  `finiteSizeNumericallyResolved` remains `null` until resolution is independently established.
  `eigenvalueBracketEv` is the floating-point bisection interval, not a bound on roundoff,
  discretization error, or the physical energy.
- Nuclear stability, electromagnetic/weak widths, lifetime, survival probability, and total
  theory uncertainty remain unknown (`null` / `not_computed` / `undetermined`). An electronically
  bound tritium input must never become a prediction of an infinitely lived atom.
- Finite-basis results use `origin:supplied_matrix_reference`. Residuals test the supplied matrix
  problem; they do not establish the physical validity of its entries. Theory uncertainty and
  decay widths remain `null`.

These reports are separate from `trech_scores.jsonl` and `trech_provenance.jsonl`; they do not
alter simulation config hashes, tallies, or learned-model counters.

## Validation and next stages

```sh
node tests/test_atomic_stability.cjs
node tests/test_atomic_composition.cjs
cmake --build build/atomic-research --parallel 4
ctest --test-dir build/atomic-research --output-on-failure
```

The default hydrogen numerical level is approximately −13.597963 eV versus the reduced-mass
point-Coulomb comparison −13.5982872643 eV. Their difference is about 0.000324 eV; this grades
the discretization of the chosen Hamiltonian, not accuracy against measured hydrogen spectra.
Tests cover refinement, bound/excited eigenvalues, charge/mass scaling, recoil accounting,
finite-size signs, small boxes, missing physics, Feshbach reconstruction, singularities, batch
requests, source/runtime evidence, same-host replay, and the C++ argument boundary.

Phase A remains partial. Next are a convergent correlated two-electron helium basis with
fermion exchange, an actual two-nucleon deuteron calculation, matched relativistic/QED and
nuclear-response terms, and independent spectral benchmarks. Nuclear decay, larger atoms,
molecules, quantified model uncertainty, and held-out predictive improvement remain research
work in the [runtime roadmap](../AGENTS/engine/runtime/ROADMAP.md#atomic-stability-research).
