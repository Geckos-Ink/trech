# Chemistry workspace and field inspection — roadmap

[Root principles](../../../AGENTS.md) · [Root roadmap](../../../ROADMAP.md) · [Parent](../ROADMAP.md) · [Handbook](AGENTS.md)

Related owners: [Quantum probability and nuclear diagnostics](../../scenarios/chemistry/probability/ROADMAP.md) · [Rendering, appearance and playback](../rendering/ROADMAP.md).

Maintain work in its owning branch. Dated results apply to the recorded checkout; they do not validate subsequent changes.

## Interactive probability fields and phase (2026-10-28)

- [x] Generic C++ scalar-field integrals, signed positive/negative components and 1–99%
  finite-grid absolute-mass thresholds, with exact tie inclusion. JS recomputes imported-grid
  diagnostics; source arrays stay unchanged. No learned-inference/RNG calls are introduced.
- [x] Optional solver exports signed real MO point amplitudes and independent joint-minus-
  isolated-fragment density. Geometry/unit/source/role validation rejects malformed phase
  arrays and unlabeled negative densities. Explicit Chemistry emit cap grows to 8 MiB.
- [x] Interactive Field explorer: gradient ray-marched volume, quantitative movable sections,
  enclosed-mass slider/contours, phase lobes/nodes and recorded orbital overlays on joint or
  difference fields. Legends/hover values and projected owner-labelled nuclei provide context.
  Controls preserve the source arrays and current clock; same-clock field switches retain cursor.
- [x] Correct outward contour winding and separate field-display lighting avoid random back-face
  triangle artifacts and material-optics shading. GPU ray marching uses scaled float16 textures,
  linear display sampling and 128 steps; original scalar values remain inspectable.
- [x] Nonuniform occupied-energy contributions: solver-evaluated diameter curves and spherical
  radial electron distributions for every occupied state, grouped by computed eigenvalues and
  occupation; engine validates geometry/membership and recomputes totals. Complete small-system
  grids expose energy-color contributions and cut faces. Ne-20 reference resolves core/outer
  distributions with computed 2/2/6 occupations, without fixed shell radii or linear fades.
- [x] Verification: Release CTest 27/27; Studio pytest 94 passed / 1 skipped; optional rotated-H2
  CLI and actual QProcess ethanol service gates pass. Eight paired Geant4 runs are byte-identical,
  preserve transport and drop no emits. Native Metal volume/phase/section/profile QA is recorded
  with the deliberately refreshed README screenshot manifest.
- [ ] Profile angular/radial and grid/image convergence studies, correlated basis benchmarks,
  energy decomposition for larger systems with omitted 3D orbital grids, and more than eight
  nucleus-centred profiles remain open. Basis-character labels are not exact atomic quantum
  numbers. Finite-radius molecular profiles include the whole joint wavefunction.
- [ ] Complex/spinor phases, adiabatic state matching, correlated/time-dependent quantum states,
  independently validated bond/entanglement measures and charge-transfer accuracy remain open.
  Own-basis closed-shell RHF fragment differences are comparisons, not proof of a shared bond.
- [ ] Field/texture streaming beyond in-memory scenes, scientific image-convergence gates, and
  richer camera/occlusion handling for transparent overlapping fields remain open. Sampling,
  log ranges and alpha are representation choices, not improved physics precision.


## Readable quantum states and nuclear grouping (2026-10-28)

- [x] States & particles tab: engine-emitted electron/proton/neutron inventory, discrete orbital
  energies and occupations, selectable recorded |ψ|² surfaces/points, total energy and dipole.
  Cursor changes update diagnostics; virtual orbitals visibly contain zero electrons.
- [x] One-nucleus labels, red/blue species counts, recorded RMS distances and radial-count plot;
  larger nucleon glyphs and separate sample-extent guides improve grouping without moving samples.
- [x] Optional electronic-reference action delegates to the shared engine tool (QProcess),
  validates through TRECH before/after calculation, then runs the ordinary scenario. No PySCF
  dependency in Studio; set TRECH_QUANTUM_PYTHON externally. Failed/stale jobs preserve drafts.
- [x] Complete large-scene restore from provenance, fresh batch output directories and compact
  numeric JSON rows prevent duplicate emits/stale-run mixing/excessive Qt text blocks.
- [x] Verification: 90 Studio pytest tests pass, one GPU animation test skips in the restricted
  runner; separate native Metal captures show orbital/nuclear views. Real QProcess/PySCF ethanol
  calculation preserves the venv executable and returns a TRECH-validated 26-electron scene.
- [ ] Multiple simultaneous orbital overlays, graphical nucleus picking and
  state tracking across geometries remain open. Energy eigenstates must not become guessed
  circular trajectories, imposed radial shells or persistent electron identities.
