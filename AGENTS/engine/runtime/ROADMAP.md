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

- [ ] Extended hook context remains unimplemented: track-start/end callbacks and track context,
  run IDs, step positions/times and `rng.normal()` are absent from the executable API. Their
  earlier draft documentation was corrected; any future addition needs explicit deterministic
  serialization, dispatch/replay tests and output contracts rather than autocomplete-only claims.
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
- [ ] Existing default-thread strict replay gap: repeated `hello_world.js` runs with the same
  pre-cleanup binary and seed produced primary track totals 43.83843135088059 / 43.49945092979526 mm;
  the updated binary also varies. The serial (`run.threads:1`) old/new comparison matches exactly.
  Diagnose default Geant4 MT seeding/replay with the local dependency build; strict byte replay
  remains the required contract, not established by passing inference tests.
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
