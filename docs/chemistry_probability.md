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
  order with z varying fastest (C order). Values are finite, non-negative number/probability
  densities; spacing is positive in the declared length unit. Each dimension is 2–128 and
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
Scene grids still load in memory; aggregate scenes can exceed the current 4 MiB emit guardrail,
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
