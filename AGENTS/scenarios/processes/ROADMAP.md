# Reusable solution and material processes — roadmap

[Root principles](../../../AGENTS.md) · [Root roadmap](../../../ROADMAP.md) · [Parent](../ROADMAP.md) · [Handbook](AGENTS.md)

Related owners: [Learned state and pair operators](../../engine/operators/ROADMAP.md) · [Independent process references](../references/ROADMAP.md) · [Recorded process and scalar views](../../studio/processes/ROADMAP.md).

Maintain work in its owning branch. Dated results apply to the recorded checkout; they do not validate subsequent changes.

## Deep reusable JS process libraries

- [x] Generic JS process runtime: strict gating, detached state, stage completion, blocked
  operator reports and invariant-checked proposal commits. Domain solution library supplies
  units, state, H/O/Na/Cl conservation, channels and contextual engine operator roles.
- [x] Small `water_salt_recipe.js`: take water and salt, mix, heat, evaporate, crystallize.
  Plan enters config/hash; operators remain engine-owned. No validated process models are
  bundled, so the example blocks honestly and reports no spatial state.
- [x] Material-independent `trech_process_operators.js`: explicit state/aux/context units,
  role/kind binding, authored provenance, exact discrete topology/conservation checks and
  transactional continuous/discrete proposals. Solution plans include detached contracts;
  bound reports retain the engine trace/accounting plus stable error codes. C++ read-only
  `ctx.operatorCatalog()` exposes declared paths, loaded IO, scale and carried validation
  metadata in strict and predictive modes without inference, RNG or operator selection.
- [x] Loaded-model byte identities and optional process artifact pins: C++ hashes the exact
  loader snapshot once; detached catalog IDs persist across file replacement and change on
  reload. JS pins the complete loaded role/kind group before inference, records observed IDs
  in bound reports and blocks on changed/missing/additional artifacts without state/clock/RNG
  changes. FNV-1a-64 identities are explicitly noncryptographic and do not certify validity.
- [x] Loaded model `feature_units` and optional process `model_units`: complete named-IO
  labels validated in C++, exposed as detached catalog metadata and compared against the
  complete loaded role/kind group's IO union before invocation. Missing/mismatched labels
  block without state/clock/RNG changes; strict and legacy unchecked paths remain unchanged.
  Intermediate and overlapping state/aux/context labels must agree. This checks authored
  labels, not dimensional correctness, conversion, physical origin or measured accuracy.
- [x] SHA-256 identities and byte sizes from the same loader snapshot, alongside compatible
  FNV pins; process contracts can pin either algorithm without fallback. A sorted
  `trech_model_artifacts_v1` manifest covers every scenario-registry model (point/cascade/operator,
  including failed loads) in both provenance phases and run-end scores. Studio displays recorded
  load status, digest and byte size without reopening artifacts. No-model output shape and
  config hashes remain unchanged; hashes do not certify authenticity or physical validity.
- [x] Separate optics/stratifier loaders now enter the same manifest in sorted `loaders` entries,
  with exact loaded-byte FNV/SHA-256/size, failures and intentional strict/disabled statuses.
  Isolated stratifier workers load one captured byte snapshot; legacy run-boundary FNV hashes
  use it rather than reopening paths. JSON rejects trailing/malformed artifacts; both backends
  reset identities after failed reloads. Strict mode now also gates the optics surrogate
  override, retaining the independent extractor. Studio displays recorded loader status/identity.
- [x] Unit labels parse to SI dimensions/scale with multiplicative conversion
  (`TRECH_PROCESS_OPERATORS.units`), and opt-in `dimensional_check` derives the required
  `d_<field>_dt` / `set_<field>` / `hazard_<channel>` units from the declared state at bind time
  (`trech_process_units` CTest). Residual: runtime model matching still compares exact labels
  (an equivalent spelling such as `Hz` vs `1/s` passes the audit but not the catalog match); no
  value is converted automatically, affine temperatures are rejected, spatial pair outputs and
  non-`d_/set_/hazard_` outputs are only parsed, and no scenario has adopted the flag yet.
- [ ] Contract extensions: persistent-link/pair-state bindings,
  process pins for separate loaders, artifact signatures and general measured
  response/error requirements remain open. The catalog describes artifacts; it does not certify
  physical origin, runtime input completeness or validity.
  Stratifier capture retains one full artifact byte snapshot and validates it before per-worker
  instantiation; streaming model loading and automatic memory budgeting remain open.
