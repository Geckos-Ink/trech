# Geant4 transport and diagnostics — roadmap

[Root principles](../../../AGENTS.md) · [Root roadmap](../../../ROADMAP.md) · [Parent](../ROADMAP.md) · [Handbook](AGENTS.md)

## Choose a subcategory

| Scope | Context | Work remaining |
| --- | --- | --- |
| Optics and nondegenerate transport | [AGENTS.md](optics/AGENTS.md) | [ROADMAP.md](optics/ROADMAP.md) |

Maintain work in its owning branch. Dated results apply to the recorded checkout; they do not validate subsequent changes.

- [x] Reset strict multi-worker event safety to remove worker-history-dependent MSC branches.
  A manual gate compares exact event and full track trajectories across Tasking/MT with two/eight
  workers, without forcing serial or rounding results. Serial and one-worker compatibility hold.
- [ ] Full strict MT byte replay still needs deterministic run reduction and output ordering;
  see [runtime validation and residuals](../runtime/ROADMAP.md).

- [x] Klein-Nishina Compton cross-check and photofraction energy sweep (2026-11-06).
  `compton_energy_transfer`: 662 keV gamma in 200 mm water, KN `<T>/E` 0.38156 vs Geant4
  0.38254 (0.26%, z=+0.56, 16423 first-Compton primaries); max sampled transfer 0.721420 vs edge
  0.721435. Serial (`threads: 1`) strict reruns are byte-identical. Sweep (20000 events each):
  10/20/30/50/100 keV derived 0.927/0.675/0.391/0.117/0.0162 vs measured
  0.928/0.676/0.393/0.115/0.0162, |z| ≤ 0.91, 57× span. The sweep runs use default threads,
  so they are reproducible only up to last-ULP merge order (see the strict MT gap below).
  Verification: dev and Release CTest 39/39 each (new `trech_klein_nishina`); all five `analytic` cases pass,
  including the three existing ones after the first-interaction tally refactor. The full
  validation suite was not rerun and `docs/validation_report.*` was not refreshed.
- [x] Binned Klein-Nishina spectrum shape and pair-production threshold/branching (2026-11-07).
  `compton_energy_transfer` now histograms first-Compton `u = T/T_max` in 20 bins and compares
  them to the binned free-electron KN `dσ/dT` (Pearson χ², pooled to expected ≥ 5): 662 keV in
  water χ² = 10.54/19, p = 0.94 over 16423 entries; the mean/edge results are byte-unchanged.
  New `pair_fraction` (`analytic_pair_production.js`, 10 MeV gamma, 200 mm water, serial strict):
  `σ_conv/σ_total` 0.23390 vs measured 0.23652 (1.1%, binomial z = +0.83, 4254/17986); strict
  reruns are byte-identical. Sweep: 1.0 MeV gives exactly 0 derived and 0/38004 measured; 1.5/2/5
  MeV give z = −1.05/−1.28/+0.22; strictly rising, 173× span from 1.5 to 10 MeV. Graded by
  `analytic_compton_transfer_cross_check` (now with the spectrum gate, p ≥ 0.001),
  `analytic_pair_fraction_cross_check` and `analytic_pair_fraction_energy_sweep`.
  Verification: dev and Release CTest 41/41 each; all seven `analytic` validator cases pass on
  fresh runs. The full validation suite was not rerun and `docs/validation_report.*` was not
  refreshed.
