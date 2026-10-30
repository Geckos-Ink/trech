# Validation Summary

Last updated: 2026-10-19 (incremental validation)

Original optics probe source files:
- scores: /tmp/trech_optics_precision/trech_scores.jsonl
- provenance: /tmp/trech_optics_precision/trech_provenance.jsonl

Run summary:
- phase: run_end
- physics_list: QBBC+Optical
- geant4_version: Geant4 version Name: geant4-11-04-patch-02 [MT]   (12-June-2026)
- n_events: 200
- seed: 20260522
- optics_enabled: True
- total_edep_mev: 0.0
- optical_photon_tracks: 200
- optical_photon_steps: 720
- optical_photon_track_length_mm: 28807.50863415675
- config_hash: 4df16c4a4698ff08
- output_dir: /tmp/trech_optics_precision
- macro_path: 
- rng_engine: MixMaxRng

Notes:
- Generated from the most recent run_end records.

## Refraction / Studio precision probe

- Scenario: `examples/scenarios/viz_refraction_demo/viz_refraction_demo.js` (200 events).
- Recorder: 192 sampled trajectories; Studio playback used 686 rendered segments after its
  deterministic trajectory budget, labelled water 214 / glass 247 / air 225.
- Medium-label coverage: 100%; interaction-label coverage: 100%.
- Interactions in the rendered sample: 494 optical boundaries + 192 world boundaries; **zero
  segments were falsely classified as scattering**. Air remains visible with the documented
  0.58× width / 0.72× opacity representation style.
- Headless Studio capture succeeded through the real wgpu path at 960×720 output with 2×
  supersampling; the JSON sidecar records simulation and representation precision separately.

## Water + n-pentane beaker probe

- Scenario: `examples/scenarios/beaker_water_n_pentane/beaker_water_n_pentane.js` (30 °C; 60 Geant4-driven frames
  after the initial empty-beaker frame).
- Cascade: 2/2 stages, no missing inputs; Geant4 densities water 1.0 / n-pentane 0.6262 g/cm³;
  PubChem payload contains CID + SMILES only.
- Inferred: both liquids colourless, n-pentane upper layer; held-out vapour pressure 87.17 kPa
  vs validation-only NIST 81.98 kPa (6.3%); 60-minute evaporation 13.99% = 4.38 g
  (6.99 mL liquid equivalent), with mass closure and emitted fraction σ=0.08.
- Observer playback: empty → water pour → pentane pour → transient intermix/phase separation →
  a continually renewed rising/drifting/fading plume. Physical time is retained beside the
  scenario-emitted 545× accelerated clock; no fixed vapour targets are replayed.
- Validation report: 45 cases, 41 pass / 0 fail-error / 0 skip / 4 informational; beaker case
  11/11 focused checks.

## Polyurethane engine-side reaction operator

- The promoted-default meso `StateEvolution` model is a portable 27→32→8 MLP (2,216 parameters)
  trained on 115,437 expanded parcel rows and evaluated on 38,565 rows from independent runs;
  its carried worst-output R² is 0.9929.
- The full 620-parcel / 180 s operator-teacher pair passes 8/8 observer gaps and 13/13 trust
  checks: 0.56% expansion gap, at most 1.07 s milestone drift, 1.19 K core-skin drift, and zero
  out-of-domain in 2,812,320 parcel-step inferences.
- The default operator also passes the nominal/zero-gravity foam guard 26/26: 31.1× expansion,
  5.0° vs 2.6° lean, 28.8% vs 11.9% broken bonds, and five parcels reaching the table vs zero.
  The teacher is the retained reduced JS law and the model remains explicitly `measured:false`.

## Constitutive candidate and Studio vectors (2026-10-19)

- Fresh nominal, chemistry-reference and zero-g foam runs retain every prior default result.
  The refreshed 49-case report has 42 pass / 4 info / 3 skip / 0 fail/error; remaining cases reuse
  the preceding pass's cached outputs. The slow bulk-water, D(T) and shaken-glass runs remain skipped.
- Six additional full runs grade the opt-in mechanics operator at nominal gravity, zero-g and
  305 K. Zero-g passes 7/7 gaps; nominal fails height (5.35% vs 5%) and lean (6.07° vs 1.5°),
  and hot fails lean (3.20°). All pairs pass 22/22 trust checks and use zero OOD evaluations.
  `mechanics_source=reference` stays the default. The ≥0.998 held-out R² on independent synthetic
  teacher rows is migration fidelity, not measured foam mechanics; the candidate remains unpromoted.
- CTest 18/18, seven paired-validator unit tests, NumPy/Torch trainer/export tests, Studio playback
  17/17, precision 3/3 and five GPU animation/capture tests pass. A real MR capture verifies emitted
  vector arrows, with their original magnitude/direction and disclosed display style. Candidate
  promotion artifacts remain under `build/rel/foam_mechanics_candidate/`; default artifacts are
  under `build/rel/positive_output_validation/`.
