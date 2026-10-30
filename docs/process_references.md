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
and position, opacity and isovalue ratio. Declarations enter `hooks.inputs.display`.

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
modelled. External accuracy anchors, mesh/time convergence and a trained aerodynamic lift remain open.

## Validation and next work

`test_process_references.cpp` exercises the inventory fixture and both 2D/3D solvers through the actual QuickJS host: inventory,
growth controls, uniform flow preservation, positive state, integrated flux balance, exact
replay and inlet-speed sensitivity. `validate_process_references.py` runs seven Geant4 fixtures,
checks zero inference/dropped emits, and compares repeated scores/emits/viz-scene bytes.

Quantitative phase-change/aerodynamic validation remains open: independent experimental or
trusted solver anchors, uncertainty, resolution/time convergence, held-out compositions,
geometries and histories. Train future scale-tagged models from particle-derived features plus
properly labelled response data, evaluate on independent runs, and grade the gap before exposing
a predictive path. These illustrative comparisons are not synthetic Geant4 truth. The residuals
are registered in `tools/validation/js_law_audit.json` and both roadmaps.
