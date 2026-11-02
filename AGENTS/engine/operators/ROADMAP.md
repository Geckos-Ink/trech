# Learned state and pair operators — roadmap

[Root principles](../../../AGENTS.md) · [Root roadmap](../../../ROADMAP.md) · [Parent](../ROADMAP.md) · [Handbook](AGENTS.md)

## Choose a subcategory

| Scope | Context | Work remaining |
| --- | --- | --- |
| Operator migration contract | [AGENTS.md](migration/AGENTS.md) | [ROADMAP.md](migration/ROADMAP.md) |
| Operator migration prerequisites | [AGENTS.md](prerequisites/AGENTS.md) | [ROADMAP.md](prerequisites/ROADMAP.md) |

Related owners: [Reusable solution and material processes](../../scenarios/processes/ROADMAP.md) · [Scenario law migration ledger](../../scenarios/migrations/ROADMAP.md).

Maintain work in its owning branch. Dated results apply to the recorded checkout; they do not validate subsequent changes.

The dated mechanism descriptions retain their landing state. Current required-input gating is in the [inference handbook](../inference/AGENTS.md); later furnace and process adoption is in the [process workstream](../../scenarios/processes/ROADMAP.md).

## Engine-side inference operator — removing hard-coded JS physics/chemistry

`ctx.cascade` answers *"given this context, what are the properties?"*. That left the other half of
the physics in the scenario: the **per-element, per-step operation** that turns those properties
into motion — the reaction rate law in
[`polyurethane_foam.js`](../../../examples/scenarios/polyurethane_foam/polyurethane_foam.js), the parcel chemistry in
[`elephants_toothpaste.js`](../../../examples/scenarios/elephants_toothpaste/elephants_toothpaste.js), the bond
growth/creep/failure mechanics in
[`trech_foam_solver.js`](../../../js/trech_foam_solver.js). Those are hand-written
JavaScript formulas doing exactly the job the inference cascade exists to do. This workstream moves
them behind engine inference, trained from the Geant4 base (PubChem for structure identity and
cross-checking), so a rate law becomes a **trained artefact carrying a measured domain, a scale band
and a held-out accuracy** instead of a formula typed into a scenario.

### [landed 2026-07-25] The mechanism: `StateEvolution` + `ctx.evolve`

- **`src/ml/StateEvolution.cpp` + `include/trech/ml/StateEvolution.hpp`** — a physics-agnostic
  per-element evolution operator. The caller declares named state fields over N elements (parcels,
  cells, voxels), read-only per-element aux facts, a run-constant shared context and a bounded `dt`;
  the engine chains the scale-tagged `GenericSurrogate` models over **every element** in one
  deterministic pass and integrates. Naming convention only — no domain name enters C++: a stage
  output `d_<field>_dt` is a **rate** (accumulated across stages, so two competing reactions can
  drive one heat field without the caller sequencing them, integrated once per call), `set_<field>`
  is an **assignment** visible to higher stages, anything else is an **intermediate** a
  higher-scale stage consumes. Field bounds are the caller's declared invariants. Stage inputs are
  resolved to slots **once per call** (precedence field > aux > intermediate > `dt` > shared >
  missing-as-0), so the per-element inner loop is index arithmetic rather than a string hash per
  input per element per step. Per-stage trust profile is aggregated over elements
  (`elementsOutOfDomain`, `maxExtrapolation`, flagged input union, `scaleMismatch`/`trainedScale`/
  `holdoutR2`). Forward references (an input only a higher stage produces) are reported
  `missingInputs`, never silently zero-filled; an output naming an undeclared field is reported
  `unappliedFieldOutputs` rather than being a silent no-op.
- **`GenericSurrogate::coverageVector`** — positional training-domain coverage so the batched path
  gets the same trust profile without rebuilding a string-keyed map per element; `coverage(map)`
  now delegates to it, so the two forms cannot drift apart.
- **`ctx.evolve(spec)`** (`src/js/JsRuntime.cpp`) — the JS boundary. Strict-mode gated (returns
  `null` **and leaves the state untouched**, so a strict run can never silently pick up inferred
  physics); shared context always starts from the ambient Geant4 base (`buildAmbientGeant4Seed`),
  scenario `context` overrides per key; an explicit `models` list overrides selection, otherwise
  the engine chooses the one compatible `operator_role`/`element_kind` group whose
  `required_context_keys` are present;
  mutates the scenario's own `Float64Array`s **in place** so a per-step operator allocates no JS
  garbage. **Honest accounting: a batched operator over N elements with K stages reports N*K
  inferences in `hook_predict_count`** — it does not hide N predictions behind one call — and its
  out-of-domain element-stages feed `hook_predict_out_of_domain_count` like every other inference.
- **Tests:** new `tests/test_state_evolution.cpp` (13 groups, Geant4-free: rate integration,
  declared bounds both ends, rate accumulation across stages, intermediate chaining ordered by
  scale band and the reversed-order forward-reference case, `set_` visibility, the reserved `dt`
  input, shared-vs-field precedence, unapplied-output reporting, aggregated coverage
  measured-vs-heuristic, unloaded-stage degradation, purity) plus a `ctx.evolve` case in
  `tests/test_js_runtime.cpp` (in-place mutation, aux read-only, N*K counting, strict-mode).
  `ctest --preset dev` **12/12**.
