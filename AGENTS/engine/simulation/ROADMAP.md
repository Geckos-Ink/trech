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
  Release full-suite run 2026-11-12 (`917adc2`): passes, recorded in `docs/validation_report.*`.
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
  `trech_scores.jsonl` and no validation case fails on it; ~~a strict "refuse to run on
  substitution" option is undecided~~ (`geometry.refuseOn`, 2026-11-12 below); `GeantLabRunner`
  reuses the first construction's report because a geometry patch already requires a lab restart.
- [x] Post-construction Geant4 overlap check recorded in provenance (2026-11-10). New
  `geometry.overlapCheck` (`true` by default; `false` or `{enable, samplesPerVolume, toleranceMm}`,
  serialized only when non-default, parse errors for out-of-range values; the `TRECH_FLOW`
  `geometry` preset mirrors them) runs a surface-sampling check on the built Geant4 solids with a
  private RNG, adds `overlap` issues (`overlaps_sibling` / `protrudes_parent`, `depth_mm`) to
  `geometry_resolution` and writes a `geometry_overlap_check` provenance block on both phases.
  CTest `trech_geometry_resolution` covers the sampler (on-surface, area weighting, determinism),
  config parsing/round-trip and both provenance blocks; a seeded config confirmed a sibling
  overlap (≥ 4.94 mm), a protrusion (≥ 1.00 mm) and no report for touching or distant volumes;
  `geometry_procedural_assembly` is clean over 91 pairs with byte-identical scores/emits vs the
  check off. **Finding (1-event sweep of 35 geometry-bearing scenarios):** four examples carried
  overlaps Geant4 had accepted silently — `briggs_rauscher_oscillator` (three probes protruding
  2 mm from the world, and the 5 cm medium cube's corners inside the 27 mm-radius beaker wall,
  ≥ 5.8 mm), `glass_from_sand` (`crucible`/`charge` siblings, ≥ 10 mm), `testscenario_efflux`
  (`efflux_chamber` vs the MediumBox, ≥ 3 mm) and `testscenario_magnetic_resonance_tissues`
  (receiver-coil side plates overlapping each other and the cap, ≥ 1.5 mm, eight pairs); the
  other 31 were clean (`elephants_toothpaste`/`polyurethane_foam` stop later without the PubChem
  cache). **[fixed 2026-11-10]** Briggs-Rauscher: liquid box 50 → 38 mm (inscribed in the declared
  beaker; beam origin and `system.volumeMm3` follow, the drawn beaker is unchanged) and probes at
  ±100 mm; `glass_from_sand`: `charge` is the crucible's daughter; efflux: the chamber is the
  medium's daughter; MRI tissues: five non-overlapping NaI plates (side plates stop at the cap,
  y plates fit between x plates). All four now report `clean`. Validation-suite runs before/after
  (same commands as `scripts/run_validation_suite.sh`): `briggs_rauscher_oscillation` 10/10 with an
  identical summary (total deposit 6.85 → 6.26 MeV over the shorter liquid path),
  `glass_from_sand_material_creation` 21/21 and `glass_operator_matches_reference` unchanged
  (geantino), `efflux_first_order_kinetics` 9/9 (Geant4 steps 12789 → 12952, kinetics identical)
  and `efflux_operators_match_reference` unchanged, `magnetic_resonance_tissue_contrast` 5/5
  (bone 0.600× → 0.589× water vs proton ratio 0.583; corr 0.9995 → 0.9996). Residual: no
  validation case fails on an overlap and no "refuse to run" option; sampling is a bound, not a
  proof (thin slivers can be missed); a lab geometry restart reuses the first report; the
  committed `briggs_rauscher`/`magnetic_resonance_tissues` demo media and
  `docs/validation_report.*` predate these geometry fixes.
- [x] Per-event secondary multiplicity and track-length shape (2026-11-10). `system_event_secondaries_*`
  (mean/stddev/stderr/min/max/zero fraction/skewness/excess kurtosis/`dispersion_index`) and
  `system_event_track_length_*_mm` reuse `EventMoments.hpp` (new `merge`, `dispersionIndex`;
  extended CTest `trech_event_moments`). Graded by `system_event_multiplicity_consistent` on the
  100 keV Beer-Lambert run (20,000 events: mean 0.872, zero-secondary 0.4341 ≥ uncollided 0.4217,
  ≥ 1 secondary in 11318 ≥ 213 photoelectric-first events, dispersion 1.16, track length
  55–367 mm). Residual: no per-volume multiplicity; scores-only at the time (provenance copy landed
  2026-11-11); multi-threaded reruns differ in the
  last float bits like the deposit shape; full validation suite and `docs/validation_report.*`
  not refreshed.
