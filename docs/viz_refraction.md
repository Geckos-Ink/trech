# Viz refraction demo — design note

## Goal

Show, in a 3D view, a light beam crossing **air → glass slab → water bulk → air**, with the refraction emerging from TRECH's engine rather than from classical Snell's-law plumbing. The viz layer must be accessible (no commercial ray-tracer dependency) and faithful to the JS → JSON → C++ boundary.

## Non-negotiables

1. The macroscopic optical constants for each material must be **derived from particle-level interactions** that Geant4 already simulates (photoelectric, Compton, Rayleigh atomic cross sections). Hardcoded handbook values (n_water = 1.333, etc.) are reference / validation only — they never feed into transport.
2. The 3D representation is **statistical, not exhaustive**. We don't render 10⁵ photons; we sample a representative subset, exactly the same trick Geant4 uses internally to scale microscopic physics to macroscopic predictions.
3. Materials are declared by **chemical composition** at the JS layer (`materials[].components` with G4-NIST element refs). Forced optical properties at the C++ level are forbidden for physics; *purely visual* forcing (e.g., "the emitter is a white box") is allowed and lives on volume `tags`.

## Pipeline

```
 JS scenario  ─┐                                                  ┌─►  trech_viz_scene.json
               │                                                  │
               ▼                                                  │
        configFromJsonString                                      │
               │                                                  │
               ▼                                                  │
        Geant4 RunManager.Initialize()                            │
               │  (physics list materializes EM atomic data)      │
               ▼                                                  │
   MolecularOpticsExtractor                                       │
        - G4EmCalculator over [E_min .. E_max]                    │
        - μ_abs = σ_PE + σ_Compton,  μ_scat = σ_Rayleigh           │
        - k(E) = μ_abs · λ / (4π)                                  │
        - Kramers-Kronig:  n(E) - 1 = (2/π) P ∫ E' k(E') / (E'² - E²) dE'
        - attach G4MaterialPropertiesTable (RINDEX, ABSLENGTH, RAYLEIGH)
               │                                                  │
               ▼                                                  │
       Geant4 BeamOn — optical photon transport with the derived  │
       (n, μ_abs, μ_scat) tables; refraction is sampled by        │
       G4OpBoundaryProcess at each interface.                     │
               │                                                  │
               ▼                                                  │
       SteppingAction ─► VizRecorder (sampled polylines)          │
       RunAction ─► writes scene + flushes trajectories ──────────┘
                                                                  │
                                                                  ▼
                                                       tools/viz/  (PyVista)
                                                       trech-viz --scene ... --trajectories ...
```

## Derivation provenance

`trech_viz_scene.json` carries the full `derived_optics` block: per-material number density, mean refractive index across the visible band, spectrum samples (E, λ, n, κ, absorption length, scatter length), and any `reference_deltas` against user-supplied handbook values. All of this is also reachable from the `trech_provenance.jsonl` config hash. Reproducibility is end-to-end.

## Honest limitation

Geant4's atomic photoabsorption tables (Livermore/Penelope models) cover X-ray and gamma energies cleanly but thin out below ~100 eV. The visible-band absorption/scatter values you see in the manifest are therefore close to zero (very long lengths), and the visible refractive index is dominated by the Kramers-Kronig integral over the UV/X-ray extinction spectrum. This is intellectually honest: it's the regime where Geant4 has data, and KK is the standard physics tool for getting the dispersion at lower energies. The validation deltas vs handbook values quantify the residual.

The alternative — running a full microscale Geant4 sub-simulation per material to *measure* visible-light cross sections from photon-electron interactions — is a research-grade project and is not attempted in v1.

## Visualization choices

Two volume-tag conventions are visualization-only, never physics:

- `viz_emitter` — render as a white box even if the material would otherwise be transparent.
- `viz_forced_white` — generic forced-color marker for non-physical scene aids.

Anything else gets its tint from `derived_optics.display_rgb` and its opacity from the mean absorption length divided by the volume characteristic size.

## Sampling

`viz.maxTrajectories` caps the number of distinct photon polylines kept. `viz.sampleEveryNth` is a deterministic stride over `(event_id, track_id)` mixed with the run seed, so reruns with the same seed produce the same polyline set. `viz.maxSegmentsPerTrajectory` truncates very long tracks (the `capped` flag in the JSONL record tells the viewer it happened).
