# Toward an Integrated Quantum Description of Atomic Stability

**A critical research review, mathematical synthesis, and falsifiable computational proposal**  
**Date:** 2 November 2026  
**Status:** Conceptual research study. The proposed integration is not a newly demonstrated fundamental law.

## Abstract

Can one construct an atom from its constituent particles in a single mathematical description and predict whether the resulting whole is stable? Existing quantum mechanics already provides composition rules: a many-body Hilbert space, (anti)symmetrization for identical particles, coupled Hamiltonians, quantized fields, and the variational principle. Mathematical results establish stability of nonrelativistic Coulomb matter under specified assumptions. Accurate atomic and ab initio nuclear calculations exist. The unsolved problem is different: a scalable, quantitatively controlled, fully coupled calculation of arbitrary atoms directly from the Standard Model, encompassing nonperturbative QCD, nuclear and electronic structure, quantum electrodynamic corrections, and possible decays. This study organizes the known laws and proposes an integrated, channel-resolved computational formulation. Novelty would lie in its tractable implementation and independently improved predictions, not in simply adding known Hamiltonian terms.

## 1. What a theory of an entire atom must explain

An atomic system is specified at minimum by proton number Z, neutron number N, electron number n_e, quantum state, and environment. For neutral atoms n_e=Z, but charged ions are equally legitimate. Proton and neutron are composite QCD states; the electron is an elementary lepton. The electromagnetic field mediates atomic interactions and electromagnetic transitions; weak interactions permit beta decay and some other transmutations. Both the nuclei and electronic cloud can be excited, deformed, polarized, or correlated.

There are four distinct senses of *stability*:

1. **Stability against collapse:** the Hamiltonian has a lower bound, and increasingly large matter does not acquire an energy decreasing faster than linearly in its number of constituents (stability of the second kind).
2. **Binding against fragmentation:** the atom is energetically below its applicable ionization and breakup thresholds.
3. **Stability against transmutation:** there are no accessible energetically and dynamically allowed nuclear decay channels, or those channels have negligible widths on a specified timescale.
4. **Dynamical persistence under a specified environment:** the preparation remains approximately intact for a stated time in an electromagnetic, thermal, or collisional environment.

These are not equivalent. Tritium is a recognizable atom with bound electrons, but its nucleus beta-decays with a half-life of about 12.32 years. An isolated excited hydrogen atom can be Coulomb-bound yet radiatively decay. A neutral ground-state atom in a trap can be ionized by external radiation without implying an intrinsic failure of quantum mechanics.

**Scientific assessment:** It is incorrect to say that physics has no rule for combining individual particle laws. The many-body Hamiltonian and quantum field theory supply those rules. It is accurate to say that full, model-independent, computationally feasible predictions of arbitrary atoms across all the relevant scales remain a substantial open challenge [1–5].

## 2. Inventory of particle-level laws

### 2.1 Electrons

At low velocity an electron in a fixed potential obeys

\[
i\hbar\partial_t\psi=\left(-\frac{\hbar^2\nabla^2}{2m_e}+V\right)\psi.
\]

Including spin and leading magnetic interaction leads to the Pauli Hamiltonian. Relativistic spin-1/2 electrons obey the Dirac equation (natural units, \(\hbar=c=1\)):

\[
(i\gamma^\mu D_\mu-m_e)\psi_e=0.
\]

Bound-state QED adds electron self-energy, vacuum polarization, retardation, and other radiative corrections. The single-particle Dirac equation is not itself the complete interacting multi-electron theory.

### 2.2 Protons and neutrons

Protons and neutrons are composite spin-1/2 baryons made primarily of up and down valence quarks together with sea quarks and gluons. At low energies their interactions are described by nuclear effective field theory, with systematic two-nucleon, three-nucleon, and (at higher orders) higher-body operators. Schematic form:

\[
H_N=\sum_{a=1}^{A}\frac{\mathbf P_a^2}{2m_a}
+\sum_{a<b}V_{NN}^{(ab)}
+\sum_{a<b<c}V_{3N}^{(abc)}+\cdots,
\qquad A=Z+N.
\]

