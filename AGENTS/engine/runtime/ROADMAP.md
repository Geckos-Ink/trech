# JavaScript host and live lab — roadmap

[Root principles](../../../AGENTS.md) · [Root roadmap](../../../ROADMAP.md) · [Parent](../ROADMAP.md) · [Handbook](AGENTS.md)

Maintain work in its owning branch. Dated results apply to the recorded checkout; they do not validate subsequent changes.

## Atomic stability research

- [x] First executable slice of [IASF](../../../docs/researches/atomic_stability_research.md):
  independent one-electron radial Coulomb solver in JS on installed Node/V8, reduced-mass
  center-of-mass removal, analytic validation, leading perturbative charge-radius component,
  separate mesh/box changes, and channel-resolved electronic binding with nuclear stability
  and widths left unknown. Bounded batches and runtime/source/input SHA-256 evidence support
  repeated experiments. See [usage and limits](../../../docs/atomic_stability.md).
- [x] Real-symmetric finite-basis eigensolver and Feshbach identity on supplied matrices,
  with residual/orthogonality telemetry, pole/conditioning rejection and projected-eigenproblem
  tests. This validates mathematical composition, not physical matrix elements.
- [x] Verification (2026-11-04): fresh Geant4-free Release build and CTest **38/38** pass;
  the five atomic gates also pass after adding host-independent and composition-CLI tests.
  Shipped hydrogenic batch and synthetic matrix requests execute through the C++ launcher.
  Hydrogen's default continuum-Coulomb discrepancy is about 0.000324 eV. This establishes
  the bounded matrix calculation/replay contract, not measured spectral accuracy. Full Geant4
  physics, native embedded-V8, Windows, and Studio suites were not run for this separate path.
- [ ] Finish Phase A: correlated/antisymmetrized two-electron helium with basis convergence;
  actual deuteron two-nucleon interaction and charge/current response rather than input mass;
  matched relativistic/QED corrections and independent NIST transition/isotope benchmarks.
- [ ] Implement the IASF resolution/matching/reference-subtraction ledger and physical nuclear/
  electronic basis construction, dynamic nuclear polarization, consistent thresholds/rest
  masses, open photon/weak channels, and validated transition matrix elements. No present
  lifetime, nuclear stability, molecular prediction, or new-theory claim follows from this slice.
- [ ] Establish quantitative basis/model/input-constant uncertainties and held-out predictive
  improvement. Mesh/box changes and the bisection bracket are not certified error bounds;
  small leading size terms remain numerically unresolved. Larger atoms, molecules, and all
  later research phases remain unimplemented. Integration into learned Geant4 cascades requires
  separate data lineage, training, validation, and strict-mode contracts.
- [ ] Validate cross-platform floating-point replay and deployable/relocatable research hosting.
  The optional C++ launcher uses configured Node/source paths; Windows launch code is untested.
  Full embedded-V8 TRECH host parity remains separate in the
  [dependency roadmap](../../tooling/dependencies/ROADMAP.md).

## Runtime cleanup and repeated inference work (2026-10-30)

- [x] Deterministic `ctx.rng.normal(mean=0,sigma=1)` uses Box–Muller with two draws from the
  existing hook stream and no cached spare. Finite numeric/nonnegative-sigma validation and
  zero-sigma calls consume no draws; overflow throws after sampling. Runtime tests cover mixed
  uniform/int/normal replay, fresh hosts, changed seed/event identity, exact draw consumption,
  defaults/scaling and distribution moments/tails. Studio completion exposes the implemented API.
  Verification (2026-11-04): Debug CTest 36/36 pass; the strengthened RNG gate also checks
  byte replay and overflow draw consumption. Two serial 24-event Geant4 runs match scores,
  viz scene/trajectories and normal-sample hook emits byte-for-byte, with zero model inferences
  and dropped emits. The full manual all-family physics suite was not rerun.
- [ ] Validate normal-sampling replay across platforms/toolchains: `log`, `sqrt` and `cos`
  currently use the platform C++ math library. Same-platform replay does not establish
  cross-platform byte identity.
