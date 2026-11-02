# Optics and nondegenerate transport — roadmap

[Root principles](../../../../AGENTS.md) · [Root roadmap](../../../../ROADMAP.md) · [Parent](../ROADMAP.md) · [Handbook](AGENTS.md)

Maintain work in its owning branch. Dated results apply to the recorded checkout; they do not validate subsequent changes.

## Anti-degeneration (standing objective — keep working on this every iteration)

This is a **primary, never-"done" goal**: continuously reduce the ways a TRECH
run collapses into a degenerate, low-information result, and continuously raise
the realism of its Geant4 sampling, training, and inference. Treat the metrics
below as regression signals — re-measure them whenever physics/optics/ML
changes, and never let them slide back toward degeneracy.

Two distinct degeneration failure modes, tracked separately:

1. **Simulation-sampling degeneration** — every primary identical, so a run of N
   events carries the information of 1 (the glass-of-water baseline emitted 4000
   byte-identical straight photons: 1 distinct exit point, 0° angle spread, 0 nm
   wavelength spread). *Lever: Geant4 simulation variety.*
2. **Learned/derived-physics degeneration** — the engine's optical/material
   constants collapse to trivial values (visible-band `n≈1.0`, infinite
   absorption/scatter lengths) because the derivation/training has too little
   signal, so transport produces near-straight, colourless tracks. *Levers:
   training and inference.*

### Workstreams (rotate through these; each iteration should push at least one)

- **Geant4 simulation variety**
  - [landed] Beam source variety: `beam.originMm` + `beam.spread`
    (`spotRadiusMm`, `divergenceDeg`, `energySpreadFractional`) sample primaries
    over a disk / divergence cone / energy band from Geant4's seeded engine
    (reproducible scores; see `examples/scenarios/glass_of_water_varied/glass_of_water_varied.js`).
  - [landed] Optical-photon polarization sampling: `beam.polarization`
    (`""`/`unpolarized` → a random transverse linear state per event drawn from
    the seeded engine; `linear` + `polarizationAngleDeg` → fixed; `none` →
    legacy). The default **kills the `ZeroPolarization` fallback** on every
    optical photon while staying reproducible. Verified physical, not a no-op: a
    *fixed* s-pol vs p-pol run reflects ~2.2× differently at the 30° air→glass
    face (classical Fresnel R_s/R_p ≈ 2.36), and the unpolarized ensemble
    averages back to the unpolarized-Fresnel reference (aggregate inverse-Fresnel
    n unchanged). Conditional serialization keeps existing config hashes;
    round-trip covered in `tests/test_config_roundtrip.cpp`.
  - [landed] Emission spectra: `beam.spectrum` is a weighted line list
    (`{energyMeV|energyEv|wavelengthNm, weight}`); each event samples one line
    by weight from the seeded engine (binary search over a cumulative table),
    then `energySpreadFractional` still broadens it. JS helper `spectra`
    generates the table (`blackbody(T)` Planck-weighted, `whiteVisible()` flat,
    `lines(list)` explicit) so the engine stays physics-agnostic. Demo
    `examples/scenarios/glass_of_water_spectral/glass_of_water_spectral.js` fires a 5778 K sunlight
    spectrum through the cup: wavelength stddev 22.9 nm → **102 nm** (full
    visible band), and the derived `n(λ)` gives real normal dispersion (violet
    refracts more: glass Δn≈+0.0063, water Δn≈+0.0047 across 387–775 nm — right
    sign/order, ~2–3× under handbook, the residual the surrogate tracks).
  - [landed 2026-06-11] Beam-profile presets in helpers:
    `helpers.beamProfiles.spread(name, overrides)` bundles named source
    varieties for `beam.spread` (`pencil` — the degenerate baseline, `laser`,
    `ledLamp`, `flashlight`, `sunbeam` with the 0.27° solar half-angle; pair
    with `spectra.*` for the energy axis). `glass_of_water_varied.js` now uses
    the `ledLamp` preset, which matches its historical hand-rolled values
    exactly — verified hash-preserving (canonical beam JSON byte-identical).
  - Next: variance-reduction-aware variety so spread improves statistics
    without exploding event counts.