- [x] Klein-Nishina angular distribution and energy-angle closure (2026-11-07).
  `compton_energy_transfer` now also tallies the first-Compton scattered photon's `cos θ` from the
  pre/post momentum direction (independent of the energy reading) in 20 equal-width bins. It is
  graded against KN `dσ/dcos θ` and `<cos θ>`, and the free-electron relation
  `E'/E = 1/(1+ε(1−cos θ))` closes the two readings. 662 keV in water: `<cos θ>` 0.31682 vs KN
  0.31870 (z = −0.41), χ² = 12.57/19 (p = 0.86), max closure residual 3.3e-16 over 16423
  scatters. The existing mean/edge/spectrum results are byte-unchanged and a serial strict rerun is
  byte-identical. Pooling moved into the shared `klein_nishina::pooledPearsonChi2`; a short trailing
  remainder now merges into the previous cell. That changes nothing for the current runs, where
  every bin expects ≫ 5. Verification: dev and Release CTest 41/41 each (extended
  `trech_klein_nishina`). All seven `analytic` validator cases pass on fresh Release runs, and the
  Compton case fails when the angular χ² or the closure residual is corrupted. Caveat: under
  free-electron kinematics the closure makes the angle histogram a one-to-one remap of the energy
  histogram. Its independent content is the direction sampling and the closure itself. It becomes a
  separate physics test only with a bound-electron model. The full validation suite was not rerun
  and `docs/validation_report.*` was not refreshed.
- [x] Photonuclear-aware photon totals and the giant-dipole branching check (2026-11-07).
  `fillAttenuationBreakdown` now adds the registered gamma inelastic cross section
  (`G4HadronicProcessStore`, the `G4GammaNuclearXS` table QBBC's general process samples) to
  every gamma `mu_total`, `SteppingAction`'s `fHadronInelastic` first interactions feed a new
  `primaries_photonuclear_first` tally, and a new `photonuclear_fraction` check grades
  `σ_pn/σ_total`. The term is exactly zero in water at ≤ 10 MeV, so every earlier check value is
  unchanged (all eight `analytic` cases pass on fresh Release runs with the recorded figures).
  The pair sweep now reaches 15/23/30 MeV (413× span, all |z| ≤ 1.3). The photonuclear check
  rides in `analytic_pair_production.js` (energy ceiling raised from 14 to 50 MeV) and is graded
  by `analytic_photonuclear_fraction_giant_dipole`: exactly 0 at 5/10 MeV; 15/23/30 MeV derived
  0.00592/0.04913/0.01497 vs measured 0.00531/0.05007/0.01396 (z = −1.01/+0.55/−1.00). The
  derived and measured maxima are both at 23 MeV. Without the photonuclear term, the 23 MeV pair
  prediction would be 0.4876 vs measured 0.4687 (z = −4.72). A serial strict rerun at 23 MeV is
  byte-identical. A 4-worker MT run gives the same `mu_pn` (master-thread query), with both checks
  at |z| < 2. Verification: Release and Debug CTest 41/41 each. The full
  validation suite was not rerun and `docs/validation_report.*` was not refreshed. Scope: these
  remain self-consistency checks of Geant4's own EM and photonuclear tables.
- [x] Photonuclear final-state conservation, kinematic edge and photoneutron yield (2026-11-07).
  For every primary photon's first photonuclear absorption, `SteppingAction` infers the target
  `(A, Z)` from the products' baryon number and charge and matches it to the step material's
  isotopes. It takes the ground-state mass from `G4NucleiProperties` and grades the final state
  with Geant4-free relativistic kinematics (`PhotonuclearKinematics.hpp`, new CTest
  `trech_photonuclear_kinematics`). The grades are four-momentum closure and, for every baryonic
  ejectile, the two-body edge `T_max(γ + A → x + R_ground)`; emission from a closed channel
  counts as a violation. The check entry also derives per-isotope `(γ,n)` thresholds and edges
  (16O: 15.67 MeV; 2H/17O/18O traces: 2.23/4.14/8.05 MeV). New validator case
  `analytic_photonuclear_final_state` (15/23/30 MeV, 50000 events each): `|ΔE|/E` max
  1.9e-12/2.1e-12/2.2e-12, `|Δp|/E` ≤ 4.2e-10, 0 unmatched targets, edge excess max
  −1.4e-3/−2.4e-5/−3.2e-3 over 172/2391/620 ejectiles. At 15 MeV, below 16O's `(γ,n)` threshold,
  no neutron appears. The 23 MeV neutron maximum is 5.68 MeV, below 16O's 7.03 MeV edge. The case
  fails when the closure or the edge excess is corrupted. Branching values and every earlier check
  are unchanged; all nine `analytic` cases pass on fresh Release runs. A serial strict 23 MeV
  rerun gives identical scores. Verification: Release and Debug CTest 42/42 each. The full
  validation suite was not rerun and `docs/validation_report.*` was not refreshed.
  **Finding:** Geant4 11.4 QBBC's sub-200 MeV photonuclear model (`GammaNPreco`,
  G4LowEGammaNuclearModel; Fermi break-up for A ≤ 16) sends 16O mostly into α break-up. Per
  absorption at 23 MeV it gives 2.50 α, 0.096 p and 0.0064 n (5 neutrons in 779 absorptions);
  at 15 MeV every absorption is α + 12C. Measured 16O giant-dipole decay is dominated by (γ,n)
  and (γ,p), so Geant4's *branching* (σ_pn) is right but its *channel mix* is not. The
  photoneutron yield is reported, not gated.
