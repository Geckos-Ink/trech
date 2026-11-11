# Geant4 transport and diagnostics — context and contracts

[Root principles](../../../AGENTS.md) · [Root roadmap](../../../ROADMAP.md) · [Parent](../AGENTS.md) · [Roadmap](ROADMAP.md)

## Choose a subcategory

| Scope | Context | Work remaining |
| --- | --- | --- |
| Optics and nondegenerate transport | [AGENTS.md](optics/AGENTS.md) | [ROADMAP.md](optics/ROADMAP.md) |

Read the root principles and the parent handbook first; then open only the subcategory relevant to the task. Source paths and shell commands in code spans/blocks are repository-relative unless stated otherwise; Markdown links resolve from this file.

What Geant4 covers as base truth, what it does not model by design (and which TRECH layer replaces it),
and pending migration items for the pinned checkout: [`docs/GEANT4_features_and_limits.md`](../../../docs/GEANT4_features_and_limits.md).

- **Post-`Initialize` carriers are pre-allocated before `SetUserInitialization`.** `derivedOptics`,
  `analyticChecks`, `materialProbes` are `shared_ptr` carriers on `RunOptions` filled after Geant4
  `Initialize` (tables built) in [`src/sim/GeantRunner.cpp`](../../../src/sim/GeantRunner.cpp) and paired
  with the measured tally in `RunAction::EndOfRunAction`. A copy made before the carrier exists
  sees null — allocate first.
- **VizRecorder records the *outgoing* momentum direction.** Each point's `dx/dy/dz` is its
  outgoing segment's direction: post-step points carry the post-boundary (refracted/reflected)
  direction; the birth point uses `GetPreStepPoint()->GetMomentumDirection()` (not the track's
  post-step `dir`, which mis-records emission for a photon that interacts on step 1) and the
  pre-step kinetic energy (else step 1's energy loss vanishes from a Bragg curve). Optical
  boundary points carry `boundary` = the `G4OpBoundaryProcess` status class
  (refraction/reflection/total_internal_reflection/absorption/detection). See
  [`src/sim/VizRecorder.cpp`](../../../src/sim/VizRecorder.cpp), [`src/sim/SteppingAction.cpp`](../../../src/sim/SteppingAction.cpp).
- **Trajectory consumers must not infer scattering from a visible bend.** Points carry the Geant4
  `process`/classified `interaction`; scatter emphasis requires the recorded `scatter` class.
- **Material number density is element density.** `ctx.materials["…"].numberDensityPerCm3.H`
  is hydrogen atoms/cm³ from the constructed `G4Material`, summed over isotope components.
  Isotope-specific ¹H observables must use `elements[].isotopes[]`, not equate D/T with ¹H.
  [`src/sim/MaterialProbe.cpp`](../../../src/sim/MaterialProbe.cpp), opt-in via `materialProbe`.

- **Geometry substitutions are recorded, not silent.** `resolveMaterial` in
  [`src/sim/DetectorConstruction.cpp`](../../../src/sim/DetectorConstruction.cpp) walks
  `sim::chooseMaterial` ([`GeometryResolution.hpp`](../../../include/trech/sim/GeometryResolution.hpp)):
  requested (declared, case-insensitive, then NIST) → fallback (parent medium / world material) →
  `G4_AIR`. An empty request inherits silently; a non-empty unresolved one is a `material_fallback`.
  An unknown, not-yet-built or missing-`medium` parent places the volume in the world
  (`parent_fallback`), and an invalid shape or duplicate name drops it (`volume_skipped`). Each is
  printed as `TRECH geometry:` on stderr and copied by RunAction into the provenance
  `geometry_resolution` block (`RunOptions::geometryResolution`, filled during `Initialize`). The
  behaviour itself is unchanged; the `TRECH_FLOW` `materials`/`geometry` presets catch the same
  defects at authoring time. CTest `trech_geometry_resolution`.
- **Constructed geometry is overlap-checked without touching the run RNG.** After construction
  DetectorConstruction samples `geometry.overlapCheck.samplesPerVolume` (default 1000) surface
  points per placed volume (MediumBox included) from a private splitmix64 stream seeded by the
  volume name ([`OverlapSampling.hpp`](../../../include/trech/sim/OverlapSampling.hpp), Geant4-free),
  moves them through each placement's real transform and asks the real Geant4 solids
  (`Inside`, `DistanceToIn`/`DistanceToOut` safeties) whether a point leaves its mother
  (`protrudes_parent`) or enters a sibling (`overlaps_sibling`; disjoint bounding spheres are
  skipped). Geant4's own `CheckOverlaps` draws points from the global CLHEP engine, which would
  shift a strict run's stream; this check leaves scores and emits byte-identical (verified on
  `geometry_procedural_assembly` with the check on vs off). Overlaps deeper than `toleranceMm`
  become `overlap` issues (with `depth_mm`, a lower bound) in `geometry_resolution` and a
  `TRECH geometry:` stderr line; every run that ran the check writes a `geometry_overlap_check`
  summary (`clean`, volumes/pairs checked). Default config is not serialized (hashes unchanged);
  `overlapCheck: false` disables it. Touching faces are surface points, not overlaps.