- [x] Step context and run ID (2026-11-10): engine `onStep` dispatches expose track/parent IDs,
  particle, pre-step volume, post-step process, pre/post positions (mm), global times (ns) and
  kinetic energies (MeV) in `ctx.step`; `ctx.runtime.runId` carries `G4Run::GetRunID` (`null` for
  `onInit`). None of these enter `hashHookSeed`. `tests/test_js_runtime.cpp` checks absent detail
  on plain dispatches, every serialized field (including `null` process) and an identical
  `ctx.rng.uniform()` draw with/without detail. A real 1 MeV e- run shows step continuity
  (post point/time/energy of step n = pre of step n+1, `msc`/`eIoni` processes) and a replay with
  identical (sorted) emits; `geometry_procedural_assembly` uses it for a first-interaction tally.
  Studio completion lists the fields.
- [x] Track-start/end callbacks (2026-11-14). `onTrackStart` / `onTrackEnd` dispatch from a
  `TrechTrackingAction` installed only when one is registered, with `ctx.track` (`id`,
  `parentId`, `primary`, `particle`, `volume`, `process`, `positionMm`, `timeNs`,
  `kineticEnergyMeV`, `lengthMm`, `stepCount`) and their own guardrail `hooks.maxTrackCallbacks`
  (default 100000 per callback, serialized only when set). Counters appear in scores/provenance
  only when a track hook is registered, and the track ID enters `hashHookSeed` only for these
  dispatches, so all existing outputs are unchanged: `geometry_procedural_assembly` (which uses
  `onStep`) gives byte-identical scores and emits and the same config hash as the previous binary.
  `tests/test_js_runtime.cpp` checks every serialized field, `null` creator for primaries,
  `ctx.track` null and an unchanged seed in `onStep`, replay of an identical track dispatch and
  distinct streams per track; `test_config_roundtrip` checks the conditional key and clamping.
  Geant4 spot run (1.25 MeV gamma into water, 300 events, `threads: 1`, all three hooks): 461
  starts = 461 ends = the summed `ctx.event.totalTrackCount`, one primary per event, creator
  processes `compt` 147 / `eIoni` 9 / `eBrem` 4 / `phot` 1; for every track `stepCount` equals
  its `onStep` count and `lengthMm` its summed step lengths, and no track gains kinetic energy;
  a rerun gives byte-identical emits; `maxTrackCallbacks: 100` reports 100/461/361
  clamped/raw/dropped for each callback. Studio completion lists the hooks, `ctx.track` and the
  guardrail. Residual: multi-worker dispatch order inherits the strict-MT ordering gap below,
  and, like `maxStepCallbacks`, the guardrail compares each worker's own count to the cap; no example scenario uses the
  track hooks yet; no validation case grades them (the identities above are a spot run).
- [x] `JsRuntime` lazily constructs one ambient Geant4 seed per hook dispatch for all five
  inference entry points. Each caller copies it before overrides; new dispatches invalidate it.
  Point prediction relies on the surrogate's existing required-input validation. Shared stage
  training-property and string-array serializers preserve property order and null/absent metrics.
- [x] Joint-domain coverage standardizes inputs once and reuses prediction scratch in all three
  batched operators, retaining center order, early exits, distances and arithmetic. Removed the
  unused state-evolution field lookup, empty `TrechJsApi.cpp` translation unit, and redundant
  direct CMake link dependencies; all authoring bindings belong to `JsRuntime.cpp`.
- [x] Chemistry frame validation always calls the electronic-spectrum validator, including for
  absent/null spectra. Orphan occupied-energy components now fail at inspection. Its regression
  test checks rejection separately from valid-output assertions, eliminating a Debug JSON-key
  assertion and a Release false positive.
