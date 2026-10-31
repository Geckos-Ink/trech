# Crystallization and aerodynamics: initial comparison references

These scenarios begin the work requested in [AUTHOR_NOTES.md](AUTHOR_NOTES.md). They are
**independent comparisons**, not Geant4-trained higher-scale predictions. Their tests establish
bookkeeping, numerical invariants and replay; they do not establish experimental accuracy.
Geant4 transports real particles through separate material probes and records its own tallies.
Neither comparison solver uses those tallies to manufacture a claim of learned physics.

```sh
build/rel/trech run examples/scenarios/nacl_dehydration_reference/nacl_dehydration_reference.js --output build/nacl
build/rel/trech run examples/scenarios/aerodynamics_reference/aerodynamics_reference.js --output build/aerodynamics
python3 scripts/validate_process_references.py --trech build/rel/trech
python3 scripts/validate_euler3d.py --trech build/rel/trech
```

The fixtures run serially and record their assumptions in `hooks.inputs`. They remain
independent references. Geant4 material probes do not calibrate their response laws.

## NaCl: retire inventory geometry; consume measured interfaces

The old separated trays and connected parcel cluster are retired from active playback and the
README gallery. Inventory diagnostics still test Na/Cl/solvent bookkeeping, but emit no spatial
material frame. `microscope_interface_status.available:false` explains missing data. Media drivers
skip animation rather than capture those inventories or substitute Geant4 probe geometry.
Historical binary captures remain historical; they are no longer promoted as growth.