- [x] Declared empty-neighbourhood completion (2026-11-09): C++ `PairInteractionResult::noPairs`
  (JS `blockedReason:"no_pairs"`) separates a well-formed call with no pair from a malformed
  block. Spatial contracts may declare `empty_neighbourhood: "complete"` (default `"block"`):
  only that verdict, after complete selection, an untruncated search and zero inference, yields a
  `no_op` report; the process runtime commits unchanged state, advances the clock and reports
  `no_op`, and Studio's recipe view counts these commits apart from inference.
  `test_pair_interaction`/`test_process_spatial` cover the verdict, malformed blocks, default
  blocking, populated neighbourhoods, incomplete selection staying blocked and replay.
- [x] Declared empty-population completion (2026-11-09): `ctx.evolve`/`ctx.react` accept boolean
  `report_empty_population`; a zero-element call then returns `blockedReason:"no_elements"` with
  its selection (zero inference/draws, no `react` sequence index) instead of `null`. Scalar-kind
  bindings may declare `empty_population: "complete"` (default `"block"` keeps zero-element arrays
  `invalid_binding`); only that verdict with a `selected` operator yields
  `no_op:"empty_population"`, committed like the empty-neighbourhood no-op.
  `test_process_empty_population` covers the raw verdict and legacy `null`, flag typing, default
  blocking, unavailable-role blocking, populated execution, runtime commit, strict mode and that a
  later `react` replays identically with or without the empty call.
- [ ] Spatial process completion residuals: persistent topology/pair-state contracts, empty
  populations for per-element-kind and spatial bindings (no kind to select over zero elements),
  and per-domain evidence that "no neighbour"/"no element" really means "no change" for a given
  material process. No shipped scenario declares `empty_population` yet.
- [x] Shared per-element material bindings: a declared state field supplies dynamic kinds
  within an explicit allowed set. Numeric state/aux arrays remain isolated; kind arrays are
  detached from engine proposals. Pins check the union of all declared kinds and unit IO
  unions are checked separately per kind. C++ `require_complete_selection` blocks incomplete
  active-kind selection before inference/reaction sequence allocation; raw calls retain partial
  execution by default. This is selection completeness, not a guarantee of model input readiness.
- [x] Spatial neighbour process bindings over explicit, read-only x/y/z arrays, unit-declared
  cutoff, optional pair budget and explicit field symmetry. C++ `ctx.interact` now supports
  the complete-selection gate and rejects incomplete/nonfinite supplied coordinates instead
  of filling absent axes with zeros. Pins/units cover canonical material-combination groups;
  truncated proposals roll back state/clock while retaining inference reports. Synthetic host
  tests cover 3D neighbour selection, dynamic kinds, strict mode, rollback and exact replay.
  This supplies an execution boundary, not validated thermal/mass transport or interface physics.
- [ ] Train/validate composition/concentration-conditioned dissolution, thermal and phase-change
  operators from particle-derived context plus labelled independent response anchors. No reference
  fixture should be relabelled as microscopic training truth.
- [ ] Coupled thermal/latent-energy, mass transport and spatial 3D solution state; local
  supersaturation, nucleation, faceted interfaces and reversible crystal growth/dissolution.
  Sequential thermal preparation and single-channel parcel counts do not implement these.
- [ ] Generalize the domain libraries across materials/process families on the shared unit,
  capability, provenance and error contracts; additional physical families, parallel/coupled
  process scheduling and persistent-link/pair-state binding remain missing. Spatial neighbour
  binding is implemented, without validated transport laws. Heterogeneous bindings
  currently share numeric state/topology and expected model IO; per-kind schemas and validated
  cross-material response models remain open. Tests use synthetic operators only.
- [x] Retire the salt trays/parcel cluster from active playback and the README gallery. C++
  `TRECH_INTERFACE_SEQUENCE` checks calibrated measured meshes, timestamps, uncertainties and
  documented validation declarations. Native-um interfaces enter config/provenance and replay as
  held triangles; format inspection explicitly does not verify physical accuracy. Missing data
  reports unavailable and media drivers skip the animation. The supplied Wikimedia photograph
  is retained as an attributed visual reference, without invented specimen calibration or depth.
- [ ] Supply/review validated microscope-scale interface data: no calibrated 3D time sequence is
  bundled. Photo-based appearance, inventory bookkeeping and synthetic parser tests do not
  establish solution transport, faceted growth or physical accuracy. Reconstruction review,
  experimentally quantified uncertainty and conserved liquid/solute exchange remain open.
- [x] Genuine 3D **independent Euler comparison**: five conservative variables, x/y/z face flux,
  spherical stair-step obstacle, physical-volume integrals and measured numerical residuals.
  JS-authored camera, field/linear-gradient range, slices, opacity, surfaces and volume mode feed
  the same Studio live/export path. Masked voxels do not create false obstacle isosurfaces.
  Historical 2D media keeps its original identity; transparency remains representation.
