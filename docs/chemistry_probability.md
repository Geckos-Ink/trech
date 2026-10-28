# Multi-molecule scenarios and probability views

Studio's Chemistry workspace can now describe multiple atoms/molecules in one JSON scene and
replay supplied probability/number-density frames. It does not manufacture bound-electron orbits
from particle transport. The source and clock of every view matter:

| View | Data source | What the animation means |
| --- | --- | --- |
| Molecular structures | Authored placed atoms and declared connectivity | Recorded geometry; no implied force law |
| Joint electron density | Supplied density grid, e.g. the independent RHF comparison | Recorded density changes on its declared physical or parameter clock |
| Electron probability samples | Supplied point ensemble | Samples of a spatial density, not persistent electron identities/trajectories |
| Proton/neutron ensemble | Geant4 `G4Fancy3DNucleus` | Independent nuclear initial-state configurations; ensemble index is not physical time |

Geant4 transport does not directly provide the bound molecular electronic wavefunction. Its
nuclear initialization model is also not time evolution of a nuclear wavefunction. These are
separate data sources, not a claim that Geant4 calculated molecular bonding or a reaction path.
An electron-density isosurface is a chosen level of number density: electrons have no hard
molecular boundary, and a shared field can extend across several molecular owners.

## Use in Studio

Open **Chemistry → Open chemistry workspace**. Use **Scene JSON → Import JSON** to load
[`two_molecules.json`](../examples/chemistry/two_molecules.json), or append a Structure-tab draft
with **Add structure as molecule**. Set each entity's explicit position/rotation in the JSON.
The checkbox selects the scene instead of the single-structure draft. Export preserves the scene;
the JavaScript source Save action still saves source code only.

For the complete recorded-density example, open
[`chemistry_probability_reference.js`](../examples/experiments/chemistry_probability_reference.js)
and press Run. Choose a density/sample/nuclear view in the selector above the tabs. Options
controls `nuclear_samples` (0 disables it, 1–32 configurations) and the ordinary transport probe.
Explicit isotope mass numbers are required for nuclear samples. The current sampling panel is
2≤A≤250; natural-isotope selection and a single-proton internal distribution remain unavailable.
Nuclear views keep their native **fm**, separately from the molecular/electronic **Å** view; the
UI never inflates a nucleus into the electronic scale. Red/blue glyphs denote proton/neutron
samples; their color and drawn radius are display choices. Each nuclide's pool is inspected one
nucleus at a time, not interpreted as correlated simultaneous molecular nuclear configurations.

The timeline holds recorded states without interpolation. It says **no physical clock** for
ensemble indices and parameter scans. A physical density sequence must supply physical timestamps;
point index across frames is never treated as electron identity. Missing fields explicitly clear
the previous density instead of retaining a stale surface.

## JSON scene surface

```json
{
  "schema": "trech_chemistry_scene_v1",
  "length_unit": "angstrom",
  "time_kind": "snapshot",
  "molecules": [
    {"id":"left", "position":[0,0,0], "rotation_deg":[0,0,0],
     "structure":{"atoms":[{"element":"H","massNumber":2,"position":[0,0,0]}],
                  "bonds":[], "charge":0}},
    {"id":"right", "position":[3,0,0],
     "structure":{"atoms":[{"element":"O","massNumber":16,"position":[0,0,0]}],
                  "bonds":[], "charge":0}}
  ],
  "links": []
}
```

This example declares atoms and placements, not molecular stability or a predicted reaction.
A link is `{"a":{"molecule":"left","atom":0},"b":{"molecule":"right","atom":0},"order":1}`.
It is authored connectivity. Rotation uses degrees, applied about x, then y, then z, followed by
translation. Atom endpoints are local zero-based indices. IDs must be unique; single-atom
structures are valid entities. Limits are 64 entities / 256 atoms / 1024 links.

`frames` optionally contains up to 128 records. `time_kind:"physical"` requires strictly
increasing non-negative `time_s`; `"parameter_scan"` instead uses `parameter_value` and carries
null physical time. A `"snapshot"` has at most one frame. Canonical exports use an explicit
`cursor` that the parser also accepts. Each frame can provide its own placed `molecules` and
`links`; otherwise the initial entities/links are used. Frame geometry is supplied, not generated
from the optional `ctx.react` inventories. Keep reaction-model validation separate from playback.

