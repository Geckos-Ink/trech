# Magnetic resonance and MRI — context and contracts

[Root principles](../../../AGENTS.md) · [Root roadmap](../../../ROADMAP.md) · [Parent](../AGENTS.md) · [Roadmap](ROADMAP.md)

Read the root principles and the parent handbook first; then open only the subcategory relevant to the task. Source paths and shell commands in code spans/blocks are repository-relative unless stated otherwise; Markdown links resolve from this file.

### Magnetic resonance / MRI — Shipped (4 stages)

Stage 1 discovers the Larmor line (γ/2π 42.5768 vs CODATA 42.5775 MHz/T) from Geant4 proton
density; Stage 2 makes the output photons real Geant4 tallies (cortical bone 0.59× water); Stages
3–4 reconstruct a 1D line and a 2D brain image. Geant4 supplies proton density + transport; spin
dynamics/FFT are hook-layer.
