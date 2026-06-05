# Optics Surrogate — Held-Out Validation

- Panel run: `/Users/riccardo/Sources/GitHub/trech/build/dev/out_optics_panel`
- Materials: 14  ·  ridge λ = 1.0

Leave-one-out: each material's handbook n is predicted by a ridge
model trained on the Geant4-derived composition (+density) of every
*other* material. This tests whether a data-driven optical model
generalises the material-specific dispersion the single global
valence-oscillator energy cannot. Handbook n is a validation target
only — the engine's photon transport always uses the derived n.

| Material | handbook n | extractor n | Δ extractor | surrogate n (LOO) | Δ surrogate |
|---|---:|---:|---:|---:|---:|
| air | 1.000 | 1.0004 | +0.0001 | 1.4297 | +0.4294 |
| water | 1.333 | 1.3310 | -0.0020 | 1.3223 | -0.0107 |
| ethanol | 1.361 | 1.2633 | -0.0977 | 1.4556 | +0.0946 |
| glycerol | 1.474 | 1.3805 | -0.0935 | 1.4250 | -0.0490 |
| pmma | 1.491 | 1.3493 | -0.1417 | 1.4778 | -0.0132 |
| polyethylene | 1.510 | 1.3036 | -0.2064 | 1.5051 | -0.0049 |
| polystyrene | 1.590 | 1.3070 | -0.2830 | 1.5145 | -0.0755 |
| pvc | 1.540 | 1.3011 | -0.2389 | 1.4670 | -0.0730 |
| teflon | 1.350 | 1.5431 | +0.1931 | 1.4420 | +0.0920 |
| silica | 1.458 | 1.4238 | -0.0342 | 1.4436 | -0.0144 |
| pyrex | 1.474 | 1.4332 | -0.0408 | 1.4768 | +0.0028 |
| nai | 1.775 | 1.3306 | -0.4444 | 1.5628 | -0.2122 |
| lif | 1.392 | 1.5559 | +0.1639 | 1.3515 | -0.0405 |
| caf2 | 1.434 | 1.4629 | +0.0289 | 1.4970 | +0.0630 |

## Verdict

- Mean |n − handbook|: **extractor 0.1406** vs **held-out surrogate 0.0839**
- The held-out surrogate recovers **materially more** refraction than the physics extractor alone: learning the residual from the Geant4-derived composition generalises to unseen materials. This is the promotion signal the ROADMAP inference workstream asks for.
