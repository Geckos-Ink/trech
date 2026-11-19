# Water and fluid comparisons — context and contracts

[Root principles](../../../AGENTS.md) · [Root roadmap](../../../ROADMAP.md) · [Parent](../AGENTS.md) · [Roadmap](ROADMAP.md)

## Choose a subcategory

| Scope | Context | Work remaining |
| --- | --- | --- |
| Foam mechanics and validation | [AGENTS.md](foams/AGENTS.md) | [ROADMAP.md](foams/ROADMAP.md) |
| Lava lamp thermofluid | [AGENTS.md](lava/AGENTS.md) | [ROADMAP.md](lava/ROADMAP.md) |

Related owners: [Project workflow and shared status](../../project/AGENTS.md) · [Scenario law migration ledger](../migrations/AGENTS.md).

Read the root principles and the parent handbook first; then open only the subcategory relevant to the task. Source paths and shell commands in code spans/blocks are repository-relative unless stated otherwise; Markdown links resolve from this file.

`trech_euler3d_reference.js` now evolves genuine x/y/z momentum and flux in an independent 3D
Euler comparison, not a learned aerodynamic lift; the 2D module and its captures remain historical.
JS-authored scalar grids/camera feed Studio's validated volume/slice/surface representation.
`tests/fixtures/js/euler3d_accuracy.js` verifies exact periodic 3D entropy/shear cell averages
on 6/12/24 grids and fixed-grid CFL refinement at a common time. C++ `scalarFieldError` /
`TRECH_FIELD_ERROR` supplies co-located, volume-normalized L1/L2/Linf/bias diagnostics.
`scripts/validate_euler3d.py` records these studies, exact replay and common-time obstacle
diagnostics with source/binary hashes. These are numerical verification, not obstacle accuracy
or particle training labels. Airflow exposes `cfl` and optional `duration_s` (zero retains step-count
playback). Recorded camera projection supports perspective/orthographic with shared parallel-ray
volume, sprite and surface rendering; oblique sections and streaming remain open.
No cosmetic extrusion or staged ball animation supplies missing physical validation.
Contract: [solution processes](../../../docs/solution_processes.md); remaining physical/spatial work is in the [independent references roadmap](../references/ROADMAP.md).
Continuum fields are declared to the engine (`ctx.evolveField`). Its registered prediction methods
(lattice Boltzmann, a learned operator and any method added later) and their statistical
selection are owned by the [lattice handbook](../../engine/lattice/AGENTS.md).

### Fluids / H₂O — Shipped

Rigid-SPC/E MD reproduces measured structure (O-O g(r) first peak 2.798 Å) and dynamics
(self-diffusion Einstein 2.57 vs Green-Kubo 2.79 ×10⁻⁹ m²/s; D(T) trend). `glass_of_water_shaken`
cascades nano facts → macro PBF fluid params with no hand-typed macro property; `lava_lamp` is a
duration-independent inferred 3D thermofluid (persistent parcels, four separate precision axes).
Honest scope: Geant4 is the per-tick clock; the MD/PBF/parcel solvers are hook-layer physics for
comparison.
`h2o_bulk_freeze_boil` really freezes. It uses a separate core,
[`trech_water_mw.js`](../../../js/trech_water_mw.js): coarse-grained mW water (Molinero & Moore
2009, melting point 274.6 K, so −1 °C is genuinely supercooled). 600 mobile molecules sit on a
fixed ice Ih basal floor (the nucleation template) with a free surface and vacuum above. The
thermostat drives 10 → −1 → 100 °C. Every molecule's phase is detected each frame by CHILL+
(Nguyen & Molinero 2015), never assigned. At −1 °C an ice front grows from the floor (measured
≈ 18 Å/ns over the first 0.5 ns, then it stalls ~1.5 bilayers below the free surface, whose top
layers stay liquid-like). At 10 °C the floor can order at most one contact bilayer (the reference run did within 40 ps; a
separate 300 ps check at 10 °C stayed below it). That is not freezing; verdicts count ice only
beyond 1.5 bilayers. On heating the ice melts and 100 °C is a hot
liquid. No molecule evaporated in the 120 ps hold (real water's kinetic flux would release about 3
from this surface). Nucleation is heterogeneous by construction (ideal template); this is not a
boiling-point measurement. Rigid SPC/E (melting near 215 K) cannot freeze at −1 °C, which is why the
bundle does not reuse `trech_water_md.js`. The GIF's playback clock is time-dilated per stage
(declared on every frame).
Gaps are listed in the [fluids roadmap](ROADMAP.md#water-phase-program-h2o_bulk_freeze_boil).

- **White-noise heterogeneity vanishes when you refine the mesh.** Symptom: a coarse run leans and
  cracks, a finer one is symmetric — the "precision" knob silently changed the physics. Cause:
  per-parcel independent noise averages out over more parcels. Fix: sample imperfection from a
  **spatially correlated field** with a physical correlation length (`makeSmoothField` in
  [`trech_foam_solver.js`](../../../js/trech_foam_solver.js)); real mixing/cell-size
  imperfection comes in patches, and patches survive refinement.
- **Gravity + inertia at a chemical-process timestep destroys a contact solver.** Symptom: a poured
  liquid free-falls a whole parcel diameter per step and the material collapses flat. Cause: a
  minutes-long process needs ~10⁻²·s steps, over which free-fall is ~15 mm. Fix: integrate the
  **overdamped** solution (terminal creep velocity under the material's own drag) for material
  inside the body, and keep ballistic integration only for detached pieces falling through air.

- **MD sampling lessons.** Single-origin MSD is too noisy for per-block D (use multi-time-origin);
  each block must equilibrate longer than water's ~2–3 ps structural relaxation or D is inflated.
