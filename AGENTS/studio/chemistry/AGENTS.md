# Chemistry workspace and field inspection — context and contracts

[Root principles](../../../AGENTS.md) · [Root roadmap](../../../ROADMAP.md) · [Parent](../AGENTS.md) · [Roadmap](ROADMAP.md)

Related owners: [Quantum probability and nuclear diagnostics](../../scenarios/chemistry/probability/AGENTS.md) · [Rendering, appearance and playback](../rendering/AGENTS.md).

Read the root principles and the parent handbook first; then open only the subcategory relevant to the task. Source paths and shell commands in code spans/blocks are repository-relative unless stated otherwise; Markdown links resolve from this file.

**Chemistry workspace:** `studio/trech_studio/ui/chemistry.py` edits explicit atom/isotope/position/charge/bond inputs,
sent as typed string parameters through the ordinary engine bridge. `chemistry_mode.js` validates
them, snapshots them in `hooks.inputs` for config/hash/provenance, and emits `chemistry_state`,
native-Å `material_frame`, and optional conserved `chemistry_reaction_step` records. The dock
displays engine facts/traces and restores loaded structure/reaction inputs as drafts. It computes
no valence, stability, polarization, reaction rates or isotope effects. 3D remains a held authored
structure; discrete inventories do not imply atomistic reaction paths. Scope/contract:
[`docs/chemistry_mode.md`](../../../docs/chemistry_mode.md). Tests: `studio/tests/test_chemistry.py`.
Atom row labels are zero-based; omitted bond order stays unknown. Chemistry opens with bounded
side docks and a scrollable atom table; source headers show filenames with full-path tooltips.

**Probability/scene views:** `studio/trech_studio/engine/chemistry.py` owns JSON scene import/export and immutable
large-argument staging; `studio/trech_studio/ui/chemistry.py` edits scene JSON and requests view changes. Pure
`studio/trech_studio/render/probability.py` consumes `quantum_frame`/`chemistry_nuclear_ensemble` and preserves units,
shared field owners, source and emitted clocks. Scalar grids feed `density_surface_mesh` directly,
never Gaussian orbital guesses; missing fields clear the last surface rather than silently hold
stale density. Transparent density overlays use a display palette and threshold, not material
optics. Nuclear views are separate fm ensembles; timelines label ensemble/parameter clocks as
nonphysical. Tests: `test_probability.py`, `test_chemistry.py`; contract: `docs/output_schema.md`.

**States and particle diagnostics:** `studio/trech_studio/ui/probability_details.py` reports engine-emitted inventories,
orbital energies/occupations/dipole and nuclear centroid/RMS/radial counts, updating on the held
frame cursor. Clicking an orbital chooses its recorded field; no shell/orbit law is drawn.
`ParticleFrame.guides` draws labelled sample-extent circles separately from declared bonds;
nucleon glyph size is representation. `studio/trech_studio/engine/quantum.py` launches the optional offline PySCF
reference tool via QProcess; the UI/renderer never imports it. TRECH validates before/after the
job. Failed jobs preserve existing data, and edited drafts are not overwritten on job completion.
Large JSON numeric arrays use bounded rows to avoid one Qt text block per voxel. Each run writes
a fresh output directory; loaded scene grids restore from provenance, not summary emits.


**Interactive scalar-field inspection:** generic C++ `scalarFieldStatistics` / authoring
`TRECH_FIELD_STATS(values,spacing)` computes signed integrals and 1–99% absolute-mass ranked
thresholds, including full ties and actual enclosed fractions. JS ignores imported statistics and
recomputes them, with no model inference or normalization. Optional signed real `amplitude`
point samples accompany cell-average orbital |ψ|². `density_difference` fields explicitly name
their reference; ordinary densities remain nonnegative. The optional PySCF tool supplies joint
minus isolated-fragment density on a common grid (own fragment bases; not a bonding test).
Studio's `studio/trech_studio/ui/density_explorer.py` / pure `studio/trech_studio/render/density.py` provide movable numeric heatmap
sections, log legends and enclosed-mass controls. `studio/trech_studio/render/density_gpu.py` + `studio/trech_studio/render/shaders/density.wgsl`
ray-march recorded fields; `+ψ/−ψ` lobes and orbital overlays retain the supplied signs. The
maximum-scaled float16 GPU texture/interpolation/alpha are representation; original CPU values
and C++ statistics are unchanged. Scalar contours use outward winding and separate display
lighting, not material optics. Probability contours are not extra quantum energy levels.
Chemistry raises its explicit per-record emit budget to 8 MiB for phase/difference records;
full multi-frame grids remain in provenance, with existing streaming residuals in the [paired roadmap](ROADMAP.md).

**Occupied energy distributions:** the optional reference service evaluates all occupied-state
contributions directly on nonuniform nucleus-centred radial/diameter coordinates, groups only
numerically degenerate computed energies and retains occupations. TRECH validates membership,
geometry/units/counts and sums totals; complete small-system `energy_components` also sum to
the recorded 3D density. Studio's `studio/trech_studio/ui/electron_levels.py` plots diameter density versus the
spherical radial measure (4πr²), while the Field explorer colors local energy contributions and
exposes cut faces. `chemistry_atomic_levels_reference.js` / `neon_atom.json` provide a Ne-20
core/valence comparison. No preset shell radii, linear electron distribution, atomic quantum-number
assignment or Geant4 bound-electron prediction is implied. See [the probability contract](../../../docs/chemistry_probability.md).

Electron-level and particle-detail panels scroll within the Chemistry dock so complete spectra/profiles do not force the native window beyond the screen. Native gradient/profile captures and their source/run hashes extend the documentation gallery.
