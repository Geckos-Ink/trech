# Validation Summary

Last updated: 2026-01-17T14:10:00Z

Source files:
- scores: trech_scores.jsonl
- provenance: trech_provenance.jsonl

Run summary:
- phase: run_end
- physics_list: QBBC+Optical
- geant4_version: Geant4 version Name: geant4-11-04 [MT]   (5-December-2025)
- n_events: 100
- seed: 424242
- optics_enabled: True
- total_edep_mev: 20.690004316014548
- optical_photon_tracks: 1254
- optical_photon_steps: 12842
- optical_photon_track_length_mm: 443157.64436723216
- config_hash: df1188206ab7f5ec
- output_dir: .
- macro_path: 
- rng_engine: MixMaxRng

Notes:
- Generated from the most recent run_end records.

## Refraction viz demo (latest smoke run)

Scenario: `examples/experiments/viz_refraction_demo.js`, `--events 60`, `--output build/dev/out_viz_refraction`.

- Optical photons fired through air → glass slab → water bulk → air at 35° incidence (2.25 eV monochromatic).
- `optics.derive.enable: true` ran the `MolecularOpticsExtractor` against air, glass (SiO₂), water. Below `modelValidMinEv = 100 eV` the Livermore atomic photoabsorption tables are treated as unconstrained (cross section 0), so visible-band absorption/scatter lengths come out effectively infinite (1e6 mm cap). The visible refractive index is now the Kramers-Kronig integral over the high-E extinction spectrum **plus an f-sum-rule valence oscillator** that restores the valence-electron oscillator strength the atomic tables miss below ~100 eV (the resonance the truncated KK integral could not see).
- Derived n at the visible band (means): air ≈ 1.00038, water ≈ 1.33075, glass ≈ 1.47217 — at ~handbook (n_water = 1.333, n_glass ≈ 1.46; recovery ≈99% / ≈103%), and ordering physically correct (glass > water > air). This supersedes the v1 KK-only values (air 1.00001 / water 1.00118 / glass 1.00582) that sat far below handbook because the truncated KK integration missed the 5–15 eV molecular electronic resonances; the f-sum valence oscillator closes that gap. See `docs/viz_refraction.md` for the model and the residual.
- Refraction is now at full handbook contrast: trajectory polylines bend at the textbook Snell angles at the air/glass, glass/water, water/glass and glass/world boundaries, sampled by Geant4's `G4OpBoundaryProcess` from the derived `G4MaterialPropertiesTable`.
- Outputs written: `trech_viz_scene.json` (24 KB), `trech_viz_trajectories.jsonl` (60 sampled polylines × 4 segments). `trech_scores.jsonl` now carries `viz_enabled`, `viz_trajectories`, `viz_segments`, `viz_dropped`, `viz_capped`.
- 3D rendering: `tools/viz/` PyVista app (entry point `trech-viz`) consumes the manifest + trajectories.