- [x] Verification: Debug/Release CTest 27/27 each; fresh Geant4-free Release build/CLI inspection
  and CTest 24/24. Old/new glass-furnace (551,979 inferences), single-model surrogate, serial strict
  transport and probability-reference runs preserve score/emit/viz bytes; provenance differs only
  in CLI/output paths. The probability and chemistry-mode validation scripts pass all 20 real
  Geant4 runs, including paired replay, strict inference gating, diagnostic isolation and zero
  dropped emits. The full manual all-family physics suite was not rerun.
  Coverage microbenchmarks (`-O2 -ffp-contract=off`, 81,920 mixed points per
  model, median of three trials) are 1.11×/1.24×/1.12× faster for the committed atomic response,
  molecular response and efflux transport models, with identical hashes of every diagnostic.
  These timings measure coverage alone, not whole-simulation speed.
- [x] Diagnose and remove the strict multi-worker transport discrepancy. Geant4 safety cached
  across events at a repeated source position made MSC choose worker-history-dependent branches
  despite identical per-event seeds. Strict runs with multiple actual workers now reset that
  geometry helper at event start, consuming no RNG. The manual worker gate checks 12 real runs
  (24 events each, Tasking/MT × two/eight workers × three repeats): event-id-keyed scores and full
  event/track-keyed trajectories match exactly across all configurations, with no inference or
  trajectory caps. True Serial and Tasking with one worker preserve five scientific artifact bytes
  and config hashes against the pre-fix binary. No dependency code/build was changed.
- [ ] Finish strict MT byte replay: deterministic run reduction and JSONL/viz append ordering
  remain open. Raw run totals still vary by floating-point merge rounding (~1e-14 in the tested
  track totals), and event/trajectory record order varies. The manual gate retains exact raw
  hashes/differences and `full_strict_byte_replay_established:false`; keyed physics equality is
  not the required byte-replay contract. Broader geometry/physics/source and platform coverage
  remains unvalidated. One-worker/true-serial behavior remains deliberately unchanged.