- [ ] PySCF service accuracy/coverage limits and general learned electronic/nuclear/reaction
  dynamics belong to engine/model work; see the [probability workstream](../../scenarios/chemistry/probability/ROADMAP.md) and [chemistry probability contract](../../../docs/chemistry_probability.md).


## Chemistry workspace — initial implementation

- [x] Four native-window Chemistry screenshots in the root README and linked from Studio's
  README, with source/clock captions, capture instructions and SHA-256 manifest. Covers structure
  editing, JSON/density surfaces, electron samples and Geant4 nuclear ensembles.
- [x] Engine bridge: newest executable builds are checked with a bounded Geant4-free inspection
  probe for typed overrides, bundle sources and Studio metadata, with fallback across builds/PATH.
  Explicit/environment choices remain authoritative; every `EngineLocation` resolves relative
  paths before subprocess cwd changes. Missing/nonexecutable choices report without fallback.
- [ ] Probe compatibility does not establish version/source identity, every scenario or optional
  backend. Discovery is synchronous with a three-second timeout per candidate; asynchronous
  discovery and richer engine capability metadata remain open.
  Locator/preview tests pass 19/19, covering stale builds, fallback, path normalization, timeouts,
  invalid explicit choices, disappearing candidates, filesystem failures and symlink loops.

- [x] Multi-entity JSON scenes with placements/rotations/links and recorded density frames;
  import/export, append current structure, restore and content-addressed large-file overrides.
- [x] Direct scalar-grid density surfaces beside authored structures, supplied probability points,
  field view selector and source labels. Missing fields clear the last density; camera fitting
  uses visible threshold extents while preserving the full grid. Density transparency is an
  unlit display overlay, separate from the material optics pipeline.
- [x] Separate fm Geant4 proton/neutron ensemble views (both or either particle type), with
  parameter/ensemble clocks explicitly marked nonphysical. No individual electron trajectories
  or nucleus exaggeration into molecular units. Headless capture supports `--quantum-view`.
- [ ] Picking an individual nucleus/molecule, editable graphical placements and multiple simultaneous field overlays remain open. Nuclear samples are per-nuclide
  ensemble pools; current selector does not claim correlated nuclear evolution across a molecule.
- [ ] Streaming/chunking for large grids: fields cap at 131072 density samples/8192 points, but
  aggregate JSON scenes and 8 MiB Chemistry emits can still exceed memory/payload budgets. Density
  source metadata is displayed as supplied, not authenticated by Studio. Full correlated quantum
  dynamics and learned reaction paths require engine/model work.

- [x] Chemistry menu/dock opens `chemistry_mode.js`; explicit atom/isotope/Å-coordinate table,
  net charge and declared bond-order editor; six engine-evaluated starting scaffolds.
- [x] Typed string overrides pass to engine inspection/run; authored graphs/plans enter config
  hash/provenance. Native-unit held spheres/bonds use the existing renderer. Edited drafts are
  labelled pending a new run. Saved run structures/plans can be restored as drafts.
- [x] Engine results show isotope facts, electron bookkeeping, live particle probes, learned
  atomic/nano response/traces and unavailable capabilities. Optional supplied reaction plans
  show last recorded discrete inventory and operator trace; all steps remain in Emits.
- [x] Ten Chemistry tests cover authoring/restore/index bookkeeping, invalid edits, native-unit
  frames, JSON staging and actual engine inspection/run argument wiring. Seven probability tests
  cover recorded grids, missing fields, samples, nuclear units/clocks and file round trips.
  All 12 Studio test modules pass;
  Metal-rendered molecular structure capture was visually checked.
- [x] Chemistry layout leaves room for the viewport and a scrollable atom table, with zero-based
  atom row labels. The source header shows the filename with full path in its tooltip.
- [ ] Direct 3D atom/bond picking/dragging, bond-order glyphs, import/export formats and dedicated
  chemistry project persistence (source Save does not save transient controls; provenance does).
- [ ] Reaction timeline/species views and product geometry playback after the engine emits
  validated atomistic dynamics. No atomistic path is synthesized from species counts.
- [ ] Transferable electronic/stability/polarization and isotope-conditioned models require engine
  training/holdout/independent-validation work. UI currently reports them unavailable; supplied
  hazard attachment alone never establishes scientific coverage or a calibrated physical clock.
- [ ] Large plan/output streaming and payload-cap feedback; large graphs/plans can exceed hook
  payload limits and emits/frames remain in memory. Studio keeps its existing dependency surface;
  the optional offline electronic-reference service requires PySCF in its own runtime.
- [ ] Local Qt `offscreen` cannot host the native Metal widget (process crash at surface creation).
  Chemistry glue tests stub the viewport; headless 3D captures use rendercanvas's separate
  offscreen backend. Native Cocoa launch/layout and separate Metal rendering were checked.
  Detecting unsupported Qt surface platforms before widget construction remains open.