- [x] Verify smooth 3D periodic entropy/shear transport against independent exact conservative
  cell averages, with 6/12/24 grid refinement and fixed-grid CFL refinement at common physical
  time. Generic C++ field norms reject invalid/mismatched arrays without interpolation.
  `scripts/validate_euler3d.py` records exact replay, source/binary hashes and common-time
  obstacle grid/CFL diagnostics. Scenario `cfl` and optional `duration_s` expose these controls.
  Smooth-anchor orders are 0.68–0.87 spatial and 1.03–1.11 temporal; the latter uses a smaller-CFL
  same-grid numerical reference, not a claim that spatial error disappears. These anchors are
  numerical verification only and are never Geant4 training labels.
- [x] Recorded perspective/orthographic orbit projection shared by Studio live/export, including
  parallel volume/section rays, sprite/ribbon facing and surface shading. Legacy records default
  to perspective; display projection does not alter fields or simulation precision.
- [ ] Validate aerodynamic accuracy on independent 3D obstacle anchors, shocks/acoustics, wall
  geometry and longer-time grid/time refinement, then train the particle-derived lift. Smooth
  periodic checks and unanchored obstacle diagnostics do not close this gate. Inviscid comparison
  is not Geant4-trained flow; viscosity, turbulence, boundary layers, solid heat transfer and
  structural response remain unavailable. One regular isotropic scalar grid per stream,
  axis-aligned sections, positive isovalues, bounded full-frame payloads and float16 display precision are
  current limits; oblique sections and streaming/reconstruction review remain open. No external
  obstacle dataset with quantified uncertainty or particle-derived aerodynamic training corpus
  is bundled. First-order coarse-grid diffusion can saturate longer-time entropy errors; the
  present exact-anchor gate covers t=0.04 s on a unit periodic cube only.

Interface/3D reference verification: Debug and Release CTest 35/35 and native Metal Studio
pytest 146/146 pass. Seven process-reference runs plus seven exact/common-time Euler runs
pass positive-state, conservation, replay and zero inference/dropped-emits checks. Orthographic
volume/slice/surface GPU tests pass. Historical full-3D Metal captures also verified a
2664-triangle surface. These are implementation/numerical checks, not external physical
validation. Synthetic interface fixtures remain test-only.