- [x] Per-species secondary multiplicity, optical photons split out (2026-11-11).
  `system_event_secondaries_<species>_*` for `gamma`/`electron`/`positron`/`optical_photon`/
  `neutron`/`other` ([`SecondarySpecies.hpp`](../../../include/trech/sim/SecondarySpecies.hpp),
  classifier + sum identity in CTest `trech_event_moments`). `system_event_multiplicity_consistent`
  now also requires species sum = total, count-valued species, electron events covering
  photoelectric-first primaries and no positrons at 100 keV (20,000-event rerun passes; species
  mean electron 0.8718 = total). Spot runs: 10 MeV pair production (2,000 events) has 170
  positron events ≥ 160 pair-first primaries; `config_stratify_ml` (1.5 MeV e⁻, optics, 20 events)
  gives 114.55 optical photons/event, exactly the run's `optical_photon_tracks`. Studio's Run
  summary lists each produced species. Residual: compact summary per species (no min/skew/kurtosis);
  the species sum can fall short of the stepped-track total only if a primary never steps (not
  observed); no per-volume or per-process split; provenance copy landed 2026-11-11; pair/optics spot runs are
  not validation cases; `docs/validation_report.*` not refreshed.
- [x] Per-volume event-deposit shape and provenance copy of the event shape (2026-11-11).
  Every `scoreEdep` volume now gets the same power-sum summary per event (`volume_event_edep`,
  `{mean_mev, stddev_mev, stderr_mev, min_mev, max_mev, zero_fraction, shape_defined, skewness,
  excess_kurtosis}`), flushed once per event from a per-thread buffer. The multiplicity,
  track-length, species and per-volume fields are also copied verbatim into `run_end` provenance
  (closing the "no provenance copy" residuals above); `run_start` and every existing score are
  unchanged (Beer-Lambert 20,000-event rerun: mean 0.8718, zero-secondary 0.4341, deposit skew
  2.595, kurtosis 9.01, as recorded). New validation case `system_volume_event_edep_consistent` on
  a `geometry_procedural_assembly` run (now in `scripts/run_validation_suite.sh`): 400 events, 19
  volumes, 9 hit, every `mean · events` equal to `volume_edep_mev` within 1e-9, scored volumes
  144.76 of 147.96 MeV; a rerun gives identical per-volume values. Studio's Run summary lists hit
  volumes. Verification: Release and Debug CTest 52/52 (extended `trech_geometry_resolution` for
  the provenance copy), `tests/test_system_observable_cases.py` 9/9, Studio `test_ui_panels.py`
  20/20; the three `engine` system-observable cases pass on fresh Release runs. Residual: no
  per-volume histograms (the system-level histograms landed 2026-11-11 below), multiplicity or
  track length; per-volume
  entries are keyed by name, so repeated placements of one name share an entry; MT reruns differ
  in the last float bits like the other moments; full validation suite and
  `docs/validation_report.*` not refreshed.
- [x] Fixed-binning per-event histograms (2026-11-11). `system_event_edep_histogram` (log10, 10
  bins/decade over 1 eV–1 TeV, zero/underflow/overflow slots) and
  `system_event_secondaries_histogram` (exact 0..15, then octaves) from the Geant4-free
  [`EventHistogram.hpp`](../../../include/trech/sim/EventHistogram.hpp), one integer accumulable per
  slot, populated span only, copied into `run_end` provenance. Integer merges make them
  worker-count independent: a 4,000-event 662 keV Compton run gives identical histograms at 1 and 4
  threads (the float mean differs in the last bit). New validation case
  `system_event_histogram_consistent` on the Beer-Lambert run (every event counted once, fixed-grid
  edges, zero slot = zero fraction, max/min in the end bins, run mean between the bin-edge sums,
  verbatim provenance copy); it passes on fresh Release Beer-Lambert (20,000 events),
  `geometry_procedural_assembly` and the 4-thread Compton runs. Studio's Run summary lists the
  bins verbatim. Verification: Release and Debug CTest 52/52 (extended `trech_event_moments`),
  `tests/test_system_observable_cases.py` 15/15; the Studio test was exercised without pytest
  (no Studio venv on the checking host), so Studio pytest was not run.
  Residual: ~~per-volume histograms and a track-length histogram are not binned~~ (landed
  2026-11-12 below); the
  fixed grid cannot resolve structure finer than 1/10 decade (e.g. the 100 keV full-absorption
  line is one bin); the full validation suite and `docs/validation_report.*` not refreshed.