In this definition, the interactions are strong interactions; add nuclear internal Coulomb interactions separately when not incorporated into the specific effective nuclear interaction. Actual nuclear potentials depend on spin, isospin, orbital motion, momentum, and regularization scale. A simplistic universal scalar attraction is inadequate. Three-body forces matter even when the two-body potential is known [4,5].

### 2.3 Quarks and gluons

At the underlying level the QCD Lagrangian is, schematically,

\[
\mathcal L_{\mathrm{QCD}}=
\sum_q\bar q(i\gamma^\mu D_\mu-m_q)q
-\frac14 G^a_{\mu\nu}G_a^{\mu\nu}.
\]

QCD is nonperturbative at the relevant low energies; direct multi-hadron calculations from lattice QCD are difficult. Quark/gluon and nucleon descriptions should not simply be placed as independent species in the same effective Hamiltonian, because this counts the underlying structure twice. Instead one *matches* the microscopic theory to the effective theory at a chosen scale and includes estimated truncation and matching errors [5,6].

### 2.4 Electromagnetic and weak fields

Electromagnetic interactions are described by QED, including the quantized photon field. Coulomb terms are a convenient instantaneous low-energy representation, not an independent replacement for the underlying QED field. Radiative and magnetic corrections can be introduced as matched effective operators.

Weak interactions change flavor and may change proton/neutron content through beta processes, emitting an electron or positron and a neutrino/antineutrino. They must be included as transition couplings to other particle-number/composition sectors if intrinsic nuclear lifetime is part of the goal.

### 2.5 Fundamental framework

The Standard Model combines QCD, QED and weak/electroweak interactions; effective low-energy atomic Hamiltonians are approximations derived or matched from that framework. No presently practical single numerical treatment of arbitrary atoms with all quarks, gluons, leptons, radiation, and weak decay channels has been demonstrated. This limitation must not be mistaken for the absence of a composition law.

## 3. The existing whole-atom composition equation

For \(Z\) proton coordinates \(\mathbf R_p\), \(N\) neutron coordinates \(\mathbf R_n\), and \(n_e\) electron coordinates \(\mathbf r_e\), a schematic nonrelativistic Hamiltonian is:

\[
\boxed{\begin{aligned}
H_{\mathrm{base}}={}&\sum_{i=1}^{n_e}\frac{\mathbf p_i^2}{2m_e}
+\sum_{a=1}^{Z}\frac{\mathbf P_{p,a}^2}{2m_p}
+\sum_{b=1}^{N}\frac{\mathbf P_{n,b}^2}{2m_n}\\
&+\sum_{u<v}\frac{q_uq_v}{4\pi\epsilon_0|\mathbf x_u-\mathbf x_v|}
+\sum_{a<b}V_{NN}^{(ab)}
+\sum_{a<b<c}V_{3N}^{(abc)}
+\cdots.
\end{aligned}}
\]

The Coulomb pair sum is over charged electrons and protons only. It includes electron–electron repulsion, proton–proton repulsion and electron–proton attraction. Neutron electromagnetic form factors and magnetic moments require additional operators. The nuclear potentials in this convention contain **only the strong parts**, so the explicit Coulomb terms are not double-counted. Higher terms may include four-nucleon interactions if justified at the selected EFT order, finite nucleon structure, magnetic and relativistic corrections, and QED/weak interactions.

The total wave function is **one joint state**, not a list of separate orbital predictions:

\[
\Psi=\Psi(\mathbf r_1,s_1,\ldots,\mathbf r_{n_e},s_{n_e};
\mathbf R_1,\sigma_1,\tau_1,\ldots,\mathbf R_A,\sigma_A,\tau_A).
\]

It satisfies

\[
H\Psi=E\Psi,\qquad
E_0=\inf_{\langle\Psi|\Psi\rangle=1}\langle\Psi|H|\Psi\rangle.
\]

