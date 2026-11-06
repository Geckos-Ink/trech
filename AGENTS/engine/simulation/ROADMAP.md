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
- [ ] Next analytic checks: the Klein-Nishina *angular/energy spectrum* shape (binned `dσ/dT`
  vs a sampled histogram, not just its mean and edge), a bound-electron reference
  (Livermore/Monash Compton with Doppler broadening) graded against an independent dataset, and
  the pair-production threshold/branching above 1.022 MeV.

- [x] `onEventEnd` resim routing supports independent sparse-training and wrong-scale policies
  without changing hull OOD accounting. Multiple causes queue/count an event once and remain
  visible beside feature-classification precedence. See the [trust validation/gaps](../inference/trust/ROADMAP.md).

