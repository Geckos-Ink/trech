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

### Fluids / H₂O — Shipped

Rigid-SPC/E MD reproduces measured structure (O-O g(r) first peak 2.798 Å) and dynamics
(self-diffusion Einstein 2.57 vs Green-Kubo 2.79 ×10⁻⁹ m²/s; D(T) trend). `glass_of_water_shaken`
cascades nano facts → macro PBF fluid params with no hand-typed macro property; `lava_lamp` is a
duration-independent inferred 3D thermofluid (persistent parcels, four separate precision axes).
Honest scope: Geant4 is the per-tick clock; the MD/PBF/parcel solvers are hook-layer physics for
comparison.

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
