# Validation Summary

Last updated: 2026-07-15T05:23:57Z

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

- Scenario: `examples/experiments/beaker_water_n_pentane.js` (60 one-minute observer ticks).
- Cascade: 2/2 stages, no missing inputs; Geant4 densities water 1.0 / n-pentane 0.6262 g/cm³;
  PubChem payload contains CID + SMILES only.
- Inferred: both liquids colourless, n-pentane upper layer; held-out vapour pressure 61.14 kPa
  vs validation-only 57.3 kPa (6.7%); 60-minute evaporation 7.73% = 2.42 g (3.86 mL liquid
  equivalent), with mass closure and emitted fraction σ=0.08.
- Validation report: 40 cases, 36 pass / 0 fail-error / 0 skip / 4 informational; beaker case
  8/8 checks.
