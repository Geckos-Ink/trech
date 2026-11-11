# Geant4 in TRECH — what we can rely on, where TRECH must build its own physics

Geant4 is TRECH's **base of truth** at the particle/nano scale (root principle: *Geant4 is the
base of truth; classical formulas are for comparison*). But Geant4 was designed for a
particular job, CERN-style detector and radiation simulation, and that origin limits what it
covers. This document records:

1. **which Geant4 version** TRECH is pinned to and what changed in it that matters to us;
2. **what Geant4 provides** that TRECH can treat as precise base truth, and in what validity
   window;
3. **what Geant4 does not model, by design**, and therefore what TRECH has to implement itself
   (as hook-layer *physics for comparison*, learned surrogates or authored state);
4. **where the limit is not Geant4's but physics' or mathematics'**: gaps that no
   simulation toolkit closes, which TRECH must treat as permanent and label honestly.

Every "TRECH implements" entry below is subject to the root labelling discipline: it is **not a
Geant4 result**, and any inferred value must say so in provenance and UI.

> **Status of this document.** This is a reference/positioning document. It does not implement
> anything. Claims about Geant4 are checked against the vendored source in
> [`thirds/geant4`](../thirds/geant4) at the commit below. Claims about TRECH are checked against
> current `src/`, `js/` and the [AGENTS handbooks](../AGENTS/AGENTS.md). When the submodule
> moves, re-check [§1](#1-version-baseline) and [§6](#6-migration-items-for-the-pinned-checkout).

---

## Contents

1. [Version baseline](#1-version-baseline)
2. [What Geant4 is, and why that shapes its limits](#2-what-geant4-is-and-why-that-shapes-its-limits)
3. [What TRECH can count on (Geant4 capability map)](#3-what-trech-can-count-on-geant4-capability-map)
4. [Structural limits of Geant4 and what TRECH does instead](#4-structural-limits-of-geant4-and-what-trech-does-instead)
5. [Limits that belong to physics and mathematics, not to Geant4](#5-limits-that-belong-to-physics-and-mathematics-not-to-geant4)
6. [Migration items for the pinned checkout](#6-migration-items-for-the-pinned-checkout)
7. [Responsibility matrix by TRECH family](#7-responsibility-matrix-by-trech-family)
8. [Decision checklist for contributors](#8-decision-checklist-for-contributors)
9. [References](#9-references)

---

## 1. Version baseline

Checked on 2026-11-11 after `git fetch --tags` of the submodule.

| Item | Value | Notes |
| --- | --- | --- |
| Submodule checkout | `thirds/geant4` @ `f3d5293d38`, tag **`v11.5.0.beta`** (`G4VERSION_NUMBER 1150`, "geant4-11-05-beta-01") | This is the upstream `master` tip; fetching found nothing newer. |
| Newest *stable* upstream release | **`v11.4.3`** (tagged 2026-10-01) | A patch of the 11.4 line, newer by date than the 11.5 beta. 11.5.0 final is not tagged yet. |
| Geant4 actually installed and linked | `build/geant4-install`: **11.4.2** (`G4VERSION_NUMBER 1142`), with `G4EMLOW8.8` | All current TRECH builds, tests and validation reports were produced against **11.4.2**, not against the checkout. |
| Datasets required by the checkout | G4NDL 4.7.1, **G4EMLOW 9.0**, PhotonEvaporation 6.1.2, RadioactiveDecay 6.1.2, G4PARTICLEXS 4.2, G4PII 1.3, RealSurface 2.2, G4SAIDDATA 2.0, G4ABLA 3.3, G4INCL 1.3, G4ENSDFSTATE 3.0, G4CHANNELING 2.0, G4TENDL 1.4, G4NUDEXLIB 1.0, G4URRPT 1.1 | From [`cmake/Modules/G4DatasetDefinitions.cmake`](../thirds/geant4/cmake/Modules/G4DatasetDefinitions.cmake). G4EMLOW moved 8.8 → 9.0, required by the extended DNA option 4. |

**Consequence.** The checkout is a *beta*, and TRECH has not been rebuilt against it. Until it is
(see the [dependency roadmap](../AGENTS/tooling/dependencies/ROADMAP.md)), "what Geant4 does" in
any TRECH output means **11.4.2**. Everything in §3–§4 holds for both 11.4.2 and 11.5.0.beta
unless marked otherwise. A rebuild used to have one breaking change, the removed DNA constructors in
§6. The source now guards it.

---

## 2. What Geant4 is, and why that shapes its limits

Geant4 is a **Monte Carlo transport toolkit**. Its core abstraction is:

> independent particles, one at a time, are stepped through a **static geometry** made of
> **bulk materials**, and at each step a set of **processes** competes by cross section to
> decide what happens next (condensed-history EM, hadronic models, decays, boundary effects).

That design comes from high-energy and nuclear physics needs: detector response, shielding,
dosimetry, space radiation and medical physics. Four assumptions of that design produce almost
every limit TRECH meets:

| Design assumption | Why it is right for HEP | Why it limits TRECH |
| --- | --- | --- |
| **Particles are independent** (linear transport; tracks don't see each other within an event, events are independent) | Detector occupancy is low; beam particles don't interact | No collective behaviour: no fluids, no plasma response, no space charge, no many-body correlations, no feedback of deposited energy on the medium. |
| **Geometry and materials are frozen during a run** | A detector doesn't change while a beam crosses it | No flow, deformation, phase change, mixing, growth, reaction-driven composition change. |
| **Matter is a bulk mixture of elements** (density, composition, mean excitation energy, optional temperature/pressure/state) | Above ~keV, chemistry barely matters to cross sections | Molecules, bonds, crystal/band structure, H-bond networks, conformers don't exist as such, with a few explicit exceptions (Geant4-DNA water, MicroElec, channeling, phonons). |
| **Time horizon is the event** (ns–µs; DNA chemistry stage defaults to 1 µs) | Detector signals live in that window | Seconds-to-hours processes (diffusion, kinetics, heat, fluid motion, biology) are outside the toolkit. |

TRECH's thesis is to **learn the map from this base to the scales above it**. That makes these
limits the job description for the inference cascade, not an embarrassment to hide. The
cascade exists because Geant4 stops where §4 says it does.

---

## 3. What TRECH can count on (Geant4 capability map)

These capabilities are part of the pinned source. TRECH may use them as **base truth inside their
validity window**, recorded in provenance through the physics-list string
(`options.physicsList`, e.g. `QBBC+Optical`, `QGSP_BIC_HP+DNA_Opt4+Chem_Opt3`).

### 3.1 Electromagnetic physics (the TRECH workhorse)

| Capability | Geant4 component | Validity / limits in the pinned source | TRECH usage today |
| --- | --- | --- | --- |
| Photon interactions: photoelectric, Compton, Rayleigh, conversion (e⁺e⁻, triplet), photonuclear | `G4GammaGeneralProcess`, standard / Livermore / Penelope models; `G4EmExtraPhysics` for γ-nuclear | Standard EM tables span `minKinEnergy` 0.1 keV → `maxKinEnergy` 100 TeV ([`G4EmParameters.cc`](../thirds/geant4/source/processes/electromagnetic/utils/src/G4EmParameters.cc)); triplet production below 1 MeV is not sampled (`lowestTripletEnergy`). Livermore/Penelope models extend lower (∼100 eV order, element- and process-dependent). | Optics derivation, analytic cross-checks (Beer-Lambert, photo fraction, Compton transfer, pair fraction, photonuclear fraction), primary-fate tallies |
| Charged-particle ionisation, bremsstrahlung, multiple scattering, stopping | Standard EM options 0–4, WVI/GS/SS variants, `G4LindhardSorensenIonModel`, nuclear stopping | Electrons/muons/hadrons tracked down to `lowestElectronEnergy` / `lowestMuHadEnergy` = 1 keV by default, then deposited locally. Production cuts are converted to energies on a 0.99 keV–10 GeV grid ([`G4VRangeToEnergyConverter.cc`](../thirds/geant4/source/processes/cuts/src/G4VRangeToEnergyConverter.cc)). Condensed-history MSC has step/boundary artefacts that are physics-list-dependent. | CSDA range check, Bragg curves in viz, energy-deposit moments |
| Material EM facts: cross sections, stopping powers, ranges, mean excitation energy | `G4EmCalculator`, `G4IonisParamMat`, `G4LossTableManager` | Only as precise as the selected models and data; the CSDA table must be requested explicitly (`SetBuildCSDARange`) | `MolecularOptics`, `AnalyticCrossCheck`, `MaterialProbe`, Geant4-trained atomic→molecular response |
| Atomic de-excitation: fluorescence, Auger, PIXE | Livermore/atomic de-excitation (G4EMLOW) | Shell-level, isolated-atom data; no chemical shifts | Implicit in low-energy lists |
| Positron annihilation incl. 3γ and positronium (DNA) | `G4eplusTo2or3GammaModel`, `G4DNAPositronium`, `G4LEPTSPositroniumModel` | 3γ on-fly enabled by default only in EM option 4 | Not used explicitly |
| Polarised EM | `G4EmLivermorePolarizedPhysics`, `processes/electromagnetic/polarisation` | Photon and lepton polarisation transfer | Not used |
| X-ray/radiator processes | `G4Cerenkov`, `G4Scintillation`, `G4TransitionRadiation`, `G4XrayReflection` | Cherenkov needs a user-supplied `RINDEX`; scintillation needs user yields/spectra | Cherenkov/scintillation available via `G4OpticalPhysics` |

### 3.2 Track-structure (nano-scale) physics: Geant4-DNA and MicroElec

These are the parts of Geant4 that reach **eV scale and below the condensed-history picture**,
the closest Geant4 comes to TRECH's "nano" rung.

| Capability | Component | Validity / limits | TRECH usage |
| --- | --- | --- | --- |
| Event-by-event electron/proton/ion track structure in liquid water: elastic, excitation, vibrational excitation, ionisation (including multiple ionisation), attachment, charge exchange, solvation | `G4EmDNAPhysics`, options 2, 4, 6, 8; `G4EmDNABuilder` | **Liquid water** is the primary medium. DNA-base materials (G4_ADENINE, G4_CYTOSINE, G4_GUANINE, G4_THYMINE) appear in specific models. In 11.5, option 4 electrons reach **10 MeV** (G4EMLOW 9.0). The DNA↔standard EM transition energies now live in `G4EmParameters`. | Gated by `chemistry.enable` + `TRECH_ENABLE_DNA_CHEM` (default **OFF**) via [`DnaChemistry.cpp`](../src/chem/DnaChemistry.cpp) |
| Water radiolysis chemistry: radical species, diffusion, reactions (step-by-step, IRT, Smoluchowski), scavengers | `G4EmDNAChemistry` (+ options 1–3), `G4Scheduler`, `G4DNAIRT`, `G4DNASmoluchowskiReactionModel`, `G4DNAScavengerMaterial` | Radiolysis of water only (plus scavenger concentrations). Scheduler default end time **1 µs**, minimum time step 1 ps ([`G4Scheduler.cc`](../thirds/geant4/source/processes/electromagnetic/dna/management/src/G4Scheduler.cc)). It is not a general chemistry engine. | Same gate |
| Micro-electronics track structure | `G4MicroElec*` | A handful of materials (Si, SiO₂, Al₂O₃, BN, …), for radiation effects in electronics | Not used. A candidate base for CNT/solid-state rungs only as an analogue (no carbon nanotube model). |

### 3.3 Hadronic, nuclear and decay physics

| Capability | Component | Validity / limits | TRECH usage |
| --- | --- | --- | --- |
| Reference physics lists | `FTFP_BERT*`, `QGSP_BERT*`, `QGSP_BIC*`, `QBBC`, `Shielding`, `LBE`, `NuBeam`, INCLXX variants (all in [`physics_lists/lists`](../thirds/geant4/source/physics_lists/lists/include)) | Each is a *validated combination for an application domain*. None is universally correct. | `physics.list` (default `QBBC`; an unknown name throws) |
| Data-driven neutrons < 20 MeV including thermal | `_HP` lists, `G4ParticleHPThermalScattering` (S(α,β)), G4NDL, TENDL, URR probability tables | Only as complete as the evaluated libraries; material temperature affects Doppler broadening and thermal scattering | `config_nitrogen_carbon_cycle.js` uses `QGSP_BIC_HP` for ¹⁴N(n,p)¹⁴C |
| Radioactive decay | `G4RadioactiveDecay`, ENSDF data | Time threshold controlled via `G4HadronicParameters`; TRECH exposes `physics.radioactiveDecayThresholdYears` | ¹⁴C β⁻ decay in the nitrogen–carbon cycle |
| Intra-nuclear cascade, string, precompound/evaporation models | Bertini, BIC, INCL++, FTF, QGS, ABLA | **Phenomenological** (§5.1); validated against data, not derived from QCD | Indirect, through the physics list |
| Ultracold neutrons, muonic atoms | `G4UCNBoundaryProcess`, `G4MuonicAtom` | Specialised | Not used |

### 3.4 Optical photons and boundaries

| Capability | Component | Validity / limits | TRECH usage |
| --- | --- | --- | --- |
| Optical photon transport: bulk absorption, Rayleigh, Mie (Henyey–Greenstein), wavelength shifting | `G4OpticalPhysics`, `G4OpAbsorption`, `G4OpRayleigh`, `G4OpMieHG`, `G4OpWLS`, `G4OpWLS2` | **Ray optics with polarisation.** All bulk properties (`RINDEX`, `ABSLENGTH`, `RAYLEIGH`, `MIEHG`, …) are **user inputs**, not computed by Geant4. | `optics.enable` registers `G4OpticalPhysics` |
| Surface optics: Fresnel refraction/reflection, TIR, roughness models (GLISUR, UNIFIED, LUT, Davis), measured surfaces | `G4OpBoundaryProcess`, `G4OpticalSurface`, RealSurface data | Microfacet statistics, not wave scattering | Boundary class recorded per viz point (`refraction`/`reflection`/`total_internal_reflection`/…) |

The input requirement is where TRECH adds something: **`MolecularOptics` derives the refractive
index and attenuation from Geant4's own cross sections** (`G4EmCalculator`: photo + Compton +
Rayleigh, Beer-Lambert, a discrete Kramers–Kronig transform, an f-sum valence-electron plasma
energy) instead of typing them in. Geant4 performs the ray transport. The *n(λ)* that feeds it
is a TRECH derivation, labelled as such.

### 3.5 Solid-state and special-purpose packages

| Capability | Component | Limits |
| --- | --- | --- |
| Crystal channeling | `processes/solidstate/channeling` (`G4Channeling*`, G4CHANNELING data) | Planar/axial channeling of high-energy charged particles in bent/straight crystals |
| Acoustic phonon transport | `processes/solidstate/phonon` (`G4Phonon*`, `G4LatticeManager`) | Ballistic phonons in cryogenic crystals (dark-matter detector R&D); lattice from config files; no thermal conductivity, no electron–phonon transport |
| Crystal unit cells / extended materials | `G4CrystalUnitCell`, `G4ExtendedMaterial` | Descriptive lattice attachment, used by channeling/phonons only |

### 3.6 Fields, spin, geometry and infrastructure

| Capability | Component | Limits | TRECH usage |
| --- | --- | --- | --- |
| Charged-particle transport in **prescribed** magnetic/electric/gravity fields | `geometry/magneticfield` (`G4UniformGravityField`, EM field equations, integrators) | Fields are **external, static inputs**; the transported particles never source them | Not used yet |
| Spin precession in fields | `G4Mag_SpinEqRhs`, `G4EqEMFieldWithSpin` | Spin of the *tracked particle* (e.g. muon g-2), not bulk nuclear magnetisation | Not used. MRI spin dynamics are hook-layer (§4). |
| Annihilation-photon entanglement bookkeeping | `G4EntanglementAuxInfo` | Correlated polarisation of annihilation γ pairs only | Not used |
| Geometry: CSG/BREP solids, placements, parameterisations, navigation, overlap check | `geometry/` | Static per run; Geant4's `CheckOverlaps` draws points from the global RNG | TRECH runs its own RNG-isolated overlap check (see the [simulation handbook](../AGENTS/engine/simulation/AGENTS.md)) |
| Materials: NIST database, elements, isotopes, custom mixtures | `G4NistManager`, `G4Material`, `G4Isotope` | Bulk only. `temperature`/`pressure`/`state` are labels that few processes read. There is no `G4_SODIUM_CHLORIDE`, so build compounds from elements. | `DetectorConstruction`, `MaterialProbe` (element and isotope number densities) |
| Multithreading, accumulables, scoring, biasing, fast simulation (parameterisation) | `G4MTRunManager`, `G4AccumulableManager`, `G4ScoringManager`, `processes/biasing`, `G4FastSimulationManager` | MT ordering is nondeterministic at the reduction level | MT-safe tallies via accumulables. Strict MT resets `G4SafetyHelper` per event. |

---

## 4. Structural limits of Geant4 and what TRECH does instead

Each limit below is **by design**, not a bug that a newer Geant4 will fix. For each: what is
missing, what TRECH does today, and whether that TRECH layer is expected to stay
permanently outside Geant4.

Legend for the last column: **Permanent**, Geant4 will not cover this and TRECH owns it for
good. **Partial**, Geant4 has a narrow analogue that TRECH may draw on. **Watch**, an upstream
development could change the boundary.

| # | Missing in Geant4 | Consequence | What TRECH does (labelled *physics for comparison* or *inferred*) | Outlook |
| --- | --- | --- | --- | --- |
| L1 | **Particle–particle and collective interactions** within an event (space charge, plasma response, many-body correlations) | No emergent collective behaviour from transport alone | `PairInteraction` + `ctx.interact`; MD in [`trech_water_md.js`](../js/trech_water_md.js) | Permanent |
| L2 | **Medium feedback**: deposited energy does not heat, ionise or chemically change the material for later events | A beam never "boils" or "bleaches" the target | `StateEvolution` + `ctx.evolve` carries named continuous state between ticks. Geant4 acts as the per-tick clock and source term. | Permanent |
| L3 | **Static geometry/materials** within a run: no flow, deformation, mixing, phase change, growth | No fluids, foams, crystallisation, melting | PBF/SPH and parcel fluids (`glass_of_water_shaken`, `lava_lamp`), [`trech_euler3d_reference.js`](../js/trech_euler3d_reference.js), [`trech_foam_solver.js`](../js/trech_foam_solver.js), [`trech_crystallization_reference.js`](../js/trech_crystallization_reference.js); geometry can change only between runs (a new config re-initialises Geant4, and `trech lab` reuses a kernel only for compatible configs) | Permanent |
| L4 | **Time horizon** ns–µs (DNA chemistry ≤ ∼µs by default) | Seconds-to-hours processes are out of reach | Hook-driven multi-tick runs, `ctx.evolve`, process runtime ([`trech_process_runtime.js`](../js/trech_process_runtime.js)) | Permanent |
| L5 | **Molecules and bonds** are absent outside Geant4-DNA water/DNA bases: materials are element mixtures | No bond energies, conformers, polarisation, vibrational/rotational spectra, H-bond networks | Geant4-trained atomic → molecular response ([`trech_molecular_particle.js`](../js/trech_molecular_particle.js), `geant4_trained:true`); comparison-only PySCF/PubChem models (`geant4_trained:false`); authored chemistry graphs ([`trech_chemistry.js`](../js/trech_chemistry.js)) | Permanent (thesis: *lift particles into atoms and molecules through learning*) |
| L6 | **Thermal/eV-scale condensed matter** (kT ≈ 25 meV) beyond DNA water, MicroElec, thermal-neutron S(α,β) and cryogenic phonons | No thermodynamics, no heat transport, no diffusion of ordinary molecules, no phase equilibria, no osmotic pressure | MD (rigid SPC/E water: g(r), diffusion), osmotic/Pascal/efflux test scenarios, [`trech_solution_processes.js`](../js/trech_solution_processes.js) | Permanent |
| L7 | **General chemistry**: no reaction networks, kinetics, catalysis or solvents beyond water radiolysis | Combustion, oscillators, polymerisation, dissolution are absent | `DiscreteTransition` + `ctx.react` (integer stochastic state, conservation checks), Briggs–Rauscher, elephant's toothpaste, polyurethane foam, electrolysis/combustion scenarios | Permanent. Geant4-DNA chemistry stays the only Geant4-native chemistry base. |
| L8 | **Optical properties are inputs**, and optics is ray-based: no interference, diffraction, coherence, near-field, nonlinear optics, lasing; Mie only as an HG phase function | A material's colour or index cannot come "from Geant4" alone | `MolecularOptics` derives n/absorption from Geant4 cross sections (§3.4); optics surrogate; wave optics would be a TRECH layer | Permanent for derivation and wave effects. Ray transport stays Geant4. |
| L9 | **Self-consistent electromagnetism**: fields are external maps, with no Maxwell solution sourced by the simulated charges, no induced currents, no circuits | No electronics, no eddy currents, no plasma | CNT tight-binding band structure, CNTFET netlists solved Gauss–Seidel to the DC fixed point (electronics handbook) | Permanent |
| L10 | **Electronic band structure / solid-state transport** (only MicroElec dielectric parameters, channeling, phonons) | No semiconductors, metals vs insulators, mobility | CNT zone-folding TB with curvature gaps and trigonal warping | Permanent. MicroElec is at best an analogue base for electron transport in some materials. |
| L11 | **Bulk nuclear magnetism**: no magnetisation, Bloch dynamics, relaxation (T1/T2), NMR/MRI signal formation | MRI cannot be a Geant4 result end-to-end | Geant4 supplies proton density and photon transport; Larmor/Bloch/FFT reconstruction is hook-layer (resonance handbook) | Permanent |
| L12 | **Gravity and continuum mechanics** (gravity exists only as an optional field acting on tracks) | No sedimentation, buoyancy, stress, fracture | Hook-layer fluid/foam solvers with overdamped creep; Euler 3D comparison | Permanent |
| L13 | **Biology** beyond DNA-damage track structure/chemistry | No cells, metabolism, signalling | Biology track in scenarios, labelled inferred/comparison | Permanent. Geant4-DNA is the only biological base. |
| L14 | **Prediction across scales**: Geant4 returns tallies, never macro laws | Someone must lift the tallies | `ScaleCascade` + `ctx.cascade`, `GenericSurrogate` + `ctx.predict`, OOD hull/starvation/scale-mismatch trust policies | Permanent. This is TRECH's reason to exist. |
| L15 | **Byte-level reproducibility under MT**: reductions merge in worker order; `CheckOverlaps` consumes the global RNG; navigation safety is reused across events | Strict mode can't trust Geant4 defaults | `threads:1` for byte-identical float scores, a private-RNG overlap check, a per-event `G4SafetyHelper::InitialiseHelper()` in strict MT | Partial. Upstream could fix some of it. |
| L16 | **Physics-list choice is the user's responsibility**: results depend on it and Geant4 does not choose for you | Different lists give different answers in transition regions | `physics.list` is explicit and recorded in provenance. A default inferred from context remains an open cascade gap. | Watch |
| L17 | **Data completeness**: evaluated libraries have gaps (exotic isotopes, low-energy cross sections for materials other than water, molecular effects) | Silent extrapolation risk | Fail closed: unknown nuclides are "unknown, never zero"; custom materials skip unresolvable components with a warning | Watch (new G4 datasets) |

### 4.1 What "override" means in TRECH

TRECH never **patches** Geant4 physics or calibrates a Geant4 result against a classical formula.
It "overrides" in exactly three sanctioned ways:

1. **Extend above the base.** A hook-layer solver or learned model consumes Geant4-derived
   facts (cross sections, densities, deposits, track statistics) and predicts a higher-scale
   quantity. It is labelled *physics for comparison* or *inferred*, never as a Geant4 tally.
2. **Derive inputs Geant4 asks for.** Where Geant4 needs a user-supplied property (optical
   `RINDEX`, scintillation yields, field maps), TRECH may derive it from Geant4's own particle
   data (e.g. `MolecularOptics`) rather than typing it in. The derivation is recorded as one.
3. **Choose among Geant4's own options.** Physics list, DNA option, γ-nuclear model edge,
   radioactive-decay threshold and CSDA tables are Geant4 knobs that TRECH sets explicitly and
   records.

Anything else, such as replacing a Geant4 cross section with a hand value or tuning transport to
match a textbook curve, violates the root principles.

---

## 5. Limits that belong to physics and mathematics, not to Geant4

Some gaps would remain with a perfect toolkit, because the underlying theory is unsolved,
intractable or chaotic. TRECH must **label these as permanent uncertainty**, not as "to-do".

### 5.1 Fundamental theory

- **Non-perturbative QCD.** QED is computable to extreme precision, but nuclear and hadronic
  interactions at intermediate energies cannot be derived from QCD in practice. Lattice QCD does
  not produce reaction cross sections at the scale needed. Geant4's hadronic models (cascades,
  string models, precompound/evaporation) are therefore **phenomenological and data-tuned**.
  TRECH inherits their systematic uncertainty and should treat physics-list spread as an
  error bar, not noise.
- **Quantum many-body problem.** The exact electronic Schrödinger equation scales
  exponentially with electron count. Practical methods trade accuracy for cost (DFT functionals
  have no universal exact form; coupled-cluster CCSD(T) scales as ∼N⁷). The atom → molecule
  rung will **always** be an approximation or a learned map. This is why the molecular series
  keeps PySCF RHF/STO-3G as *comparison*, not truth.
- **Measurement is probabilistic.** Quantum outcomes follow the Born rule. A Monte Carlo
  ensemble is the correct representation, not an approximation of a hidden exact trajectory.
  A single event is a sample. Only distributions are predictions.
- **No quantum gravity.** Irrelevant at TRECH's energies and lengths, stated here for
  completeness: TRECH makes no claim in that regime.
- **Fundamental constants and evaluated data carry uncertainty.** CODATA values and nuclear
  data evaluations (ENDF/B, JEFF, TENDL) have quoted uncertainties that propagate into every
  "base truth". The Larmor check in the resonance scenarios (42.5768 vs CODATA 42.5775 MHz/T)
  shows the scale of agreement that is meaningful.

### 5.2 Emergence, scale and coarse-graining

- **Scale separation is not guaranteed.** A chain of scale-tagged models assumes that each
  rung needs only a few summary inputs from the rung below. Near **critical points** (diverging
  correlation length), in **turbulence** (energy cascades across all scales) and in
  **fracture/nucleation** (rare microscopic events control macroscopic outcomes), this
  assumption fails. The cascade must detect those regimes (scale-mismatch and OOD trust
  policies) rather than extrapolate through them.
- **Closure problem.** Hydrodynamics is derivable from kinetic theory only asymptotically
  (Chapman–Enskog, small Knudsen number). Averaging nonlinear equations always generates
  unknown higher moments (Reynolds stress in RANS, sub-grid stress in LES), so a learned
  closure is necessary, not a shortcut.
- **Far-from-equilibrium statistical mechanics has no general theory** comparable to Gibbs
  ensembles at equilibrium. Driven, reacting, living systems (oscillators, foams, biology) are
  modelled case by case.
- **Turbulence and Navier–Stokes.** Global existence and smoothness of 3D Navier–Stokes
  solutions is an open Millennium Prize problem. Direct numerical simulation cost grows
  roughly as Re³ (grid ∼Re^(9/4) times time steps). A stirred glass of water (Re ∼10⁴) is
  feasible only coarse-grained, and a molecule-by-molecule simulation (∼10²⁵ molecules) is
  impossible. **Statistical lifting is a necessity**, which is the TRECH thesis restated.

### 5.3 Predictability and numerics

- **Deterministic chaos.** Sensitivity to initial conditions (positive Lyapunov exponents)
  bounds the horizon of trajectory prediction for fluids, weather-like flows and many
  oscillating reactions. TRECH's *strict* mode guarantees **reproducibility** (same bytes from
  the same seed), not **predictability** (the same trajectory as a real glass of water). For
  chaotic systems only statistical observables (spectra, distributions, correlation functions)
  are meaningful predictions.
- **Ill-posed inverse problems.** Kramers–Kronig needs the absorption spectrum over *all*
  frequencies, but any real dataset is truncated, so the derived refractive index is an
  approximation with a quantifiable truncation error. Image reconstruction (MRI) and spectral
  unfolding share this character and need regularisation, which is a modelling choice.
- **Extrapolation has no guarantee.** A learned model outside the convex hull of its training
  data has no error bound. TRECH's hull/OOD checks and `geant4_trained` / `measured` /
  `mc_sampled` flags exist because of this, and should never be weakened to make a demo pass.
- **Floating-point arithmetic is not associative.** Parallel reductions in a different order
  give different last bits. This is the root cause behind the `threads:1` rule for
  byte-identical float scores.
- **Monte Carlo convergence is ∼1/√N.** Rare events need biasing or impractical statistics.
  Every tally carries a statistical error, and a missing error bar is a missing result.

---

## 6. Migration items for the pinned checkout

Found by comparing the `v11.4.1` and `v11.5.0.beta` imports in the submodule history and the
Geant4 `History` files. These matter only when TRECH is rebuilt against the checkout (it
currently links 11.4.2).

| Change in 11.5.0.beta | Geant4 reference | TRECH impact |
| --- | --- | --- |
| **`G4EmDNAPhysics_option1/3/5/7` removed** ("Removed DNA option 1, 3, 5, 7 constructors", phys-ctor-em-V11-04-08) | [`physics_lists/constructors/electromagnetic/History`](../thirds/geant4/source/physics_lists/constructors/electromagnetic/History) | **Handled.** [`src/sim/GeantRunner.cpp`](../src/sim/GeantRunner.cpp) includes those headers only under `G4VERSION_NUMBER < 1150`. Against 11.5+, `chemistry.model` naming one of them throws before any kernel is created (`dnaPhysicsOptionAvailable` in [`DnaChemistry.cpp`](../src/chem/DnaChemistry.cpp), CTest `trech_dna_chemistry_bridge`). It is never remapped to another option, because that would change the physics behind a recorded config. Checked so far only by syntax checks against 11.4.2 and an emulated 11.5, not by a real 11.5 build. |
| `G4EmDNAPhysics_stationary*` constructors removed | same | Not used by TRECH |
| DNA option 4 electrons extended to **10 MeV**; standard EM for electrons deactivated below 10 MeV in that configuration; **G4EMLOW 9.0 required** | same | `DNA_Opt4` runs will change physics, so they need a revalidation. The data install must move to G4EMLOW 9.0. |
| DNA ↔ standard transition energies moved into `G4EmParameters` | same | Only matters if TRECH starts setting DNA energy limits. Use `G4EmParameters` then. |
| `G4EmStandardPhysics_option2`: `ApplyCuts` now true | same | Lists that use opt2 EM may shift low-energy secondary production. Regression comparisons should flag it. |
| Multiple ionisation (double/triple/quadruple) and dissociation channels for multiply ionised water | `G4EmDNABuilder`, `G4ChemMIDissociationChannels` | Richer DNA chemistry yields. Regression baselines with DNA chemistry will move. |
| Large refactors of `G4GammaGeneralProcess`, `G4EmModelActivator`, `G4OpticalPhysics` | diff stat of the same path | TRECH classifies photoelectric-first events through `G4GammaGeneralProcess` sub-process subtypes. Re-verify `primaries_photoelectric_first_fraction` and the optics boundary classification after rebuild. |

The rebuild itself is tracked in the [dependency roadmap](../AGENTS/tooling/dependencies/ROADMAP.md).
Do not trigger it implicitly: it is a heavy build and needs confirmation.

---

## 7. Responsibility matrix by TRECH family

| TRECH family | Geant4 provides (base truth) | TRECH provides (labelled) | Permanently outside Geant4 because of |
| --- | --- | --- | --- |
| **Optics / H₂O** | Photon cross sections, ray transport, Fresnel boundaries, Cherenkov | n(λ)/absorption derivation (KK, f-sum), optics surrogate, spectral rendering | L8, §5.3 (truncated KK) |
| **Fluids** | Composition and energy-deposit facts, per-tick clock | MD (SPC/E), PBF/SPH, parcel thermofluid, Euler 3D comparison, foam mechanics | L1, L3, L4, L6, L12, §5.2 |
| **Chemistry** | Material/isotope facts; water radiolysis (Geant4-DNA, optional) | Authored reaction graphs, `ctx.react` kinetics, conservation, molecular response models | L5, L7, §5.1 (many-body) |
| **Biology** | DNA track structure and radiolysis in water | Higher-scale biological response (inferred) | L13 |
| **CNT electronics** | Electron transport through the channel material | Band structure (TB), device I–V, logic netlists | L9, L10 |
| **Magnetic resonance / MRI** | Proton density, photon/particle transport, tissue composition | Larmor discovery, Bloch dynamics, k-space/FFT reconstruction | L11, §5.3 (inverse problems) |
| **Nuclear cycles** | n-capture, (n,p), β-decay via HP lists and radioactive decay | Cycle bookkeeping and spatial analysis | (none: this is Geant4's home ground) |
| **Analytic cross-checks** | All particle-level inputs | Classical formulas fed by Geant4 data, compared and never calibrated | By design |
| **Multi-scale cascade** | The bottom rung's training labels | Every rung above it | L14, §5.2 |

---

## 8. Decision checklist for contributors

Before implementing any physical concept in TRECH:

1. **Is it in §3?** Then use Geant4 through config (physics list, constructors, `G4EmCalculator`,
   material probe) and record the choice in provenance. Do not reimplement it.
2. **Does Geant4 ask for it as an input** (optical constants, yields, fields)? Prefer deriving
   it from Geant4 particle data (§4.1 rule 2) and label the derivation. A typed constant is
   acceptable only as a declared authoring input.
3. **Is it in §4?** Implement it above the base: a hook-layer comparison solver or a learned
   cascade rung trained on Geant4 output. Label it (`geant4_trained`, `measured`,
   `mc_sampled`, *physics for comparison*). Never feed its output back as a Geant4 result.
4. **Does it hit §5?** State the irreducible uncertainty (chaos horizon, closure, extrapolation,
   phenomenological hadronics) in the scenario docs and provenance. Do not present it as a
   pending feature.
5. **Does it depend on the Geant4 version?** Check §1 and §6, and record residual gaps in the
   owning `ROADMAP.md`.

---

## 9. References

**Vendored Geant4 sources and docs (pinned checkout)**

- Physics lists: [`thirds/geant4/source/physics_lists/lists/include`](../thirds/geant4/source/physics_lists/lists/include)
- EM constructors and their history: [`thirds/geant4/source/physics_lists/constructors/electromagnetic`](../thirds/geant4/source/physics_lists/constructors/electromagnetic)
- EM parameters (energy limits): [`G4EmParameters.cc`](../thirds/geant4/source/processes/electromagnetic/utils/src/G4EmParameters.cc)
- Geant4-DNA: [`thirds/geant4/source/processes/electromagnetic/dna`](../thirds/geant4/source/processes/electromagnetic/dna)
- Optical: [`thirds/geant4/source/processes/optical`](../thirds/geant4/source/processes/optical)
- Solid state: [`thirds/geant4/source/processes/solidstate`](../thirds/geant4/source/processes/solidstate)
- Datasets: [`G4DatasetDefinitions.cmake`](../thirds/geant4/cmake/Modules/G4DatasetDefinitions.cmake)
- Vendored manuals: [`docs/geant4-docs/`](geant4-docs) (Physics Reference Manual, Physics List
  Guide, Book for Application Developers)

**Geant4 collaboration papers**

- S. Agostinelli et al., *Geant4 — a simulation toolkit*, Nucl. Instrum. Meth. A 506 (2003) 250.
- J. Allison et al., *Geant4 developments and applications*, IEEE Trans. Nucl. Sci. 53 (2006) 270.
- J. Allison et al., *Recent developments in Geant4*, Nucl. Instrum. Meth. A 835 (2016) 186.
- S. Incerti et al., *Geant4-DNA example applications for track structure simulations in liquid
  water*, Med. Phys. 45 (2018) e722.

**TRECH owners**

- [Engine simulation handbook](../AGENTS/engine/simulation/AGENTS.md) and [optics](../AGENTS/engine/simulation/optics/AGENTS.md)
- [Dependency handbook](../AGENTS/tooling/dependencies/AGENTS.md) and [roadmap](../AGENTS/tooling/dependencies/ROADMAP.md)
- Scenario families: [fluids](../AGENTS/scenarios/fluids/AGENTS.md), [chemistry](../AGENTS/scenarios/chemistry/AGENTS.md), [electronics](../AGENTS/scenarios/electronics/AGENTS.md), [resonance](../AGENTS/scenarios/resonance/AGENTS.md)
- [Output schema](output_schema.md) (provenance fields: physics list, DNA options, geometry resolution)
