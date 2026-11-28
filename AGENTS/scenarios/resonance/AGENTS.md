# Magnetic resonance and MRI — context and contracts

[Root principles](../../../AGENTS.md) · [Root roadmap](../../../ROADMAP.md) · [Parent](../AGENTS.md) · [Roadmap](ROADMAP.md)

Read the root principles and the parent handbook first; then open only the subcategory relevant to the task. Source paths and shell commands in code spans/blocks are repository-relative unless stated otherwise; Markdown links resolve from this file.

### Magnetic resonance / MRI — Shipped (4 stages)

Stage 1 discovers the Larmor line (γ/2π 42.5768 vs CODATA 42.5775 MHz/T) from Geant4 proton
density; Stage 2 makes the output photons real Geant4 tallies (cortical bone 0.59× water); Stages
3–4 reconstruct a 1D line and a 2D brain image. Geant4 supplies proton density + transport; spin
dynamics/FFT are hook-layer.

Stage 4's driver (`scripts/run_magnetic_resonance_brain.py`) acquires k-space by spin-warp
encoding (2026-11-28): `PROTOCOL` declares the apparatus (bandwidth, phase-encode time, TE, one
uniform readout decay, noise, object oversampling, the control's gradient scale); `acquire` sums
the 2×-oversampled object under Gx and stepped Gy (3D: Gy, Gz) with γ̄ = 42.57747892 MHz/T;
`reconstruct` inverts on `scanner_axis` (pixel j at (j − n/2)·FOV/n). The emit's `acquisition`
block and the `geometry_from_gradients` / `miscalibration_detected` flags grade the encoding;
`tests/test_mr_brain_acquisition.py` checks it without Geant4. User guide:
[docs/scenarios/magnetic_resonance_imaging.md](../../../docs/scenarios/magnetic_resonance_imaging.md).