- **Event-deposit shape comes from additive power sums.** `system_event_edep_*` shape scores
  (stderr, min/max, zero fraction, skewness, excess kurtosis) use Σx..Σx⁴ accumulables plus
  min/max merge modes, summarised by the Geant4-free
  [`include/trech/sim/EventMoments.hpp`](../../../include/trech/sim/EventMoments.hpp) (CTest
  `trech_event_moments`). Mean/variance keep their historical arithmetic; shape is withheld
  (`null`, `shape_defined:false`) below the raw-sum cancellation floor.
  Floating sums merge in worker order, so multi-threaded reruns can differ in the last bits of
  every `system_event_edep_*` float (already true of the historical variance; counts, min/max and
  zero fraction are exact). Byte-identical scores need `threads:1`.
- **Per-event multiplicity reuses the same summary.** `EventAction` keeps the event's primary count
  from `BeginOfEventAction` and passes `max(0, tracks − primaries)` and the summed step length of
  all tracks to `RunAction::RecordEventMultiplicity`; `EventScalarAccumulables` holds Σx..Σx⁴,
  zero count and min/max for each scalar, scored as `system_event_secondaries_*` (plus
  `dispersion_index` = variance/mean, `null` at zero mean) and `system_event_track_length_*_mm`.
  "Secondaries" counts every stepped non-primary track, optical photons included when optics is
  on, and ignores production cuts (a sub-cut deposit is not a track). Scores only; provenance is
  unchanged. 100 keV Beer-Lambert, 20,000 events: mean 0.872 secondaries, zero-secondary fraction
  0.4341 ≥ uncollided 0.4217 (and > zero-deposit 0.4322: sub-100 eV Compton electrons deposit
  locally without a track), dispersion 1.16, mean track length 190 mm.