- [x] Track-length and per-volume deposit histograms (2026-11-12). `EventHistogram.hpp` now names
  one shared log10 grid (`logEdge`/`logSlot`; the deposit functions are aliases) that also bins
  the per-event summed track length in mm (`system_event_track_length_histogram`, 1 nm–1 km) and
  each `scoreEdep` volume's per-event deposit (`volume_event_edep.<name>.histogram`); all three
  are written by one `logHistogramJson` and travel in the `run_end` provenance copy. The system
  deposit and multiplicity histograms are unchanged (Beer-Lambert 20,000-event rerun gives the
  recorded 47 deposit bins byte for byte). Validation: `system_event_histogram_consistent` grades
  the track-length histogram with the same shared checks as the deposit
  (`_log_histogram_checks`: scheme, every event once, fixed grid, trimmed span, zero slot =
  zero fraction, extremes in end bins, mean between the bin-edge sums, verbatim provenance copy);
  `system_volume_event_edep_consistent` applies them to every volume. Both pass on fresh Release
  Beer-Lambert (track length 9 bins `[50.1, 398)` mm, min 55.4 / max 367.3 inside the end bins)
  and `geometry_procedural_assembly` (19 volumes, 9 hit; phantom 27 bins, 234 zero events) runs.
  A 2,000-event assembly run gives identical track-length and per-volume histograms at
  `threads: 1` and `4`. Verification: Release and Debug CTest 52/52 (extended
  `trech_event_moments`), `tests/test_system_observable_cases.py` 15/15 (new per-check
  corruptions), Studio `test_ui_panels.py` 21/21. Residual: no per-volume multiplicity or
  track-length; ~~per-species multiplicity is not binned~~ (landed 2026-11-12 below); per-volume histograms cost 124 integer
  accumulables per scored volume (19 volumes → 2,356 slots, not profiled at large volume counts);
  Studio does not list per-volume histograms; full validation suite and
  `docs/validation_report.*` not refreshed.
- [x] Per-species secondary-multiplicity histograms (2026-11-12). Each species class
  (`gamma`/`electron`/`positron`/`optical_photon`/`neutron`/`other`) gets a
  `system_event_secondaries_<species>_histogram` on the total's integer-then-log2 layout, filled in
  `RecordEventSecondarySpecies` (6 × 44 integer accumulables) and written by one
  `multiplicityHistogramJson` that also produces the unchanged total; all travel in the `run_end`
  provenance copy. A 20,000-event 10 MeV `analytic_pair_production` run gives identical species
  histograms at `threads: 1` and `4` (electrons 0..63 per event, positrons 0/1, gammas 0..7).
  `system_event_histogram_consistent` grades each species with the total's checks (shared
  `_multiplicity_histogram_checks`: scheme, every event once, grid, zero bin = species zero
  fraction, max in the last bin, species mean between the bin-edge sums) plus "every species zero
  bin ≥ the total's zero bin" and the verbatim provenance copy; it passes on fresh Release
  Beer-Lambert (electrons only) and the 10 MeV pair run (gamma, electron, positron). Studio's Run
  summary lists one histogram section per produced species. Verification: Release and Debug CTest
  52/52, `tests/test_system_observable_cases.py` 15/15 (new species corruptions), Studio
  `test_ui_panels.py` 22/22. Residual: ~~no per-volume multiplicity or track length~~ (landed
  2026-11-12 below); no species-resolved track length or deposit; full validation suite and
  `docs/validation_report.*` not refreshed.
