# Multi-scale inference — context and contracts

[Root principles](../../../AGENTS.md) · [Root roadmap](../../../ROADMAP.md) · [Parent](../AGENTS.md) · [Roadmap](ROADMAP.md)

## Choose a subcategory

| Scope | Context | Work remaining |
| --- | --- | --- |
| Coverage, uncertainty and trust | [AGENTS.md](trust/AGENTS.md) | [ROADMAP.md](trust/ROADMAP.md) |

Read the root principles and the parent handbook first; then open only the subcategory relevant to the task. Source paths and shell commands in code spans/blocks are repository-relative unless stated otherwise; Markdown links resolve from this file.

`ctx.cascade` reports `outputUncertainty` for its final predicted keys and
`measuredUncertaintyFraction` for coverage by model-carried RMSE or marginal intervals.
See the [trust contract](trust/AGENTS.md#cascade-dependency-trust) for overwrite and null semantics.

### C++ engine — `trech_ml` ([`src/ml/`](../../../src/ml), [`include/trech/ml/`](../../../include/trech/ml))

The deep-learning backend is **required** (`TRECH_ML_BACKEND=torch`, LibTorch in `thirds/torch`;
configure fails without it and without a `TRECH_ML_PYTHON` that imports torch + NumPy). There is
no learning-free build: a simplistic stand-in would invalidate development validation. Model files
still pick their evaluator by extension. `.pt` runs through LibTorch. A `.json` model (dense,
ridge, logistic, set networks) runs on the engine's own deterministic `trech_dmath` evaluator,
which strict, byte-reproducible runs depend on. That evaluator is a format, not a fallback.

#### [`src/ml/ScaleCascade.cpp`](../../../src/ml/ScaleCascade.cpp) · [`ScaleCascade.hpp`](../../../include/trech/ml/ScaleCascade.hpp)

The core-doctrine engine: chains scenario-declared `scale`-tagged `GenericSurrogate` models
(ascending `atomic/nano/micro/meso/macro`, unscaled runs last) in one deterministic pass. Each
stage reads named inputs from the current context (seed + lower stages' outputs), predicts, and
merges outputs back. Non-owning over the `JsRuntime`'s registry.

- **Key symbols:** the chaining pass returning the flat augmented context + reserved `__cascade`
  (`stagesRun`, `stagesExtrapolating`, `stagesScaleMismatched`, `stagesStarved`, per-stage `trace` of
  `{model, scale, ran, missingInputs, outputs, inDomain, domainMeasured, extrapolation,
  maxStandardizedDeviation, outOfDomainInputs, starvedInputs, scaleMismatch, trainedScale, hasHoldout,
  holdoutR2, holdoutSamples}`, `seedKeys`). The per-stage **trust profile** (workstream 3) flags a
  stage predicting outside its trained domain (extrapolation, propagates up the ladder) or in an
  in-hull starved region, applied off its trained dimension band (`scaleMismatch`), and carries the
  model's held-out accuracy — so a low-confidence stage is surfaced, not a silent guess. An
  out-of-domain event can be *routed to resim* (see `EventAction` + `stratify.resimOnLowConfidence`).
  Effective `inDomain` includes consumed out-of-domain ancestry; `localInDomain` retains the
  current model's numeric coverage and sorted `upstreamOutOfDomainInputs` names inherited facts.
  `stagesExtrapolating` counts both local and inherited failures for hook/resim accounting.
  Distances, hull measurement and `outOfDomainInputs` remain local. Lineage is per call and follows
  each current fact producer; clean overwrites replace it and unrelated branches stay independent.
  Density and off-band evidence follow the same rule independently: effective `starved` /
  `scaleMismatch` include sorted `upstreamStarvedInputs` / `upstreamScaleMismatchedInputs`;
  `localStarved` / `localScaleMismatch` retain current-model checks. Matching counters include
  inherited evidence; local `starvedInputs`/joint diagnostics and `trainedScale` remain local.
  These causes do not become hull OOD failures or alter the hull-only resim policy.
  Independent `stratify.resimOnStarvation` / `resimOnScaleMismatch` opt into their event routing;
  the [trust contract](trust/AGENTS.md) owns counts, precedence and scope.
  `collectOutputAccuracy` (declared alongside `NamedOutputAccuracy` here, the shared record every
  inference path reports through) fills each stage's per-output measured error.
- **Tests:** [`tests/test_scale_cascade.cpp`](../../../tests/test_scale_cascade.cpp) (ordering/missing-input,
  per-stage coverage in/out-of-domain + `stagesExtrapolating`, missing-input blocking, scale-mismatch + carried holdout,
  Geant4-free) + JS-boundary case in `test_js_runtime.cpp`.

#### [`src/ml/ArchitectureGenerator.cpp`](../../../src/ml/ArchitectureGenerator.cpp) · [`ArchitectureGenerator.hpp`](../../../include/trech/ml/ArchitectureGenerator.hpp)

Engine-side **ML architecture generation**, run by `trech arch <job.json>` (`CliCommand::Arch`).
Contract: [`docs/inference/evolvo_architectures.md`](../../../docs/inference/evolvo_architectures.md#in-the-engine-trech-arch).
Status: shipped. Tested on synthetic tables only; no scenario requests it.

- **Classic reference family (always, C++):**
  - Structures: linear plus SiLU MLPs of depth 1/2. The width is the GFSL-NN ladder rung
    nearest 4·max(in, out, 4), capped at 8 params per training target and by `max_params`.
  - `trainClassicNative`: full-batch Adam with plateau stopping, `trech_dmath` math, splitmix64
    initialization, and the TU at `-ffp-contract=off`. Weights are byte-reproducible for a job.
    Progress is measured from the loss at the last counted `relTol` improvement (the `anchor`),
    which is Evolvo `PlateauStopper`'s rule. Never measure from the latest best: slow steady
    descent would then be stopped as a plateau, and the reference would be too weak to mean
    anything.
  - The best by `ln(loss) + size_cost·ln(params)` is the **bar** every evolved model must beat.
    It is never a fallback for a failed search.
- **Evolvo bridge:**
  - `runPythonModule` uses `posix_spawn`(p) with no shell; stdout/stderr go to a log; it adds a
    PYTHONPATH prefix, a timeout and SIGTERM→SIGKILL. It is POSIX-only (on Windows the job fails).
  - Request and result are `trech_arch_request_v1`/`_result_v1`, bound by the request's
    SHA-256.
  - The worker always searches the whole language. Dense chains also export a JSON twin, which
    the engine prefers (deterministic evaluator). Everything else is loaded as TorchScript.
    `engine_native_only` and `require_engine_native` were removed and are refused.
  - Interpreter: job, then `--python`, then `$TRECH_PYTHON`, then the CMake `TRECH_ML_PYTHON`
    compile default (`TRECH_ARCH_PYTHON` is migrated from old caches). Root: `$TRECH_ROOT`, then `TRECH_REPOSITORY_ROOT`.
- **Decision is the engine's:**
  - The exported model is reloaded with `GenericSurrogate`, its names are checked, and it is
    re-scored on the selection rows (`scored_by: engine`, `report_agrees`).
  - It is accepted only if its score is strictly better than the classic reference's. If it
    loses (`rejected`), the better model, the reference, is kept. Every other outcome
    (`not_started`, `timeout`, `no_result`, `mismatched_result`, `unavailable`, `error`,
    `no_model`, `unloadable`) sets `ok: false` and `generator: "none"` with no model, and
    `trech arch` exits 1. The `generator` is `evolvo` (default) or `classic` (reference only,
    no search); `auto` was removed.
- Never put Python into the simulation process. LibTorch inference is linked, but training and
  the search run in the worker. C++ owns orchestration and the decision; the general search
  lives in Evolvo; `trech_torch.arch_worker` is glue.
- **Tests:** CTest `trech_architecture_generator` (classic, bridge, fake workers),
  `trech_architecture_evolvo_live` (the real worker; an unavailable one fails), `trech_cli_parse`
  (arch flags). Torch/NumPy Python tests (`trech_evolvo_arch`, `trech_ml_model_audit`,
  `trech_surrogate_output_links`, `trech_joint_domain`, `trech_group_hierarchy_py`,
  `trech_ml_model_recheck`) run under `TRECH_ML_PYTHON` and fail, never skip, without torch or
  NumPy.

#### [`src/ml/GroupHierarchy.cpp`](../../../src/ml/GroupHierarchy.cpp) · [`GroupHierarchy.hpp`](../../../include/trech/ml/GroupHierarchy.hpp)

Recursive **group lifting** of a population, exposed as `ctx.lift` (`jsHookLift` in
`src/js/JsRuntime.cpp`). Each level partitions the current elements into groups (`cell_size`
lattice from `origin`, explicit ids, or one group of everything) and evaluates a v3 set model with
a `group_lift` block on every group's members. The groups become the next level's elements:
features are the model outputs, position is the members' weight-centroid and weight is the sum.
Contract: [`docs/inference/group_hierarchy.md`](../../../docs/inference/group_hierarchy.md). Status: mechanism +
trainer tested on synthetic data only; no scenario uses it.

- **Member inputs:** level-below features by name, or engine-synthesized `present`, `weight` and
  `rel_x/y/z` = (member − centroid) / length. The length is the call's `length`, else the lattice
  edge, else the model's carried `group_lift.length`. Absent slots are filled with the model's
  input means (`present = 0`), so they standardize to zero and never trip coverage.
- **Order is fixed:** cells by (ix, iy, iz), explicit ids ascending, members ascending; centroids
  accumulate in that order. The TU is compiled `-ffp-contract=off` like `GenericSurrogate`
  because `trech_torch/hierarchy.py` replays the same sums.
- **Blocking, never truncation:** over-capacity groups (`overflow`), groups with blocked members
  (`blockedByMembers`) and failed predictions publish NaN / `valid:false`. Missing member features,
  context, positions or length skip the level and all above it (`skipReason`,
  `lower_level_unavailable`). `top` is non-null only for one valid final group.
- **Trust lineage:** a group's effective `inDomain`/`starved` include any member's lineage;
  `localOutOfDomain`/`localStarved` are the model's own checks. Level `scaleMismatch` is local or
  inherited from a lower level. Effective counts feed `hook_predict_out_of_domain_count`; each
  evaluated group is one `hook_predict_count` inference. Strict mode returns `null`.
- **Planning:** without `levels`, `ctx.lift` selects every model declared with
  `operator_role: "group_lift"` (and matching `element_kind`, when given) in ascending scale, then
  name order, grouped by its carried `cell_size`, or as one group without one.
- **`GenericSurrogate::groupLift()`** parses the optional block (v3 only). Load fails closed unless
  every slot repeats the slot-0 names under `member_prefix`, the mask is the member feature
  `present`, and `cell_size`/`length` are positive. `latent_outputs` must name outputs (or be a
  boolean). `setLayout()` / `inputMean()` expose what the hierarchy needs.
- **Tests:** [`tests/test_group_hierarchy.cpp`](../../../tests/test_group_hierarchy.cpp) (1e-9
  parity per level vs the committed NumPy reference in `tests/fixtures/ml_group_hierarchy/`,
  base-order invariance, keys, overflow/blocked propagation, missing inputs, OOD lineage,
  carried length, loader rejections) and the `ctx.lift` case in `test_js_runtime.cpp`.

#### [`src/ml/GenericSurrogate.cpp`](../../../src/ml/GenericSurrogate.cpp) · [`GenericSurrogate.hpp`](../../../include/trech/ml/GenericSurrogate.hpp)

Scenario-agnostic named-IO learned inference. Portable `generic_surrogate_v1`/`v2` JSON feed-forward
and `generic_surrogate_v3` set networks (DeepSets / MPNN over element blocks of the named inputs;
`networkKind()`), LibTorch-free; also loads `ridge_optics_n_v1`/`logistic_stratifier_v1`; optional
`.pt`. Each cascade stage and every `ctx.predict` is one of these.

- **Named TorchScript (2026-11-16):** a raw `.pt` module is positional-only unless a
  `<model>.pt.io.json` sidecar (`trech_torchscript_io_v1`) sits next to it. The sidecar must
  carry the module's `model_sha256` and unique `input_features`/`output_features`; optional
  `feature_units`, `trained_scale_bands`, `holdout` and `prediction_interval` are read exactly
  like a JSON model's. With it the module serves named `predict` (ctx.predict, cascades,
  operators) at its declared layout; a present but invalid, stale or incomplete sidecar fails the
  load. `ioSidecarSha256()` feeds `model_artifacts.io_sidecar_sha256`. Optional
  `input_mean`/`input_std` and `input_domain` drive hull, occupancy and joint checks;
  `routing_domain` supports operator routing. The module consumes raw inputs in its
  named layout. `torchscript_io.py` derives the sidecar from a JSON twin or training manifest.

- **Set networks (v3):** used by a scenario operator since 2026-11-11 (`glass_from_sand`
  `conduction_source=set_network`, through `ctx.evolve` with the neighbour set as `aux`).
  `buildSetNetwork` fails closed on any layout mismatch; `predictSet`
  sums in ascending element order with the dense-layer `evalLayer` arithmetic (fma, fixed order)
  shared with v1/v2, decides presence from the RAW mask feature, and uses the extra
  `Workspace` buffers (`state`, `nextState`, `aggregate`, `scratchA/B`), so batched operators
  stay allocation-free once warm. Contract and NumPy/pure-Python/TorchScript twins:
  `tools/torch/trech_torch/set_networks.py`; C++ parity is held to 1e-9 against committed
  fixtures in `tests/fixtures/ml_set_networks/`.

- **Loaded byte identity:** `contentId()` is empty after a failed load, otherwise an
  algorithm-qualified `fnv1a64:` fingerprint of the same bytes parsed/loaded (not a reopened
  path or reserialized JSON). JSON consumes the complete artifact. Catalog reads retain this
  snapshot even after file replacement. Optional Torch loading consumes the same stream and
  is exercised by `test_torch_backends`, including replacement/deletion and failure reset.
  `contentSha256()` / `contentSizeBytes()` describe that same snapshot and reset on failed load.
  `JsRuntime::modelArtifactsJson()` serializes all registry entries without inference/RNG/file IO;
  GeantRunner captures it before constructing actions for provenance and scores. Hashes establish
  byte identity, not authenticity or physical validity.

- **Output links:** v2 declares one `identity`/`exp`/`sigmoid` inverse transform per output, applied after
  destandardisation. Its layers live under `network.layers` so older readers reject encoded
  targets. Overflow rejects the whole prediction before publishing any output; v1 arithmetic is
  unchanged. `trech-train-surrogate --log-outputs ...` fits positive targets in log space and
  reports held-out errors in decoded physical units. `--logit-outputs ...` fits targets strictly
  inside (0,1), with overflow-safe sigmoid decoding into [0,1]. Finite extreme logits may
  saturate; non-finite encoded values fail before decoding/publishing, preserving atomic output
  rejection. The trainer never clips or smooths fraction labels implicitly; train/holdout
  endpoints and overlapping log/logit declarations are rejected. Mixed links agree across named,
  positional and optional TorchScript paths. This is a generic numerical capability,
  never a material-specific law. The foam constitutive candidate exercises it through
  `ctx.evolve`, but stays opt-in (`mechanics_source=operator`): its full-run observer gates fail.
  `scripts/validate_foam_mechanics.sh` runs the explicit candidate suite; it must not be promoted
  from row-level R² alone. Teacher distillation is labelled `measured:false`.

- **Key symbols:** `predict`/`predictVector`; **`predictInto(inputs, n, out, m, Workspace&)`** — the
  allocation-free batched path every operator uses (`predictVector` delegates to it, so there is one
  arithmetic implementation and the two forms cannot drift). Weights are stored **input-major**
  (`weights[i * rows + o]`) so the evaluation loop runs inputs-outside / neurons-inside, giving each
  neuron its own accumulator that still sums bias, then input 0, 1, 2 … in declared order; the
  accumulation uses an explicit `std::fma` and the translation unit is compiled `-ffp-contract=off`
  (see `CMakeLists.txt`), so learned inference is bit-identical at **every optimization level** and
  across compilers instead of depending on an optimiser's FMA choice.
  Operators reuse that workspace for `coverageVector(inputs, workspace)`, standardizing each
  joint-domain input once before scanning training centers in the original order.
  `coverage(inputs) -> {inDomain, domainMeasured,
  extrapolation, maxStandardizedDeviation, outOfDomainInputs, starvedInputs}` — the training-domain
  check that grounds the cascade's low-confidence flag (compares each input's `|z|=(x-mean)/std`
  against the trained hull edge `input_domain.standardized_radius`, or heuristic
  `kDefaultStandardizedDomainRadius`=3σ when absent → `domainMeasured:false`; `starvedInputs` flags
  in-range values in an unpopulated `input_domain.occupancy` bin — density inside the hull, via
  `hasOccupancy()`; **`jointMeasured`/`jointStarved`/`jointDistance`/`jointRadius`** is the
  MULTIVARIATE version both per-feature checks structurally cannot make — a point in range on every
  axis yet far from any training point (`input_domain.joint` = a farthest-point covering set of
  standardized training rows + the radius covering the training set, via `hasJointDomain()`;
  `jointMeasured:false` means NOT CHECKED, never "fine"); plus carried training provenance `trainedScaleBands()` (harvester band tags) and
  held-out accuracy `hasHoldout()`/`holdoutR2Min()`/`holdoutSamples()` plus the per-quantity split
  `outputAccuracy(o) -> {r2?, mae?, rmse?}` / `hasOutputAccuracy()`. The `rmse` field holds
  the held-out root mean square residual in the output's own units. Metrics are independently
  optional. A top-level `prediction_interval{nominal_coverage ∈ (0,1), half_width{<output>: ≥0}}` (read
  independently of `holdout`) adds `interval_half_width`/`interval_coverage` to the same per-output
  record — a calibrated `±` at a nominal marginal coverage, e.g. split-conformal CV residuals. The
  block's calibration source and achieved coverage stay in the model JSON; a block without a valid
  coverage claim yields no interval, and a negative/non-finite width is skipped per output.
- **Tests:** [`tests/test_generic_surrogate.cpp`](../../../tests/test_generic_surrogate.cpp) (v3 set-network parity/permutation/mask/rejection +
  feed-forward +
  coverage measured-vs-heuristic + missing-input-out-of-domain + carried bands/holdout). Trainer:
  [`tools/torch/trech_torch/train_surrogate.py`](../../../tools/torch/trech_torch/train_surrogate.py)
  (exports `input_domain.standardized_radius` + `occupancy` + `joint` + `trained_scale_bands` +
  `holdout{r2_min,n,r2,mae,rmse}` so a trained stage carries its measured domain — per-feature AND
  joint — its scale band, and its per-output held-out accuracy).

#### [`src/ml/OpticsSurrogate.cpp`](../../../src/ml/OpticsSurrogate.cpp) · [`OpticsSurrogate.hpp`](../../../include/trech/ml/OpticsSurrogate.hpp)

Composition → refractive index surrogate (TorchScript `.pt` **or** ridge `.json`). Predicts `n`
only (abs/scat carry a negative "not predicted" sentinel so the caller keeps extractor values).
Opt-in via `optics.derive.surrogateModelPath`; leave-one-out validated, off by default.
GeantRunner permits the override only in predictive mode. The loader parses/hashes one binary
snapshot; `contentId`/`contentSha256`/`contentSizeBytes` reset on failed reload.

- **Key symbols:** `encodeComposition` (renormalises all 14 `kCompositionElements` slots, matching
  the Python harvester); `kCompositionElements`.
- **Tests:** [`tests/test_optics_surrogate.cpp`](../../../tests/test_optics_surrogate.cpp). Committed model:
  [`data/optics_surrogate_ridge.json`](../../../data/optics_surrogate_ridge.json).

#### [`src/ml/TorchScriptStub.cpp`](../../../src/ml/TorchScriptStub.cpp) · [`Stratifier.cpp`](../../../src/ml/Stratifier.cpp) · [`FeaturePipeline.cpp`](../../../src/ml/FeaturePipeline.cpp) · [`OnlineEventStats.cpp`](../../../src/ml/OnlineEventStats.cpp)

Event stratification stack. `FeaturePipeline` owns the frozen feature schema (`kSchemaId` =
`trech_event_features_v1`, `FeatureNames`); `Stratifier` labels events predictable/exceptional;
`TorchScriptStub` is its model backend (`.pt` or logistic `.json`, validated against
`FeatureNames` at load); `OnlineEventStats` is the Welford/vectorized-Torch accumulator.
`TorchScriptStub` is move-only in both builds, with lifecycle methods defined out of line so
clients need no complete Torch Module type. TorchScript interpreter errors fail inference cleanly.
`captureStratifierModel` captures/validates bytes before Geant4 action setup; workers use
`LoadSnapshot` to retain isolated modules without reopening paths. Failed/strict/disabled snapshots
never retry a changed path. RunAction emits the captured FNV hash instead of hashing current files.
[`EventFeatures.hpp`](../../../include/trech/ml/EventFeatures.hpp) is the shared snapshot struct.

- **Tests:** [`tests/test_stratifier.cpp`](../../../tests/test_stratifier.cpp),
  [`tests/test_model_loader_snapshots.cpp`](../../../tests/test_model_loader_snapshots.cpp).

JS model definitions, structure searches and the versioned checkpoint store that feed
`models[]` are owned by [training tools](../../tooling/training/AGENTS.md#js-model-definitions-and-checkpoint-store--toolsml--jstrech_mljs--ml)
([contract](../../../docs/inference/ml_models.md)). They change nothing in the C++ loaders: a resolved
checkpoint is an ordinary `generic_surrogate` path.

### Multi-scale cascade & surrogates — Shipped (mechanism), Experimental (trained stages)

The bounded `particle_observer_cascade` now extends the shared Geant4-table-trained atomic/nano
CHNO response to a learned **meso** photon-volume observer. Its two-stage property pass consumes
learned composition cross sections and predicts uncollided/deposited-energy fractions before
current-run MC. The new observer uses actual Geant4 MC labels, with 192 fitting / 12 development /
18 untouched final conditions, preserved first-candidate failures and freeze-before-test hashes.
All final and fresh-realization error gates pass; fourteen of eighteen fresh queries still flag
per-feature starvation and five joint starvation. It stays experimental within the unit-density
cube/source/energy domain, with no experimental-accuracy or molecular-dynamics claim.
The [observer contract](../../../docs/inference/particle_observer.md) owns metrics, training/validation and
engine-carried global residuals; the [chemistry handbook](../../scenarios/chemistry/AGENTS.md)
owns its shared JS helper. The [expanded Geant4 study](../../../docs/inference/multiscale_domain_study.md)
quantifies the opt-in dense TorchScript observer and first particle-trained recursive hierarchy.
The dense candidate had the lowest new-panel RMSE. Both recursive paths ran in native replay
and retained gaps in interval coverage on new compositions.

`ScaleCascade`/`ctx.cascade` chains scale-tagged models from the Geant4 base up; `ctx.predict` is
the single-model path; **`StateEvolution`/`ctx.evolve` is the per-element OPERATOR path** — the
mechanism for moving a scenario's hand-written per-element rate law behind engine inference
(mechanism shipped + tested). **`DiscreteTransition`/`ctx.react` is the integer stochastic
operator path**: learned hazards, engine-owned seeded channel choice, availability, exact declared
conservation and atomic mutation. **`PairInteraction`/`ctx.interact` is the pair/neighbour path**
(mechanism shipped + tested 2026-08-15; **no scenario migrated onto it yet**): deterministic cell
list, canonical `(a,b)` enumeration, caller-declared symmetry applied equal-and-opposite,
persistent bond state, `pairs × stages` accounting — the prerequisite for moving the MD force loop,
the foam bond network and the PBF neighbourhood sums out of scenario JS. The first trained
continuous operator now lives at
`data/polyurethane_cascade/meso_reaction_operator.json`: a meso 27→8 MLP distilled from 115,437
polyurethane reference rows, with a measured input hull and independent 38,565-row worst-output
held-out R²=0.9929. `chemistry_source=operator` runs end to end through `ctx.evolve`; the model
explicitly carries its reduced-law teacher and `measured:false`. It is the promoted scenario
default after passing the independent holdout, all eight full-size observer gaps, 13/13 trust
checks, and the nominal/zero-g mechanics guard; `reference` remains the audit/harvest teacher.
Local creep/drag/strength also have a v2 constitutive candidate, selected through
`constitutive_response` / `foam_parcel`; it stays opt-in because full-run shape gates fail despite
held-out R²=0.9980. `mechanics_source=reference` is the default. Both paths remain comparison
physics, with independent physical training data and the bond/contact migration still open.
The first promoted discrete/biology migrations live under `data/discrete_operators/`:
`h2o_cycle_transition_operator.json` drives the H2O electrolysis/combustion topology through
`ctx.react` (R²min=0.9973), while `efflux_transport_operator.json` (`ctx.evolve`, **3D**:
x/y/z + OU velocity, 64 hidden, R²min=0.9993 — its learned OU memory γ must track the teacher's,
a 0.005 γ error doubled 3D clearance) and `efflux_crossing_operator.json` (`ctx.react`, R²=0.9827) remove the membrane
efflux transport/crossing laws from its normal JS path. Both scenarios default to `operator`;
their `reference` sources are audit-only distilled teachers, and their generic paired gates require
zero OOD plus exact run-level inference accounting. `testscenario_efflux` `learn_domains=learn|evaluate`
(operator physics only) runs `ctx.learnDomains` on the transport operator's own inputs (position,
radius, velocity, mass, permeant/cleared flags, unit innovations) and outputs (new velocity,
pre-bound displacement rates). With 13 features the budget picks an affine basis, so the learner
approximates the smooth SiLU operator piecewise; agreement is reported against
cleared/permeant/retained classes applied afterwards.
`ctx.cascade(seed, modelNames)` can narrow a property pass when the same config also declares
independent operator models. Operator models declare `operator_role`, `element_kind`, and
`required_context_keys`; absent an explicit `models` override, `ctx.evolve` selects the single
compatible group from ambient Geant4/material + caller context. Its `selection` trace makes
selected/ambiguous/no-compatible outcomes auditable, and the latter two never mutate state.
**Domain routing (2026-11-18):** an undeclared `ctx.evolve`/`ctx.react` call over several kinds of
one role, or over unlabelled operator models (role, no `element_kind`), routes per element
instead of declining. `trech_ml`'s `DomainRouter` (`DomainRouting.hpp`) makes same-band stages
with a shared output rivals. A rival runs on an element only when its own `coverageVector` covers
the element's current context, including the lower bands' intermediates. That context includes an
optional measured `routing_domain`: facts the law does not read, such as the phase fraction that
separated its training population (`GenericSurrogate::routingDomain`, written by
`trech-measure-routing-domain`). Elements in a thin gap inside the rivals' combined envelope run the
nearest rival (`elementsNearest`), and elements outside it stay untouched. Each element's unnamed
group is its path of covering rivals, with id `d` + FNV-1a-32 of that path. `group_by: "declared"`
opts out, and `ctx.interact` does not route. `glass_from_sand.js` `grouping: "domain"` is the
worked scenario (validation `glass_domain_routing_matches_declared`). Tests:
`trech_state_evolution`, `trech_discrete_transition`, `trech_js_runtime`, `trech_routing_domain`. Contract:
[scenario hooks](../../../docs/engine/scenario_hooks.md).

**Live statistical subdivision:** [`DomainDiscovery.cpp`](../../../src/ml/DomainDiscovery.cpp)
implements recursive projected-gap detection over live per-element facts for `ctx.detectDomains`.
Optional routing ids partition the search into independent parents. The engine checks original
axes and standardized LibTorch principal components, then pairwise diagonals as a fallback.
Children require minimum support and a gap relative to both the projected span and typical spacing.
Each leaf carries its parent and call-local binary path. Non-finite rows are unassigned. This
predictive-mode diagnostic leaves model routing, inference counters and state untouched. The
glass-furnace and lava-lamp examples expose `detect_domains=true`. The JS runtime test covers
oblique data, a uniform grid, permutation, parent isolation and strict-mode gating. The paired
[NumPy validator](../../../scripts/validate_domain_discovery.py) checks every live assignment.
The optional density detector uses connected components in a local Euclidean-distance graph,
with a shared scale for coordinates in common units. Lava parcels carry IDs across
statistical subdivisions using mutual-majority overlap and record predecessor counts.
`trech-train-domain-specialists` fits projected populations from distinct runs and freezes their
split planes, support and trained models together. Its TorchScript forward selects a supported
expert or delegates to the pooled model. See the
[multi-scale domain study](../../../docs/inference/multiscale_domain_study.md).
**Method arbitration:** [`MethodArbiter.cpp`](../../../src/ml/MethodArbiter.cpp)
([`MethodArbiter.hpp`](../../../include/trech/ml/MethodArbiter.hpp)) is the engine-wide,
domain-free selection among prediction methods. A path that owns several ways to predict the same
quantity (algorithms, learned operators, surrogate networks, baselines, and any method added
later) passes per-element context and one prediction per method; NaN means the method abstains
there. The arbiter works as follows:
- one `DomainLearner` per method learns that method's log error from the elements it predicted;
- the method with the lowest predicted error is chosen, but only under the learned policy, and an
  element leaves the recent leader only when the advantage exceeds the error learners' own
  uncertainty;
- the learned policy competes with the recent leader (lowest decayed log error) and is used while
  it wins on both the decayed log-ratio and the decayed total squared error;
- before any evidence separates the methods, the lower median of distinct predictions is used;
- the summary reports own-element and common-element RMSE, coverage, shares, per-method error
  domains and three phase windows.

`DomainLearner::predict` (no side effects, optional remoteness from the law's support) serves
methods that must predict before a call's reference exists. Paths using it:
- `ctx.evolveField` ([lattice handbook](../lattice/AGENTS.md)), covered by `trech_field_evolution`;
- `ctx.evolve` overlapping rivals, through
  [`RivalArbitration`](../../../include/trech/ml/RivalArbitration.hpp). When the routed call
  carries `reference_rates`, `StateEvolution` defers integration, collects every rival's total
  and the cooperating sum per overlapping element, and the pool's per-set arbiter chooses.
  Covered by `trech_state_evolution` (alternatives per context domain, cooperation, no-evidence
  identity).
- `ctx.react` overlapping hazard rivals, through a separate `RivalArbitration` pool fed by
  `reference_hazards` (per-cell channel probabilities for the step). `DiscreteTransition`
  evaluates every cell first, recomposes each rival's channel odds alone and their cooperating
  combination (base odds plus every rival's change), applies the arbiter's choice, then draws
  once per cell in cell order. `RivalCandidates` lives in `DomainRouting.hpp`. A choice of
  `members.size()` names the combination, and -1 leaves the operator unchanged. Covered by
  `trech_discrete_transition` (alternatives, cooperation, deterministic replay, no-evidence
  identity) and `trech_js_runtime` (graded then deployed `ctx.react`, channel validation).

The remaining multi-method paths are queued in the [roadmap](ROADMAP.md#priority-queue).

**Online response-domain learning:** [`DomainLearner.cpp`](../../../src/ml/DomainLearner.cpp)
([`DomainLearner.hpp`](../../../include/trech/ml/DomainLearner.hpp)) backs `ctx.learnDomains`.
Where `ctx.detectDomains` looks for gaps in the feature distribution, the learner subdivides a
population where **one response law stops explaining it**, using the response the scenario's own
operator produced as the teacher. It is model-based recursive partitioning, fit online:
- tree of half-space splits; each leaf is a domain with a weighted-ridge law over an affine or
  quadratic basis (LibTorch batched solves). Fewer than four rows per quadratic coefficient fit the
  affine part only;
- split directions are feature axes, leading principal axes and directions regressed from the
  parent law's residuals. Quantile cuts are scored with prefix sums, then refined between
  neighbours. Acceptance requires BIC, two-fold cross-validated gain (`min_gain`), a material share
  of variance (`exact_law`, so ridge bias and rounding never pose as structure) and support from
  several calls. Same-law siblings merge;
- every prediction is prequential (before the call's rows are learned) and graded against a
  pooled single-domain law on the same rows;
- per domain and per context (inside the envelope / extrapolating), the predictor is chosen by
  weighted prequential error among the ridge law, ridge + an online LibTorch residual MLP (zero
  output layer, Adam), the pooled law and ridge + the forecast of the law's own residual-bias
  tendency. Extrapolating rows start on the pooled law; leaving it needs 10× the evidence and half
  its error. Extrapolation means leaving the per-feature box or the joint support (≤32
  farthest-point centres + covering radius, exported); remote rows (half a span past the box or 3
  radii from the support) return to the pooled law whenever it is less remote. A residual network
  may move its law by at most 3 residual standard deviations.
  Linear terms extrapolate at most two spans, curvature never, and outputs stay within one span of
  the observed responses. A frozen learner grades with targets but never changes laws, choices or
  trend histories;
- targets must be the operator's law, not the integrator's clamp: `ctx.evolve` `report_rates`
  returns pre-bound rates. Learning `(after − before)/dt` hid the furnace's negative cold-batch
  melt rate behind the zero bound, and the deployed law then melted cold cells in closed loop;
- change points (own-law error ≥ `drift_z`² × its history, via a fast window for thinly fed
  domains) drop pre-change rows in a forgetting learner. A stationary learner (`forgetting = 1`)
  keeps reservoir samples across calls and runs and only searches for a split;
- tendencies: exponentially weighted trends (slope, standard error, forecast, z) of each domain's
  population, feature and target means, error, value at the mean and raw-unit sensitivities
  (model parameters), plus learner-level domain count and errors; `extinction_eta` for shrinking
  domains;
- capacity from [`ComputeBudget`](../../../src/ml/ComputeBudget.cpp): hardware threads, physical
  memory and a measured LibTorch matmul rate set buffered rows, maximum domains, basis degree,
  split candidates, residual-network width/steps and offline specialist width/epochs
  (`trech budget`). `TRECH_COMPUTE_BUDGET` pins it. The resolved budget travels with every report
  and state, because results under different budgets differ;
- `exportState` / `fromState` (`trech_domain_learner_v1`, optional reservoir rows) give warm
  starts, multi-run campaigns and frozen deployment. Malformed states fail closed.

The learner never mutates scenario state; deployment is the scenario's explicit choice and is
labelled learned. Tests: `trech_domain_learner` (regime recovery, no-split control, merges,
drift recovery, tendency ablation, residual network, reservoir, frozen replay, determinism,
block-wise density discovery, capacity) and `trech_domain_learner_numpy` (NumPy twin,
[`domain_learner.py`](../../../tools/torch/trech_torch/domain_learner.py)). Density discovery for
`ctx.detectDomains` is now evaluated block-wise (identical distances, ~32 MiB per block) up to
65,536 rows per parent. Campaigns: [`study_domain_learning.py`](../../../tools/torch/study_domain_learning.py);
results in the [multi-scale domain study](../../../docs/inference/multiscale_domain_study.md#online-response-domain-learning).
**Shipped & real:** the mechanism, ambient auto-seed, strict-mode gating,
determinism, the committed optics ridge, and the **per-stage trust profile** (workstream 3 — every
stage/`ctx.predict` reports training-domain coverage `inDomain`/`extrapolation`/`domainMeasured`,
in-hull `starvedInputs`, off-trained-band use `scaleMismatch`/`trainedScale`, and carried held-out
accuracy `holdoutR2` + the per-output `outputAccuracy{r2,mae,rmse}` (`ctx.predict` reports the same
as a reserved `__accuracy`), so scenarios can disclose model error alongside query trust. The run reports
`hook_predict_out_of_domain_count`, and `stratify.resimOnLowConfidence` **routes an out-of-domain
event to the resim queue** — acting on the flag, not just surfacing it; the trainer exports the
measured hull + occupancy + scale bands + holdout, legacy models fall back to heuristic/absent and
say so). **Experimental/illustrative:** most stage models (`data/*_cascade/`) are hand-authored
linear maps demonstrating the chain, not broadly trained (so their coverage is heuristic
`domainMeasured:false`, bands empty, `holdoutR2` null) — labelled so. **First bounded non-optics
lift:** the CHNO photon-response family now trains atomic and nano stages from actual Geant4
interaction data with measured domains/holdouts (see the [molecular track](../../scenarios/chemistry/AGENTS.md#molecular-polarizationtorsion--experimental-comparison-prototypes)). General learned
state/bond/electronic dynamics across bands remain open.
Tracked as the standing objective in the [inference roadmap](ROADMAP.md).

The JS-law audit source is [`tools/validation/js_law_audit.json`](../../../tools/validation/js_law_audit.json).
It must list every hook-bearing experiment and name any remaining authored state-law residual.
[`tests/test_js_law_audit.py`](../../../tests/test_js_law_audit.py) prevents unregistered hook scenarios and
regressions of the retired H2O/efflux normal-path function names. The audit currently records
2 fully operator-backed hook experiments out of 24; `operator_partial`/`reference_only` entries are
active roadmap work, not an honesty waiver.
