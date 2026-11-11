# Multi-scale inference — context and contracts

[Root principles](../../../AGENTS.md) · [Root roadmap](../../../ROADMAP.md) · [Parent](../AGENTS.md) · [Roadmap](ROADMAP.md)

## Choose a subcategory

| Scope | Context | Work remaining |
| --- | --- | --- |
| Coverage, uncertainty and trust | [AGENTS.md](trust/AGENTS.md) | [ROADMAP.md](trust/ROADMAP.md) |

Read the root principles and the parent handbook first; then open only the subcategory relevant to the task. Source paths and shell commands in code spans/blocks are repository-relative unless stated otherwise; Markdown links resolve from this file.

### C++ engine — `trech_ml` ([`src/ml/`](../../../src/ml), [`include/trech/ml/`](../../../include/trech/ml))

All ML degrades gracefully without LibTorch: the two learned inference paths carry a LibTorch-free
`.json` backend chosen by file extension, so Geant4-trained models run in a stock build.

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

#### [`src/ml/GenericSurrogate.cpp`](../../../src/ml/GenericSurrogate.cpp) · [`GenericSurrogate.hpp`](../../../include/trech/ml/GenericSurrogate.hpp)

Scenario-agnostic named-IO learned inference. Portable `generic_surrogate_v1`/`v2` JSON feed-forward
and `generic_surrogate_v3` set networks (DeepSets / MPNN over element blocks of the named inputs;
`networkKind()`), LibTorch-free; also loads `ridge_optics_n_v1`/`logistic_stratifier_v1`; optional
`.pt`. Each cascade stage and every `ctx.predict` is one of these.

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
  `outputAccuracy(o) -> {r2?, mae?, rmse?}` / `hasOutputAccuracy()` — `rmse` is a **measured 1-σ
  residual in the output's own units**, the honest replacement for a scenario hand-typing a σ. Each
  metric is independently optional and an unmeasured output is absent, never a 0. An optional
  top-level `prediction_interval{nominal_coverage ∈ (0,1), half_width{<output>: ≥0}}` (read
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
([contract](../../../docs/ml_models.md)). They change nothing in the C++ loaders: a resolved
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
The [observer contract](../../../docs/particle_observer.md) owns metrics, training/validation and
engine-carried global residuals; the [chemistry handbook](../../scenarios/chemistry/AGENTS.md)
owns its shared JS helper.

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
zero OOD plus exact run-level inference accounting.
`ctx.cascade(seed, modelNames)` can narrow a property pass when the same config also declares
independent operator models. Operator models declare `operator_role`, `element_kind`, and
`required_context_keys`; absent an explicit `models` override, `ctx.evolve` selects the single
compatible group from ambient Geant4/material + caller context. Its `selection` trace makes
selected/ambiguous/no-compatible outcomes auditable, and the latter two never mutate state.
**Shipped & real:** the mechanism, ambient auto-seed, strict-mode gating,
determinism, the committed optics ridge, and the **per-stage trust profile** (workstream 3 — every
stage/`ctx.predict` reports training-domain coverage `inDomain`/`extrapolation`/`domainMeasured`,
in-hull `starvedInputs`, off-trained-band use `scaleMismatch`/`trainedScale`, and carried held-out
accuracy `holdoutR2` + the per-output `outputAccuracy{r2,mae,rmse}` (`ctx.predict` reports the same
as a reserved `__accuracy`), so a low-confidence guess is flagged not hidden and a scenario emits the
engine's **measured** σ rather than one it typed; the run reports
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
