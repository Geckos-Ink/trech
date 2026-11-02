# Quantum probability and nuclear diagnostics — roadmap

[Root principles](../../../../AGENTS.md) · [Root roadmap](../../../../ROADMAP.md) · [Parent](../ROADMAP.md) · [Handbook](AGENTS.md)

Related owners: [Chemistry workspace and field inspection](../../../studio/chemistry/ROADMAP.md) · [Geant4 transport and diagnostics](../../../engine/simulation/ROADMAP.md).

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


## Chemistry quantum states and shared reference service (2026-10-28)

- [x] Reusable optional PySCF RHF/6-31g scene calculation, shared by terminal and Studio through
  the engine bridge; geometry-conditioned total density, individual orbital probability grids,
  energies, occupations and dipole. TRECH validates source/geometry/field/spectrum/count contracts;
  live Geant4 Z-minus-charge checks the electron inventory. Strict suppresses inferred spectra.
- [x] Nuclear C++ sample diagnostics: exact one-nucleus inventory, per-configuration centroid and
  proton/neutron RMS/max distances, finite radial histogram with explicit overflow. No RNG or
  particle-coordinate changes. Studio shows grouping, counts, distributions and extent guides.
- [x] State selection makes individual orbital lobes/nodes inspectable, with explicit occupied
  and virtual states. Quantization is in energies, not discrete allowed positions/Bohr paths.
  Fixture contains six occupied grids plus LUMO; quadrature gaps retained (core orbital ~0.5%).
- [x] Summary emits no longer duplicate a full multi-frame density sequence; provenance retains
  the complete restorable scene. Studio uses fresh run directories, guarded async reference
  jobs and bounded-row numeric JSON formatting.
- [x] Verification: Release CTest 26/26; Studio pytest 90 passed / 1 skipped (GPU-specific
  animation check in the restricted runner). Native Metal orbital/nuclear captures were inspected.
  Eight paired Geant4 runs preserve transport/RNG and drop zero emits. The actual optional
  QProcess service computes the default 26-electron ethanol scaffold and round-trips through
  TRECH inspection; a rotated H2 CLI job and failure-without-overwrite gate also pass.
- [ ] Reference service is bounded to 16 frames/32 atoms/64 electrons, even-electron RHF
  and fixed 6-31g basis. Spin/ground-state suitability, convergence/basis/correlation/solvent
  studies, general accuracy and unrecorded virtual grids remain open. Optional PySCF must be
  installed externally; this service never silently replaces missing learned physics.
- [ ] Canonical orbital indices are not tracked adiabatic states across a scan; atomic
  spectroscopic quantum numbers, physical excited-state energies, quantum
  nuclear shell structure and time-dependent coupled electron/nuclear dynamics remain open.
- [ ] General particle-trained electronic/stability/reaction prediction remains the next learned
  lift. The independent QM calculation and Geant4 initialization diagnostics do not close it.


## Multi-molecule probability scenes

- [x] Root README native Studio screenshot gallery: molecule/isotope editor, joint electron
  density with JSON authoring, density samples and O-16 proton/neutron ensembles. Raw captures,
  source/run metadata and SHA-256 manifest live in `docs/images/studio-chemistry/`; captions
  preserve each view's source, scale and nonphysical-clock limitations.
- [x] Studio automatic discovery tries newest executable builds first, checking typed overrides,
  bundle sources and Studio metadata with a bounded Geant4-free inspection probe before fallback.
  Explicit/environment choices remain authoritative and normalize before subprocess cwd changes,
  including direct `EngineLocation` construction. Invalid explicit paths report without fallback.
- [ ] Discovery checks protocol compatibility, not version/source identity or every scenario and
  optional backend. Probes are synchronous with a three-second timeout per candidate; asynchronous
  discovery and richer engine capability/version metadata remain open.

- [x] Generic C++ `TRECH_READ_JSON` data import; JS validates named molecular/atomic entities,
  placements/rotations, declared cross-entity links and supplied regular density grids/point
  ensembles. Scene/field state enters canonical config/hash/provenance and restores identically.
  Electron fields bind geometry/isotopes/net charge; stale fields reject after edits. Explicit
  physical clocks and parameter clocks remain distinct; strict omits imported inferred fields.
- [x] C++ `NuclearSpatialProbe`: opt-in Geant4 `G4Fancy3DNucleus` initial-state samples, explicit
  isotopes, separate fm views, exact proton/neutron inventories and isolated RNG. This diagnostic
  does not propagate nuclear wavefunctions, time or reactions and cannot perturb transport.
- [x] Studio JSON import/export/append-entity authoring, view selector, direct recorded-grid
  isosurfaces, supplied probability points and nuclear ensemble playback. No invented electron
  orbits, inferred hard molecular boundaries, sample identities or position interpolation.
  Large scene overrides use immutable content-addressed JSON files instead of OS-sized arguments.
- [x] Independent joint water/D2 RHF/6-31g comparison, three authored approach placements,
  reproducible 1600-point visualization ensembles, geometry binding and source manifest/hash.
  Cell-average quadrature replaces inaccurate core point sampling without renormalization;
  grid integrals 11.9901/12 electrons (<0.1% gap). No Geant4-training/dynamics claim.
- [x] Verification: Release CTest 26/26, all 12 Studio test modules, eight real Geant4
  probability-workbench runs (both modes, nuclear sampling on/off, exact paired replay and
  unchanged transport tallies), plus the twelve legacy Chemistry runs. Electron and nuclear
  Metal captures were visually checked. These gates validate source/geometry/unit/clock/RNG
  contracts and the bounded reference, not general quantum dynamics or chemical accuracy.
- [ ] **Next learned lift remains required:** train geometry-/isotope-conditioned electronic
  density and correlated nuclear/molecular state from particle histories, validated on separate
  molecules/energies/geometries against independent quantum/experimental references. Imported
  density frames and Geant4 nuclear initial states do not establish this learned map.
- [ ] Coupled time-dependent electronic/nuclear dynamics, isotope effects on molecular stability,
  forces, reaction discovery and calibrated atomistic reaction paths remain open. Current joint
  density fixture is a neutral clamped-nuclei small-basis RHF comparison; correlation/solvent/excited-state
  accuracy is unvalidated. The approach is authored, not a predicted collision/reaction.
- [ ] Nuclear ensembles are pools per nuclide, not a correlated simultaneous multi-nucleus state.
  Natural-isotope selection, single-proton internal structure and nucleus picking remain open.
- [ ] Large grids/frames need streaming and chunked emits. Each field is bounded to 131072 grid
  samples and 8192 points, but aggregate scenes can exceed the 8 MiB Chemistry record guardrail
  or practical in-memory limits; dropped emits remain reported. Density source declarations are
  supplied metadata, not independently authenticated scientific validation. Geometry binding does
  not verify the claimed quantum method or density accuracy.
