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
        - + f-sum valence oscillator:  χ = (ħω_p)² / (E₀² - E²)     │
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

## Visible-band dispersion: the f-sum-rule valence oscillator

Geant4's atomic photoabsorption tables (Livermore/Penelope models) cover X-ray and gamma energies cleanly but thin out below ~100 eV. The visible-band absorption/scatter values you see in the manifest are therefore close to zero (very long lengths). The problem is the **real part**: the visible refractive index of condensed matter is dominated by valence-electron oscillator strength in the deep UV (~10–25 eV), exactly the band the atomic tables miss. Kramers-Kronig over the truncated (>100 eV) extinction spectrum alone yields **n ≈ 1** for glass and water (~1 % of the real refraction) — and lowering the KK floor does *not* help: below model validity Geant4's photoabsorption is a ~1/E³·⁵ Born extrapolation that blows up to n = 2–3 and renders the media opaque.

We restore the missing dispersion with a single physics-based **Lorentz valence oscillator** added to the KK susceptibility:

```
χ_valence(E) = (ħω_p)² / (E₀² − E²),     n = √(1 + χ_KK + χ_valence)
```

- **Strength** `(ħω_p)²` is fixed by the **f-sum rule** from the *valence* electron density — summed per element via the closed-shell (noble-gas core) rule, exact from the Geant4 material composition. Using *total* electrons over-counts tightly bound core shells (which resonate at keV, not optical energies) and overshoots badly (glass ~169 %); valence counting is the physical choice.
- **Resonance** `E₀` is one global constant (`optics.derive.valenceResonanceEv`, default **22 eV** — the valence-plasmon scale of light-element condensed matter). It is *not* a per-material handbook lookup; that one number recovers ~100 % of water, glass *and* air refraction, which is strong evidence the model captures real physics rather than curve-fitting.

Result (validation_glass_of_water): **n_water ≈ 1.33 (99 %), n_glass ≈ 1.47 (103 %), n_air ≈ 1.0004**, and Geant4's optical transport then refracts at the textbook Snell angles. The full derivation (electron densities, ħω_p, E₀, mean excitation energy) is carried in `derived_optics` for provenance.

## Honest limitation (remaining residual)

A *single* global oscillator energy cannot capture the material-specific dispersion that distinguishes, e.g., water (1.333) from glass (1.46) exactly — that lives in the per-material valence binding (E₀/ħω_p ratio), real condensed-matter detail Geant4 does not carry. The residual is small (glass over-recovers ~3 %, water under ~1 %) and reported honestly via the validation deltas. Closing it is the job of the **surrogate training** track (learn the material-specific correction from the improved extractor output) and, longer term, a microscale visible-band Geant4 sub-simulation to *measure* low-energy cross sections — a research-grade project not attempted in v1.

## Visualization choices

Two volume-tag conventions are visualization-only, never physics:

- `viz_emitter` — render as a white box even if the material would otherwise be transparent.
- `viz_forced_white` — generic forced-color marker for non-physical scene aids.

Anything else gets its tint from `derived_optics.display_rgb` and its opacity from the mean absorption length divided by the volume characteristic size.

## Sampling

`viz.maxTrajectories` caps the number of distinct photon polylines kept. `viz.sampleEveryNth` is a deterministic stride over `(event_id, track_id)` mixed with the run seed, so reruns with the same seed produce the same polyline set. `viz.maxSegmentsPerTrajectory` truncates very long tracks (the `capped` flag in the JSONL record tells the viewer it happened).