Identical fermions are antisymmetrized. In an isospin formulation the nucleons are antisymmetrized as fermions including the isospin labels. Electrons obey the Pauli exclusion principle as well. One must remove overall center-of-mass motion for intrinsic energies and avoid spurious center-of-mass excitations.

This is already a lawful way to merge descriptions of electrons and nucleons. Its challenge is quantitative: nonperturbative nuclear forces, large Hilbert spaces, extreme differences in length/energy scales, high-precision QED, and open decay channels.

## 4. Why simply summing each particle's energy fails

An atom's energy is not \(\sum_i E_i^{\mathrm{isolated}}\). Interactions and entanglement make the state of each particle depend on the others:

\[
E[\Psi]=\sum_i\langle T_i\rangle_\Psi
+\sum_{i<j}\langle V_{ij}\rangle_\Psi
+\sum_{i<j<k}\langle V_{ijk}\rangle_\Psi+\cdots.
\]

Moreover, both the interaction energies and kinetic energies change when the combined state \(\Psi\) relaxes. Pairwise interactions alone are not necessarily enough (e.g. nuclear three-body forces), and a nonlinear physical *outcome* need not correspond to adding an arbitrary nonlinear term to the Schrödinger equation. The wavefunction can evolve linearly while observable correlations are complex and collective.

### Example: hydrogen

With one electron and one pointlike nucleus of charge \(+Ze\), the reduced-mass Coulomb solution predicts

\[
E_n^{(0)}=-\frac{\mu c^2(Z\alpha)^2}{2n^2},\qquad
\mu=\frac{m_em_N}{m_e+m_N}.
\]

For hydrogen \(Z=1\), this predicts binding of approximately 13.6 eV at leading order; fine structure, radiative and proton-size corrections refine the result. The NIST neutral-hydrogen ionization energy is 13.598434599702 eV [7].

### Example: helium exposes the interaction problem

With an infinitely massive point nucleus, a two-electron helium Hamiltonian in Hartree atomic units is

\[
H=-\tfrac12(\nabla_1^2+\nabla_2^2)
-\frac2{r_1}-\frac2{r_2}+\frac1{r_{12}}.
\]

The last term is electron–electron repulsion. If both opposite-spin electrons occupy a variational 1s orbital of effective charge \(\zeta\), their total energy is

\[
E(\zeta)=\zeta^2-2Z\zeta+\frac58\zeta
\quad \text{(Hartree)},
\]

which has minimum at \(\zeta=Z-5/16\). For helium, \(E_{\mathrm{trial}}=-2.84765625\) Hartree. A high-precision correlated nonrelativistic calculation yields \(E_{\mathrm{He}}=-2.903724377034\ldots\) Hartree [8]. The elementary product state therefore misses about 1.526 eV of ground-state binding energy: including one-particle orbitals and a Coulomb term is insufficient without fully allowing their quantum correlations to develop. The physical ionization energy is 24.587389 eV (NIST); the simple point-nucleus model predicts roughly 23.066 eV [7]. These comparisons are illustrative, not equal-approximation accuracy claims, because the measured value also contains recoil, relativity, QED, and finite-nuclear-size effects.

## 5. What is already proved about stability

In the mid-1960s Dyson and Lenard established foundational stability results for many-particle Coulomb quantum mechanics. Lieb, Thirring, and later authors developed powerful bounds based on quantum statistics and kinetic-energy inequalities [1,2]. A typical stability-of-matter statement has the form

\[
E_0(N_{\mathrm{constituents}})\geq -C N_{\mathrm{constituents}}
\]

for appropriately bounded charges, masses, and particle species under the relevant mathematical model. This expresses extensivity of the lower energy bound and rules out unrestricted collapse in that model. It does **not** say every combination of \(Z,N,n_e\) is a bound, nuclear-stable atom. Neither does it supply all excited spectra or lifetimes.