- **Harvest path:** `harvest_table(..., expand=)` in
  [`tools/torch/trech_torch/dataset.py`](../../../tools/torch/trech_torch/dataset.py) + `--expand` on
  `trech-train-surrogate`: a payload key holding a LIST of per-element samples yields one training
  row per entry, with the emit's scalar columns merged in. This is what makes per-element operator
  training practical — one bounded emit per step carries many parcel samples instead of one hook
  emit per parcel.
- **Scenario wiring (`polyurethane_foam.js`):** the hand-written law is now isolated in
  `stepChemistryReference` (retained as the graded comparison **and** as the harvest teacher),
  beside `stepChemistryOperator`, which contains **no rate law at all** — it declares the eight
  per-parcel state fields (`gel`, `blow`, `temperature_k`, `dissolved_co2`, `trapped_gas`,
  `local_expansion`, `rigidity`, `inverse_relative_viscosity`) and hands them to `ctx.evolve`.
  Selected by the typed `chemistry_source` parameter (`operator` promoted default / `reference`
  teacher and audit fallback);
  `emit_operator_samples` adds the deterministic harvest sideband (every 10th step, every 10th
  parcel, full-size steps only). The operator model is declared **only** in operator mode, so a
  reference run's config and hash are untouched — and the reference path was verified
  **bit-identical** to the pre-refactor result across expansion, cream/gel/solid times, exotherm,
  core-skin gap and lean (two drifts found and fixed while extracting it: aggregates must be read
  before conduction redistributes heat, and `a/b` is not `a*(1/b)` in IEEE doubles).
  `inverse_relative_viscosity` is carried instead of the Castro-Macosko `eta_r` because it is the
  form every consumer uses and, unlike `eta_r`, does not diverge at the gel point.

### [landed 2026-07-25] First trained operator + independent fidelity gate

- **Committed model:** `data/polyurethane_cascade/meso_reaction_operator.json` is a portable
  LibTorch-free 27→32→8 `GenericSurrogate` MLP (2,216 parameters): eight state fields,
  `reactivity`/`exposure`, 16 shared coefficient/context facts and reserved `dt` → six
  `d_*_dt` rates + `set_rigidity` + `set_inverse_relative_viscosity`. It was fitted on 115,437
  expanded parcel rows spanning 285–310 K and 0.02–0.08 s, with actual full-population
  reactivity/exposure extrema added at every sampled step. Inputs are emitted at their exact
  teacher values (not rounded inward at the hull edge). The model carries a measured hull,
  `trained_scale_bands:["meso"]`, and a 38,565-row **independent-run** holdout with worst-output
  R²=0.9929; the adjacent manifest records the operating-point split, all output metrics and the
  2,216-parameter / ~80 KB deployment cost.
- **Trainer/harvest hardening:** `trech-train-surrogate --validation-runs` keeps whole simulation
  runs out of fitting, preventing neighbouring parcels from leaking across a random row split.
  `--note` / `--teacher` / `--measured` travel with both model and manifest; provenance paths are
  workspace-relative. The polyurethane sampler now emits both previously omitted operator state
  fields, uses the exact reserved `dt` input name, and includes live auxiliary extrema.
- **Independent model families can coexist:** `ctx.cascade(seed, modelNames)` optionally narrows a
  property pass to named stages, so declaring the meso operator beside the nano→macro property
  cascade cannot accidentally evaluate it on missing parcel inputs. The JS-boundary test checks
  the selected-stage result and honest inference count.
- **Paired observer gate:** both chemistry sources emit
  `operator_vs_reference{comparison_key,tolerances,observables}`. The new
  `polyurethane_operator_matches_reference` validation case requires identical seed/recipe/
  precision, measured domain, meso scale, no missing inputs, independent held-out R²≥0.99,
  no starved final-step inputs, held-out N≥30,000, low out-of-domain fraction, and guarded gaps
  for expansion, cream/rise/gel/solid, exotherm, core-skin temperature and trapped gas. This is
  the evidence gate for promoting the trained path, rather than treating a good row-wise R² as
  sufficient. The full 620-parcel / 180 s pair passes all eight gaps: expansion 0.56%;
  cream/rise/gel/solid 0.71/0.83/0.04/1.07 s; exotherm 0.16 K; core-skin gap 1.19 K; trapped
  fraction 0.0033. All 2,812,320 parcel-step inferences stay in-domain, with no missing or
  final-step starved input.
- **Promotion decision:** `operator` is now the scenario default. The full nominal/zero-gravity
  operator pair also passes the aggregate foam guard 26/26: 31.1× expansion, 5.0° vs 2.6° lean,
  28.8% vs 11.9% broken bonds, five parcels reaching the table vs zero, and less detachment
  without gravity. `reference` remains selectable and is run by the suite as the paired teacher;
  promotion does not relabel it as measured physics.
- **Honesty:** the deployable model and emitted summary both say its teacher is the retained
  reduced law and `measured:false`. This is *the reduced model, learned* — a migration of the
  operation into engine-side inference, not new experimental foam physics. Rates are conditioned
  on `dt`; only full-size teacher steps are harvested, while smaller remainder steps remain visible
  through the model's trust profile.

### [next] Complete the JS-law removal — audited migration programme

The remaining work is now an **explicit repository-wide migration**, not an open-ended request to
"use more ML." The audit covers every experiment with runtime hooks. A migration is complete only
when scenario JS declares context/state/topology, calls a reusable engine inference operator and
grades/emits the result; moving the same law into another `.js` helper does **not** count.

Follow the [migration contract](migration/ROADMAP.md), [shared prerequisites](prerequisites/ROADMAP.md) and [scenario ledger](../../scenarios/migrations/ROADMAP.md) for delivery and completion gates.
