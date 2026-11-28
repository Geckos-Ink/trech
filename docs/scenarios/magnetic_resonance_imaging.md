# Magnetic resonance imaging: how the brain image is acquired

[Scenario documentation](README.md) · [Documentation index](../README.md)

The brain phantom ([scenario](../../examples/scenarios/testscenario_magnetic_resonance_brain/testscenario_magnetic_resonance_brain.js),
[driver](../../scripts/run_magnetic_resonance_brain.py)) produces a proton-density MRI of a
procedural head. Each tissue's brightness is the ¹H (proton) number density that Geant4 computes
for that tissue's material. This page explains how the driver turns those densities into k-space
and back into an image, and what the validation checks on the result.

## What comes from where

| Part | Source |
| --- | --- |
| Which tissue sits where | A procedural, BrainWeb-inspired digital phantom (the driver draws it). |
| How bright each tissue is | Geant4: the scenario reports each tissue material's ¹H number density in `material_probes`. |
| How the scanner encodes position | A declared acquisition protocol (`PROTOCOL` in the driver): gradients, timing, a uniform readout decay and receiver noise. |
| How the image is formed | An inverse FFT of the acquired k-space. |

The acquisition and reconstruction are signal processing. They are not engine physics, and
Geant4 does not simulate nuclear spin. The protocol's readout decay is a single apparatus value
for every voxel (field inhomogeneity), so it blurs the image slightly but adds no tissue contrast.
T1/T2 weighting is not implemented.

## Spin-warp acquisition

Since 2026-11-28 the driver acquires k-space the way a 2D Fourier (spin-warp) scanner does.
Before that, it took the FFT of the phantom image, so the "acquisition" could only reproduce
its own grid.

- **The object is finer than the scanner.** The phantom is drawn on a grid twice as fine as the
  240 × 240 image along each axis. Each scanner pixel therefore covers four object cells, and
  edges fall inside pixels as they do in a real head.
- **Readout (x).** While the receiver samples every dwell time Δt (62.5 kHz bandwidth, so
  Δt = 16 µs), a readout gradient Gx is on. A spin at position x accrues phase at the rate
  γ̄·Gx·x, where γ̄ = 42.577 MHz/T is the proton gyromagnetic ratio over 2π.
- **Phase encoding (y).** Before each readout line, a phase-encode gradient Gy is switched on for
  τ = 1 ms. Each line uses the next step of Gy, from −120 to +119 steps.
- **Each sample is an explicit sum over voxels.** For phase step n and sample time t,

  S(n, t) = Σ ρ(x, y) · exp(−2πi γ̄ (Gx·x·t + Gyₙ·y·τ)) · exp(−t / T2*) + noise.

  Here ρ is the proton density relative to CSF, T2* = 40 ms is the uniform readout decay, and the
  receiver noise is fixed-seed complex Gaussian noise at 0.1 % of the largest sample.
- **The gradients set the field of view.** Gx is chosen so one dwell advances k by 1/FOV, which
  gives FOV = 1 / (γ̄·Gx·Δt). For a 180 mm FOV, Gx = 8.16 mT/m. The phase-encode step is
  0.130 mT/m, and the largest phase-encode gradient is 15.7 mT/m.
- **Reconstruction** is an inverse 2D FFT on that nominal grid. Pixel j sits at
  (j − n/2)·FOV/n.
- **The volume (3D)** uses the same readout along x, phase-encodes both y and z, and is
  reconstructed with an inverse 3D FFT on a 112³ grid.

## What the validation checks

The suite case `magnetic_resonance_brain_image` grades the driver's `mr_brain_image` emit. It
checks the tissue contrast (intensity tracks proton density, r ≥ 0.95; CSF brightest; grey matter
brighter than white; skull dark; air below 0.12) and that the reconstruction is faithful to the
object at scanner resolution (r ≥ 0.9). Two checks grade the encoding itself:

- **`geometry_from_gradients`.** The driver measures the head's half-widths where the central row
  and column first rise through half the scalp level. In the reconstruction they must be within
  half a pixel (0.375 mm) of the same measurement on the object. Measured: 71.82 and 88.17 mm
  against 72.00 and 88.13 mm, an error of 0.18 mm.
- **`miscalibration_detected`.** A control acquisition runs with the gradients 3 % weak, while the
  reconstruction still assumes the nominal ones. Weaker gradients reach less k-space per sample,
  so the head reconstructs about 3 % smaller (70.29 and 85.93 mm). That 2.19 mm error must exceed
  the tolerance, which shows the geometry check would catch a scaling mistake.

The emit's `acquisition` block records the protocol, γ̄, the gradients, the readout duration
(3.84 ms), the FOV the gradients imply, the object grid, and every measured half-width.

To run it:

```sh
build/render-venv/bin/python scripts/run_magnetic_resonance_brain.py \
    --binary build/dev/trech --runs-dir build/dev
```

`tests/test_mr_brain_acquisition.py` (CTest `trech_mr_brain_acquisition`, numpy only) checks the
encoding without a Geant4 run. It checks that the gradients give the requested FOV, that a point
source reconstructs on its own pixel in 2D and 3D, and that an object on the scanner grid
acquires exactly its FFT. It also checks that 3 %-weak gradients shrink the head by 3 %.

## Not yet

The README brain GIF and the catalog thumbnail were rendered with the earlier FFT-of-phantom
acquisition; recapturing them is a gated media task. T1/T2-weighted sequences (they need a
Geant4-anchored relaxation proxy), non-Cartesian trajectories and real BrainWeb ingestion are
queued in the [resonance roadmap](../../AGENTS/scenarios/resonance/ROADMAP.md#priority-queue).
