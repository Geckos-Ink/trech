# TRECH — AI Agent Reference

TRECH is a **C++/Geant4 simulation and learning toolkit**: experiments are authored in
**JavaScript** (QuickJS), which computes and composes a config that is handed as JSON to a
**deterministic-by-default C++ runtime** that drives Geant4 and writes a provenance-first data
trail. Its reason to exist is the **multi-scale inference cascade** — take a precise Geant4
particle/nano base and lift its behaviour, via statistical/ML inference, *scale by scale up the
dimension ladder* (atomic → nano → micro → meso → macro) to the scale a human observes.

This file is the fast-access operational map for agents. It is not the README (user-facing) and
not a changelog (git owns chronology). Maturity: **active H2O/optics baseline** with landed
tracks for fluids, chemistry cycles, biology, CNT electronics, magnetic resonance/MRI, analytic
cross-checks, the ML cascade, and a desktop UI ([`studio/`](studio/)).

**What TRECH is NOT:** it is **not a classical-formula physics engine** — closed-form laws are
*comparison/validation references only* and MUST NOT drive scenario behaviour unless explicitly
documented as an analytic cross-check. Hook-layer MD/Bloch/fluid solvers are labelled "physics
for comparison," not Geant4 results. [`studio/`](studio/) is a **viewer/client, never a second
physics engine**. A `predictive`-mode inferred result is never a strict Geant4 tally.