The visual target is [Ihor Panas’s light micrograph](https://commons.wikimedia.org/wiki/File:Sodium_chloride_crystals,_light_microscopy.jpg)
(CC BY-SA 4.0, June 2017). It is an appearance reference; the source supplies no calibrated
specimen length, 3D reconstruction, time sequence or measured growth rate. No artificial 3D
geometry or time evolution is inferred from it.

Supply `--param 'interface_file="path/to/recording.json"'` to display recorded interfaces.
C++ `TRECH_INTERFACE_SEQUENCE` inspects bounded `trech_interface_sequence_v1` JSON:

- `source`: `kind:"independent_measurement"`, citation, reconstruction method and license.
- `calibration`: `length_unit:"um"`, nonnegative `spatial_uncertainty_um` and `time_uncertainty_s`.
- `validation`: documented method/reference and a nonempty finite numeric `metrics` map.
- `frames`: strictly increasing, nonnegative `time_s`, finite 3D `vertices`, indexed nondegenerate
  `triangles`. At most 500 frames, 200000 total vertices, 400000 total triangles, 2 MiB per frame
  and 16 MiB for the entire recording.

Missing/malformed data fails authoring. The inspected detached recording enters config/hash
under `hooks.inputs.interface_sequence`; its exact triangles become native-um `material_frame`
geometry on the measured clock. Studio computes display normals only, holds frames without
interpolation and reports the independent source. Extra transport events create no extra
measurements. A single supplied frame stays static. `inspection.format_validated:true` explicitly
coexists with `physical_accuracy_verified:false`: declarations and format checks cannot prove
experimental accuracy. Source/reconstruction review remains necessary. No calibrated NaCl
interface sequence is bundled yet. Synthetic test triangles are never published as microscopy.

## Three-dimensional compressible airflow comparison

`trech_euler3d_reference.js` evolves five conservative cell variables (density, x/y/z momentum,
total energy), using first-order Rusanov flux on **all three** Cartesian face directions and a
3D spherical stair-step obstacle. Pressure, temperature and all velocity components vary in the
third dimension; no slice is extruded. A CFL-limited step uses the sum of the three directional
wave speeds. Face contributions accumulate before state commit. Nonpositive density/pressure
stops the comparison without clipping. Reservoir faces supply the inlet; the x outflow is
zero-gradient. Reports carry physical-volume integrals and integrated boundary/wall exchange
for mass, three momenta and total energy, with explicit conservation residuals.

The retained `trech_euler_reference.js` is the historical 2D comparison. Old screenshots/GIFs
keep their original identities and are not relabelled as 3D runs. The current scenario emits
x/y/z SI cells plus a regular scalar grid on every held frame. JS typed Display options author
camera azimuth/elevation, temperature/pressure/density, volume/slice/surface mode, section normal
and position, opacity, isovalue ratio and perspective/orthographic projection. Declarations enter
`hooks.inputs.display`. Orthographic projection shares parallel volume/section rays and
sprite/ribbon/surface view directions in the live and capture renderer. It does not change data.
`cfl` (0.01–0.3) refines the numerical timestep. Positive `duration_s` advances each output
interval to its exact physical time; zero retains `substeps` CFL steps per recorded interval.
Use the duration control when comparing refinements; equal step counts do not imply equal time.

Studio validates `trech_scalar_grid_v1`, retains numeric units, excludes obstacle voxels with an
explicit active mask, and draws linear scalar gradients through its volume shader. Scalar
textures use maximum-scaled float16, linear display filtering and 128 ray samples; original CPU
values remain unchanged. Axis-aligned slices and masked marching-tetrahedra surfaces are
representations. Cubes touching excluded cells do not generate false obstacle isosurfaces.
Lighting, grey obstacle glyphs, transfer ranges, opacity and camera are display choices.
Classic media capture delegates this field to Studio instead of silently omitting the volume.

The ideal-gas closure (`gamma=1.4`, `R=287.05 J/(kg K)`) remains an explicitly authored
comparison, not particle-derived inference. NASA documents the independent
[Euler equations](https://www1.grc.nasa.gov/beginners-guide-to-aeronautics/euler-equations-2/) and
[ideal-gas closure](https://www1.grc.nasa.gov/beginners-guide-to-aeronautics/equation-of-state/).
No viscosity, turbulence, boundary layers, solid thermal coupling, deformation or fracture is
modelled. Independent obstacle accuracy anchors, shock/acoustic/wall and longer-time convergence,
and a trained aerodynamic lift remain open.

## Exact three-dimensional transport verification

`tests/fixtures/js/euler3d_accuracy.js` contains independent closed-form periodic solutions,
separate from the solver: an oblique density sine, a product of three density sines, and an
oblique shear wave. They vary along x, y and z and advect with velocity `(0.7,-0.4,0.3)`.
The shear vector `(0.15,-0.1,-0.05)` is perpendicular to wave vector `(1,1,1)`; density and
pressure are constant in its exact continuum solution. Substitution into the independent
[Euler equations](https://www1.grc.nasa.gov/beginners-guide-to-aeronautics/euler-equations-2/)
reduces these modes to translation. These are mathematical verification anchors, not measured
airflow or Geant4 predictions.

All five conservative variables use exact voxel averages. Sine integrals include the product
of `sinc(pi/n)` factors; shear energy also integrates its squared sine term, rather than
squaring the mean velocity. The same conservative averages initialize the solver. The unit
periodic cube has no obstacle or external boundary flux. Each step evaluates each periodic
seam once, and density/pressure remain positive without clipping. Grid studies use 6/12/24
cells per side at CFL 0.3 and **t=0.04 s**. The chosen horizon keeps the coarse grid out of
longer-time diffusion saturation. This does not verify long-time accuracy.

Generic C++ `scalarFieldError` / `TRECH_FIELD_ERROR` measures co-located, volume-normalized
L1/L2/Linf and signed bias in the supplied units, with no interpolation. Every conserved
component's norms and integrated conservation residuals enter the report. The convergence gate
uses density for the entropy modes and x momentum for shear; it requires observed spatial order
between 0.5 and 1.5. Fixed-grid time studies use n=12 and CFL 0.3/0.15/0.075 against a same-grid
CFL 0.009375 numerical reference, requiring observed order between 0.8 and 1.5. These temporal
differences isolate timestep sensitivity at fixed spatial discretization; they do not estimate
continuum accuracy or remove spatial error. The reporting approach follows NASA's distinction
between [verification](https://www.grc.nasa.gov/www/wind/valid/tutorial/verassess.html) and
[grid convergence](https://www.grc.nasa.gov/www/wind/valid/tutorial/spatconv.html).

| Exact mode | Observed spatial orders | Observed temporal orders |
| --- | --- | --- |
| Oblique entropy | 0.677, 0.852 | 1.026, 1.107 |
| Triaxial entropy | 0.774, 0.871 | 1.033, 1.106 |
| Oblique shear | 0.679, 0.857 | 1.058, 1.096 |

`test_euler3d_accuracy.cpp` runs the fixture through the actual QuickJS/C++ host. The validation
script additionally runs it twice through the ordinary Geant4 CLI and requires byte-identical
scores/emits, zero inference and zero dropped records. It records obstacle diagnostics at
grid_x 20/30/40 and n=30 CFL 0.3/0.15/0.075, all at 0.0001 s. These grid sizes preserve the
physical domain and nominal sphere radius, but their stair-step wall masks still differ.
Unanchored obstacle temperature ranges/integrals are disclosed diagnostics, not an accuracy
or convergence claim. The fresh `build/euler3d_validation/validation_*/report.json` retains
the complete norms, orders, controls, source hashes and binary SHA-256; logs and emitted records
remain beside it. Reports explicitly deny physical-accuracy certification and use as particle
training data. No experimental uncertainty, shock or acoustic benchmark is supplied here.

## Validation and next work

`test_process_references.cpp` exercises the inventory fixture and both 2D/3D solvers through the actual QuickJS host: inventory,
growth controls, uniform flow preservation, positive state, integrated flux balance, exact
replay, invalid-input rollback, fixed-time advance and inlet-speed sensitivity.
`validate_process_references.py` runs seven Geant4 fixtures,
checks zero inference/dropped emits, and compares repeated scores/emits/viz-scene bytes.

Quantitative phase-change/aerodynamic validation remains open: independent experimental or
trusted solver anchors, uncertainty, resolution/time convergence, held-out compositions,
geometries and histories beyond these smooth periodic modes. Train future scale-tagged models from particle-derived features plus
properly labelled response data, evaluate on independent runs, and grade the gap before exposing
a predictive path. These illustrative comparisons are not synthetic Geant4 truth. The residuals
are registered in `tools/validation/js_law_audit.json` and both roadmaps.
