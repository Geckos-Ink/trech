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
- [ ] Next analytic checks: a bound-electron Compton reference (Livermore/Monash with Doppler
  broadening, enabled by a physics-list option) graded against an independent dataset rather than
  the formula Geant4 implements (the energy-angle closure residual above is the ready-made
  detector of Doppler broadening); pair-production checks above the oxygen
  giant-dipole region, which need photonuclear absorption added to `mu_total` (or tallied as its
  own branch) before the denominator is honest; and an independent XCOM comparison of the
  pair/photo fractions (today they are self-consistency checks of Geant4's own tables).

- [x] `onEventEnd` resim routing supports independent sparse-training and wrong-scale policies
  without changing hull OOD accounting. Multiple causes queue/count an event once and remain
  visible beside feature-classification precedence. See the [trust validation/gaps](../inference/trust/ROADMAP.md).