See `docs/solution_processes.md`. Current visual/data limitations are stated above the folded historical README
diagnostic gallery. No new preview is substituted for unavailable physical/spatial models.
Spatial-binding verification: Debug and Release CTest 34/34 pass. Synthetic host coverage
includes 3D cutoff geometry, scalar/dynamic pair kinds, both field symmetries, Float64Array
positions, Unicode pair ordering, unit/pin/selection gates, strict mode and rollback/replay.
The eight-event Geant4 recipe retains `e492145ebbf38567`, unchanged blocked inventories/clock
and zero inference, transition draws or dropped emits. This uses the existing local Geant4
installation and does not validate the newer dependency checkout or any transport response model.
Earlier verification: Release CTest 29/29; the recipe's real eight-event Geant4 run reports
`no_compatible` dissolution operators, unchanged inventories and zero inference/dropped emits.
QuickJS tests exercise sequencing with explicit operator test doubles, strict gating, detached
metadata, blocked stages and rejection of invalid proposals. These tests do not validate kinetics.
`test_process_operators.cpp` adds host-backed continuous/discrete synthetic fixtures, catalog
load/IO/metric/strict parity, exact replay, explicit zero vs missing inputs, auxiliary isolation,
contract detachment and rollback. Its carried metrics are test data, not physical validation.
Current contract verification: Release and Debug CTest 32/32 pass. The real eight-event
Geant4 recipe preserves inventories/clock, records all four contracts in provenance, reports
`operator_blocked` / engine `no_compatible` on every event and has zero inference/dropped emits.
Catalog-read/no-read paired stochastic transfers preserve exact results and inference/RNG counts.
Artifact-pin verification: loader tests cover path-independent exact-byte IDs, replacement,
whitespace changes, full JSON parsing and failure reset. Host tests cover relative-path snapshot
identity, pinned continuous/discrete calls, complete-group mismatch/strict gates and identical
stochastic results with/without rejected pin checks. Optional Torch stream loading uses the
same byte snapshot; the later [optional-backend gate](../../tooling/dependencies/ROADMAP.md#dependency-checkout-refresh--2026-10-27) now exercises snapshot identity,
replacement and failed-load reset with real synthetic TorchScript modules.
The artifact-pin change passes Release and Debug CTest 32/32 each. A fresh eight-event Geant4
recipe run retains the prior `e492145ebbf38567` config hash and the same blocked inventories/clock,
with zero inference, transition draws or dropped emits.
Unit-label verification: Release and Debug CTest 32/32 each, plus focused loader/host checks for
malformed/legacy metadata, loaded-snapshot persistence, v2 decoded-output units, multistage unions,
detachment, combined pins/units and strict gates. Rejected continuous/discrete unit checks leave
subsequent stochastic results and counters identical. A fresh eight-event recipe run keeps
`e492145ebbf38567`, blocked state/clock and zero inference/draws/dropped emits. This uses the
existing local Geant4 installation; it does not validate the newer dependency checkout.
Per-element binding verification: Release and Debug CTest 33/33 each. The new host test covers
changed material assignments, distinct synthetic hazards, kind-array isolation, proposal rollback,
per-kind unit unions and pins, missing/ambiguous/partial selection gates, strict mode and identical
stochastic replay with/without rejected preflights. Raw partial continuous/discrete calls retain
their prior behavior. Per-kind IO schemas and measured physical response remain open; spatial
neighbour binding is covered by the subsequent `test_process_spatial.cpp` host gate.
The eight-event recipe smoke retains `e492145ebbf38567`, unchanged inventories/clock and zero
inference, transition draws or dropped emits.

SHA-256/manifest verification: Debug and Release CTest 33/33 each; Studio pytest 105 passed,
one Metal-adapter check skipped in the sandbox. Known SHA-256 vectors cover empty/short inputs,
padding boundaries, all byte values and a million-byte input. Loader/host tests cover snapshot
persistence after replacement/deletion, failed-load reset, non-operator/missing registry entries,
catalog/manifest parity, detached reads, FNV/SHA pin compatibility, missing-digest refusal and exact
stochastic replay with rejected SHA checks. Twelve fresh-output Geant4 runs (six repeated cases:
point, cascade, operators, strict, missing model, blocked recipe) verify manifest start/end/scores
parity and hashes against Python hashlib, exact score/emit replay and zero dropped emits. The
no-model recipe keeps `e492145ebbf38567` and matches the prior score/emit bytes. Studio's real-run
summary layout was visually inspected. These checks use the existing local Geant4 installation;
they do not validate the newer dependency checkout, optional Torch or the full family physics suite.

Separate-loader/discovery verification (2026-11-02): Debug and Release CTest 36/36 each;
optional Torch loader/snapshot/backend gates 4/4; Studio pytest 157 passed, five GPU checks skipped
because the sandbox exposes no graphics adapter. Seven fresh Geant4 runs verify registry/loader
manifest parity across start/end/scores, Python hashlib digests/byte sizes, predictive exact replay,
strict optics equality with an omitted-surrogate baseline, failed/disabled status and no-model
omission. Two persistent lab batches retain both loader manifests, classifier predictions and
legacy FNV hashes after both files are replaced. The real-run summary was visually inspected.
Synthetic classifier/backend fixtures verify execution contracts, not physical accuracy; the
full manual family-validation suite and newer dependency checkout were not validated.

## 2026-08-15 material creation: a run that makes a new material

- **[landed] `examples/scenarios/glass_from_sand/glass_from_sand.js`.** Every other scenario simulates materials
  that exist at t=0. This one creates one: a crucible of silica sand, soda ash and limestone is
  held in a furnace until the carbonates calcine, the batch melts and silicate fusion produces
  soda-lime glass — an inventory that is exactly **zero in the first frame**. Geant4 builds and
  probes all four materials (the three raw components *and* the declared product, so the cascade
  can read the product's real composition); a nano→macro cascade turns those facts into this
  batch's calcination/melt/fusion onsets and its conduction coefficient — **no onset is typed into
  the scenario**; and three engine operators advance the crucible using the material class each
  cell holds *at that moment*: per-material thermal `ctx.evolve`, per-material discrete
  `ctx.react`, and per-pair-material `ctx.interact` conduction. Cells migrate
  `batch_solid → melt → glass`, so the selected operator changes as the run proceeds — the concrete
  case the [per-kind selection workstream](../../engine/inference/ROADMAP.md#workstreams-rotate-through-these-each-iteration-should-push-at-least-one) exists for.
- **[landed] Real stoichiometry, engine-enforced.** The declared channels are
  `Na2CO3 → Na2O + CO2`, `CaCO3 → CaO + CO2` and `6 SiO2 + Na2O + CaO → Na2O·CaO·6SiO2`, with
  Si/Na/Ca/C/O conservation vectors the engine validates *before* any inference, draw or mutation.
  The nominal 150-tick run creates 108 glass units from zero, releases 433 CO2, and closes with all
  five element balances exactly 0. Chemistry never fires below its inferred onset (coldest
  calcination 1139.8 K vs inferred 1132 K; coldest fusion 1430.0 K vs inferred 1414 K), the first
  glass appears at the bottom of the charge (10 mm) because heat only enters at the floor, five of
  the six material combinations actually conduct, and a formed glass cell — which has no declared
  chemistry left — is reported *unclaimed* rather than kept reacting.
- **[landed] Accounting and honesty.** The run reports 73,846 operator inferences plus 2 cascade
  stages = the engine's own `hook_predict_count` (73,848) with **zero** out-of-domain inferences;
  the models declare their intended operating range as mean/std, so a furnace run far outside it
  would be flagged rather than silently extrapolated. Guarded by the new
  `glass_from_sand_material_creation` validation case (20/20 checks) and registered in
  `tools/validation/js_law_audit.json` under a new **`operator_native`** status: the scenario was
  born operator-backed, so there is no teacher to retire and no reference switch to keep — and the
  audit test now *forbids* one for that status instead of requiring it.
- **[landed] The five per-material operators are now trained artefacts.** `physics_source`
  (`operator` promoted default / `reference` teacher) selects between the distilled family in
  `data/glass_furnace_operators_trained/` and the hand-authored illustrative family it came from.
  A deterministic harvest sideband (`emit_training_rows`) records the teacher's exact inputs and
  outputs — through `ctx.predict`, so no law is re-implemented in JS — for the states the run
  actually visits; five independent furnace operating points (1500/1600/1700-fine/1750/1880 K,
  8,528 / 2,927 / 3,515 rows per family) were fitted and two never-fitted ones
  (1820 K with a hotter ambient, 1560 K at a coarser discretisation, 757–2,211 rows) held out by
  **whole run**. Each committed model carries a measured meso hull, an occupancy histogram, its
  trained scale band and its held-out metrics; the paired
  `glass_operator_matches_reference` case passes 8/8 observer gaps and 22/22 trust checks (glass
  units, CO2, carbonates, first-glass tick and cell count identical; mean temperature within
  0.001 K), with exact run-level inference accounting (73,846 operator + 2 cascade = the engine's
  73,848) and zero out-of-domain inferences. The run stays byte-reproducible.
- **[honest reading] What the training did and did not buy.** The teacher is a hand-authored
  **linear** map, so a linear distillation reproduces it to ~1e-6 and its near-unit held-out R² is
  *expected* — it is evidence of migration fidelity, **not** of physical accuracy. What the trained
  family genuinely adds is the trust profile the illustrative maps could not have: a measured
  domain and occupancy taken from the states the system actually visits (so a furnace run outside
  them is flagged rather than silently extrapolated), a trained scale band, and carried held-out
  accuracy. Cell-to-cell conduction was deliberately **not** distilled: its law is exactly linear
  in the temperature difference, so a distilled twin would carry the same coefficient plus fit
  error and no new signal — both sources keep the reference conduction family and the summary says
  so.
- **[landed 2026-11-11] Conduction through a set network (opt-in).** `conduction_source`
  (`pair` default / `set_network`). The set path replaces the six per-pair-material maps by one
  DeepSets model per CELL material (`data/glass_furnace_conduction_set/`, generic_surrogate_v3)
  evaluated with `ctx.evolve` over the cell's face-neighbour set — present, temperature offset and
  one-hot material per neighbour, permutation invariant by construction. The models are distilled
  from the pair path's own per-cell conduction rates (`conduction_set_sample_<kind>` harvest rows,
  `tools/torch/build_glass_conduction_set_models.py`, every run recorded). At default conditions
  it matches the pair run's glass units (648), glass cells (72) and first-glass tick; mean T
  +0.98 K; the learned conduction's net heat is 0.29% of the heat it moves and is reported in the
  summary (`conduction.net_to_moved_ratio`). Guarded by `glass_set_conduction_matches_pair`
  (17/17). The pair path stays the default: it is exactly equal-and-opposite.
- **[open] Real measurements, not a distilled teacher.** The onsets, hazard slopes and
  conductances remain illustrative: nothing here is trained on measured calcination/fusion data.
  Closing that needs a harvested or literature-anchored panel over temperature, batch ratio and
  grain size, promoted through the same paired gate — and `data/glass_furnace_cascade/` (the two
  property stages) is still hand-authored too. Equal cell heat capacity is assumed, which is what
  makes conduction exactly equal-and-opposite.