A frame's `fields` records contain:

- `id`, `particle` (`electron`, `proton`, `neutron`), explicit `owner_ids`, `length_unit`
  (`angstrom` or `fm`), and `density_unit`.
- `source:{kind,method,...}` with kind `quantum_reference`, `geant4`, `inferred` or `authored`.
  Imported source metadata is explicitly marked externally supplied. It is not independently
  authenticated by importing it.
- `grid:{shape:[nx,ny,nz],origin:[x,y,z],spacing,values}`: isotropic regular grid, x/y/z axis
  order with z varying fastest (C order). Values are finite; ordinary number/probability densities are non-negative, while
  explicitly labelled density_difference fields may be signed; spacing is positive in the declared length unit. Each dimension is 2–128 and
  each field holds at most 131072 values.
- `isovalue`: a positive display threshold in `density_unit`. Studio extracts this scalar grid
  directly using marching tetrahedra; it does not substitute atom-centred Gaussian orbitals or
  smooth the density. Surface color, transparency and camera framing are representation choices.
- Optional `samples:[[x,y,z],...]` (up to 8192) and `sampling_note`. These are supplied ensemble
  samples. Their drawn count is not an electron count.
- Electron fields require `geometry:{charge,atoms:[{element,massNumber?,position},...]}` binding
  the field to its owners' placed atoms in scene order. Coordinates are in Å; positions match
  within 1e-8 Å, and element/isotope/net charge must match. Editing a placement/atom requires
  recomputing or replacing its field. This catches stale geometry, not scientific inaccuracy.

Field IDs retain particle and units across frames. Several owner IDs designate a joint/shared
field; no forced per-molecule assignment is introduced. Strict mode omits fields labelled
`inferred` and records the omission. Independent quantum comparisons remain visible and labelled;
they are not strict Geant4 tallies. The engine's existing learned-inference gating remains intact.

`scene_json` accepts a JSON-encoded string. `scene_file` reads JSON relative to the JS scenario
(or accepts an absolute file path). Choose one. `TRECH_READ_JSON(path)` parses JSON without
executing it; normalized scene/field contents enter `hooks.inputs`, config hash and provenance.
Studio stages large overrides as immutable content-addressed JSON files under its output root,
avoiding OS argument limits and preventing an edited draft from changing an already-started run.
Scene grids still load in memory; aggregate scenes can exceed the current 8 MiB Chemistry emit guardrail,
which reports dropped emits. Large-scene streaming/chunking remains roadmap work.

## Included independent quantum comparison

Water + D2 are placed at declared 4/3/2 Å separations. PySCF solves a **joint neutral
RHF/6-31g** state at each placement. This permits a field spanning both molecules; it is not a
sum of fixed authored atom halos. The scaffold/approach is imposed, not a collision simulation,
free-energy path or predicted chemical reaction. Isotopic molecular motion is not determined by
a clamped-nuclei electronic calculation. Correlation, solvent and excited-state accuracy remain
unvalidated; this is a comparison reference, not a Geant4-trained electronic lift.

The total-density grid stores 0.16 Å **cell-average densities**, using numerical Gauss quadrature
(refined near nuclei). Direct core point sampling over-counted electrons and was replaced;
values are not renormalized to force agreement. Integrals are 11.9901/12 electrons, with the
<0.1% finite-grid/quadrature gap retained in the manifest. Each frame includes 1600 independent
visualization samples from the recorded cell-average density, not 1600 electrons. Methods,
software version, SCF convergence, geometry hash, integral gap and scene SHA-256 are recorded in
[`data/chemistry_probability/`](../data/chemistry_probability/).

```bash
build/rel/trech run examples/experiments/chemistry_probability_reference.js \
  --param events=3 --output build/chemistry_probability
python3 scripts/validate_chemistry_probability.py
build/render-venv/bin/python tools/quantum/build_density_scene.py
PYTHONPATH=studio build/studio-venv/bin/python -m trech_studio.capture \
  --run build/chemistry_probability --out build/electrons --still \
  --quantum-view density:joint_electrons
```