- [x] Per-volume step length and created secondaries (2026-11-12). Attribution follows the deposit:
  a step's length counts in its pre-step (deepest) volume and a secondary counts in the volume of
  its first step's pre-step point, its creation vertex. Every `scoreEdep` volume gains
  `volume_event_track_length` (power-sum shape + log10 mm histogram) and
  `volume_event_secondaries` (shape, dispersion index + multiplicity histogram), copied into
  `run_end` provenance; `volume_event_edep` is unchanged (400-event assembly rerun reproduces the
  recorded phantom mean and zero count). `geometry_procedural_assembly`, 2,000 events: all 19
  volumes' histograms identical at `threads: 1` and `4`; scored volumes hold 89.2 of 360.4 mm and
  0.814 of 0.899 secondaries per event (the rest is in the world/unscored volumes); e.g. a
  dosimeter cell is crossed without deposit in 0.45 % of events. `system_volume_event_edep_consistent`
  now also grades both blocks per volume (shared log10/multiplicity histogram checks, non-negative
  length, maxima within the event maxima, integer secondaries, "secondaries need steps": the
  secondaries zero fraction ≥ the step-length zero fraction) and their sums against the event
  means; it passes on fresh 400- and 2,000-event Release assembly runs. Studio adds a
  "Per-volume track length and secondaries" Run-summary section. Verification: Release and Debug
  CTest 52/52, `tests/test_system_observable_cases.py` 15/15 (12 new corruptions), Studio
  `test_ui_panels.py` 22/22. Residual: ~~one `std::string` hash lookup per step~~ (pointer cache
  landed 2026-11-12 below); per-volume entries
  are keyed by name, so repeated placements of one name share an entry; secondaries created in
  zero-length steps would break the "need steps" check (none seen); Studio does not list the
  per-volume histograms; full validation suite and `docs/validation_report.*` not refreshed.
- [x] Per-step scored-volume lookup cache and overhead measurement (2026-11-12). `SteppingAction`
  resolves the pre-step volume once per step through `TrechRunAction::VolumeScoreIndex`
  (per-thread `G4VPhysicalVolume*` → index map, filled lazily from the name index, cleared in
  `BeginOfRunAction` since a rebuilt geometry may reuse addresses) and feeds the deposit and step
  tallies by index; the name-based `AddVolume*` overloads remain for other callers. A
  20,000-event `geometry_procedural_assembly` run gives `volume_edep_mev` and all three per-volume
  blocks identical to the name-lookup build. Wall time (Release, interleaved, 3 runs each):
  cached 14.4–15.0 s, name lookup 14.4–15.8 s, and `scoreEdep` disabled on every volume
  14.3–15.0 s (same event track-length histogram, so identical transport): the whole per-volume
  scoring costs less than the ~0.7 s run-to-run noise here, and the cache brought no measurable
  wall-time change. Verification: Release and Debug CTest 52/52. Residual: not profiled with
  many scored volumes or optical-photon-heavy runs (where steps dominate); no CTest exercises the
  cache directly (it needs a Geant4 geometry).
- [x] Species-resolved created secondaries per volume (2026-11-12). Each
  `volume_event_secondaries.<name>` entry gains `species` (gamma/electron/positron/optical_photon/
  neutron/other: mean, stddev, stderr, max, zero fraction, dispersion index), filled from the
  secondary's first step in `AddVolumeStep(index, length, createdSpecies)` (6 × 7 power-sum
  accumulables per volume, no per-species histograms). All earlier per-volume fields are unchanged
  against the previous binary. `geometry_procedural_assembly` 2,000 events: species means sum to
  each volume's total, identical at `threads: 1` and `4`; scored volumes hold 0.787 of 0.871
  electrons and 0.026 of 0.0265 gammas per event. `system_volume_event_edep_consistent` adds
  `species_present`, `species_sum_to_total`, `species_count_valued`, `species_within_volume`
  (species max ≤ volume max, species zero fraction ≥ volume zero fraction) and globally
  `species_volumes_within_total`; passes on fresh 400- and 2,000-event (1 and 4 threads) Release
  runs. Studio's per-volume row appends the produced species' means. Verification: Release and
  Debug CTest 52/52, `tests/test_system_observable_cases.py` 15/15 (5 new corruptions), Studio
  `test_ui_panels.py` 22/22. Residual: ~~no species-resolved per-volume track length or
  deposit~~ (landed 2026-11-14 below); no per-species per-volume histograms.
