# Recorded process and scalar views — roadmap

[Root principles](../../../AGENTS.md) · [Root roadmap](../../../ROADMAP.md) · [Parent](../ROADMAP.md) · [Handbook](AGENTS.md)

Related owners: [Reusable solution and material processes](../../scenarios/processes/ROADMAP.md) · [Independent process references](../../scenarios/references/ROADMAP.md) · [Rendering, appearance and playback](../rendering/ROADMAP.md).

Maintain work in its owning branch. Dated results apply to the recorded checkout; they do not validate subsequent changes.

## Process-driven experiments and honest spatial views

- [x] `water_salt_recipe.js` exposes library-described process steps through ordinary inspection
  and emits operator/blocking reports; no process solver is introduced into the viewer.
- [x] Run summary reads the engine's `trech_model_artifacts_v1` scenario-registry manifest:
  loaded/missing point/cascade/operator models, declared paths/roles/scales, SHA-256 and byte size.
  Failed loads expose their recorded diagnostic. No path reopening, rehashing or inferred validity;
  legacy loaded-name-only output says identities were not recorded, and unknown schemas stay visible.
- [x] Per-stage recipe execution view (2026-11-08): the Processes dock lists every planned
  `hooks.inputs.recipe.steps` stage with recorded `process_recipe_state` calls, committed/blocked/
  rejected counts, last engine error code/reason, contract, model-selection status and summed
  inference/out-of-domain/draw accounting (rejected proposals keep theirs). Unreported stages read
  "not reached"; strict runs say inference was disabled by design. Model-load status stays in Run
  summary. `studio/tests/test_recipe_status.py` covers the summary and panel; on the recorded
  `process_contracts_recipe` run `mix` shows 8 `operator_blocked` calls and three later stages
  not reached.
- [x] Declared no-op commits (2026-11-09): stages count committed `no_op` steps by reason
  ("N no-op" in the summary, "declared no-op commits: N × empty neighbourhood (no operator
  ran; clock advanced)" in details); a `no_op` label on an uncommitted step is not counted.
  Covered by `test_recipe_status.py`.
- [ ] Residual: no per-stage timeline cursor sync, no capability preview before a run (which
  roles have compatible models), and no geometry is shown for blocked stages by design.
- [x] Separate optics/stratifier snapshots display recorded digests/size and loaded/failed/disabled
  statuses from the manifest's optional `loaders` array. Strict/disabled statuses are intentional,
  without warnings or file reopening; older manifests retain their previous behavior.
- [ ] Artifact signatures and process pins for separate loaders require engine support.
  Hashes do not prove physical validity or establish that inference ran.
  Verification (2026-11-02): Studio pytest 157 passed; five GPU checks skipped without an adapter.
  Mixed registry/loader, failed, disabled, legacy and unknown-schema records are covered; the
  real-run summary layout was inspected. Engine Debug/Release CTest each pass 36/36, optional
  Torch gates 4/4, plus seven fresh runs and a two-batch model-replacement lab check.
- [x] Retire salt inventory animation and consume C++-inspected measured native-um interface
  triangles on their recorded clock. Missing calibrated data produces no fabricated geometry.
  Source/calibration/validation declarations remain in config; format checks do not prove accuracy.
- [x] Display genuine 3D independent Euler scalar state using JS camera yaw/pitch, axis slices,
  linear transparent gradients, masked isosurfaces and volume mode, shared by live/export paths.
  Scalar masks hide obstacle voxels without creating false boundary contours. Old 2D media
  remains historical. These are comparison fields, not learned/experimentally validated flow.
- [ ] Obtain/review calibrated NaCl interface time sequences; the user-supplied single Wikimedia
  photograph is appearance only. No validated microscopy sequence or liquid/solute transport is
  bundled. Experimental uncertainty, reconstruction review and physical phase-change models remain open.
- [x] Authored perspective/orthographic projection in live/export, including parallel volume
  and section rays, sprite/ribbon facing, surface shading and projection metadata. Legacy
  records retain perspective. Airflow Options includes projection plus engine CFL/duration.
- [ ] Add oblique sections; currently one isotropic regular
  scalar grid per stream, positive isosurfaces, authored linear transfer, full bounded frame payloads.
  Volume filtering/128 ray samples/float16 are representation limits. Field streaming, live display
  overrides of authored defaults and generalized multi-field/vector overlays remain open.
- [x] Engine exact 3D periodic entropy/shear anchors check common-time grid and fixed-grid CFL
  convergence, with C++ co-located field norms and exact replay. The standalone validation script
  also records common-time obstacle grid/CFL diagnostics. These are numerical checks, not
  independent obstacle accuracy or particle training labels; Studio continues to consume records.
- [ ] Validate 3D obstacle aerodynamic accuracy, shock/acoustic/wall response and longer-time
  grid/time convergence, then train particle-derived response. External obstacle anchors with
  uncertainty and a particle-derived training corpus are not bundled; smooth periodic verification
  at t=0.04 s does not close this gate. Coarse first-order longer-time diffusion remains a limit.
  Inviscid comparison has no viscosity, turbulence, boundary layers or solid thermal/structural coupling.

Recorded-field verification: 146 Studio tests passed with native Metal access, including
orthographic volume/slice/surface tests. Engine Debug and Release CTest 35/35, seven process
reference runs and seven exact/common-time Euler runs pass. Earlier Metal volume/slice/surface
captures retain their identities. The source photograph does not close the missing calibrated
interface dataset or physical-validation gaps.

Artifact-view verification: Studio pytest 105 passed, one GPU-detail check skipped because the
sandbox exposes no Metal adapter. New Qt/parser checks cover recorded digests with missing local
files, missing models, score/provenance precedence, legacy output and unknown schemas. A summary
loaded from a real Geant4 run with both loaded and missing models was visually inspected. Engine
Debug/Release CTest each pass 33/33, with twelve replay/hash/parity smoke runs recorded in this
roadmap. No reference media was regenerated.