Other capture views are `samples:joint_electrons`, `structure`, and
`nuclear:O:16:both` / `nuclear:O:16:protons` / `nuclear:O:16:neutrons`.
Nuclear sampling uses an isolated CLHEP RNG and cannot consume the transport RNG sequence.
The real-run validator checks exact paired replay, proton/neutron counts, zero dropped emits,
strict gating and identical Geant4 transport tallies with the diagnostic enabled/disabled.
These tests do not validate general chemical reaction dynamics.

References: [PySCF density-grid evaluation](https://pyscf.org/contributor/dft_developer.html),
[vendored Geant4 nuclear initializer](../thirds/geant4/source/processes/hadronic/util/src/G4Fancy3DNucleus.cc).


## Shared electronic reference calculation and quantum states

Studio's **Calculate electronic reference (RHF/6-31g)** sends the current placed geometry to
`tools/quantum/build_density_scene.py`, through `engine/quantum.py`. TRECH validates the request
before calculation, validates the returned scene again, and emits the results for Studio to
replay. The same service is usable from the terminal:

```bash
build/render-venv/bin/python tools/quantum/build_density_scene.py \
  --scene examples/chemistry/two_molecules.json --out build/reference.json
build/rel/trech run examples/experiments/chemistry_mode.js \
  --param 'scene_file="../../build/reference.json"' --output build/reference_run
```

PySCF is an **optional engine-tool dependency**, never imported by Studio's UI or renderer.
Set `TRECH_QUANTUM_PYTHON` to a Python executable with PySCF; otherwise Studio tries the local
`build/render-venv/bin/python`, then its own interpreter. No package is installed automatically.
A failed/unsupported calculation leaves previous results intact. If the draft changes during a
job, its result is saved separately and does not overwrite the new draft. Jobs are bounded to
16 frames, 32 atoms, 2–64 electrons and the existing grid limits; currently only even-electron,
closed-shell RHF/6-31g references are supported. The grid starts at 0.16 Å and may coarsen
up to 0.32 Å to stay within its disclosed size budget; its electron-count gap is checked before
publishing. Spatial fields cover up to six occupied states (core and frontier) plus LUMO;
the complete spectrum and every occupation remain recorded. Electron parity does not establish that a molecule
has a closed-shell ground state; open-shell/excited/correlated calculations remain future work.

**States & particles** shows engine-emitted electron/proton/neutron counts, the calculated
geometry-dependent total energy/dipole and a discrete orbital spectrum with occupations. Clicking
a recorded state selects its own spatial |ψ|² field or its probability samples. The fixture records
all orbital energies and occupations, with grids for six occupied orbitals and the first virtual
state (LUMO). Other unoccupied grids are explicitly unrecorded. Molecular orbitals can span several
nuclei; their labels are canonical states at each geometry, not persistent adiabatically tracked
states across the scan. Orbital eigenvalues are not excitation energies or measured spectral lines.

Energy quantization does **not** mean an electron can only occupy selected radii or a classical
orbit. Positions have continuous probability, and total density adds occupied contributions,
which can hide individual lobes/nodes. No spherical atomic shell law is imposed on a molecule.
Each orbital grid is a **single-orbital probability density**, independent of its occupation:
an occupied RHF orbital can contain two electrons, whereas the displayed LUMO contains zero.
The coarse orbital grid has 0.32 Å spacing and 12-point/axis core quadrature; the largest occupied
normalization gap is about 0.5%, retained rather than corrected. Rendering colors/thresholds are
choices. Correlated electrons, time evolution, chemical stability and reaction paths remain open.
[PySCF's SCF API](https://pyscf.org/pyscf_api_docs/pyscf.scf.html) defines the computed energies,
coefficients and occupations.

Nuclear views now show **one named nucleus**, count every proton/neutron, and expose each
configuration's centroid and species RMS distances. Grey circles mark its sampled extent, not
hard boundaries or nuclear shells. A red/blue histogram shows radial **counts** across the recorded
configurations in 0.5 fm bins (last bin includes overflow); it is not a radial density per unit
volume. C++ computes these diagnostics from the sampled coordinates. It preserves the original
positions and transport RNG. This remains a
[Geant4 nuclear initializer](https://geant4.web.cern.ch/documentation/dev/prm_html/PhysicsReferenceManual/hadronic/PartonString/ReactionInitialStatePSM.html),
not a nuclear structure/shell solver. Low sample counts remain noisy, visibly disclosed.

Full scene grids live in `provenance.config_json.hooks.inputs.scene` and per-frame outputs.
`chemistry_state.scene` holds the initial entities/links with empty frames and declares
`scene_restore_source`; Studio restores the full scene from provenance. This avoids repeating
an entire multi-frame orbital sequence in one capped emit. Each Studio run uses a fresh output
directory so append-mode engine records cannot mix earlier results into a new calculation.


## Explore gradients, phase and density redistribution

The **Field explorer** tab replaces the single flat threshold surface as the default electronic
view. Select a total-density, individual orbital, or redistribution field and use:

- **Volume**: a continuous log-density color gradient and soft display opacity. The enclosed-mass
  slider clips the low-density tail at a threshold computed by TRECH, with target and actual
  included fractions displayed. The full source grid is retained.
- **Orbital phase**: orange +ψ and blue −ψ lobes from signed real orbital amplitudes. The zero
  between phase regions is a node. Global sign is arbitrary; these colors do not denote electric
  charge. The heatmap changes to signed amplitude and initially selects a Y-normal section;
  moving the section can reveal a nodal plane or nonzero lobes.
- **Enclosed-grid contours**: 10/50/90% thresholds ranked by recorded density, not a preset
  shell geometry. These show spatial probability/number-density concentration, not new energy
  states. Ties can make actual enclosed fractions exceed the target.
- **Movable 3D section**: an X/Y/Z section through the recorded field with a quantitative log
  color scale. The accompanying 2D section is always available, labels projected nuclei by
  molecule (A/B/…), and reports source cell coordinates/values on hover. No trajectories are
  synthesized. Phase slices use point samples; probability slices use cell averages.
- **Orbital overlay** on a joint or redistribution field: display a recorded orbital's signed
  lobes in the same 3D scene. Choose states in the selector or **States & particles**. Enclosure,
  log window, display opacity and section controls update the current view without rerunning
  physics or resetting the timeline. Same-clock field switches preserve the selected cursor.

C++ `scalarFieldStatistics` (`TRECH_FIELD_STATS`) integrates the supplied regular cell grid and
sorts absolute values to emit thresholds for 1–99% finite-grid mass. For unsigned |ψ|² this is
finite-grid probability, for total density electron number, and for signed redistribution
absolute signal. The diagnostic does not normalize a field, invent a wavefunction or improve
its physical precision. The displayed phase isosurfaces use point-amplitude thresholds linked
to the cell-average probability threshold; finite discretization means their geometric enclosed
volume is not an independently exact probability integral.

The PySCF service now preserves real orbital amplitudes using AO values × MO coefficients.
The regular amplitude grid shares the orbital probability grid's geometry, but stores point
values in Å^-3/2. This is why phase can now be inspected; squaring a wavefunction loses its sign.
[PySCF's orbital-grid implementation](https://github.com/pyscf/pyscf/blob/master/pyscf/tools/cubegen.py)
is the source reference. Real RHF fields do not cover complex/spinor or time-dependent states.

**Joint** means all declared owners were included in one electronic calculation; it does not
assert a covalent bond or entanglement between two molecules. When every fragment admits the
bounded closed-shell reference, `density_redistribution` contains joint RHF density minus the
sum of separately solved, clamped isolated-fragment RHF densities, evaluated on the same grid
and quadrature. Orange shows increase and blue decrease; C++ reports their separate integrated
magnitudes and residual net difference. Fragment calculations use their own 6-31g bases without
ghost-basis counterpoise, so basis differences contribute. This comparison is an inspectable
response of the chosen mean-field reference, not proof of bonding, reaction or accurate charge
transfer. Open-shell fragment comparisons remain unavailable.

The GPU uses maximum-scaled float16 textures and linear sampling, 128 ray samples, a disclosed
log color window and display alpha. These choices preserve the source arrays and engine
statistics, but image quality/opacity is not a physics convergence claim. Original values remain
available in the section inspector. Chemistry's explicit record budget is now 8 MiB; overall
multi-frame memory and streaming remain bounded-workbench limitations.

Reproducible captures use the same controls:

```bash
PYTHONPATH=studio build/studio-venv/bin/python -m trech_studio.capture \
  --run build/chemistry_fields_run --out build/joint_field --still \
  --quantum-view density:joint_electrons --density-mode volume --density-overlay mo_6
PYTHONPATH=studio build/studio-venv/bin/python -m trech_studio.capture \
  --run build/chemistry_fields_run --out build/orbital_phase --still \
  --quantum-view density:mo_6 --density-mode phase --density-mass 70
```

Other capture controls: `--density-decades`, `--density-opacity`, `--density-axis x|y|z`,
`--density-section 0..1`, `--density-cutaway`. These are recorded as representation metadata. Reference GIF
regeneration remains explicitly gated.


## Nonuniform occupied-level distributions through an atom

Open **Chemistry → Atomic core/valence reference (Ne)**, or run
`examples/experiments/chemistry_atomic_levels_reference.js`. This independent, clamped Ne-20
RHF/6-31g reference has ten electrons. The solver resolves three occupied-energy groups with
occupations 2, 2 and 6; groups combine only numerically degenerate eigenvalues (within 1e-8 Eh).
Neither their spatial widths nor their energies are linearly spaced or assigned from shell radii.
Orbital eigenvalues are not measured excitation energies or exact atomic spectroscopic labels.

The default **Occupied energy contributions** field mixes a display color for each group's
occupation-weighted density, using the actual local contribution fractions. Brightness follows
log density. Its cutaway exposes a sampled section through the inner cloud; overlapping colors
mean overlapping contributions, not sharp boundaries or electron paths. The numeric 2D section
uses the same source arrays. Move the section or select an individual recorded orbital to
inspect its nodes. The coarser decomposition grid and GPU interpolation are display limitations;
the finer total-density grid is also available separately.

The **Electron levels** tab exposes the actual distributions without volume occlusion:

- **Diameter** plots occupation-weighted density along X/Y/Z through a selected nucleus, in
  electrons/Å³. Log scaling reveals the core concentration and outer-state nodes/tails.
- **Radius** plots the spherical-average density multiplied by 4πr², in electrons/Å. This is
  the electron-number distribution over radial intervals, rather than density at one point.
  A high density at the centre does not imply maximal radial probability at radius zero.
- Colored curves are the recorded occupied-energy groups; white dashed is their engine-summed
  total. Hover reports source coordinates and values. Span/log controls change only the plot.

Profiles use direct AO/MO evaluation on 129 nonuniform radii from 0 to 4 Å and 257 diameter
positions, with 8-point cos(theta) × 16-point azimuth quadrature for spherical averages. All
occupied states contribute, including those without stored 3D grids. Up to eight nucleus centres
are recorded. For a molecule each profile contains the joint wavefunction around that centre;
it does not assign electrons to the selected atom. Finite-radius integrals and quadrature gaps
remain in the source. The Ne reference's core radial peak is about 0.057 Å, versus about
0.33–0.36 Å for outer contributions; finite-radius integrals differ from the group occupations
by about 0.12%. These numbers characterize this bounded mean-field reference, not validated
Geant4 electronic prediction or general isotope-dependent chemistry.

TRECH validates complete occupied-state membership, energies, occupations, nonnegative arrays,
geometry-centred profiles and component sums before emitting them. It recomputes profile totals
and grid statistics. The optional service selects a bounded set of 3D orbitals (core plus five
frontier occupied states and LUMO); a complete 3D energy decomposition is emitted only when all
occupied grids were recorded. Profile density, angular resolution, basis/correlation accuracy
and finite-radius convergence require further validation; no preset shell geometry is substituted.

```bash
build/rel/trech run examples/experiments/chemistry_atomic_levels_reference.js \
  --output build/chemistry_neon --param events=1
PYTHONPATH=studio build/studio-venv/bin/python -m trech_studio.capture \
  --run build/chemistry_neon --out build/neon_levels --still \
  --quantum-view density:energy_density --density-mode levels --density-cutaway
```