- [x] C++ filesystem fixtures now reserve unique directories atomically and clean up through
  RAII, including generated JS/model bundles. See the [validation workstream](../../tooling/validation/ROADMAP.md#completed-fixture-isolation).

## Cascade dependency trust (2026-11-02)

- [x] Effective cascade `inDomain` and hook out-of-domain accounting include consumed
  out-of-domain predictions, even when their values fit the next model's hull.
  `localInDomain` and sorted `upstreamOutOfDomainInputs` retain the distinction between numeric
  coverage and inherited evidence; local extrapolation distances stay local. Independent branches,
  clean overwrites and separate calls retain independent trust.
- [x] Starvation and off-band ancestry now cross the JS boundary through separate effective/local
  fields and sorted inherited input keys. Effective stage totals include these causes while OOD
  counts/resim routing retain their hull-only contract. Cross-call and persistent-state lineage
  remains in the [trust roadmap](../inference/trust/ROADMAP.md).

- [x] All five inference APIs report per-dispatch starvation and wrong-scale evaluation counts
  for the independent event resim policies. Tests cover cause overlap, multiplicity, inherited
  cascade evidence, strict/reset behavior and absent callbacks. OOD counts and existing prediction
  result payloads retain their contracts; see [trust routing](../inference/trust/ROADMAP.md).

## 2026-07-15 Studio fidelity, adaptive lab rounds, and liquid-pair checkpoint

- **[landed] Typed JavaScript scenario values and Studio override contract.** Scenarios can call
  `TRECH_VALUE.number/integer/boolean/string/choice` with defaults and UI metadata (groups, units,
  ranges, steps, choices). Ordinary `trech run` returns defaults; repeatable
  `--param name=<json>` values are type/range/choice validated in the QuickJS runtime before
  simulation. The Geant4-free `trech inspect` command evaluates the real scenario/includes and
  emits `{config,parameters}` for clients. Studio now uses that path for a right-sidebar Options
  panel and passes selections back on Run. Representative refraction, H2O-fluid, and CNT-fluid
  scenarios expose sizes/levels, temperatures, source and sampling controls without changing
  their defaults. Remaining visual scene-node mutation and live-lab reinitialization stay in the
  Studio M2 roadmap rather than being conflated with this authored override surface.
- **[landed] Medium/process-exact optical playback and precision reporting.** The trajectory
  recorder now emits each point's medium plus the Geant4 process/classified interaction ending
  the incoming segment. Studio distinguishes boundary refraction/world exit from true scattering,
  makes labelled air paths finer/translucent, and scales ribbon width/alpha with the sampled
  optical-track count so weak beams render tight and transparent. Preview inspector/status and
  capture JSON sidecars report MC events, trajectory sampling/caps, medium/process coverage,
  proportion standard errors, native spatial step, output raster and supersampling. Hollow
  Geant4 tubes now become true annular Studio meshes instead of placeholder solid cylinders.
  Loaded-vs-recorded tracks and exact render-segment budget truncation are disclosed too.
- **[landed] Adaptive real-time rounds in TRECH.** In `trech lab`, an omitted
  `simulate.events` measures actual wall time per completed round, updates an EWMA, and selects
  the next batch that fits `lab.targetHz`, within configured min/max bounds. Persistent
  `roundsPerTick` and per-command `simulate.events` overrides remain available. Machine-readable
  `lab_round_plan` telemetry and `lab.roundPlanner` snapshots expose actual/planned precision and
  throughput to Studio.
- **[landed, with mandatory uncertainty] Water + n-pentane beaker.**
  `beaker_water_n_pentane.js` uses Geant4 material/optics facts plus PubChem CID+SMILES only, then
  a two-stage scale cascade predicts colour, phase separation/layer order and the 60-minute
  evaporation endpoint for the declared beaker/air context. The lower stage now learns temperature
  from neighboring n-alkanes while holding n-pentane out at every temperature. At 303.15 K the
  held-out volatility gap is 6.3%; the inferred endpoint is 13.99% / 4.38 g evaporated with emitted
  fraction σ=0.08. Its 61 material-resolved frames now stage empty beaker → water pour → pentane
  pour → intermix/phase separation → moving/fading plume, and retain physical time beside an
  explicit 545× playback clock. The refreshed `beaker_water_pentane.gif` uses labelled blue/gold
  display tints while leaving cascade-driven layout and evaporation untouched.
- **[ ] Widen the liquid-pair/evaporation training domain before metrology claims.** Replace the
  compact illustrative macro response surface with a harvested panel spanning polarity,
  temperature, open-surface geometry, airflow/boundary layers and multiple liquid pairs; hold out
  whole substances/pairs, calibrate uncertainty, and keep runtime reference properties forbidden.
  Also close the current n-pentane derived-index residual (n≈1.218 vs validation-only 1.358)
  through the generic optics training path rather than injecting the handbook value.
- **[ ] Persist/adapt lab timing priors by stable config signature only if startup latency matters.**
  The landed planner learns the active scenario online and reacts to patches, but starts each lab
  process from the configured `run.nEvents`. A future cache must be optional, provenance-visible,
  machine-local, invalidated by config/engine changes, and must never be mistaken for physics ML.
- **[partial: compatible-batch kernel reuse landed] Finish safe live reconfiguration in
  `trech lab`.** `GeantLabRunner` now initializes Geant4 once and reuses it for later compatible
  `BeamOn` batches; event-count/seed/planner changes are allowed, every batch receives its own
  canonical config hash, and an exercised 25 / adaptive-1 / explicit-5 sequence completed without
  the Geant4 UI-singleton teardown crash. Kernel-bound patches (geometry, beam, physics, scoring,
  output) now fail explicitly and require a lab restart. Remaining: classify cheap beam edits,
  implement/test safe geometry/physics reinitialization without stale material/action state, and
  wire that restart/reinitialize handshake through Studio before claiming arbitrary live editing.
  Lab remains stdin/JSONL-driven; Geant4 macro/UI flags are deliberately run-mode-only rather
  than pretending they compose with the persistent command loop.
