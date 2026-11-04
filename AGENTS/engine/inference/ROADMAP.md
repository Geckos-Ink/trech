# Multi-scale inference — roadmap

[Root principles](../../../AGENTS.md) · [Root roadmap](../../../ROADMAP.md) · [Parent](../ROADMAP.md) · [Handbook](AGENTS.md)

## Choose a subcategory

| Scope | Context | Work remaining |
| --- | --- | --- |
| Coverage, uncertainty and trust | [AGENTS.md](trust/AGENTS.md) | [ROADMAP.md](trust/ROADMAP.md) |

Maintain work in its owning branch. Dated results apply to the recorded checkout; they do not validate subsequent changes.

## Cascade dependency trust

- [x] Out-of-domain evidence now propagates through the actual consumed facts even when a
  lower-stage output fits a later model's numeric hull. The trace distinguishes local coverage
  from inherited evidence; hook OOD accounting uses both. See the
  [trust workstream](trust/ROADMAP.md#dependency-trust-propagation) for semantics, regression
  coverage and the remaining cross-call/persistent-state lineage gaps.
- [x] Starvation (per-feature or joint) and off-trained-band evidence also follow consumed facts,
  with separate effective/local fields and sorted inherited input names. Their stage counters
  include inherited evidence; hull-domain/OOD accounting remains independent. See the same
  trust workstream for regression coverage and validation limits.

## 2026-10-18 — real input dependencies and continued 3D replay parity

- **[landed] No implicit zero physics.** `ScaleCascade`, `StateEvolution`, `DiscreteTransition`
  and `PairInteraction` skip predictions whose declared inputs are absent. Intermediate availability
  is tracked per element/pair and material kind, so registering a producer for one material cannot
  supply fake zeros to another. Traces retain `missingInputs`; only actual evaluations count as
  `ran`/inferences, and blocked discrete evaluations consume no draw. Neighbours have no persistent
  pair state unless linked; link geometry requires supplied positions. Explicit numeric zero inputs
  remain valid. Regression coverage includes biased missing-input models and material-local chains.
- **[landed] Point inference starts from Geant4 context.** `ctx.predict(name, features?)` now uses
  ambient event/material/optics facts just like cascade/operators. The surrogate demo replaces its
  fixed water density/composition with live Geant4 element mass fractions and density, waits for
  material initialization, and exposes a water/ethanol material control with a paired validation gate.
  This grades input sensitivity/provenance, not new accuracy validation for ethanol.
- **[landed] Studio radius/bond replay.** Emitted radii draw instanced sphere meshes, declared
  bonds follow held-frame centres, camera bounds include radii, and non-mm streams hide the
  unrelated Geant4 mm scene. GPU frame caches are bounded; malformed bond rows are dropped.
- **[validated]** `ctest --preset dev` 17/17; Studio's pure/UI suites and four Mac-GPU
  animation/capture tests pass. A real molecular-run capture was visually checked. Refreshed
  `docs/validation_report.{md,json}`: 49 cases, **42 pass / 0 fail/error / 4 info / 3 skip**;
  efflux, H2O-cycle, polyurethane and glass operator/reference gates all pass. The skips are the
  slow bulk-water, diffusion-temperature and shaken-glass scenarios; they were not rerun here.
- **[landed] Offline validation inputs.** `PUBCHEM_MODE=cache-only` preflights the selected
  local records and skips network refresh, failing before builds/output deletion on incomplete
  inputs. Default online behavior remains. See the [validation contract](../../tooling/validation/AGENTS.md).
- **[open] Training remains the larger gap.** This change removes fabricated missing-input
  predictions and one fixed feature vector; it does not replace the scenario migration ledger's
  authored material laws or turn distilled/illustrative maps into Geant4-trained response models.
  Continue the foam/CNT/resonance/chemistry migrations with independent data and observer gates.
- **[open] 3D parity remains partial.** Vectors landed 2026-10-19; moving apparatus/meshes, chart/label/grid overlays,
  stream selection, unit-labelled scale bars and transparent-sphere sorting remain in
  [desktop milestones](../../studio/ROADMAP.md#studio-desktop-ui). Sphere tessellation and bond line width are representation choices.

The standing objective retains its original baseline and dated landings. Current runtime contracts are in the [inference handbook](AGENTS.md); the [process workstream](../../scenarios/processes/ROADMAP.md) records later artifact and binding extensions.

## Multi-scale statistical inference (standing objective — the core engine thesis)

**This is the reason TRECH exists**, and like anti-degeneration it is a **primary, never-"done"
goal**: every iteration should make the statistical/ML layer predict *more of a context
automatically*, cascading a precise Geant4 particle/nano base up the dimension ladder
(atomic → nano → micro → meso → macro) to the scale of the observer/experiment — so a user can
pose a macroscopic question ("what does this glass of water do while I stir it — the fluid
motion, the waves?") and get an answer inferred from the microscopic truth, **without
hand-specifying every intermediate model** (only overriding when they *want* to be specific).

### The gap we are closing

Today the ML in the tree is **narrow point-predictors**: `OpticsSurrogate` (composition→n), the
event stratifier (features→p(exceptional)), and per-call `ctx.predict(name, features)`. Each is
correct, but each predicts *one hardcoded quantity the scenario must ask for by hand*. That is
"statistics used only for certain too-precise operations" — the opposite of a general-purpose
engine that predicts everything relevant in a context by default. The **cascade** is the bridge
from the former to the latter.

### Foundations landed

- **[landed 2026-07-05] Scale-cascade subsystem (first cut).** `ScaleCascade`
  (`include/trech/ml/ScaleCascade.hpp` + `src/ml/ScaleCascade.cpp`) chains the scenario's
  declared models **by scale band** into one deterministic pass: seed the context with
  Geant4-derived facts, evaluate stages in ascending scale order, and each stage's named
  outputs merge into the context so the next-higher scale consumes them automatically. Exposed
  to hooks as `ctx.cascade(seed) -> {...context, __cascade{stagesRun, trace}}`; the per-model
  band is a new physics-agnostic `ModelConfig.scale` (`atomic/nano/micro/meso/macro`, unscaled
  runs last, conditionally serialized so existing config hashes hold). Strict-mode-gated,
  counts each ran stage as a `hook_predict_count` inference, degrades to the bare seed when no
  models load. Guarded by `tests/test_scale_cascade.cpp` (C++, Geant4-free: chaining, scale
  ordering independent of declaration order, missing-input recording) and a two-stage
  `ctx.cascade` case in `tests/test_js_runtime.cpp`. This is the *plumbing* for the doctrine;
  the models that ride it are the ongoing work below.

### Workstreams (rotate through these; each iteration should push at least one)

1. **Seed the cascade from Geant4 automatically. [landed 2026-07-11]** `ctx.cascade()` now
   **auto-seeds from the ambient Geant4 base** with no argument: `buildAmbientGeant4Seed` in
   `src/js/JsRuntime.cpp` populates the seed from the active hook context's per-event tallies
   (`edep_mev`, `track_length_mm`, `step_count`, `track_count`, `optical_photon_{steps,tracks,
   track_length_mm}`) and, when the scenario opted into `materialProbe`, the material probes
   (`material.<name>.{density_g_per_cm3, electron_density_per_cm3, mean_excitation_energy_ev,
   radiation_length_mm, number_density.<Element>}`). An explicit `ctx.cascade(seed)` argument
   still overrides/augments per key (override-on-demand), and the seed keys are surfaced on
   `__cascade.seedKeys` (sorted) for provenance. The bottom of the ladder is now *always* the
   real Geant4 base — the scenario copies nothing by hand. `cascade_multiscale_demo.js` was
   switched to the argument-free call (physics identical: edep 1 → `ionization_density` 0.6 →
   `bulk_response` 2.4). Deterministic (pure function of the numeric Geant4 facts), strict-mode
   still returns null. Guarded by a new argument-free `ctx.cascade()` case in
   `tests/test_js_runtime.cpp` (ambient event + material seeding, seed-key provenance).
2. **Train real chained stages, not toy ones.** Land at least one genuine two-band chain where a
   lower-scale surrogate trained on Geant4 output feeds a higher-scale one (e.g. material EM/optical
   facts → droplet/bulk property → observable). Reuse `trech-train-surrogate` per stage; validate
   each band held-out (LOO / beats-baseline), and gate promotion like the optics ridge.

3. **Coverage/uncertainty per band:** follow the [trust workstream](trust/ROADMAP.md#workstream-3--coverage-and-uncertainty) for the full mechanism, remaining adoption and calibration work. Independent event resim policies now act on starvation and wrong-scale evidence; automatic resimulation/retraining remains open.
4. **Worked cascades across the scenario families — NOT just optics/fluids.** The cascade is
   domain-agnostic; land real per-band chains in several families, not one. The canonical thesis
   example is the "glass of water" (fluid movement/waves inferred from a Geant4-derived
   microscopic base). **[canonical glass-of-water landed 2026-07-11]**
   `examples/scenarios/glass_of_water_shaken/glass_of_water_shaken.js` pours ~1 L of water into a wide glass and shakes
   it, answering the thesis question directly: a short rigid-SPC/E nano MD **measures** water's
   number density (0.0334/Å³) and hydrogen-bond coordination (≈4.86, g(r) peak 2.77 Å),
   `ctx.cascade` lifts those facts **nano→micro→macro (3 bands in one pass, zero hand-wiring)** into
   the macroscopic fluid parameters, and a Position-Based-Fluid solver (uniform spatial grid,
   ~4,300 particles at ~6 mm) plays three phases the video shows — **pour** (water falls from a
   faucet and fills the tumbler), **settle**, **shake** (smooth-but-random) — with waves and
   splashes that stay contained (mass conserved) and stable. **No macroscopic water property is
   hand-typed**: the rest density comes out at 999.2 kg/m³ (a *grounded* n→ρ coarse-graining, 0.10%
   off measured water — a check, not an input), and the cohesion (which merges drops on contact,
   drawn as a **2 mm metaball isosurface**) + viscosity come from the measured coordination.
   Illustrative stage models under `data/glass_cascade/` (density grounded, cohesion/viscosity
   labelled illustrative — same honesty as `cascade_demo`); rendered by
   `tools/viz/demos/render_glass_of_water_shaken.py`; guarded by `glass_of_water_shaken_waves`
   (category `fluid`). **Chemistry now has a cascade too (landed 2026-07-25):**
   `examples/scenarios/briggs_rauscher_oscillator/briggs_rauscher_oscillator.js` lifts the Geant4-built reagent/mixture
   materials + declared recipe through a two-stage cascade (`data/briggs_rauscher_cascade/`) into
   the coefficients of a reduced FKN/Oregonator oscillator; the oscillation (8 colourless→amber→
   deep-blue cycles, amber-before-blue, ~10.5 s period, settle on reagent depletion) is emergent,
   not typed, and guarded by `briggs_rauscher_oscillation` (category `chemistry`, 10/10). **Two
   reactive-foam cascades landed 2026-07-25:** `examples/scenarios/polyurethane_foam/polyurethane_foam.js`
   (`data/polyurethane_cascade/`; dual gel+blow reactions → 26.9× expansion, cream→gel→solid
   ordering, rigid porous endpoint; guarded by `polyurethane_foam_expansion`, 15/15) and
   `examples/scenarios/elephants_toothpaste/elephants_toothpaste.js` (`data/elephants_toothpaste_cascade/`;
   iodide-catalysed runaway → 8e4× acceleration, 18.4× steaming lather eruption, drains and never
   solidifies; guarded by `elephants_toothpaste_eruption`, 16/16) — the pair demonstrates emergent
   *consistency* (rigid sponge vs soft lather) from the same doctrine, and — since the foam
   mechanics upgrade — emergent **gravity/imperfection consequences** (leaning, cracking, shedding
   pieces onto the table) graded against a zero-gravity control. Still open
   on this workstream: biology (efflux/osmosis cell observables), CNT electronics
   (gap→device→logic), and magnetic resonance (proton density→image) each have the same
   micro→observer arc and should get a cascade too, and the chemistry + fluid stage models should
   graduate from illustrative maps (Briggs–Rauscher's macro response surface is a compact
   illustrative map, σ=0.12 emitted; the polyurethane σ=0.14 and elephant's-toothpaste σ=0.15
   response surfaces are equally illustrative — a wider trained reactive-foam / catalytic-kinetics
   panel is the follow-up) to **trained, held-out-validated** per-band chains. See the
   scenario-family table in the AGENTS.md "Multi-scale statistical inference" doctrine.
5. **Default-on, override-on-demand.** Progress the API so a scenario opts into "predict the
   relevant behaviour for this context" and only specifies models/scales when it wants to
   constrain them — the "without requiring to be specified (if not forced by user)" target.
   **[per-material dynamic selection landed 2026-08-15]** The inference level is no longer fixed
   for a run: `ctx.evolve`'s `element_kind` accepts a per-element array, and the engine selects an
   operator **per material** from that material's own context, binding each group's stages to its
   own elements (`EvolutionStage.elementKindIndex`). Two materials sharing one state array are
   advanced by different trained operators in the same deterministic pass; a material that selects
   nothing is reported (`selection.groups[]`, run status `partial`) and left **bit-identical**
   rather than being pushed through another material's law, and `hook_predict_count` grows by
   matched element-stages only. Guarded by `tests/test_state_evolution.cpp` (per-kind operators,
   an unclaimed kind, a kind-free stage composing with per-kind ones) and a JS-boundary case in
   `tests/test_js_runtime.cpp`. **[extended 2026-08-15]** the same per-element kind selection now
   covers `ctx.react` (an unclaimed cell consumes no RNG draw and mutates nothing, so the other
   cells' seeded draws are unaffected), and `ctx.interact` selects per canonical **pair kind** —
   the engine composes the unordered material combination (`melt|sand`) from the two members and
   binds each stage to one combination, because a grain-grain, a grain-melt and a melt-melt contact
   are three different interactions. Every operator now reports its per-kind groups, and each stage
   trace carries the kind it served and how many elements/pairs it actually evaluated. Guarded by
   new groups in `tests/test_state_evolution.cpp`, `tests/test_discrete_transition.cpp`,
   `tests/test_pair_interaction.cpp` and the JS-boundary case in `tests/test_js_runtime.cpp`.
   **Landed with a scenario that needs it:** `examples/scenarios/glass_from_sand/glass_from_sand.js` ([material-creation milestone](../../scenarios/processes/ROADMAP.md#2026-08-15-material-creation-a-run-that-makes-a-new-material)).
   **Remaining:** the stage models there are hand-authored illustrative maps — a *trained*
   per-material chain is still the open workstream-2 gap.
6. **Move the hard-coded per-element physics/chemistry OUT of scenario JavaScript and into
   engine-side trained inference. [mechanism + first trained operator + paired fidelity gate
   landed 2026-07-25; broader operators pending]** See the [engine-side operator workstream](../operators/ROADMAP.md#engine-side-inference-operator--removing-hard-coded-js-physicschemistry).

### Cascade metrics to watch (regression signals)

- **Scales bridged in one run**: how many distinct bands a single cascade chains (baseline
  narrow-ML = 1). Growth here is the headline signal that the engine is becoming multi-scale.
- **Hand-wired predictions eliminated**: fraction of a scenario's predictions that come from
  `ctx.cascade` (auto-chained) vs. individual hand-built `ctx.predict` calls.
- **Per-band held-out accuracy** and **fraction of stages flagged low-confidence** (once
  workstream 3 lands) — so a longer cascade cannot silently trade accuracy for reach.
- **Stages flagged jointly starved** (in range on every axis, far from any training point) and the
  count of committed models that carry a joint reference at all — an unchecked model is not a clean
  one. `plan_experiments --models` converts both into the operating points to simulate next.
- **Fraction of emitted uncertainties that are measured** rather than hand-typed: every inferred
  quantity a scenario reports with a σ should be reporting the engine's `outputAccuracy.rmse`, not
  a constant in the scenario. Today the mechanism exists on every inference path and the nine
  committed trained operators carry σ; no scenario has switched over yet.
- **Model evaluations per second** (the inference core is now the inner loop of operator-backed
  scenarios: a polyurethane run performs 2.8M evaluations). Reproduce with the `-O2` A/B harness in
  the [batched-inference-core entry](../operators/prerequisites/ROADMAP.md#engine-prerequisites--land-in-this-order); a regression here shows up as run time, not as a wrong
  number, so nothing else will catch it.
