# Validation Summary

Last updated: 2026-07-25T16:44:20Z

Source files:
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

- Scenario: `examples/experiments/viz_refraction_demo.js` (200 events).
- Recorder: 192 sampled trajectories; Studio playback used 686 rendered segments after its
  deterministic trajectory budget, labelled water 214 / glass 247 / air 225.
- Medium-label coverage: 100%; interaction-label coverage: 100%.
- Interactions in the rendered sample: 494 optical boundaries + 192 world boundaries; **zero
  segments were falsely classified as scattering**. Air remains visible with the documented
  0.58× width / 0.72× opacity representation style.
- Headless Studio capture succeeded through the real wgpu path at 960×720 output with 2×
  supersampling; the JSON sidecar records simulation and representation precision separately.

## Water + n-pentane beaker probe

- Scenario: `examples/experiments/beaker_water_n_pentane.js` (30 °C; 60 Geant4-driven frames
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