- **Secondaries are also split by species.** `SteppingAction` classifies each track with a
  non-zero parent ID at its first step through the Geant4-free
  [`SecondarySpecies.hpp`](../../../include/trech/sim/SecondarySpecies.hpp) (`gamma`, `electron`,
  `positron`, `optical_photon` by particle name, `neutron`, `other` by PDG code);
  `EventAction` hands the per-event counts to `RunAction::RecordEventSecondarySpecies`, one
  `EventScalarAccumulables` per class, scored as
  `system_event_secondaries_<species>_{mean,stddev,stderr,max,zero_fraction,dispersion_index}`.
  Classes are exhaustive and exclusive, so species means sum to the total (exactly in every run
  checked: Beer-Lambert 100 keV all electrons; 10 MeV pair production γ 0.46, e⁻ 1.74, e⁺ 0.085;
  1.5 MeV e⁻ with optics, optical photons 114.55/event = the run's 2291 `optical_photon_tracks`).
- **MT-safe run-level tallies use Geant4 accumulables.** Event feature moments and primary tallies
  merge through accumulables so worker events cannot vanish from the summary (`event_feature_stats`
  runs unconditionally now). Integer per-primary counts (uncollided, photoelectric-first) are
  MT-order-independent and reproducible without `threads:1`.
- **Strict MT transport resets event-local geometry safety.** At `BeginOfEventAction`, workers
  in a strict run with more than one actual worker call `G4SafetyHelper::InitialiseHelper()`.
  Geant4 otherwise retains safety at a repeated source position across events; MSC can then
  choose different branches from the same event seed depending on the previous event on that
  worker. The reset consumes no RNG and leaves true Serial / one-worker trajectories unchanged.
  Run reductions and output append order remain nondeterministic; exact event/track-keyed
  transport is not full byte replay. See the [runtime gap](../runtime/ROADMAP.md).
- **Custom materials fail-safe, never half-build.** `buildCustomMaterials`
  ([`src/sim/DetectorConstruction.cpp`](../../../src/sim/DetectorConstruction.cpp)) resolves every
  component up front, mass-fraction-renormalizes over what resolved, and warns+skips unresolvable
  components rather than constructing a malformed `G4Material` (which crashed Geant4 table
  builders — e.g. there is no `G4_SODIUM_CHLORIDE`, so build NaCl from `element` symbols).

### C++ engine — `trech_chem` ([`src/chem/`](../../../src/chem))

#### [`src/chem/DnaChemistry.cpp`](../../../src/chem/DnaChemistry.cpp) · [`DnaChemistry.hpp`](../../../include/trech/chem/DnaChemistry.hpp)

Geant4-DNA EM/chemistry bridge, gated behind `chemistry.enable` + `TRECH_ENABLE_DNA_CHEM`;
`chemistry.solver` (non-`stub`) enables the chemistry stage. The Geant4-free
`dnaPhysicsOptionAvailable(option, G4VERSION_NUMBER)` gate encodes Geant4 11.5's removal of DNA
options 1/3/5/7. `runGeant4` checks it before creating any kernel and `buildDnaPhysics` checks it
again: an unavailable option throws (fail closed), never falling back to another constructor.

- **Tests:** [`tests/test_dna_chemistry_bridge.cpp`](../../../tests/test_dna_chemistry_bridge.cpp).

### C++ engine — `trech_sim` ([`src/sim/`](../../../src/sim), Geant4-gated by `TRECH_ENABLE_GEANT4`)

Canonical Geant4 wiring order: RunManager → DetectorConstruction + PhysicsList(QBBC) +
ActionInitialization → Initialize → BeamOn. Only compiled when Geant4 is found.

#### [`src/sim/GeantRunner.cpp`](../../../src/sim/GeantRunner.cpp) · [`GeantRunner.hpp`](../../../include/trech/sim/GeantRunner.hpp)

Owns the RunManager lifecycle. `runGeant4(cfg, options, argc, argv)` is the run entry; the
`GeantLabRunner` reuses the kernel across compatible `BeamOn`s for `trech lab`. Pre-allocates the
post-`Initialize` carriers and calls `SetBuildCSDARange(true)` only when a `csda_range` check is
configured. `SetNumberOfThreads` when `run.threads > 0`.
Builds the physics list from `physics.list` (default QBBC; an unknown name throws before any run)
and applies `physics.radioactiveDecayThresholdYears` via `G4HadronicParameters` before process
construction — `config_nitrogen_carbon_cycle.js` uses `QGSP_BIC_HP` + 1e6 years so thermal
¹⁴N(n,p)¹⁴C and the ¹⁴C β⁻ decay are both Geant4-sampled (QBBC samples neither here).

#### [`src/sim/DetectorConstruction.cpp`](../../../src/sim/DetectorConstruction.cpp) · [`PrimaryGeneratorAction.cpp`](../../../src/sim/PrimaryGeneratorAction.cpp)

Geometry/materials and the beam source. `buildCustomMaterials` fail-safes custom mixtures (see
contracts). `TrechPrimaryGeneratorAction` owns beam sampling: `beam.spread`
(spot/divergence/energy), `beam.polarization` (optical photons only; kills `ZeroPolarization`),
and `beam.spectrum` (weighted line list) — all conditionally serialized and reproducible under a
fixed seed.

#### [`src/sim/RunAction.cpp`](../../../src/sim/RunAction.cpp) · [`EventAction.cpp`](../../../src/sim/EventAction.cpp) · [`SteppingAction.cpp`](../../../src/sim/SteppingAction.cpp) · [`ActionInitialization.cpp`](../../../src/sim/ActionInitialization.cpp)

Per-run/event/step Geant4 user actions. `RunAction::EndOfRunAction` pairs analytic predictions
with measured tallies and merges accumulables (`AddPrimaryTrackLength` etc.); `SteppingAction`
tracks per-primary fate (`primaries_uncollided`, `primary_mean_track_length_mm`,
`primaries_photoelectric_first_fraction` — classified via `G4GammaGeneralProcess` sub-process EM
subtype) and pushes trajectory points into the `VizRecorder`. **`RunAction::DispatchHook` returns
`HookInferenceCounts` (hull OOD, starvation and wrong-scale evaluations)**.
`EventAction::EndOfEventAction` applies independent `stratify.resimOnLowConfidence`,
`resimOnStarvation` and `resimOnScaleMismatch` policies to that dispatch only. Qualifying events
increment `stratify_low_confidence_count` once; `dumpResimQueue` controls candidate writing.
Feature-exceptional reasons retain precedence, while conditional cause lists preserve every
enabled inference trigger. Legacy event/queue fields stay byte-identical when the two new
policies are disabled. Full semantics and remaining limits: [trust contract](../inference/trust/AGENTS.md).

#### [`src/sim/MolecularOptics.cpp`](../../../src/sim/MolecularOptics.cpp) · [`AnalyticCrossCheck.cpp`](../../../src/sim/AnalyticCrossCheck.cpp) · [`MaterialProbe.cpp`](../../../src/sim/MaterialProbe.cpp) · [`VizRecorder.cpp`](../../../src/sim/VizRecorder.cpp)

The Geant4-data extraction surfaces:

- **MolecularOptics** — derives n/absorption/scatter from `G4EmCalculator` cross sections (photo +
  Compton + Rayleigh) via Beer-Lambert + discrete Kramers-Kronig; anchor-free (`optics.derive`).
- **AnalyticCrossCheck** — `evaluateBeerLambert` / `evaluateCsdaRange` / `photo_fraction` /
  `compton_energy_transfer` / `pair_fraction` / `photonuclear_fraction` (shared
  `fillAttenuationBreakdown`); each pairs a
  closed-form prediction with a measured tally via `AnalyticCheckResult.measuredField` (new check
  types stay data-driven). The Klein-Nishina reference lives in Geant4-free
  [`include/trech/sim/KleinNishina.hpp`](../../../include/trech/sim/KleinNishina.hpp) (fixed Simpson
  quadrature for the mean, the binned `u = T/T_max` spectrum over `kTransferHistogramBins` = 20
  bins, `<cos θ>` and the `kCosThetaHistogramBins` = 20 equal-width `cos θ` bins, plus the shared
  `pooledPearsonChi2`; tested by `trech_klein_nishina`). `SteppingAction` classifies a
  primary's first discrete interaction by EM subtype and passes `(subtype, (E-E')/E, u-bin, cos θ,
  kinematic residual)` to `TrechRunAction::AddPrimaryFirstInteraction`. `cos θ` comes from the
  pre/post momentum *direction*, and the residual is `|E'/E − 1/(1+ε(1−cos θ))|`. Conversions
  (`fGammaConversion`) feed `primaries_pair_first`; photonuclear absorption (`fHadronInelastic`,
  selected inside `G4GammaGeneralProcess`) feeds `primaries_photonuclear_first`. The `compton_energy_transfer` entry carries the
  energy and angle histograms, the KN bin probabilities and engine-side Pearson χ² values (expected
  counts pooled to ≥ 5, a short trailing remainder merged into the last cell); `pair_fraction`
  records the CLHEP `2 m_e c²` threshold and a binomial z. Any check whose prediction is exactly zero
  (pair below threshold, no photonuclear cross section) is `within_tolerance` only for an
  exactly-zero measurement.
  **Photon `mu_total` includes photonuclear absorption.** For gamma probes
  `fillAttenuationBreakdown` adds `G4HadronicProcessStore::GetInelasticCrossSectionPerVolume` —
  the registered `photonNuclear` process (`G4GammaNuclearXS` data) that the general process
  samples — so every first interaction the stepping action counts has a term in the
  denominator. It is exactly zero below the lowest photonuclear threshold (water: zero at
  10 MeV, 7.8e-6/mm at 13 MeV), so lower-energy check values are unchanged. Omitting it biases
  the 23 MeV pair check by z = −4.7. The store query is master-thread safe after `Initialize`;
  never query it for a non-gamma probe (it would return that particle's hadronic inelastic).
  **Photonuclear final state.** For a gamma primary whose first interaction is `fHadronInelastic`,
  `SteppingAction` reads the step's secondaries, infers the target `(A, Z)` from baryon number and
  baryonic charge, matches it against the step material's isotopes, and computes the
  four-momentum closure and the per-ejectile two-body edge with Geant4-free
  [`PhotonuclearKinematics.hpp`](../../../include/trech/sim/PhotonuclearKinematics.hpp)
  (tested by `trech_photonuclear_kinematics`) using `G4NucleiProperties` masses. It hands a
  `PhotonuclearFinalState` to `TrechRunAction::AddPhotonuclearFinalState`. The
  `photonuclear_final_state` score and the check's `final_state` / `photoneutron_channels`
  fields appear only when used, so other scores keep their shape. In Geant4 11.4 QBBC the
  final state below 200 MeV is `GammaNPreco` (G4LowEGammaNuclearModel). For 16O it is
  α-dominated (Fermi break-up), so the measured photoneutron yield is far below evaluated
  GDR data. Grade conservation and kinematics, not the channel mix.
- **MaterialProbe** — reports Geant4's known composition per material → `ctx.materials` +
  `material_probes` (opt-in, mirrors the analytic-carrier pattern). Optional
  `materialProbe.interactions{particle,processes,energiesMeV}` samples `G4EmCalculator`
  responses after initialization for learning. These are Geant4 interaction-table data, not
  MC tallies; unavailable queries omit numeric values. Default probe/config bytes stay unchanged.
- **VizRecorder** — singleton trajectory recorder (single mutex, workers push, master flushes on
  `EndOfRunAction`); the outgoing-direction rule above lives here.

#### [`src/sim/NuclearCycleAnalyzer.cpp`](../../../src/sim/NuclearCycleAnalyzer.cpp) · [`MultiscaleBridge.cpp`](../../../src/sim/MultiscaleBridge.cpp)

Nuclear cycle Q-value/conservation analysis (`nuclear.enable` + `nuclear.cycles`) — tests:
[`tests/test_nuclear_cycle_analyzer.cpp`](../../../tests/test_nuclear_cycle_analyzer.cpp). `MultiscaleBridge`
is stubbed behind `multiscale.enable` and does not alter physics yet (**Known gap**).

### Analytic cross-checks — Shipped

Beer-Lambert / CSDA-range / photo-fraction: a closed-form prediction from Geant4's *own* cross
sections vs the run's Monte-Carlo tally, emitted with the gap. Self-consistency checks, not
external calibration. Compton energy transfer compares the free-electron Klein-Nishina
`<T>/E = sigma_tr/sigma` (and Compton edge `2eps/(1+2eps)`) with the measured mean/maximum
`(E-E')/E` of first-Compton primaries. QBBC's `G4EmStandardPhysics` uses the free-electron
`G4KleinNishinaCompton` model unless polarisation is on, so binding/Doppler effects are outside
this reference. The photo-fraction scenario takes `--param energy_mev`; the suite sweeps
10/20/30/50/100 keV and grades binomial `|z| < 4`, a strictly falling fraction and ≥10× span
(`analytic_photo_fraction_energy_sweep`).

- **Null post-`Initialize` carrier.** Symptom: analytic/optics/material results missing. Cause: a
  `RunOptions` copy captured the carrier before it was allocated. Fix: pre-allocate the `shared_ptr`
  before `SetUserInitialization`.
- **Mis-recorded photon emission direction.** Symptom: a photon that interacts on step 1 has a
  wrong first segment. Fix: birth point uses the pre-step momentum direction.
- **Missing NIST material crashes Geant4.** Symptom: SIGSEGV in table builders. Cause: a
  half-built `G4Material` (declared > added, e.g. `G4_SODIUM_CHLORIDE` which does not exist). Fix:
  `element`-component materials + fail-safe `buildCustomMaterials`.
