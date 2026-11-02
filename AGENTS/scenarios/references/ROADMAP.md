# Independent process references — roadmap

[Root principles](../../../AGENTS.md) · [Root roadmap](../../../ROADMAP.md) · [Parent](../ROADMAP.md) · [Handbook](AGENTS.md)

Related owners: [Reusable solution and material processes](../processes/ROADMAP.md) · [Scenario and process editing](../../studio/authoring/ROADMAP.md) · [Builds, dependencies and optional backends](../../tooling/dependencies/ROADMAP.md).

Maintain work in its owning branch. Dated results apply to the recorded checkout; they do not validate subsequent changes.

## Author-notes foundations: phase change, airflow and JS authoring (2026-10-30)

- [x] Independent NaCl dehydration lattice fixture: integer Na/Cl/solvent parcel accounting,
  connected growth, seeded attachment and no-dehydration/zero-attachment controls. Geant4
  probes constructed 1:1 NaCl and water separately. No calibrated solubility/kinetics or physical
  growth clock is claimed; the parcel lattice/trays are display choices.
- [x] Independent compressible ideal-gas Euler fixture: 2D conservative Rusanov/CFL stepping,
  fixed reflective obstacle, open boundary/wall exchange accounting, SI pressure/density/velocity/
  gas temperature and positive-state rejection. Uniform flow, integrated balance, replay and
  inlet-speed perturbation guards exercise implementation rather than experimental accuracy.
- [x] C++ inspected source inventory and optional `TRECH_STUDIO` data-only descriptions;
  Studio edits included modules, runs their root scenario, reapplies typed options/UI on Save,
  lists configured models/process roles and selects recorded material streams. UI metadata is
  outside physics config/hash. Both references snapshot physics assumptions in `hooks.inputs`.
- [x] Official V8 source submodule pinned at `06637ec79e4` (15.9.0 candidate). An opt-in
  standalone C++ compile/execute/code-cache probe is syntax-checked against those headers.
  Normal builds still use QuickJS; no V8 build/link/runtime/performance claim is made.
- [ ] NaCl quantitative reference: independent concentration/temperature/evaporation data,
  reversible dissolution, nucleation barriers, morphology and resolution/history convergence;
  then a particle-derived learned phase lift with separate held-out validation. The illustrative
  comparison must not be relabelled as a Geant4-trained teacher.
- [ ] Metals heat treatment is a separate family: alloy composition, time/temperature histories,
  phase fractions, grain/microstructure, residual stress and measured strength/tempering anchors.
  Salt crystallization does not validate these observables.
- [ ] Aero quantitative validation: independent shock/flow anchors and grid/time convergence at
  common physical horizons, uncertainty, held-out Mach/geometry/density conditions and learned
  particle-to-continuum lifting. Viscosity/turbulence, moving bodies, solid temperature/thermal
  coupling, deformation, fracture and reactive flow/explosion remain absent. Euler gas compression
  temperature is not viscous heating or a projectile/rocket structural prediction.
- [ ] Complete Studio parity across every scenario: moving apparatus, grids/classes, legends,
  chart/text overlays, simultaneous streams and all-family capture matrix (see [desktop milestones](../../studio/ROADMAP.md#studio-desktop-ui)).
- [ ] JS workflow execution: engine-neutral host boundary, editable training/harvest/inference
  job descriptions with provenance/validation, progress/cancellation and safe model activation.
  Current process rows describe execution and do not launch jobs or replace live workers.
- [ ] V8: heavy upstream GN/dependency build, probe link/run, host API/Geant4/operator/RNG/emit/
  exception/reset parity, same-input differential tests and reproducible performance benchmarks.
  Persisted caches need source/build/flags identities and rejection handling; cache bytes are not
  portable bytecode. Keep QuickJS until strict replay/provenance parity is demonstrated.
- [x] Unsaved JS source protection: root and included drafts show dirty markers and receive
  Save/Discard/Cancel before scenario replacement or close. Cancel/failed Save preserves the
  workspace and running jobs; browser/Chemistry switch paths respect rejection. File conflicts
  preflight all changed sources before writing; browser activation no longer opens twice.
- [ ] Authoring residuals: asynchronous/nonblocking inspection, typed-option/Chemistry draft
  persistence, crash recovery and transactional multi-file saves, source-content provenance,
  generic JS widget composition and in-flight
  validated model/kernel replacement. Save applies the next-run workspace only.

Scope and commands: `docs/process_references.md`, `docs/studio_authoring.md`, `docs/v8.md`.
Tests: `test_process_references.cpp`, `scripts/validate_process_references.py`,
`studio/tests/test_authoring.py`; comparison laws are registered in the JS-law audit ledger.
Verification: Release CTest 29/29; full Studio pytest 99/99 with local Metal access (including
the five GPU playback cases); seven fresh-output Geant4 runs with exact repeated score/emit/scene
bytes and zero dropped emits/inferences. Both new scenes were captured through Studio's native
wgpu path and visually inspected. V8 verification is syntax-only against pinned headers;
its monolith has not been built or linked.