For a particular atom, bound-state stability instead requires comparison with *all relevant fragmentation channels*. Write \(E_c^{\mathrm{threshold}}\) for the lowest allowed energy of separated products in channel \(c\), using the same theory and consistent mass convention. Define

\[
S_c=E_c^{\mathrm{threshold}}-E_0.
\]

A positive \(S_c\) is the energy needed to separate the atom into that channel; a negative value signals an energetically downhill channel. One must not infer decay solely from energy: selection rules and interaction matrix elements determine whether and how rapidly an allowed channel proceeds. For beta decay, the products occupy another particle-content sector, so rest masses and weak interactions are essential.

The massless photon field adds a mathematical nuance: arbitrarily low-energy radiation can eliminate a naive positive spectral gap even for stable systems. Thus a physical claim that an atom is stable should specify *which* fragmentation, radiation and weak channels are being considered, rather than assert a universal positive gap to every possible excitation.

## 6. Proposed integrated model: IASF

Call the proposed synthesis the **Integrated Atomic Stability Framework (IASF)**. This is a research architecture, not a claim of a novel force or a discovery of a new equation.

### 6.1 Choose a consistent resolution scale

At the highest resolution use the Standard Model field description. At nuclear resolution match QCD onto an effective nucleon+pion or nucleon-only Hamiltonian. At atomic resolution couple the nuclear charge/current response to electronic degrees of freedom in a QED-consistent way. Keep a ledger of which degrees of freedom have been integrated out, which coefficients have been matched, and what each truncation error is. **Never include free quark, gluon, and effective proton strong-interaction terms independently as if they were disjoint constituents.**

### 6.2 Separate sectors without asserting independence

Choose normalized internal nuclear basis states \(|\Phi_\nu\rangle\) from a nuclear many-body calculation and electron basis states \(|\phi_a\rangle\) from an electronic calculation. A joint state is

\[
|\Psi\rangle=\sum_{\nu,a}C_{\nu a}|\Phi_\nu\rangle\otimes|\phi_a\rangle
\quad (+\text{photon/other sectors as needed}).
\]

Solve the single matrix problem