- **Training** (feed the surrogate real signal)
  - [landed] f-sum-rule valence oscillator in `MolecularOptics.cpp` fixed the
    `n≈1` root cause physics-side (recovery ~1% → ~100% for water/glass; root
    cause + model in `docs/viz_refraction.md`). KK-floor lowering was tried and
    *rejected* (sub-100 eV Geant4 photoabsorption is 1/E^3.5 garbage).
  - [landed] Curated material→optical dataset: `optics_training_panel.js`
    derives optics for 14 materials; the engine now emits
    `element_mass_fractions` per material so training needs no NIST lookup
    table. Handbook anchors in `data/optics_handbook_anchors.json` (targets
    only, never transport). Trainer `--anchors` learns measured n.
  - Next: a microscale visible-band Geant4 sub-simulation track to *measure*
    low-energy cross sections (close the residual without handbook anchors).
  - Next: CI retrain step when the extractor/dataset changes (ties into "Torch
    surrogate adoption" in `In progress`).
- **Inference** (make predictions non-trivial and honest)
  - [landed] Hold-out validation `scripts/validate_optics_surrogate.py`:
    leave-one-out composition→handbook-n recovers materially more refraction
    than the extractor (mean |Δn| 0.141 → 0.084) — the promotion signal. Honest
    about the air OOD failure. Report committed under `docs/`.
  - [landed] Wired the validated anchor-trained surrogate into transport
    **without LibTorch**: since the validated model is a ridge regression (a
    standardised linear `n = bias + Σ wᵢ(xᵢ-meanᵢ)/stdᵢ`), `OpticsSurrogate`
    grew a ridge `.json` backend alongside the TorchScript one.
    `scripts/validate_optics_surrogate.py --export` writes
    `data/optics_surrogate_ridge.json`; set `optics.derive.surrogateModelPath`
    to it and the engine shifts the derived dispersion curve to the surrogate's
    level in transport (RINDEX). Cross-checked bit-faithful C++↔Python (max
    |Δn|=5.6e-8 across the 14-material panel); e.g. NaI, where the f-sum
    extractor fails (n≈1.33), is corrected to ≈1.77 (handbook 1.775). Opt-in,
    off by default; headline physics demos never set it.
  - Separate predictable from exceptional events so only outliers are
    re-simulated (north-star item) — a degeneracy reducer for compute, not just
    output.

### Degeneration metrics to watch (regression signals)

Measure with `scripts/degeneration_metrics.py RUN_DIR` (or
`--baseline BASE RUN` to diff two runs); it reports both failure modes from a
run's `trech_viz_trajectories.jsonl` (+ `trech_viz_scene.json` for optics).

- Sampling diversity per run: count of **distinct primary exit points**,
  **incidence-angle stddev**, **wavelength stddev**. Baseline degenerate run =
  1 / 0° / 0 nm; `glass_of_water_varied` @2000 ev = ~1950 / 0.75° / 22.9 nm.
- Optics realism: **fraction of handbook refraction recovered**
  `(n_derived-1)/(n_handbook-1)` per material. **Now ~99% (water) / ~103%
  (glass) / ~131% (air)** after the f-sum-rule valence oscillator landed (was
  ~1%); the glass-of-water demo rays now coincide. Remaining work is the
  *material-specific* residual on a broader panel (polymers under-, fluorides
  over-recover) — tracked by `scripts/validate_optics_surrogate.py`.
- [landed] Added as explicit validation cases so `docs/validation_report.md`
  traces the trend: `sampling_diversity_non_degenerate` (category
  `degeneration`) runs `glass_of_water_varied` and asserts >1 distinct exit
  point / incidence-angle stddev >0 / wavelength stddev >0 (vs the degenerate
  baseline 1 / 0° / 0 nm); the optics-recovery side is tracked by the
  `optics_n_*` cases. The diversity metric uses the first-segment displacement
  (robust), matching `scripts/degeneration_metrics.py`.

## Photon transport milestones (optical physics plan)

- Phase 1: add `optics.enable` config flag and wire Geant4 optical physics when enabled.
- Phase 2: map water optical properties (absorption, scattering, refraction) into materials.
- Phase 3: add photon-focused scoring summaries and validation runs.
- Phase 4: support spectral optics tables (energy/wavelength dependent properties) for color response.
- Phase 5: derive material optical constants statistically from Geant4 atomic cross sections (photoelectric + Compton + Rayleigh) and Kramers-Kronig dispersion — no hardcoded n at run time. See `docs/viz_refraction.md`.
- Phase 6: 3D visualization pipeline: sampled photon trajectory capture (`trech_viz_trajectories.jsonl`) + scene manifest (`trech_viz_scene.json`) + accessible Python viewer in `tools/viz/`. Materials forced as visualization-only on tagged volumes (`viz_emitter`, `viz_forced_white`).