- [x] Photonuclear final-state model comparison (2026-11-07). New optional
  `physics.gammaNuclearLowEnergyModelLimitMeV` (conditionally serialized, round-trip tested;
  provenance tag `+GammaNuclearLE<v>MeV`) sets `G4EmExtraPhysics::GammaNuclearLEModelLimit`; 0
  removes GammaNPreco so Bertini handles every absorption (`--param gamma_nuclear_le_limit_mev=0`).
  Validator case `analytic_photonuclear_model_comparison` (15/23/30 MeV, 50000 events, dev build):
  identical branching (86/779/205 absorptions); n/p/α per absorption at 23 MeV GammaNPreco
  0.006/0.096/2.50 vs Bertini 0.127/0.291/0.372 (30 MeV: 0.278/0.566/0.40). Bertini is nucleon-
  dominated as measured GDR decay is, but closes energy only to |ΔE|/E ≤ 6.6e-3 (mean +1.5e-3;
  momentum still ≤ 1e-10, all edges respected). No neutron below 16O's (γ,n) threshold in either.
  Not yet run on Release or in the full suite; `docs/validation_report.*` not refreshed.
- [ ] Next analytic checks: a bound-electron Compton reference (Livermore/Monash with Doppler
  broadening, enabled by a physics-list option) graded against an independent dataset rather than
  the formula Geant4 implements (the energy-angle closure residual above is the ready-made
  detector of Doppler broadening); an independent XCOM comparison of the pair/photo fractions and
  an IAEA photonuclear-data comparison of the giant-dipole fraction (today all are
  self-consistency checks of Geant4's own tables). The photonuclear channel mix needs an IAEA
  (γ,n)/(γ,p)/(γ,α) partial-cross-section comparison of the new `photonuclear_final_state`
  yields, plus an investigation of whether another physics-list option (e.g. Bertini or
  precompound without Fermi break-up below 200 MeV) restores (γ,n)/(γ,p) dominance.

- [x] `onEventEnd` resim routing supports independent sparse-training and wrong-scale policies
  without changing hull OOD accounting. Multiple causes queue/count an event once and remain
  visible beside feature-classification precedence. See the [trust validation/gaps](../inference/trust/ROADMAP.md).


- [x] Geometry substitutions recorded in provenance (2026-11-09). DetectorConstruction reports
  unknown materials (`material_fallback`), unknown / not-yet-built / missing-`medium` parents
  (`parent_fallback`) and invalid-shape or duplicate volumes (`volume_skipped`) into
  `geometry_resolution` on both provenance phases and as `TRECH geometry:` stderr lines; resolution
  behaviour is unchanged (CTest `trech_geometry_resolution`; a 1-event sweep of 58 geometry-bearing
  example scenarios recorded zero substitutions). Residual: the report is not in
  `trech_scores.jsonl` and no validation case fails on it; a strict "refuse to run on substitution"
  option is undecided; `GeantLabRunner` reuses the first construction's report because a geometry
  patch already requires a lab restart.