\[
\sum_{\nu',b} H_{\nu a,\nu'b}C_{\nu'b}=E C_{\nu a}.
\]

Use, for example, nuclear states computed with strong nuclear + nuclear internal Coulomb interactions, and electronic states computed with the clamped point-nucleus Coulomb potential. Then include exact electron–proton charge interactions minus the point-nucleus reference, relative-motion recoil, magnetic currents, and radiative operators. This **subtraction** avoids double-counting the reference electron–nucleus Coulomb attraction. Off-diagonal matrix elements between different nuclear and electronic states preserve their mutual polarization and correlations.

A more formal split is

\[
H=H_N+H_e^{\mathrm{ref}}+\underbrace{(V_{eN}^{\mathrm{full}}-V_{eN}^{\mathrm{ref}})
+H_{\mathrm{recoil}}+H_{\mathrm{EM,structure}}}_{V_{\mathrm{coupling}}}
+\Delta H_{\mathrm{QED}}+H_{\mathrm{weak}}.
\]

This is schematic; practical gauges, center-of-mass coordinates, radiation treatment, and EFT matching must be specified before implementing it. Nuclear electromagnetic exchange currents, finite-size terms and radiative terms must be partitioned consistently rather than counted in multiple places.

### 6.3 Exact composition via Feshbach projection

Partition Hilbert space into an explicitly simulated subspace \(P\) and an omitted subspace \(Q=1-P\). The exact eigenproblem yields the energy-dependent effective Hamiltonian

\[
\boxed{H_{\mathrm{eff}}(E)=PHP+PHQ(E-QHQ)^{-1}QHP},
\]

interpreted using the appropriate resolvent boundary condition for open channels. The remaining problem is

\[
H_{\mathrm{eff}}(E)P|\Psi\rangle=E P|\Psi\rangle.
\]

This is an **existing projection-operator identity**, not a newly invented law. Its value as an integration principle is that it tells us exactly what is lost when nuclear excitations, electronic excitations, virtual photons, or decay channels are omitted. In calculations, the second term is approximated through controlled nuclear and electronic response functions. It also shows why a static correction cannot always reproduce dynamic nuclear–electronic coupling [9].

### 6.4 Atomic nuclear-polarization response

Let \(\Phi_0\) be the nuclear ground state and \(\Phi_\nu\) excited nuclear states. Define the electron-space operator

\[
V_{0\nu}=\langle\Phi_0|V_{eN}|\Phi_\nu\rangle_N.
\]

A nuclear-excitation-induced effective interaction has the generic second-order structure

\[
\boxed{V_{\mathrm{ind}}(E)\simeq\sum_{\nu\ne0}
V_{0\nu}\frac{1}{E-H_e-E_\nu^N}V_{\nu0}},
\]

with the correct reference terms, correlations, and QED matching understood. The dependence on electronic energy and excited nuclear spectrum makes this *dynamic*. This type of physics is already known in nuclear-polarization calculations, especially for high-precision muonic atoms [10,11]. The research question is whether a joint, controlled implementation improves predictions over established separate corrections, not whether polarization has never been studied.

### 6.5 Couple electromagnetic and weak open channels

For excited states and unstable isotopes, a Hermitian closed-sector bound-state Hamiltonian alone cannot predict their lifetime. Introduce photon and decay-product channels. Perturbatively, for a specified channel \(c\), Fermi's golden rule gives

\[
\Gamma_c=2\pi\,|\langle f_c|H_{\mathrm{int}}|i\rangle|^2\rho_c(E_i),
\]

when matrix elements and final-state densities use the corresponding continuum normalization and \(\Gamma\) is an energy width (natural units). More generally the outgoing-channel effective Hamiltonian has complex resonant poles

\[
E_{\mathrm{pole}}=E_R-i\Gamma/2,
\]

and a survival approximation \(P(t)\approx\exp(-\Gamma t/\hbar)\). Very long-lived processes require a careful treatment of forbidden/allowed transitions and weak matrix elements. Environmental collision or ionization rates are separate model inputs.

## 7. Proposed operational stability description

Instead of a fictitious universal scalar that automatically declares all atoms stable or unstable, compute a **channel-resolved stability signature**:

\[
\boxed{\mathcal S(Z,N,n_e;\mathcal E)=
\left(E_0,\{S_c\}_{c\in\mathcal C},\{\Gamma_c\}_{c\in\mathcal C},
\{\langle O_j\rangle\},\delta_{\mathrm{theory}}\right)}.
\]

Here \(\mathcal E\) specifies external conditions, \(S_c\) is a separation-energy margin, \(\Gamma_c\) a transition/decay width, \(\langle O_j\rangle\) observables (radii, charge density, magnetic moments, hyperfine splitting, etc.), and \(\delta_{\mathrm{theory}}\) a quantified model error. A useful timescale-dependent classification is

\[
P_{\mathrm{survival}}(T)\simeq
\exp\!\left[-\frac{T}{\hbar}\sum_{c\in\mathrm{loss}}\Gamma_c\right].
\]

This is an approximation when decay is approximately exponential and channels can be treated with independent partial widths; it is not a replacement for full time evolution in non-Markovian regimes. A bound electronic ground state with a beta-unstable nucleus can have \(S_{\mathrm{ion}}>0\) and \(\Gamma_{\beta}>0\). This distinction prevents the common logical error of interpreting electronic binding as absolute atomic stability.

**What is original in this proposal?** The explicit specification of a common, auditable multiscale workflow and channel-resolved prediction target. The Hamiltonian, Feshbach formula, variational principle, response corrections, and decay theory are established ingredients. Without an actual implementation and out-of-sample predictions, the synthesis is not yet a new physical theory.

## 8. Practical computational research program

### Phase A: validate the composition rule on exactly tractable atoms

1. **Hydrogen / hydrogenic ions:** reproduce reduced-mass levels, recoil and leading nuclear-size correction. Then compare to QED-improved transitions and NIST spectra. This tests elementary particle coupling and prevents unit or Coulomb-sign errors.
2. **Helium:** reproduce the all-electron two-body correlation energy and its convergence toward the high-precision nonrelativistic value, then add finite nuclear mass and finite-size/QED corrections separately. This tests antisymmetry, electron–electron correlation and systematic accuracy [7,8].
3. **Deuterium:** include one proton, one neutron and one electron, compute the nucleus with a two-nucleon nuclear interaction, then couple recoil and the deuteron charge/current response to the electron. The hydrogen–deuterium isotope shift is a sensitive benchmark for cross-scale effects [12].

### Phase B: distinguish electronic binding from nuclear decay

4. **Tritium:** represent a bound atomic electron while allowing the nucleus to transform via weak interactions. Predict the beta-decay energy release and a lifetime only after including the weak transition matrix element. Benchmark against the approximately 12.32-year experimental half-life [13].
5. **Helium-3 / helium-4:** compare predicted electronic isotope shifts and hyperfine observables, nuclear charge radii and polarization contributions. These systems reveal whether the coupling scheme handles nuclear spin and structure correctly.

### Phase C: move beyond very light systems

6. **Lithium and selected isotopes:** include three-electron correlations and three-nucleon forces, benchmarking independent atomic and nuclear calculations. Then test larger atoms, progressively incorporating relativistic and QED terms.
7. **Near-threshold exotic nuclei and highly charged ions:** stress-test the coupling near separation thresholds, where discarded correlations and omitted channels can affect binding and resonant widths.

### Phase D: make a scientific claim only with predictive improvement

Measure, for each test system, ionization energies, isotope shifts, binding energies, transition frequencies, nuclear radii, allowed decay rates and computational cost. Publish systematic convergence tests under increasing electron-basis size, nuclear excitation cutoff, EFT order, QED order, and included channel count. Report an error budget separating basis truncation, nuclear interactions, matching, radiative corrections and experimental inputs.

Use pre-registered or held-out measurements (e.g. an isotope/transition not used to fit effective couplings) to test predictive rather than merely descriptive accuracy. If integrating nucleus and electrons yields no meaningful advantage over established nuclear-structure plus atomic-QED methods, report that negative result.

### Suggested solver pseudocode

```text
input: Z, N, electron_count, observables, environment, accuracy_goal
choose: EFT resolution, electromagnetic gauge/convention, sector cutoffs
nuclear_basis = solve_nuclear_many_body(Z, N, V_NN, V_3N, ...)
electron_basis = solve_electronic_reference(Z, electron_count, ...)
construct all charged-particle Coulomb and recoil operators consistently
match nuclear charge/current operators and QED corrections
subtract reference interactions to prevent double counting
H_coupled = project_full_operator(nuclear_basis, electron_basis)
repeat:
    solve low-energy coupled states
    estimate omitted-sector self-energy and truncation errors
    enlarge nuclear/electron/channel basis where needed
until observables converge within accuracy_goal
compute physical breakup thresholds using consistent rest masses
compute EM and weak transition matrix elements to open channels
report: energies, charge/current observables, thresholds, widths,
        stability by time horizon, uncertainties, provenance
```

### Current executable first stage

The [atomic research implementation](../atomic_stability.md) now provides a numerical
one-electron reduced-mass radial Coulomb solve in JavaScript on installed Node.js/V8,
with mesh/box refinement, an independently labelled leading nuclear-size component, and
channel-resolved electronic binding. A second JS module tests real-symmetric finite-basis
composition and the closed-sector Feshbach identity on supplied matrices. The optional C++
`trech-atomic` launcher supplies the host boundary; it does not replace TRECH's QuickJS hooks.

This begins Phase A; it does not complete it. Helium correlation, a nuclear deuteron solver,
QED-improved comparisons, physical matrix construction/matching, decay widths, molecular
systems, and quantified total theory errors remain open. Deuterium/He-4+ examples use externally
supplied nuclear masses/radii. Neither the finite-basis identity nor this hydrogenic benchmark
constitutes a new fundamental theory. Remaining work is tracked in the
[runtime roadmap](../../AGENTS/engine/runtime/ROADMAP.md#atomic-stability-research).

## 9. Conditions any proposed new equation must satisfy

A candidate formula cannot claim to describe the whole atom merely because it has terms for its components. It must satisfy the following tests:

- **Correct two-body limit:** recover hydrogenic Coulomb energies and mass recoil.
- **Fermion exchange:** maintain electron and nucleon statistics; exclude spurious Pauli-violating solutions.
- **Translational and rotational invariance:** no spurious center-of-mass binding; correct conserved angular momenta where symmetries apply.
- **Gauge consistency:** electronic, photon and nuclear-current couplings must yield gauge-independent observables when computed consistently.
- **Cluster separability:** widely separated physical clusters approach the sums of their isolated energies and interactions vanish appropriately.
- **Unitary closed dynamics and correct open-channel loss:** do not invent norm loss without an identified environment or channel.
- **EFT scale independence within uncertainty:** changing cutoff or matching scheme should not unpredictably alter calibrated observables.
- **No double counting:** especially proton internal QCD versus nucleon EFT, and point-nucleus Coulomb versus finite-size corrections.
- **Controlled approximations:** quantify basis, EFT, QED and nuclear-response truncation errors.
- **Falsifiable improvement:** predict measurements or ranges not used to tune the model.

The most promising contribution is likely an adaptive **compositional solver** with demonstrably reliable uncertainty control. A new fundamental force or new nonlinear Schrödinger term is unnecessary unless an observed deviation from the present framework actually demands it.

## 10. Research assessment and remaining open problems

**Solved in principle or partially with high precision:** quantum composition of nonrelativistic particles; electron antisymmetry and electronic correlations; stability of many-body Coulomb matter in specified models; light-atom energies and bound-state QED corrections; several light- and medium-nucleus ab initio calculations; nuclear charge-radius and polarization corrections in precision spectroscopy [1–5,7–11,14].

**Open or restricted in practice:** general controlled QCD-to-nuclear matching, comprehensive heavy-nucleus structure and decay, reliable simultaneous nuclear/electronic correlations beyond current perturbative regimes, highly precise dynamic nuclear polarization across a broad range of atoms, real-time excited/open dynamics, and efficient uncertainty-aware computations for arbitrary isotopes. The frontier lies in the *predictive execution and controlled matching* of laws, rather than the mathematical absence of laws for combining particles. This remains an ambitious research direction, particularly for atoms at which nuclear structure limits spectroscopic precision [10,14,15].

## 11. Conclusions

The idea that the stability of an atom must be predicted **as a property of the entire interacting system** is correct and essential. Quantum theory already encodes this through one joint state, antisymmetrization, the total Hamiltonian, and the spectrum relative to dissociation and decay channels. What is not generally available is a universally practical, fundamental-to-atomic calculation without scale-specific approximations and hard computational constraints.

A serious research program should therefore formulate and implement a channel-resolved, multiscale model in which nuclear and electronic sectors exchange charge/current response, virtual excitations, and recoil in a consistent matching scheme. Its central outputs should be binding margins, transition widths, observables, and uncertainty budgets—not an unsupported universal scalar. The decisive achievement would be new accurate predictions on held-out atomic and nuclear observables, validated against conventional calculations and measurement.

---

## References

1. F. J. Dyson and A. Lenard, “Stability of Matter. I,” *Journal of Mathematical Physics* **8**, 423 (1967). [PDF](https://bpb-us-e1.wpmucdn.com/sites.mit.edu/dist/9/2055/files/2020/05/1.1705209.pdf).
2. E. H. Lieb, “The stability of matter,” *Reviews of Modern Physics* **48**, 553 (1976). [DOI](https://doi.org/10.1103/RevModPhys.48.553).
3. E. Mátyus, “Pre-Born–Oppenheimer molecular structure theory,” *Molecular Physics* (2018). [Article](https://www.tandfonline.com/doi/full/10.1080/00268976.2018.1530461).
4. R. Machleidt and F. Sammarruca, “Recent advances in chiral EFT based nuclear forces and their applications,” *Progress in Particle and Nuclear Physics* **137**, 104117 (2024). [Preprint](https://arxiv.org/abs/2402.14032).
5. H.-W. Hammer, S. König and U. van Kolck, “Nuclear effective field theory: Status and perspectives,” *Reviews of Modern Physics* **92**, 025004 (2020). [DOI](https://doi.org/10.1103/RevModPhys.92.025004).
6. A. Yamamoto and T. Doi, “Toward Nuclear Physics from Lattice QCD on Quantum Computers,” *Progress of Theoretical and Experimental Physics* (2024). [PDF](https://scoap3-prod-backend.s3.cern.ch/media/files/84096/10.1093/ptep/ptae019.pdf).
7. NIST Atomic Spectra Database, version 5.12, ionization energies, accessed November 2026. [Data](https://physics.nist.gov/cgi-bin/ASD/ie.pl?at_num_out=on&biblio=on&e_out=0&el_name_out=on&level_out=on&shells_out=on&spectra=H-DS+i&unc_out=on&units=1).
8. J. S. Sims and S. A. Hagstrom, “High Precision Hy-CI Variational Calculations for the Ground State of Neutral Helium and Helium-Like ions,” *International Journal of Quantum Chemistry* **90**, 1600 (2002). [NIST](https://www.nist.gov/publications/high-precision-hy-ci-variational-calculations-ground-state-neutral-helium-and-helium).
9. Feshbach projected effective Hamiltonian, discussed in [this treatment of scattering and Feshbach resonances](https://pure.tue.nl/ws/files/2383820/200610889.pdf), equations 2.24–2.28.
10. S. S. Li Muli and M. Gennari, “Recent Progress in Ab Initio Nuclear Theory for Precision Physics Searches in Muonic Atoms and Superallowed β Decays,” *Atoms* **14**, 74 (2026). [Article](https://www.mdpi.com/2218-2004/14/9/74).
11. M. Gorchtein, “Guide to nuclear polarization in muonic atoms,” *Physical Review C* **113**, L011301 (2026). [DOI](https://doi.org/10.1103/jqm6-c75w).
12. U. D. Jentschura et al., “Hydrogen-deuterium isotope shift: From the 1S−2S-transition frequency to the proton-deuteron charge-radius difference,” *Physical Review A* **83**, 042505 (2011). [DOI](https://doi.org/10.1103/PhysRevA.83.042505).
13. J. J. Simpson, “Half-life of tritium and the Gamow-Teller transition rate,” *Physical Review C* **35**, 752 (1987). [DOI](https://doi.org/10.1103/PhysRevC.35.752).
14. G. Hagen et al., “Multiscale Physics of Atomic Nuclei from First Principles,” *Physical Review X* **15**, 011028 (2025). [ORNL](https://www.ornl.gov/publication/multiscale-physics-atomic-nuclei-first-principles).
15. K. Pachucki, V. Patkóš and V. A. Yerokhin, “Recoil corrections with finite nuclear size in hydrogenic systems,” *Physical Review A* **111**, 032820 (2025). [DOI](https://doi.org/10.1103/PhysRevA.111.032820).
16. V. Patkóš, V. A. Yerokhin and K. Pachucki, “Complete quantum electrodynamic alpha^6 m correction to energy levels of light atoms,” *Physical Review A* **100**, 042510 (2019). [DOI](https://doi.org/10.1103/PhysRevA.100.042510).
17. D. Lee, “Lattice Effective Field Theory Simulations of Nuclei,” *Annual Review of Nuclear and Particle Science* **75**, 109–128 (2025). [Review](https://www.annualreviews.org/content/journals/10.1146/annurev-nucl-101918-023343).