- [x] Per-volume deposit and step length by stepping-particle class (2026-11-14). Every
  `volume_event_edep.<name>` and `volume_event_track_length.<name>` entry gains `species`
  (the six `SecondarySpecies.hpp` classes applied to the particle taking the step, primaries
  included: mean, stddev, stderr, max, zero fraction; 2 × 6 × 7 power-sum accumulables per
  volume, no per-class histograms). All earlier score fields are identical to the previous
  binary on the 400-event `geometry_procedural_assembly` run. Phantom: electrons deposit 0.28464
  of 0.28465 MeV/event, gammas 6.9e-06 (below-cut binding energies); gammas take 82.75 of
  83.87 mm/event of step length. 2,000 events at `threads: 1` vs `4`: identical per-class zero
  fractions and maxima, means within 1.5e-15 relative; scored deposit per event 0.3407 electron,
  0.0036 gamma, 0.00014 positron MeV. `system_volume_event_edep_consistent` adds
  `edep_species_*` / `track_length_species_*` (present, sum to the volume mean, non-negative,
  within the volume's max and zero fraction) and `edep_species_need_steps`; passes on fresh
  400- and 2,000-event (1 and 4 threads) Release runs and fails as missing on pre-change outputs.
  Studio appends the split to both per-volume rows. Verification: `tests/test_system_observable_cases.py`
  15/15 (8 new corruptions), Studio `test_ui_panels.py` 24/24; CTest recorded in the commit.
  Residual: the classes are the secondary-reporting bins, so protons/alphas/ions share `other`
  (a heavy-charged-particle beam would need a finer class set); no species-resolved deposit or
  track length at the system level (only scored volumes); no per-class histograms; the full
  validation suite and `docs/validation_report.*` were not refreshed.
- [x] Full validation suite refreshed (2026-11-12, Release, at `917adc2`): 61 cases, 57 pass,
  4 info, 0 fail/skip; every analytic and `system_*` case above passes there, so the "suite not
  rerun / report not refreshed" residuals of the earlier entries in this file are closed for that
  checkout (details in the [validation history](../../tooling/validation/history/ROADMAP.md)).
- [x] Opt-in refusal on geometry substitutions and overlaps (2026-11-12). New
  `geometry.refuseOn` (`"any"`, one kind or an array of `material_fallback` / `parent_fallback` /
  `volume_skipped` / `overlap`; canonical order, serialized only when non-empty so existing hashes
  are unchanged; naming `overlap` with `overlapCheck` off is a parse error) is checked right after
  Geant4 construction. On a match the engine writes one `geometry_refused` provenance record
  (`geometry_resolution`, `geometry_overlap_check`, new `geometry_refusal {schema, refuse_on,
  refused_count}`), runs no events, writes no scores and exits 1 with one line per refused issue;
  the lab runner keeps refusing later batches on that kernel. The `TRECH_FLOW` `geometry` preset
  mirrors the parser and flags the overlap/check-off conflict; Studio completion lists the key and
  Run summary shows a "Geometry refusal" section. Spot runs (Release, 100 keV gamma, a 5 mm sibling
  overlap plus an unknown material): no `refuseOn` runs as before (20 events, both issues reported);
  `["overlap"]` refuses 1 issue, `"any"` refuses 2, a 4-thread run refuses identically, and
  `["parent_fallback","volume_skipped"]` on the same geometry runs normally. Verification: Release
  and Debug CTest 52/52 (extended `trech_geometry_resolution`: parsing, round-trip, rejection,
  matching, message, provenance block; extended `trech_js_runtime` preset checks), Studio pytest
  295/295. Residual: ~~no scenario opts in yet and no validation case exercises a refusal~~
  (`geometry_refusal_guard` + `geometry_refusal_guard_refuses_defects`, 2026-11-14 below); the lab
  refusal path has no automated test (needs a Geant4 kernel); a refused run's provenance carries
  zeroed hook/stratify counters and `hooks_enabled` is "any hook registered", not RunAction's
  recognised-hook test.
- [x] Refusal exercised end to end by a scenario and a validation case (2026-11-14). New bundle
  [`geometry_refusal_guard`](../../../examples/scenarios/geometry_refusal_guard/geometry_refusal_guard.js)
  opts into `geometry.refuseOn: "any"` (60 mm water target, polystyrene dosimeter, 662 keV gamma,
  200 events, no hooks). Its default geometry passes the guard (overlap check clean over 1 pair,
  no issues, 200 events scored); `--param inject_defects=true` adds a probe box 5 mm into the
  target and a `G4_UNOBTAINIUM` shield, and the engine refuses it: one `geometry_refused` record,
  `refused_count` 2 (`material_fallback` on the shield, `overlaps_sibling` target/probe, depth
  5.0 mm), no scores, exit 1. New suite case `geometry_refusal_guard_refuses_defects` grades both
  runs (the suite records the refused run's exit status in `suite_exit_status.txt` instead of
  aborting under `set -e`); it passes on fresh Release runs and the suite snippet runs under
  `set -euo pipefail`. Writing the example surfaced an authoring trap the guard caught on its
  first run: an engine box with a scalar `sizeMm` is `invalid_shape` (only `TRECH_GEOMETRY`
  normalizes scalars), so the target was never built. Verification: Release CTest (incl.
  `trech_scenario_purity_report` after regeneration), `tests/test_geometry_refusal_case.py` 4/4
  (17 corruptions), flow-preset audit pass, declarative contract 5/5 on the clean run.
  Residual: the lab refusal path still has no automated test; the full validation suite and
  `docs/validation_report.*` were not refreshed, so the committed report has no row for the new
  case; no Studio preview media exist for the new bundle. (Correction: the original entry said
  the `TRECH_FLOW` `geometry` preset missed a scalar box `sizeMm`; it already flagged it, the
  example simply did not call `validate()`. See the preset alignment entry below.)
- [x] `geometry` preset aligned with the engine's box parsing (2026-11-14). Like
  `shapeFromJson`, the preset now tries `halfSizeMm` when `sizeMm` gives no three positive
  extents and treats a shape without `type` as a box; before, both were flagged although the
  engine builds them. A scalar `sizeMm` is still flagged, now with the hint that only
  `TRECH_GEOMETRY.volume` expands single numbers and the engine would skip the volume as
  `invalid_shape`. Checked against construction on one config: the scalar box is the only issue
  in the preset and the only `volume_skipped` in `geometry_resolution`, while the half-size and
  untyped boxes are built. Verification: Release and Debug CTest 52/52 (extended
  `trech_js_runtime`), `scripts/audit_flow_presets.py --all` 69/69 pass,
  `tests/test_flow_preset_audit.py` 2/2. Residual: ~~a non-numeric `sizeMm` entry still makes the
  C++ parser throw rather than skip~~ (now a named parse error, entry below); the preset reports
  it as a plain dimension error.
- [x] Whole-event deposit and step length by stepping-particle class (2026-11-14).
  `system_event_edep_species` and `system_event_track_length_species` (compact per-class summary,
  also in `run_end` provenance) close the "no system-level split" residual of the per-volume entry
  above. The stepping particle is now classified once per step and shared with the per-volume
  split and the created-secondary class (same classifier, so those values are unchanged).
  Against the previous binary on the 400-event assembly run, every other score field and the
  config hash are identical. The classes sum to the event means on every run checked. Beer-Lambert
  100 keV, 20,000 events: electrons 0.012545 of 0.012557 MeV/event, gammas 1.18e-05 (sub-cut
  binding energies), gammas take 190.35 of 190.37 mm/event. 10 MeV pair, 20,000 events:
  electrons 2.258, positrons 0.316 MeV/event. At `threads: 1` vs `4` the zero fractions and
  maxima are identical and the means agree within 7.5e-15. On all three runs a non-primary
  class steps in exactly the events that created one of it (its step-length zero fraction
  equals `system_event_secondaries_<class>_zero_fraction`). `system_event_multiplicity_consistent`
  grades the split (9 new checks, see the validation handbook) and passes on the fresh
  Beer-Lambert run; the same checks pass on the pair runs and the assembly. Studio adds one row
  to each event section. Verification: Release and Debug CTest 52/52,
  `tests/test_system_observable_cases.py` 16/16 (9 new corruptions + missing split), Studio
  pytest 295/295. Residual: protons/alphas/ions still share `other`; no per-class histograms;
  `primary_class_steps_every_event` is graded only for the gamma-beam suite run; full validation
  suite and `docs/validation_report.*` not refreshed.
- [x] Wrong-typed geometry volume fields are named parse errors (2026-11-14). `shapeFromJson`
  and `placementFromJson` read through geometry-local helpers, so a string, boolean or null where
  a number (or a string `type`/`parent`) goes throws
  `geometry.volumes[i] ('name').<field> must be a number|string` instead of a bare
  `json.exception.type_error` with no location. A boolean is no longer silently read as 0/1.
  Every accepted form parses as before (CTest `trech_geometry_resolution`: arrays, `{x,y,z}`, the
  `halfSizeMm` fallback, radius/length aliases, placement vectors; six named rejections). The
  assembly config hash is unchanged, and an inspect sweep of all 69 scenarios (114 volumes) found
  no wrong-typed geometry field. Residual: beam and other non-geometry vectors keep the old
  `vector3FromJson` behaviour; other wrong-typed volume fields (`name`, `material`, `scoreEdep`)
  keep the library message, now behind the volume location.