> ## ⭐ The one thing to know — the engine thesis (do NOT let this get lost)
>
> **TRECH exists to take a precise Geant4 particle/nano base and lift its behaviour, via
> statistical/ML inference, SCALE BY SCALE up the dimension ladder
> (atomic → nano → micro → meso → macro) until it reaches the scale of the
> observer/experiment.** So a user can pose a macroscopic question — *"what does this glass of
> water do while I stir it: the fluid motion, the waves?"* — and get it **inferred from the
> microscopic truth**, without hand-specifying every intermediate model (only overriding when
> they *want* to be specific).
>
> Consequence for every ML change: statistics/ML must trend toward a **general-purpose,
> context-driven inference cascade**, NOT a handful of narrow point-predictors bolted onto
> specific outputs. If a scenario had to *specify* a prediction the engine could have *inferred
> from context*, that is a gap to close. Full doctrine: [Essential principles](#essential-project-principles)
> → *Multi-scale inference cascade*; standing objective in [`ROADMAP.md`](ROADMAP.md). Engine
> today: `ScaleCascade` + `ctx.cascade` (chains scale-tagged models) and `GenericSurrogate` +
> `ctx.predict` (single models). This callout is deliberately redundant with those sections so
> the thesis survives even if one place is trimmed — keep it.

## Read order and sources of truth

Authority order when sources disagree (inspect and fix the mismatch within task scope, updating
stale docs in the same change; if unsafe to resolve, record it as a gap and ask):

1. **Honesty + engine-thesis principles** (this file's [Essential principles](#essential-project-principles)) — a running result never overrides "grade the gap / Geant4 is the base of truth."
2. **Executable specs & tests** — [`docs/output_schema.md`](docs/output_schema.md) (output contracts), [`tests/`](tests/) (esp. `test_config_roundtrip.cpp`), [`CMakeLists.txt`](CMakeLists.txt).
3. **Current C++ source** under [`src/`](src/) + [`include/trech/`](include/trech/) and build config.
4. **User docs** — [`README.md`](README.md), [`CHARTS.md`](CHARTS.md) (Mermaid dataflow), [`docs/structure.md`](docs/structure.md), [`docs/scenario_hooks.md`](docs/scenario_hooks.md), [`docs/viz_refraction.md`](docs/viz_refraction.md).
5. **Roadmaps / backlog / validation reports** — [`ROADMAP.md`](ROADMAP.md) (editable source of truth), [`docs/validation_report.md`](docs/validation_report.md) + [`docs/validation_summary.md`](docs/validation_summary.md), [`studio/AGENTS.md`](studio/AGENTS.md) + [`studio/ROADMAP.md`](studio/ROADMAP.md). [`docs/trech-roadmap.md`](docs/trech-roadmap.md) is the **reference-only** initial concept (do not edit).
6. **Historical notes & git history** — the full chronology of landed work (this file records current state, not the timeline).

Rules: a roadmap does not prove a feature exists; a README does not prove a command still works;
a test proves only what it asserts.

## Collaboration and maintenance rules

- **Update markdowns as you go.** Every action that changes durable facts updates the fast-access
  references — this `AGENTS.md`, [`README.md`](README.md), [`ROADMAP.md`](ROADMAP.md), and
  [`CHARTS.md`](CHARTS.md) when architecture / dataflow / Geant4 integration changes. Studio work
  also updates [`studio/AGENTS.md`](studio/AGENTS.md) + [`studio/ROADMAP.md`](studio/ROADMAP.md).
- **Track every unfinished edge in the applicable `ROADMAP.md`** (residual, scaffold, missing
  validation/coverage, TODO) **in the same change**. Never leave unfinished work discoverable
  only from code comments or handoff prose.
- **"Implementation" means C++ source changes under [`src/`](src/)** (high priority);
  documentation-only updates do not count as implementing a roadmap item.
- **Predictions come from Geant4-driven data + learned/validated inference**, not fixed classical
  formulas. Formulas are comparison/validation only unless documented as an analytic cross-check.
- **Generated / runtime data is not source.** Everything under `build/` is gitignored and
  local-only; the engine emits run outputs (`trech_*.jsonl`, `trech_viz_*`) into a `--output`
  dir. `data/` cascade/ridge models ARE committed source of truth. Note: `trech_provenance.jsonl`
  / `trech_scores.jsonl` at the repo root are **tracked committed sample outputs** (a normal run
  targets a `--output` directory, not the repo root) — treat them as regenerable artefacts, not
  authoritative source, and don't wire tooling to them.
- **Determinism & honesty are visible.** Keep strict runs byte-reproducible; label inferred /
  hook-layer / rendering-choice results as such and measure the gap-to-truth.
- **Geant4:** check for a local clone at [`thirds/geant4`](thirds/geant4) before asking for it;
  never write absolute Geant4 paths in-repo (use `thirds/geant4-build`/`-install` or
  `build/geant4-build`/`-install`). Keep vendored deps current (see the standing dep-refresh note
  in [`ROADMAP.md`](ROADMAP.md); rebuilds are heavy — confirm before a bump).

## Essential project principles

Each principle is concrete enough to reject a wrong implementation. They decide every ML/optics/
config decision.

### Multi-scale inference cascade (the core thesis)

Geant4 gives ground truth at the particle/nano scale (cross sections, energy deposition,
composition, transport). The engine **learns the map from that base to the next scale up, then
chains those maps** to the observer scale:

```
Geant4 particle/nano facts
        │  (surrogate trained on Geant4 output)
        ▼   atomic → nano → micro → meso → macro
  material/bond   device   cell    droplet   glass-of-water / experiment
```

- Each arrow is a **scale-tagged statistical model** (`models: [{name, path, scale}]`) whose
  outputs become the next model's inputs. The engine chains them automatically
  (`ScaleCascade` + `ctx.cascade`), seeding the bottom from Geant4-derived facts and reading the
  top. The user declares *which* models exist and *at what scale*; the engine orders and plumbs.
- **General-purpose, not per-output.** The standing direction is an inference layer that, given a
  context, predicts the relevant behaviour **by default**. Treat "the user had to specify a
  prediction the engine could have inferred from context" as a gap to close.
- **Not an optics feature.** The cascade is physics-agnostic and must serve *every* family —
  fluids, chemistry, biology, CNT electronics, magnetic resonance — not just optics (the one with
  a pre-existing validated surrogate). When you grow it, rotate across families rather than piling
  onto optics.

### Geant4 is the base of truth; classical formulas are for comparison

The precise base is real; higher scales are *learned/validated predictions* and MUST be labelled
so (the "physics for comparison" discipline). Never present an inferred macro result as if Geant4
computed it directly. Analytic cross-checks feed classical formulas **from Geant4's own
particle-level data** and compare — they never calibrate the physics derivation.

### Determinism is explicit; strict mode disables inference

`determinism.mode` is `strict` or `predictive`. Strict runs are byte-reproducible and **disable
all model inference** (`ctx.predict` and `ctx.cascade` return `null`); `predictive` enables it
with provenance capture. Log stage/predict counts.

### Physics-agnostic C++; physics lives in JS

No domain switch (H2O/CNT/MRI/…) enters C++. Scales are ordered band names; models carry their
own named IO; scenarios declare physics classes/properties/extensions in JS. Keep the
JS → JSON → C++ boundary stable; hooks are a deterministic sideband, never direct Geant4 access.

### Provenance-first & reproducible

Every run writes config JSON + hash + seed + Geant4/runtime versions + determinism mode + hook/
stratify/predict counters to [`trech_provenance.jsonl`](docs/output_schema.md). New config fields
are **conditionally serialized** so byte-identical config hashes hold for scenarios that don't use
them (round-trip in [`tests/test_config_roundtrip.cpp`](tests/test_config_roundtrip.cpp)).

## Critical implementation contracts

Named invariants with their enforcing code and tests. Violating one silently corrupts
reproducibility or physics honesty.

- **Strict mode disables `ctx.predict`/`ctx.cascade`.** Both return `null` outside `predictive`
  mode. Enforced in [`src/js/JsRuntime.cpp`](src/js/JsRuntime.cpp); counted as `hook_predict_count`
  (a K-stage cascade = K predictions). Tests: [`tests/test_js_runtime.cpp`](tests/test_js_runtime.cpp).
- **Accumulating hook scenarios MUST set `run.threads: 1`.** Hook-layer state that grows across
  events (MD baths, Bloch, reaction ledgers, fluid solvers) is non-reproducible under Geant4 MT
  because worker event-completion order varies. This is the single most common determinism bug.
- **New config fields are conditionally serialized.** Emit a field only when non-default so config
  hashes stay byte-identical for scenarios that don't use it (`materialProbe`, `analytic.checks`,
  `models[].scale`, beam spread/polarization/spectrum, `run.threads`, …). Enforced in
  [`src/core/Config.cpp`](src/core/Config.cpp); round-trip in [`tests/test_config_roundtrip.cpp`](tests/test_config_roundtrip.cpp).
- **Post-`Initialize` carriers are pre-allocated before `SetUserInitialization`.** `derivedOptics`,
  `analyticChecks`, `materialProbes` are `shared_ptr` carriers on `RunOptions` filled after Geant4
  `Initialize` (tables built) in [`src/sim/GeantRunner.cpp`](src/sim/GeantRunner.cpp) and paired
  with the measured tally in `RunAction::EndOfRunAction`. A copy made before the carrier exists
  sees null — allocate first.
- **VizRecorder records the *outgoing* momentum direction.** Each point's `dx/dy/dz` is its
  outgoing segment's direction: post-step points carry the post-boundary (refracted/reflected)
  direction; the birth point uses `GetPreStepPoint()->GetMomentumDirection()` (not the track's
  post-step `dir`, which mis-records emission for a photon that interacts on step 1). See
  [`src/sim/VizRecorder.cpp`](src/sim/VizRecorder.cpp).
- **Trajectory consumers must not infer scattering from a visible bend.** Points carry the Geant4
  `process`/classified `interaction`; scatter emphasis requires the recorded `scatter` class.
- **Material number density = proton density for ¹H.** `ctx.materials["…"].numberDensityPerCm3.H`
  is atoms/cm³ from the constructed `G4Material`; scenarios read Geant4 composition instead of
  hard-coding it. [`src/sim/MaterialProbe.cpp`](src/sim/MaterialProbe.cpp), opt-in via
  `materialProbe.{enable,materials}`.
- **`viz_*` tags never alter Geant4 transport.** Visualization-only forcing (`viz_forced_white`/
  `viz_emitter` in C++; `viz_*` render hints consumed by Studio) is a rendering choice, labelled
  as such.
- **Feature/composition schemas stay in lock-step** across C++, the Python trainers, and
  [`tools/torch/trech_torch/dataset.py`](tools/torch/trech_torch/dataset.py): event features
  `FeaturePipeline::kSchemaId` (`trech_event_features_v1`) and optics `kCompositionElements`
  (14 slots incl. `I` + density). `OpticsSurrogate::encodeComposition` renormalises all 14 slots.
- **MT-safe run-level tallies use Geant4 accumulables.** Event feature moments and primary tallies
  merge through accumulables so worker events cannot vanish from the summary (`event_feature_stats`
  runs unconditionally now). Integer per-primary counts (uncollided, photoelectric-first) are
  MT-order-independent and reproducible without `threads:1`.
- **Custom materials fail-safe, never half-build.** `buildCustomMaterials`
  ([`src/sim/DetectorConstruction.cpp`](src/sim/DetectorConstruction.cpp)) resolves every
  component up front, mass-fraction-renormalizes over what resolved, and warns+skips unresolvable
  components rather than constructing a malformed `G4Material` (which crashed Geant4 table
  builders — e.g. there is no `G4_SODIUM_CHLORIDE`, so build NaCl from `element` symbols).

## Architecture and data/control flow

```
JS experiment (TRECH_CONFIG / TRECH_HOOKS / TRECH_VALUE / TRECH_FLOW / TRECH_INCLUDE)
      │  JsRuntime.evalExperimentAndGetConfigJson  (QuickJS)
      ▼
  config JSON ──► TrechConfig (configFromJsonString) ──► RunOptions overrides
      │
      ▼   runGeant4():  RunManager ─► DetectorConstruction + PhysicsList(QBBC) + ActionInitialization ─► Initialize ─► BeamOn
      │                     │ hooks dispatched via JsRuntime (onInit/onRun/onEvent/onStep) with deterministic ctx
      ▼
  outputs (--output dir):  trech_scores.jsonl · trech_provenance.jsonl · trech_event_scores.jsonl
                           trech_hook_emits.jsonl · trech_viz_scene.json · trech_viz_trajectories.jsonl
      │
      ├──► tools/viz (PyVista) + tools/viz/demos (README media)
      ├──► studio/ (PySide6 + wgpu viewer/editor)
      └──► tools/validation (regression report) · tools/torch (harvest → train → TorchScript/JSON models → data/)
```

Real-time path: `trech lab` runs a persistent process reading `{"action":…}` JSONL on stdin
(`patch`/`simulate`/`snapshot`/`help`/`quit`), reusing the Geant4 kernel across compatible
batches and writing snapshot + `lab_round_plan` telemetry JSON. Full Mermaid diagrams:
[`CHARTS.md`](CHARTS.md).

## Linked source tree and file reference

Search a filename here to find its owner, key symbols, tests, and the mistake most likely to
cause a regression. Repetitive leaf collections (scenarios, Python packages, docs, data) get
grouped linked subsections; entry points, engine files, and registries get their own.

### C++ engine — `trech_core` ([`src/core/`](src/core/), [`include/trech/core/`](include/trech/core/))

#### [`src/core/Config.cpp`](src/core/Config.cpp) · [`Config.hpp`](include/trech/core/Config.hpp)

Owns `TrechConfig` and all config JSON (de)serialization. Change here for the config surface,
new collections, and conditional serialization.

- **Key symbols:** `TrechConfig` (the whole config tree: `run`/`determinism`/`detector`/`beam(s)`/
  `optics`/`materials`/`geometry`/`hooks`/`models`/`materialProbe`/`analytic`/`nuclear`/`stratify`/
  `viz`/`lab`/`system`/`multiscale`); `configFromJsonString`; `configToJson`. Collections normalize
  single-or-array; `environment`/`medium` alias `detector` at parse time (canonical output stays
  `detector`).
- **Tests:** [`tests/test_config_roundtrip.cpp`](tests/test_config_roundtrip.cpp) (byte-stable hashes).
- **Common mistakes:** unconditionally serializing a new field breaks every scenario's config hash;
  gate it on non-default and extend the round-trip test.

#### [`src/core/RunOptions.cpp`](src/core/RunOptions.cpp) · [`RunOptions.hpp`](include/trech/core/RunOptions.hpp)

CLI parsing and run-time option carrier. Owns the command dispatch surface.

- **Key symbols:** `enum class CliCommand { Run, Inspect, Lab }`; `RunOptions` (carries
  `command`, paths, seed/events overrides, `scriptParameterOverrides`, hook counters, the
  post-`Initialize` carriers `analyticChecks`/`derivedOptics`/`materialProbes`, `hookRuntime`);
  `parseRunOptions`; `runUsage`; `applyRunOverrides`.
- **Tests:** [`tests/test_cli_parse.cpp`](tests/test_cli_parse.cpp).

#### [`src/core/LabSession.cpp`](src/core/LabSession.cpp) · [`LabSession.hpp`](include/trech/core/LabSession.hpp)

Owns the real-time `trech lab` protocol (no Geant4 dependency; the runner calls it).

- **Key symbols:** `LabSession::applyCommandJson` (parses `patch`/`simulate`/`snapshot`/`help`/
  `quit`), `observeSimulation` (feeds the wall-seconds/round EWMA), `roundTelemetryJson`
  (`lab_round_plan`), `config`. Omitted `simulate.events` → EWMA picks a count fitting
  `lab.targetHz`, bounded by `min/maxRoundsPerTick`.
- **Tests:** [`tests/test_lab_session.cpp`](tests/test_lab_session.cpp).

#### [`src/core/Provenance.cpp`](src/core/Provenance.cpp) · [`Provenance.hpp`](include/trech/core/Provenance.hpp)

Writes `trech_provenance.jsonl` (config JSON/hash, seed, Geant4/runtime metadata, determinism
mode, stratify model hash, hook/patch/emit/predict counters, event moment summaries).

- **Tests:** [`tests/test_provenance_writer.cpp`](tests/test_provenance_writer.cpp).

### C++ engine — `trech_js` ([`src/js/`](src/js/), [`include/trech/js/`](include/trech/js/))

#### [`src/js/JsRuntime.cpp`](src/js/JsRuntime.cpp) · [`JsRuntime.hpp`](include/trech/js/JsRuntime.hpp)

The QuickJS host: evaluates experiments, dispatches hooks, and owns the `ctx.*` surface and the
`GenericSurrogate` model registry. **This is where the cascade/predict hook-layer entry points
live.** Change here for the authoring runtime and the JS → JSON boundary.

- **Key symbols:** `evalExperimentAndGetConfigJson` (runs the JS, returns config JSON);
  `dispatchHook("onInit"|"onRun"|"onEvent"|"onStep", …)` → `HookDispatchReport` (patch/emit/
  predict counts); `setScriptParameterOverrides` / `scriptParametersJson` (the `TRECH_VALUE` /
  `trech inspect` / `--param` path); `loadedModelNames`; **`buildAmbientGeant4Seed`** (auto-seeds
  the bottom of the cascade from real Geant4 per-event tallies + `material.*`/`optics.*` probes
  when `ctx.cascade()` is called with no argument). `ctx.predict(name, features)` and
  `ctx.cascade(seed?) -> {...context, __cascade}` are implemented here.
- **Tests:** [`tests/test_js_runtime.cpp`](tests/test_js_runtime.cpp) (includes two-stage
  `ctx.cascade`, ambient-seed case, `TRECH_INCLUDE` error filenames/lines, `TRECH_FLOW`).
- **Common mistakes:** enabling inference in strict mode; forgetting predict-count plumbing.

#### [`src/js/TrechJsApi.cpp`](src/js/TrechJsApi.cpp)

The C-function bindings for the JS globals/`ctx` surface (`TRECH_CONFIG`/`TRECH_HOOKS`/
`TRECH_VALUE`/`TRECH_FLOW`/`TRECH_INCLUDE`, `ctx.emit`/`rng`/`event`/`materials`/`optics`/
`predict`/`cascade`). Add a new authoring primitive here + its JsRuntime wiring.

### C++ engine — `trech_ml` ([`src/ml/`](src/ml/), [`include/trech/ml/`](include/trech/ml/))

All ML degrades gracefully without LibTorch: the two learned inference paths carry a LibTorch-free
`.json` backend chosen by file extension, so Geant4-trained models run in a stock build.

#### [`src/ml/ScaleCascade.cpp`](src/ml/ScaleCascade.cpp) · [`ScaleCascade.hpp`](include/trech/ml/ScaleCascade.hpp)

The core-doctrine engine: chains scenario-declared `scale`-tagged `GenericSurrogate` models
(ascending `atomic/nano/micro/meso/macro`, unscaled runs last) in one deterministic pass. Each
stage reads named inputs from the current context (seed + lower stages' outputs), predicts, and
merges outputs back. Non-owning over the `JsRuntime`'s registry.

- **Key symbols:** the chaining pass returning the flat augmented context + reserved `__cascade`
  (`stagesRun`, `stagesExtrapolating`, per-stage `trace` of `{model, scale, ran, missingInputs,
  outputs, inDomain, domainMeasured, extrapolation, maxStandardizedDeviation, outOfDomainInputs}`,
  `seedKeys`). Per-stage **training-domain coverage** (workstream 3) flags a stage predicting
  outside the region its model was trained on so a low-confidence extrapolation is surfaced, not a
  silent guess; the flag propagates up the ladder.
- **Tests:** [`tests/test_scale_cascade.cpp`](tests/test_scale_cascade.cpp) (ordering/missing-input,
  per-stage coverage in/out-of-domain + `stagesExtrapolating`, Geant4-free) + JS-boundary case in
  `test_js_runtime.cpp`.

#### [`src/ml/GenericSurrogate.cpp`](src/ml/GenericSurrogate.cpp) · [`GenericSurrogate.hpp`](include/trech/ml/GenericSurrogate.hpp)

Scenario-agnostic named-IO learned inference. Portable `generic_surrogate_v1` JSON feed-forward
(LibTorch-free; also loads `ridge_optics_n_v1`/`logistic_stratifier_v1`; optional `.pt`). Each
cascade stage and every `ctx.predict` is one of these.

- **Key symbols:** `predict`/`predictVector`; `coverage(inputs) -> {inDomain, domainMeasured,
  extrapolation, maxStandardizedDeviation, outOfDomainInputs}` — the training-domain check that
  grounds the cascade's low-confidence flag. It compares each input's standardized deviation
  `|z|=(x-mean)/std` against the trained hull edge (`input_domain.standardized_radius` in the model
  JSON, or a heuristic `kDefaultStandardizedDomainRadius`=3σ when absent → `domainMeasured:false`).
- **Tests:** [`tests/test_generic_surrogate.cpp`](tests/test_generic_surrogate.cpp) (feed-forward +
  coverage measured-vs-heuristic + missing-input-out-of-domain). Trainer:
  [`tools/torch/trech_torch/train_surrogate.py`](tools/torch/trech_torch/train_surrogate.py)
  (exports `input_domain.standardized_radius`, the per-feature trained hull, so new stages carry a
  measured domain).

#### [`src/ml/OpticsSurrogate.cpp`](src/ml/OpticsSurrogate.cpp) · [`OpticsSurrogate.hpp`](include/trech/ml/OpticsSurrogate.hpp)

Composition → refractive index surrogate (TorchScript `.pt` **or** ridge `.json`). Predicts `n`
only (abs/scat carry a negative "not predicted" sentinel so the caller keeps extractor values).
Opt-in via `optics.derive.surrogateModelPath`; leave-one-out validated, off by default.

- **Key symbols:** `encodeComposition` (renormalises all 14 `kCompositionElements` slots, matching
  the Python harvester); `kCompositionElements`.
- **Tests:** [`tests/test_optics_surrogate.cpp`](tests/test_optics_surrogate.cpp). Committed model:
  [`data/optics_surrogate_ridge.json`](data/optics_surrogate_ridge.json).

#### [`src/ml/TorchScriptStub.cpp`](src/ml/TorchScriptStub.cpp) · [`Stratifier.cpp`](src/ml/Stratifier.cpp) · [`FeaturePipeline.cpp`](src/ml/FeaturePipeline.cpp) · [`OnlineEventStats.cpp`](src/ml/OnlineEventStats.cpp)

Event stratification stack. `FeaturePipeline` owns the frozen feature schema (`kSchemaId` =
`trech_event_features_v1`, `FeatureNames`); `Stratifier` labels events predictable/exceptional;
`TorchScriptStub` is its model backend (`.pt` or logistic `.json`, validated against
`FeatureNames` at load); `OnlineEventStats` is the Welford/vectorized-Torch accumulator.
[`EventFeatures.hpp`](include/trech/ml/EventFeatures.hpp) is the shared snapshot struct.

- **Tests:** [`tests/test_stratifier.cpp`](tests/test_stratifier.cpp).

### C++ engine — `trech_chem` ([`src/chem/`](src/chem/))

#### [`src/chem/DnaChemistry.cpp`](src/chem/DnaChemistry.cpp) · [`DnaChemistry.hpp`](include/trech/chem/DnaChemistry.hpp)

Geant4-DNA EM/chemistry bridge, gated behind `chemistry.enable` + `TRECH_ENABLE_DNA_CHEM`;
`chemistry.solver` (non-`stub`) enables the chemistry stage.

- **Tests:** [`tests/test_dna_chemistry_bridge.cpp`](tests/test_dna_chemistry_bridge.cpp).

### C++ engine — `trech_sim` ([`src/sim/`](src/sim/), Geant4-gated by `TRECH_ENABLE_GEANT4`)

Canonical Geant4 wiring order: RunManager → DetectorConstruction + PhysicsList(QBBC) +
ActionInitialization → Initialize → BeamOn. Only compiled when Geant4 is found.

#### [`src/sim/GeantRunner.cpp`](src/sim/GeantRunner.cpp) · [`GeantRunner.hpp`](include/trech/sim/GeantRunner.hpp)

Owns the RunManager lifecycle. `runGeant4(cfg, options, argc, argv)` is the run entry; the
`GeantLabRunner` reuses the kernel across compatible `BeamOn`s for `trech lab`. Pre-allocates the
post-`Initialize` carriers and calls `SetBuildCSDARange(true)` only when a `csda_range` check is
configured. `SetNumberOfThreads` when `run.threads > 0`.

#### [`src/sim/DetectorConstruction.cpp`](src/sim/DetectorConstruction.cpp) · [`PrimaryGeneratorAction.cpp`](src/sim/PrimaryGeneratorAction.cpp)

Geometry/materials and the beam source. `buildCustomMaterials` fail-safes custom mixtures (see
contracts). `TrechPrimaryGeneratorAction` owns beam sampling: `beam.spread`
(spot/divergence/energy), `beam.polarization` (optical photons only; kills `ZeroPolarization`),
and `beam.spectrum` (weighted line list) — all conditionally serialized and reproducible under a
fixed seed.

#### [`src/sim/RunAction.cpp`](src/sim/RunAction.cpp) · [`EventAction.cpp`](src/sim/EventAction.cpp) · [`SteppingAction.cpp`](src/sim/SteppingAction.cpp) · [`ActionInitialization.cpp`](src/sim/ActionInitialization.cpp)

Per-run/event/step Geant4 user actions. `RunAction::EndOfRunAction` pairs analytic predictions
with measured tallies and merges accumulables (`AddPrimaryTrackLength` etc.); `SteppingAction`
tracks per-primary fate (`primaries_uncollided`, `primary_mean_track_length_mm`,
`primaries_photoelectric_first_fraction` — classified via `G4GammaGeneralProcess` sub-process EM
subtype) and pushes trajectory points into the `VizRecorder`.

#### [`src/sim/MolecularOptics.cpp`](src/sim/MolecularOptics.cpp) · [`AnalyticCrossCheck.cpp`](src/sim/AnalyticCrossCheck.cpp) · [`MaterialProbe.cpp`](src/sim/MaterialProbe.cpp) · [`VizRecorder.cpp`](src/sim/VizRecorder.cpp)

The Geant4-data extraction surfaces:
- **MolecularOptics** — derives n/absorption/scatter from `G4EmCalculator` cross sections (photo +
  Compton + Rayleigh) via Beer-Lambert + discrete Kramers-Kronig; anchor-free (`optics.derive`).
- **AnalyticCrossCheck** — `evaluateBeerLambert` / `evaluateCsdaRange` / `photo_fraction` (shared
  `fillAttenuationBreakdown`); each pairs a closed-form prediction from Geant4's own data with a
  measured tally via `AnalyticCheckResult.measuredField` (new check types stay data-driven).
- **MaterialProbe** — reports Geant4's known composition per material → `ctx.materials` +
  `material_probes` (opt-in, mirrors the analytic-carrier pattern).
- **VizRecorder** — singleton trajectory recorder (single mutex, workers push, master flushes on
  `EndOfRunAction`); the outgoing-direction rule above lives here.

#### [`src/sim/NuclearCycleAnalyzer.cpp`](src/sim/NuclearCycleAnalyzer.cpp) · [`MultiscaleBridge.cpp`](src/sim/MultiscaleBridge.cpp)

Nuclear cycle Q-value/conservation analysis (`nuclear.enable` + `nuclear.cycles`) — tests:
[`tests/test_nuclear_cycle_analyzer.cpp`](tests/test_nuclear_cycle_analyzer.cpp). `MultiscaleBridge`
is stubbed behind `multiscale.enable` and does not alter physics yet (**Known gap**).

### Entry point & build

#### [`apps/trech-cli/main.cpp`](apps/trech-cli/main.cpp)

The `trech` executable. `main` parses options, then dispatches: `Lab` → `runLabSession` (JSONL
loop, `GeantLabRunner`); `Inspect` → prints `{config, parameters}` JSON; `Run` → eval JS,
`onInit` hook, `applyRunOverrides`, `runGeant4`. Geant4-free builds parse config and exit OK.

#### [`CMakeLists.txt`](CMakeLists.txt) · [`cmake/`](cmake/) · [`CMakePresets.json`](CMakePresets.json)

Targets: `trech_core` → `trech_ml`/`trech_chem`/`trech_js` → `trech_sim` (Geant4-gated) → `trech`.
Helpers: [`cmake/TrechOptions.cmake`](cmake/TrechOptions.cmake) (the `TRECH_ENABLE_*` options),
[`cmake/TrechWarnings.cmake`](cmake/TrechWarnings.cmake), [`cmake/TrechFindOrFetch.cmake`](cmake/TrechFindOrFetch.cmake)
(QuickJS/json vendor-or-fetch). Presets `dev` (Debug, `build/dev`) and `rel` (Release,
`build/rel`), both `TRECH_ENABLE_GEANT4=ON` + `TRECH_FETCH_DEPS=ON`.

### JS scenarios & helpers — [`examples/experiments/`](examples/experiments/)

The physics content: scenarios set `TRECH_CONFIG` (+ optional `TRECH_HOOKS`). The shipped set
doubles as the manual regression corpus and as Studio's test tree. Shared modules:
[`trech_helpers.js`](examples/experiments/trech_helpers.js) (constants, `spectra`,
`helpers.beamProfiles.spread` presets) and [`trech_water_md.js`](examples/experiments/trech_water_md.js)
(`TRECH_WATER_MD.create(cfg)` — the shared rigid-SPC/E MD core: force loop, SHAKE/RATTLE,
velocity-Verlet; both bulk water and the D(T) sweep build on it). Families (see
[Features](#features-and-recurring-development-pitfalls) for behavior/status):

| Family | Canonical scenarios | Guard (category) |
| --- | --- | --- |
| Fluids / H₂O MD | `h2o_molecule_stability`, `h2o_cluster_fluid`, `h2o_bulk_water`, `h2o_diffusion_temperature`, `glass_of_water_shaken`, `lava_lamp` | `*_stable`/`*_structure`/`*_trend`/`glass_of_water_shaken_waves`/`lava_lamp_inferred_thermofluid` (`fluid`) |
| Optics | `viz_refraction_demo`, `validation_glass_of_water`, `glass_of_water_varied`, `glass_of_water_spectral`, `optics_surrogate_demo` | glass-of-water + `optics_surrogate_transport_applied` |
| Chemistry cycles | `testscenario_h2o_electrolysis_combustion`, `config_nitrogen_carbon_cycle` | `h2o_electrolysis_combustion_cycle`, nuclear cycle checks |
| Biology / membranes | `testscenario_efflux`, `testscenario_osmotic`, `testscenario_pascal` | `efflux_first_order_kinetics`, `osmotic_shift_observed`, `pascal_principle_holds` |
| CNT electronics | `cnt_band_structure`, `cnt_logic_gates` (+ `config_cnt_*_stub`) | `cnt_band_structure`, `cnt_logic_gates` (`cnt`) |
| Magnetic resonance | `testscenario_magnetic_resonance`(`_tissues`/`_imaging`/`_brain`) | `magnetic_resonance_*` (`resonance`) |
| Analytic cross-checks | `analytic_beer_lambert`, `analytic_csda_range`, `analytic_photo_fraction` | `analytic_*_cross_check` (`analytic`) |
| Cascade / ML | `cascade_multiscale_demo`, `surrogate_generic_demo`, `beaker_water_n_pentane` | `generic_surrogate_inference`, `beaker_water_n_pentane_inference` |

Lab bootstrap: [`examples/lab/`](examples/lab/). By-design failing demo: `include_error_demo.js`.

### Python tooling — [`tools/`](tools/)

Four installable packages (each with its own `pyproject.toml`/`README.md`):

- **[`tools/torch/trech_torch/`](tools/torch/)** — the harvest→train→plan pipeline.
  [`dataset.py`](tools/torch/trech_torch/dataset.py) schema-locked harvesting + dimension-scale
  bands (keep in lock-step with the C++ schemas); `train_optics_surrogate.py` /
  `train_event_stratifier.py` / `train_surrogate.py` (console scripts `trech-train-*`; `.json`
  paths + planner are numpy-only, `.pt` needs the `[torch]` extra); `plan_experiments.py`
  (active-learning coverage → `geant4_experiment_plan.json`).
- **[`tools/validation/trech_validation/`](tools/validation/)** — the regression suite
  (`python -m trech_validation`): [`cases.py`](tools/validation/trech_validation/cases.py) (per-scenario
  assertions incl. hook-emit reads), [`runner.py`](tools/validation/trech_validation/runner.py),
  [`report.py`](tools/validation/trech_validation/report.py) → [`docs/validation_report.md`](docs/validation_report.md).
- **[`tools/viz/trech_viz/`](tools/viz/)** — PyVista 3D viewer (console script `trech-viz`) +
  [`demos/`](tools/viz/demos/) render scripts that produce the committed README media.
- **[`tools/pubchem/trech_pubchem/`](tools/pubchem/)** — property + 2D-structure cache
  (`python -m trech_pubchem fetch <names>`; `TRECH_PUBCHEM`/`TRECH_PUBCHEM_CACHE_DIR`). XLogP
  drives Overton's-rule selectivity; **only CID/SMILES/structure feed runtime**, never density/
  boiling-point/colour.

### Committed models & data — [`data/`](data/)

Source-of-truth learned models and fixtures (NOT generated build output): cascade stage models
([`data/cascade_demo/`](data/cascade_demo/), [`data/glass_cascade/`](data/glass_cascade/),
[`data/beaker_cascade/`](data/beaker_cascade/), [`data/lava_lamp_cascade/`](data/lava_lamp_cascade/)),
[`data/optics_surrogate_ridge.json`](data/optics_surrogate_ridge.json),
[`data/optics_handbook_anchors.json`](data/optics_handbook_anchors.json) (logged deltas only —
never feeds the extractor), and the read-only legacy `data/pubchem/` fallback.

### Scripts — [`scripts/`](scripts/)

Orchestration (not source): [`run_validation.sh`](scripts/run_validation.sh),
[`run_smoke.sh`](scripts/run_smoke.sh), [`run_validation_suite.sh`](scripts/run_validation_suite.sh)
(the full slow suite with `SKIP_*` gates), `update_validation_summary.py`,
`validate_glass_of_water.py`, `validate_optics_surrogate.py`, `degeneration_metrics.py`, and the
MRI multi-run drivers `run_magnetic_resonance_{tissues,brain}.py`.

### Nested handbook — [`studio/`](studio/)

The desktop UI (PySide6 + wgpu). It is a **client of the engine, never a second physics engine**.
Local ownership, layering, and honesty rules live in [`studio/AGENTS.md`](studio/AGENTS.md);
status in [`studio/ROADMAP.md`](studio/ROADMAP.md). Read that before touching `studio/**`.

### Docs — [`docs/`](docs/)

[`output_schema.md`](docs/output_schema.md) (the output contracts Studio/viz depend on — update in
lock-step with `Config.cpp`/parsers), [`structure.md`](docs/structure.md),
[`scenario_hooks.md`](docs/scenario_hooks.md), [`viz_refraction.md`](docs/viz_refraction.md),
[`validation_report.md`](docs/validation_report.md)/`.json` + [`validation_summary.md`](docs/validation_summary.md)
(committed for regression tracking), [`CNT/BackToTheCarbon.md`](docs/CNT/BackToTheCarbon.md),
[`implementation.md`](docs/implementation.md), [`notes.md`](docs/notes.md), and the reference-only
[`trech-roadmap.md`](docs/trech-roadmap.md). `docs/geant4-docs/` is a vendored HTML copy of the
Geant4 manuals.

## Features and recurring development pitfalls

Each family's micro-base → observer-target and honest scope is in [`README.md`](README.md) and the
per-scenario notes; below is status + the reusable lessons.

### Multi-scale cascade & surrogates — Shipped (mechanism), Experimental (trained stages)

`ScaleCascade`/`ctx.cascade` chains scale-tagged models from the Geant4 base up; `ctx.predict` is
the single-model path. **Shipped & real:** the mechanism, ambient auto-seed, strict-mode gating,
determinism, the committed optics ridge, and **per-stage training-domain coverage** (workstream 3
— every stage/`ctx.predict` reports `inDomain`/`extrapolation`/`domainMeasured`, so an
out-of-trained-domain guess is flagged low-confidence, not hidden; the trainer exports the measured
hull, legacy models fall back to a heuristic 3σ and say so). **Experimental/illustrative:** most
stage models (`data/*_cascade/`) are hand-authored linear maps demonstrating the chain, not broadly
trained (so their coverage is heuristic, `domainMeasured:false`) — labelled so. **Gap to close:** a
real trained per-band chain in a non-optics family (then its coverage becomes measured). Tracked as
the standing objective in [`ROADMAP.md`](ROADMAP.md).

### Fluids / H₂O — Shipped

Rigid-SPC/E MD reproduces measured structure (O-O g(r) first peak 2.798 Å) and dynamics
(self-diffusion Einstein 2.57 vs Green-Kubo 2.79 ×10⁻⁹ m²/s; D(T) trend). `glass_of_water_shaken`
cascades nano facts → macro PBF fluid params with no hand-typed macro property; `lava_lamp` is a
duration-independent inferred 3D thermofluid (persistent parcels, four separate precision axes).
Honest scope: Geant4 is the per-tick clock; the MD/PBF/parcel solvers are hook-layer physics for
comparison.

### Magnetic resonance / MRI — Shipped (4 stages)

Stage 1 discovers the Larmor line (γ/2π 42.5768 vs CODATA 42.5775 MHz/T) from Geant4 proton
density; Stage 2 makes the output photons real Geant4 tallies (cortical bone 0.60× water); Stages
3–4 reconstruct a 1D line and a 2D brain image. Geant4 supplies proton density + transport; spin
dynamics/FFT are hook-layer.

### CNT electronics — Shipped

Tight-binding zone-folding band structure + curvature gaps; CNTFET static-CMOS gate family +
adders confirmed against truth tables; subthreshold swing ~60 mV/dec; a metallic tube breaks the
logic. Geant4 transports electrons through the channel but does not compute band structure.

### Analytic cross-checks — Shipped

Beer-Lambert / CSDA-range / photo-fraction: a closed-form prediction from Geant4's *own* cross
sections vs the run's Monte-Carlo tally, emitted with the gap. Self-consistency checks, not
external calibration.

### Recurring pitfalls (do not reintroduce)

- **MT nondeterminism in accumulating hooks.** Symptom: a fixed-seed hook scenario gives different
  tallies across runs. Cause: Geant4 MT event order. Fix: `run.threads: 1`. Prevention:
  cross-check reruns are byte-identical.
- **Config-hash churn.** Symptom: unrelated scenarios' config hashes change after adding a field.
  Cause: unconditional serialization. Fix: serialize only when non-default + extend
  `test_config_roundtrip.cpp`.
- **Null post-`Initialize` carrier.** Symptom: analytic/optics/material results missing. Cause: a
  `RunOptions` copy captured the carrier before it was allocated. Fix: pre-allocate the `shared_ptr`
  before `SetUserInitialization`.
- **Mis-recorded photon emission direction.** Symptom: a photon that interacts on step 1 has a
  wrong first segment. Fix: birth point uses the pre-step momentum direction.
- **Missing NIST material crashes Geant4.** Symptom: SIGSEGV in table builders. Cause: a
  half-built `G4Material` (declared > added, e.g. `G4_SODIUM_CHLORIDE` which does not exist). Fix:
  `element`-component materials + fail-safe `buildCustomMaterials`.
- **Hook-emit file is append-mode.** `trech_hook_emits.jsonl` appends; clean the `--output` dir
  between reruns or renderers read stale emits.
- **PyVista offscreen renders repeat frame 0.** Call `plotter.render()` before each `screenshot()`.
- **MD sampling lessons.** Single-origin MSD is too noisy for per-block D (use multi-time-origin);
  each block must equilibrate longer than water's ~2–3 ps structural relaxation or D is inflated.

## Interface ownership map

- **CLI:** `trech run <exp.js> [--macro --ui --output/-o --seed --events --param]`,
  `trech inspect <exp.js> [--param n=<json>]`, `trech lab [--config --commands --output --seed
  --events]` → [`apps/trech-cli/main.cpp`](apps/trech-cli/main.cpp) + `parseRunOptions`/`runUsage`
  in [`src/core/RunOptions.cpp`](src/core/RunOptions.cpp).
- **Hook `ctx` surface:** `config`/`runtime`/`event`/`step`/`state`/`rng`/`emit`/`predict`/
  `cascade`/`materials`/`optics` → [`src/js/TrechJsApi.cpp`](src/js/TrechJsApi.cpp) +
  [`src/js/JsRuntime.cpp`](src/js/JsRuntime.cpp). Authoring globals `TRECH_CONFIG`/`TRECH_HOOKS`/
  `TRECH_VALUE`/`TRECH_FLOW`/`TRECH_INCLUDE`.
- **Config collections** (single-or-array, plural names): `beams`/`materials`/`geometry.volumes`/
  `hooks.registered`/`models`/`optics.spectrum`/`analytic.checks`/`nuclear.cycles` →
  [`src/core/Config.cpp`](src/core/Config.cpp).
- **Lab protocol:** `patch`/`simulate`/`snapshot`/`help`/`quit` → [`src/core/LabSession.cpp`](src/core/LabSession.cpp).
- **Output files** (schemas in [`docs/output_schema.md`](docs/output_schema.md)):
  `trech_scores.jsonl`/`trech_provenance.jsonl` (core writers), `trech_event_scores.jsonl`
  (stratifier), `trech_hook_emits.jsonl` (hook emits), `trech_viz_scene.json` +
  `trech_viz_trajectories.jsonl` (`VizRecorder`, gated on `viz.enable`).

## Build, run, test, debug, and release

Prerequisites: CMake ≥ 3.21, Ninja, a C++ compiler, Python 3. Geant4 is a required submodule for
simulation (`thirds/geant4`; build/install and set `Geant4_DIR` or `CMAKE_PREFIX_PATH`); LibTorch
is optional. Commands (from repo root):

```bash
cmake --preset dev
cmake --build --preset dev
./build/dev/trech run examples/experiments/hello_world.js --output build/dev/out_hello
ctest --preset dev            # 11 C++ tests (trech_nuclear_cycle_analyzer needs Geant4)
```

CMake options: `TRECH_ENABLE_GEANT4`, `TRECH_ENABLE_DNA_CHEM`, `TRECH_ENABLE_TORCH`,
`TRECH_FETCH_DEPS`. Validation & smoke (need Geant4 for physics runs; the full suite is slow and
mutates `build/dev/out_*` + the committed validation report — has `SKIP_*` gates):

```bash
scripts/run_smoke.sh                 # build + ctest
scripts/run_validation.sh            # H2O validation run; updates docs/validation_summary.md
scripts/run_validation_suite.sh      # full regression suite → docs/validation_report.md
```

Python tools install with `pip install -e tools/<pkg>` (`trech-viz`, `trech-train-*`,
`python -m trech_validation`, `python -m trech_pubchem`); Studio: see [`studio/AGENTS.md`](studio/AGENTS.md).

## Test ownership map

- **Config/CLI/lab/provenance** (`trech_core`): [`test_config_roundtrip.cpp`](tests/test_config_roundtrip.cpp)
  (byte-stable hashes — the conditional-serialization guard), [`test_cli_parse.cpp`](tests/test_cli_parse.cpp),
  [`test_lab_session.cpp`](tests/test_lab_session.cpp), [`test_provenance_writer.cpp`](tests/test_provenance_writer.cpp).
- **JS runtime & hook boundary:** [`test_js_runtime.cpp`](tests/test_js_runtime.cpp) (`ctx.predict`,
  two-stage `ctx.cascade`, ambient seed, `TRECH_INCLUDE`/`TRECH_FLOW`).
- **ML:** [`test_scale_cascade.cpp`](tests/test_scale_cascade.cpp), [`test_generic_surrogate.cpp`](tests/test_generic_surrogate.cpp),
  [`test_optics_surrogate.cpp`](tests/test_optics_surrogate.cpp), [`test_stratifier.cpp`](tests/test_stratifier.cpp).
- **Chem/nuclear:** [`test_dna_chemistry_bridge.cpp`](tests/test_dna_chemistry_bridge.cpp),
  [`test_nuclear_cycle_analyzer.cpp`](tests/test_nuclear_cycle_analyzer.cpp) (Geant4-gated).
- **Scenario physics regression:** the Python suite in [`tools/validation/`](tools/validation/)
  (per-family guards named in the scenario table), report committed to
  [`docs/validation_report.md`](docs/validation_report.md). **Known gap:** no in-CI end-to-end
  Geant4 run — the physics suite is run manually and its report committed.

## Data, security, privacy, and compatibility boundaries

- **Canonical vs derived:** committed `data/` models + scenarios + validation reports are
  canonical; `build/**` and `--output` `trech_*` files are derived/regenerable. Never treat run
  output as source.
- **Compatibility:** config hashes are a compatibility promise — preserve them via conditional
  serialization; keep the JS → JSON → C++ boundary and the `docs/output_schema.md` contracts
  stable (update parser + schema + Studio together). Feature/composition ML schemas are versioned
  (`trech_event_features_v1`, `ridge_optics_n_v1`, `logistic_stratifier_v1`).
- **Determinism:** strict mode is the reproducibility contract; predictive mode must log every
  relaxation in provenance.
- **Secrets/privacy:** none in-repo; PubChem fetches hit a public API and cache under `build/`.
  No credentials or personal data belong in configs, provenance, or this handbook.
- **Kernel-bound live edits:** `trech lab` accepts live event-count/seed/planner changes but MUST
  reject a geometry/beam/physics/scoring patch after Geant4 init with a restart-required error
  until safe reinitialization lands (**Known gap**, tracked in both ROADMAPs).

## Current status, known gaps, and roadmap snapshot

Chronology lives in git and [`docs/validation_report.md`](docs/validation_report.md). Current
labels:

### Shipped

- Deterministic JS→JSON→C++ engine, provenance, QBBC Geant4 transport, optics derivation, event
  stratification, analytic cross-checks, material-probe + optics `ctx` surfaces, nuclear cycles.
- The cascade mechanism (`ScaleCascade`/`ctx.cascade`) + `ctx.predict` + committed optics ridge.
- Fluids/H₂O MD ladder, magnetic-resonance 4-stage track, CNT band-structure + logic gates,
  chemistry cycles, biology membrane scenarios, the `lava_lamp` inferred thermofluid.
- Typed authoring (`TRECH_VALUE` + `trech inspect` + `--param`), real-time `trech lab` bootstrap,
  [`studio/`](studio/) viewer basis.

### Experimental / scaffold

- Most cascade **stage models** are illustrative hand-authored maps, not broadly trained.
- `MultiscaleBridge` (`multiscale.enable`) is stubbed and does not alter physics.
- Hook-layer MD/Bloch/PBF/parcel/reaction solvers are labelled "physics for comparison," not
  Geant4-computed.
- Studio scaffolds: property-driven scene editor, gizmos, `SceneModel → .js` serialisation.

### Known gaps

- No trained real per-band cascade in a non-optics family yet (the core standing objective).
- `trech lab` cannot yet safely reinitialize a kernel-bound geometry/beam/physics/scoring change.
- No in-CI Geant4 end-to-end run; the physics regression suite is manual.

### Near-term priorities

1. Grow the cascade toward a **general-purpose, context-driven predictor** — a trained per-band
   chain in fluids/chemistry/biology/electronics/resonance (standing objective, [`ROADMAP.md`](ROADMAP.md)).
2. Constantly **reduce simulation degeneration** (real sampled distributions; convergence to
   measured behaviour) — tracked by `sampling_diversity_non_degenerate`.
3. Studio: property-driven editing + `SceneModel → .js` round-trip ([`studio/ROADMAP.md`](studio/ROADMAP.md)).

## Task start and handoff checklist

**Start:** read every applicable `AGENTS.md` (root + `studio/` if touching `studio/**`); check
`git status` and preserve unrelated changes; find the owning source + focused test from the source
map; compare the handbook claim with current code before relying on it; note which sections your
task will change.

**Handoff:** update every changed durable fact here (owners, symbols, contracts, feature status);
add any residual/scaffold/TODO to the applicable `ROADMAP.md` in the same change; keep
[`README.md`](README.md)/[`CHARTS.md`](CHARTS.md)/[`docs/output_schema.md`](docs/output_schema.md)
consistent; run `ctest --preset dev` (and the relevant validation/smoke script if physics/output
changed); report tests run, tests skipped, and remaining gaps accurately; never label incomplete
work Shipped.
