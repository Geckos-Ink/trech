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

**Author-notes foundations:** `nacl_dehydration_reference.js` +
`trech_crystallization_reference.js` and `aerodynamics_reference.js` +
`trech_euler_reference.js` are explicitly independent comparison fixtures, not particle-trained
phase-change/aerodynamic predictions. They emit generic material frames, preserve serial
execution and snapshot comparison assumptions in `hooks.inputs`. Scope/tests:
[`docs/process_references.md`](docs/process_references.md). Do not promote illustrative salt
capacity/attachment or ideal-gas Euler laws into Geant4 truth or claim metal temper/fracture.
`JsRuntime::authoringMetadataJson` supplies inspected source inventories and optional
`TRECH_STUDIO` descriptions outside the physics config; Studio edits included modules and applies
these declarative panels/process descriptions on Save. [`docs/studio_authoring.md`](docs/studio_authoring.md).

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
> today: `ScaleCascade` + `ctx.cascade` (chains scale-tagged models), `GenericSurrogate` +
> `ctx.predict` (single models), `StateEvolution` + `ctx.evolve` (continuous named state),
> `DiscreteTransition` + `ctx.react` (integer stochastic state), and `PairInteraction` +
> `ctx.interact` (pair/neighbour interaction). This callout is deliberately
> redundant with those sections so
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

- **Studio Chemistry README screenshots** live in `docs/images/studio-chemistry/` with a
  capture guide and SHA-256 manifest. They are unmodified native-window captures, including
  the Metal viewport, distinct from the gated animation references under `studio/tests/reference/`.
  Refresh deliberately; preserve captions separating authored structures, independent quantum
  density comparisons and Geant4 nuclear initial-state ensembles.

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
- **Current dependency checkout:** Geant4 `f3d5293d38` (`v11.5.0.beta`), json
  `8617d9c94` (upstream develop), QuickJS `19d6bd8`, Evolvo `7ca9c66`.
  These upstream revisions have not yet been rebuilt or validated together; existing build
  outputs and validation reports do not establish compatibility with this checkout.
- **Local LibTorch:** gitignored `thirds/torch` is the official macOS ARM64 CPU package
  2.14.1, replacing the old x86_64 1.2.0 installation. It is not a submodule; normal presets
  keep it off. `Torch_DIR` points at `thirds/torch/share/cmake/Torch`. Standalone C++20
  tensor/TorchScript smoke passes; enabling Torch in TRECH currently fails because 2.14
  requires C++20 and `TorchScriptStub` implicitly destroys an incomplete `Module` type.
  Both integration gaps are tracked in `ROADMAP.md`.
- **Optional V8 foundation:** official `thirds/v8` submodule `06637ec79e4` (15.9.0 candidate),
  not built and not the hook backend. `TRECH_ENABLE_V8_PROBE` defaults OFF; its standalone C++
  compile/code-cache probe is syntax-checked against pinned headers, not linked/run. Normal
  builds retain QuickJS; full host parity and performance are unvalidated. See
  [`docs/v8.md`](docs/v8.md); never trigger a heavy upstream build implicitly.

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
- **Lift particles into atoms and molecules through learning.** Train and validate the
  higher-scale response even where Geant4 has no bound-atom/molecule representation.
  Particle-derived model outputs must drive that response. Keep independent quantum/PubChem
  comparisons identified as such; material identity alone does not make a model particle-trained.

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

- **Multi-molecule probability scenes:** `trech_chemistry_scene_v1` holds named placed/rotated
  structures, explicit links and supplied timed density frames. `TRECH_READ_JSON` parses data
  without evaluating it. Canonical scenes/fields enter `hooks.inputs` and round-trip through
  import/export/restore; electron fields must match their placed owners' geometry/isotopes/charge.
  `quantum_frame` preserves density values, units, source, time kind and shared owner IDs. Strict
  mode omits imported `inferred` fields; independent quantum comparisons remain labelled.
  Occupied-energy density components require a complete electronic spectrum even when its
  frame key is absent/null; inspection rejects orphan components before any inference.
- **Nuclear spatial diagnostics never drive transport.** Opt-in `materialProbe.nuclearSamples`
  samples `G4Fancy3DNucleus` on an isolated RNG engine for explicit isotopes (2≤A≤250), reports
  proton/neutron positions in fm and labels independent ensemble indices, not physical time.
  Natural mixtures and single-proton internal distributions are not invented. Tests verify exact
  replay, nucleon counts, RNG preservation and identical transported tallies with sampling on/off.
  `chemistry_probability_reference.js` adds a joint water/D2 RHF/6-31g **comparison** density;
  this is not Geant4-trained electronic dynamics. See `docs/chemistry_probability.md`.

- **Chemistry workbench is an authored graph, not inferred stability.**
  `chemistry_mode.js` + `trech_chemistry.js` validate explicit structures and derive
  isotope/atom/charge conservation for optional `ctx.react` plans. Natural-neutral CHNO
  structures reuse the Geant4-trained particle response; isotope/ion response and general
  stability/polarization remain unavailable. No built-in reaction rates or valence rules.
  `hooks.inputs` records authored state in config/hash/provenance. Studio's Chemistry dock
  edits those inputs and displays engine emits. Contract: [`docs/chemistry_mode.md`](docs/chemistry_mode.md).
- **Stoichiometry/isotopes come from Geant4.** Material components may use positive integer
  `atoms` instead of `fraction` (all-element/all-atoms mode); optional `massNumber` builds a
  pure isotope using Geant4's tabulated mass. Unknown isotopes/stoichiometric elements fail
  closed. Opt-in `materialProbe.includeIsotopes` reports isotope inventories; same-symbol
  number density sums split isotope components. Ambient inference seeds recorded nuclide facts
  under `material.<name>.isotope.Z<z>.A<a>.*`; absent nuclides are unknown, never zero.
  Tests: `test_material_isotopes`, `test_chemistry_authoring`, `scripts/validate_chemistry_mode.py`.

Named invariants with their enforcing code and tests. Violating one silently corrupts
reproducibility or physics honesty.

- **Strict mode disables `ctx.predict`/`ctx.cascade`/`ctx.evolve`/`ctx.react`/`ctx.interact`.** All
  five return `null` outside `predictive` mode; `ctx.evolve`/`ctx.interact` leave continuous element
  (and pair) state untouched and `ctx.react`
  consumes no RNG draw/call sequence and leaves integer state untouched, so a strict run can never
  silently pick up inferred physics. Enforced in
  [`src/js/JsRuntime.cpp`](src/js/JsRuntime.cpp); counted as `hook_predict_count` (a K-stage cascade
  = K predictions; a K-stage operator over N elements = **N×K** predictions — a batched call does
  not hide N inferences behind one call). Tests:
  [`tests/test_js_runtime.cpp`](tests/test_js_runtime.cpp).
- **Missing inference inputs never become synthetic zero facts.** All hook prediction paths
  require their declared inputs. A cascade stage with missing inputs is recorded and skipped;
  batched operators check intermediate availability separately per element/pair and material kind.
  Blocked stages add no inference count, state change or reaction draw. Supplied zeros are valid.
  `ctx.predict(name, features?)` now starts from the same ambient Geant4 facts as the operators and
  returns `null` for missing required inputs. The generic-surrogate demo reads composition/density
  from live material probes, with a water/ethanol perturbation guard.
- **`ctx.react` owns discrete invariants, not reaction knowledge.** Models predict only bounded
  hazards/channel weights. The caller declares integer species, channel deltas, and conserved
  coefficient vectors; `DiscreteTransition` validates exact conservation before inference,
  uses only hazards produced for that element (shared hazard keys cannot replace a blocked model),
  performs deterministic draws, enforces non-negative availability, and applies deltas atomically.
  A malformed/non-conserving topology or ambiguous hazard interface never draws or mutates.
- **Precision is a profile mapped onto scenario axes, never one global "quality" number.**
  `config.precision` carries a rung (`preview`/`balanced`/`high`/`convergence`, or `custom` when a
  control overrode it) plus the axes the scenario mapped onto it, each with a physics-agnostic role
  (`spatial`/`temporal`/`output`/`statistical`/`representation`), its control, unit, resolved value
  and `balanced` reference. C++ owns the vocabulary + uniform reporting
  ([`src/core/Config.cpp`](src/core/Config.cpp), `precision_profile`/`precision_axes` in scores,
  `precision_profile`/`precision_axis_count` in provenance); the *ladder* lives in
  `helpers.precision` ([`examples/experiments/trech_helpers.js`](examples/experiments/trech_helpers.js))
  because only the scenario knows what refining its own axis means. A `representation` axis is
  forced display-only by the parser, so a render knob can never read as improved physics.
- **Continuous precision and budgets:** `--refinement` injects `TRECH_REFINEMENT` for
  `helpers.precision.resolve` (or use JS `factor`); scenario bounds/overrides remain authoritative.
  `run.timeBudgetSeconds`/`--time-budget` are predictive batch-only soft event-boundary budgets,
  using `src/core/SimulationBudget.cpp` and a serial Geant4 manager. Run-end `n_events` is actual;
  `requested_events`, budget, wall time and stop reason are conditional metadata. Strict rejects
  timing budgets. `ScaleCascade` chooses dependency-ready stages within a band, with registration
  order breaking ties; optional third-argument `ctx.cascade` limits (`maxStages`, `targetOutputs`)
  disclose every omitted stage. No three-stage cap. Full contract: [`docs/adaptive_precision.md`](docs/adaptive_precision.md).
- **Evolvo is optional offline tooling:** pinned submodule `thirds/evolvo`; adapter/trainer
  `tools/torch/trech_torch/evolve_structure.py` evolves bounded MLP definitions, selects on
  validation runs and reports accuracy on separate test runs. Never import it into C++/Studio or
  present genetic candidates as Geant4 truth. Ordinary surrogate training accepts `--depth N`.
- **One call may span several materials, each with its own operator.** `ctx.evolve`, `ctx.react`
  and `ctx.interact` all accept a per-element ARRAY for `element_kind`. `ctx.evolve`/`ctx.react`
  select an operator per element kind; `ctx.interact` composes the canonical unordered **pair kind**
  (`PairInteraction::pairKindName`, e.g. `melt|sand`) and selects per material *combination*. A kind
  that selects nothing is reported (`selection.groups`, run status `partial`), its elements stay
  **bit-identical**, and `ctx.react` consumes no RNG for it — never advanced (or drawn) by another
  material's law. Inference counting follows *matched* element-/pair-stages. This is what lets a
  scenario whose cells CHANGE material mid-run (`glass_from_sand.js`) keep using the right
  operator.
- **`ctx.interact` owns pair enumeration and equal-and-opposite application, not the interaction
  law.** Pairs are canonical `(a,b)`, `a < b`, enumerated in ascending index order so the
  floating-point accumulation cannot change with the cell size or hash-map layout; a declared link
  is always evaluated and never double-counted against the cutoff search; a field's declared
  symmetry applies the *same double* to both members (antisymmetric ⇒ the pair exchange cancels
  exactly); contributions accumulate and apply once, so no member sees a half-updated neighbour.
- **Accumulating hook scenarios MUST set `run.threads: 1`.** Hook-layer state that grows across
  events (MD baths, Bloch, reaction ledgers, fluid solvers) is non-reproducible under Geant4 MT
  because worker event-completion order varies. This is the single most common determinism bug.
- **New config fields are conditionally serialized.** Emit a field only when non-default so config
  hashes stay byte-identical for scenarios that don't use it (`materialProbe`, `analytic.checks`,
  `models[].scale`/`operator_role`/`element_kind`/`required_context_keys`, `precision`, beam
  spread/polarization/spectrum, `run.threads`, `physics`, …). Enforced in
  [`src/core/Config.cpp`](src/core/Config.cpp); round-trip in [`tests/test_config_roundtrip.cpp`](tests/test_config_roundtrip.cpp).
- **Post-`Initialize` carriers are pre-allocated before `SetUserInitialization`.** `derivedOptics`,
  `analyticChecks`, `materialProbes` are `shared_ptr` carriers on `RunOptions` filled after Geant4
  `Initialize` (tables built) in [`src/sim/GeantRunner.cpp`](src/sim/GeantRunner.cpp) and paired
  with the measured tally in `RunAction::EndOfRunAction`. A copy made before the carrier exists
  sees null — allocate first.
- **VizRecorder records the *outgoing* momentum direction.** Each point's `dx/dy/dz` is its
  outgoing segment's direction: post-step points carry the post-boundary (refracted/reflected)
  direction; the birth point uses `GetPreStepPoint()->GetMomentumDirection()` (not the track's
  post-step `dir`, which mis-records emission for a photon that interacts on step 1) and the
  pre-step kinetic energy (else step 1's energy loss vanishes from a Bragg curve). Optical
  boundary points carry `boundary` = the `G4OpBoundaryProcess` status class
  (refraction/reflection/total_internal_reflection/absorption/detection). See
  [`src/sim/VizRecorder.cpp`](src/sim/VizRecorder.cpp), [`src/sim/SteppingAction.cpp`](src/sim/SteppingAction.cpp).
- **Trajectory consumers must not infer scattering from a visible bend.** Points carry the Geant4
  `process`/classified `interaction`; scatter emphasis requires the recorded `scatter` class.
- **Material number density is element density.** `ctx.materials["…"].numberDensityPerCm3.H`
  is hydrogen atoms/cm³ from the constructed `G4Material`, summed over isotope components.
  Isotope-specific ¹H observables must use `elements[].isotopes[]`, not equate D/T with ¹H.
  [`src/sim/MaterialProbe.cpp`](src/sim/MaterialProbe.cpp), opt-in via `materialProbe`.
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


**Electronic reference service and state views:** `tools/quantum/build_density_scene.py --scene`
calculates optional independent PySCF RHF/6-31g joint density, occupied/LUMO probability grids,
orbital energies/occupations, total energy and dipole for a bounded edited scene. Studio delegates
through `engine/quantum.py`, then ordinary TRECH inspection/run; it imports no quantum solver.
JS checks geometry binding, spectrum/field agreement, occupation sum and live Geant4 Z minus
charge. `quantum_frame` carries `electronic_structure` and `particle_inventory`; strict also
suppresses inferred spectra. States/particles UI selects recorded orbitals and reports counts.
C++ `NuclearSpatialProbe` adds exact inventory, centroid/species RMS distances and finite sampled
radial counts; one-nucleus fm guides remain display choices. Full scene restore uses hashed
`provenance.config_json.hooks.inputs.scene`; summary emits avoid repeating every grid. These are
independent reference/diagnostic improvements, not a Geant4-trained electronic lift. Scope and
remaining open-shell/correlation/dynamics work: `docs/chemistry_probability.md`, both roadmaps.


**Interactive scalar-field inspection:** generic C++ `scalarFieldStatistics` / authoring
`TRECH_FIELD_STATS(values,spacing)` computes signed integrals and 1–99% absolute-mass ranked
thresholds, including full ties and actual enclosed fractions. JS ignores imported statistics and
recomputes them, with no model inference or normalization. Optional signed real `amplitude`
point samples accompany cell-average orbital |ψ|². `density_difference` fields explicitly name
their reference; ordinary densities remain nonnegative. The optional PySCF tool supplies joint
minus isolated-fragment density on a common grid (own fragment bases; not a bonding test).
Studio's `ui/density_explorer.py` / pure `render/density.py` provide movable numeric heatmap
sections, log legends and enclosed-mass controls. `render/density_gpu.py` + `shaders/density.wgsl`
ray-march recorded fields; `+ψ/−ψ` lobes and orbital overlays retain the supplied signs. The
maximum-scaled float16 GPU texture/interpolation/alpha are representation; original CPU values
and C++ statistics are unchanged. Scalar contours use outward winding and separate display
lighting, not material optics. Probability contours are not extra quantum energy levels.
Chemistry raises its explicit per-record emit budget to 8 MiB for phase/difference records;
full multi-frame grids remain in provenance, with existing streaming residuals in both roadmaps.

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
  `optics`/`materials`/`geometry`/`hooks`/`models`/`materialProbe`/`analytic`/`nuclear`/`precision`/
  `stratify`/`viz`/`lab`/`system`/`multiscale`/`physics`); `PhysicsConfig` (`physics.list` names a
  Geant4 reference list — empty keeps QBBC; `radioactiveDecayThresholdYears` raises Geant4's 1-year
  very-long-decay cut; string shorthand = list); `configFromJsonString`; `configToJson`. Collections
  normalize single-or-array; `environment`/`medium` alias `detector` at parse time (canonical output
  stays `detector`). `ModelConfig` carries cascade `scale` plus contextual operator
  `operatorRole`/`elementKind`/`requiredContextKeys`. `PrecisionConfig`/`PrecisionAxisConfig` carry
  the run's precision rung and the scenario-mapped axes (`precision` shorthand: a bare string is the
  profile; an unknown name normalizes to `custom`; a `representation` role is forced display-only).
- **Tests:** [`tests/test_config_roundtrip.cpp`](tests/test_config_roundtrip.cpp) (byte-stable hashes).
- **Common mistakes:** unconditionally serializing a new field breaks every scenario's config hash;
  gate it on non-default and extend the round-trip test.

#### [`src/core/RunOptions.cpp`](src/core/RunOptions.cpp) · [`RunOptions.hpp`](include/trech/core/RunOptions.hpp)

CLI parsing and run-time option carrier. Owns the command dispatch surface.

- **Key symbols:** `enum class CliCommand { Run, Inspect, Lab }`; `RunOptions` (carries
  `command`, paths, seed/events overrides, `scriptParameterOverrides`, hook counters, the
  post-`Initialize` carriers `analyticChecks`/`derivedOptics`/`materialProbes`, `hookRuntime`,
  and the observation-only 3D capture `captureViz`/`captureVizNonOptical`/
  `captureVizMaxTrajectories` from `--viz`/`--viz-all`/`--viz-max-trajectories`);
  `parseRunOptions`; `runUsage`; `applyRunOverrides` (applies the capture to `cfg.viz`).
- **Common mistakes:** a `--viz` capture changes the captured run's serialized config/hash (it is
  a different, honestly-recorded run); never make it the default.
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
mode, stratify model hash, hook/patch/emit/predict counters incl. `hook_predict_out_of_domain_count`,
event moment summaries).

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
  for `ctx.predict`/`ctx.cascade` and every batched operator; lazily cached per hook dispatch,
  copied before caller overrides, and invalidated for every new context). `ctx.predict(name, features?)` and
  `ctx.cascade(seed?, modelNames?) -> {...context, __cascade}` are implemented here. `ctx.evolve`
  also owns contextual operator selection: `operator_role` + `element_kind` +
  `required_context_keys` choose one compatible scale-ordered group from ambient/context facts,
  surfaced through `result.selection`; ambiguous/no-compatible results do not mutate state.
  `ctx.react` reuses that selection and binds integer inventories + declared stoichiometry to
  `DiscreteTransition`, deriving a deterministic sub-seed per call. `ctx.interact` reuses it again
  and binds positions/cutoff, declared field symmetry and persistent links + pair state to
  `PairInteraction`.
- **Tests:** [`tests/test_js_runtime.cpp`](tests/test_js_runtime.cpp) (includes two-stage
  `ctx.cascade`, ambient-seed case, contextual `ctx.evolve` selection/no-mutation, the
  `ctx.interact` neighbour/bond case, `TRECH_INCLUDE` error filenames/lines, `TRECH_FLOW`).
- **Common mistakes:** enabling inference in strict mode; forgetting predict-count plumbing.

The C-function bindings for all authoring globals and `ctx.*` live in `JsRuntime.cpp`.
Stage training metadata and string-array serialization use shared helpers there, preserving
property order and absent-metric semantics across cascade/evolution/reaction/interaction traces.

### C++ engine — `trech_ml` ([`src/ml/`](src/ml/), [`include/trech/ml/`](include/trech/ml/))

All ML degrades gracefully without LibTorch: the two learned inference paths carry a LibTorch-free
`.json` backend chosen by file extension, so Geant4-trained models run in a stock build.

#### [`src/ml/ScaleCascade.cpp`](src/ml/ScaleCascade.cpp) · [`ScaleCascade.hpp`](include/trech/ml/ScaleCascade.hpp)

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
  `collectOutputAccuracy` (declared alongside `NamedOutputAccuracy` here, the shared record every
  inference path reports through) fills each stage's per-output measured error.
- **Tests:** [`tests/test_scale_cascade.cpp`](tests/test_scale_cascade.cpp) (ordering/missing-input,
  per-stage coverage in/out-of-domain + `stagesExtrapolating`, missing-input blocking, scale-mismatch + carried holdout,
  Geant4-free) + JS-boundary case in `test_js_runtime.cpp`.

#### [`src/ml/StateEvolution.cpp`](src/ml/StateEvolution.cpp) · [`StateEvolution.hpp`](include/trech/ml/StateEvolution.hpp)

The per-element inference **operator**: where `ScaleCascade` answers "given this context, what are
the properties?", this answers "given this state, how does it CHANGE over dt?" — the half of the
physics scenarios used to hand-write as JavaScript per-element loops (reaction rate laws, relaxation
laws). Chains scale-tagged `GenericSurrogate` models over N elements in one deterministic pass.

- **Key symbols:** `EvolutionField` (name + the caller's declared bounds), `EvolutionRequest`
  (element-major `state`/`aux` blocks, `shared` context, `dt`, optional per-element
  `elementKindNames`/`elementKindIndex` for a multi-material pass), `EvolutionResult`
  (`inferenceCount` = stagesRun × elements, `outOfDomainInferenceCount`, per-stage
  `EvolutionStageTrace`), `StateEvolution::evolve`, `rateOutputName`/`assignOutputName`.
- **Naming convention (the whole domain interface):** `d_<field>_dt` → rate, accumulated across
  stages and integrated once per call; `set_<field>` → assignment applied immediately (visible to
  higher stages); anything else → intermediate merged into the per-element context. No domain name
  enters C++.
- **Tests:** [`tests/test_state_evolution.cpp`](tests/test_state_evolution.cpp) (Geant4-free) +
  the `ctx.evolve` case in [`tests/test_js_runtime.cpp`](tests/test_js_runtime.cpp), including
  contextual role/kind selection and ambiguous/no-compatible no-mutation.
- **Common mistakes:** resolving input names per element (plan once — the inner loop must be index
  arithmetic); applying rates immediately instead of accumulating (two stages must be able to drive
  one field); reporting one inference per call instead of stagesRun × elements.

#### [`src/ml/DiscreteTransition.cpp`](src/ml/DiscreteTransition.cpp) · [`DiscreteTransition.hpp`](include/trech/ml/DiscreteTransition.hpp)

The discrete learned operator behind `ctx.react`: N integer-state elements, declared
stoichiometric channels and conserved linear quantities, evaluated through scale-tagged
`GenericSurrogate` stages. It supports direct `hazard_<channel>` outputs or `hazard` plus
`weight_<channel>`, never both.

- **Key invariants:** topology/conservation validate before inference or RNG; hazards/weights clamp
  to [0,1]; competing direct hazards above unity renormalize deterministically; at most one channel
  is attempted per element per call; availability is checked before an atomic delta; integer state
  never goes negative. `inferenceCount` is N×K model evaluations while `drawCount`,
  `transitionAttempts`, `transitionsAccepted`, and `rejectedAvailability` remain distinct.
- **Tests:** [`tests/test_discrete_transition.cpp`](tests/test_discrete_transition.cpp) +
  the `ctx.react` boundary/strict-mode case in [`tests/test_js_runtime.cpp`](tests/test_js_runtime.cpp).

#### [`src/ml/PairInteraction.cpp`](src/ml/PairInteraction.cpp) · [`PairInteraction.hpp`](include/trech/ml/PairInteraction.hpp)

The pair/neighbour **interaction** operator behind `ctx.interact`: where `StateEvolution` answers
"how does THIS element change?", this answers "what does one element do TO ANOTHER" — the shape of
every remaining authored solver loop (MD force loops, bonded foam networks, PBF neighbourhood sums,
parcel cohesion/collision). The engine builds a deterministic uniform cell list, evaluates
scale-tagged `GenericSurrogate` stages over each canonical pair, and accumulates the result back
onto both members.

- **Naming convention:** `d_<element field>_dt` → rate contribution to both members (integrated once
  over `dt`); `add_<element field>` → direct increment (neighbourhood sum, no `dt`);
  `d_<pair field>_dt` / `set_<pair field>` → the pair's own persistent state (bond rest length,
  damage); anything else → intermediate. Members are read as `a_<name>`/`b_<name>`, geometry through
  reserved `r`, `dx/dy/dz`, `ux/uy/uz`, `dt`. `set_<element field>` is refused
  (`unappliedFieldOutputs`) — many pairs cannot assign one element one value.
- **Key symbols:** `PairElementField` (name + caller-declared `PairSymmetry` + bounds),
  `PairStateField`, `PairLink`, `PairInteractionRequest` (element-major state/aux, positions,
  `cutoff`, `maxNeighborPairs`, links + pair state, shared, `dt`), `PairInteractionResult`
  (`pairCount`/`linkPairCount`/`neighborPairCount`, `neighborPairsSkipped`, `invalidLinks`,
  `duplicateLinks`, `inferenceCount` = pairs × stages, per-stage `PairStageTrace`),
  `PairInteraction::interact`, `PairInteraction::pairKindName` (canonical unordered material
  combination; a stage's `pairKindIndex` binds it to one combination).
- **Tests:** [`tests/test_pair_interaction.cpp`](tests/test_pair_interaction.cpp) (Geant4-free) +
  the `ctx.interact` case in [`tests/test_js_runtime.cpp`](tests/test_js_runtime.cpp).
- **Common mistakes:** letting the cell map or the cutoff decide accumulation order (sort/enumerate
  by index instead); applying a bond only when it is inside the cutoff (a stretched bond is exactly
  the interesting case); scaling an `add_` neighbourhood sum by `dt`; reporting one inference per
  call instead of pairs × stages.

#### [`src/ml/GenericSurrogate.cpp`](src/ml/GenericSurrogate.cpp) · [`GenericSurrogate.hpp`](include/trech/ml/GenericSurrogate.hpp)

Scenario-agnostic named-IO learned inference. Portable `generic_surrogate_v1`/`v2` JSON feed-forward
(LibTorch-free; also loads `ridge_optics_n_v1`/`logistic_stratifier_v1`; optional `.pt`). Each
cascade stage and every `ctx.predict` is one of these.

- **Output links:** v2 declares one `identity`/`exp` inverse transform per output, applied after
  destandardisation. Its layers live under `network.layers` so older readers reject encoded
  targets. Overflow rejects the whole prediction before publishing any output; v1 arithmetic is
  unchanged. `trech-train-surrogate --log-outputs ...` fits positive targets in log space and
  reports held-out errors in decoded physical units. This is a generic numerical capability,
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
  metric is independently optional and an unmeasured output is absent, never a 0.
- **Tests:** [`tests/test_generic_surrogate.cpp`](tests/test_generic_surrogate.cpp) (feed-forward +
  coverage measured-vs-heuristic + missing-input-out-of-domain + carried bands/holdout). Trainer:
  [`tools/torch/trech_torch/train_surrogate.py`](tools/torch/trech_torch/train_surrogate.py)
  (exports `input_domain.standardized_radius` + `occupancy` + `joint` + `trained_scale_bands` +
  `holdout{r2_min,n,r2,mae,rmse}` so a trained stage carries its measured domain — per-feature AND
  joint — its scale band, and its per-output held-out accuracy).

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
Builds the physics list from `physics.list` (default QBBC; an unknown name throws before any run)
and applies `physics.radioactiveDecayThresholdYears` via `G4HadronicParameters` before process
construction — `config_nitrogen_carbon_cycle.js` uses `QGSP_BIC_HP` + 1e6 years so thermal
¹⁴N(n,p)¹⁴C and the ¹⁴C β⁻ decay are both Geant4-sampled (QBBC samples neither here).

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
subtype) and pushes trajectory points into the `VizRecorder`. **`RunAction::DispatchHook` returns
the dispatch's out-of-domain inference count**, and `EventAction::EndOfEventAction` uses the
`onEventEnd` count to *act on the coverage flag*: with `stratify.resimOnLowConfidence`, an event whose
inference ran out-of-domain is routed to `trech_resim_queue.jsonl` (`reason: inference_out_of_domain`)
and counted in `stratify_low_confidence_count` (a `stratifyLowConfidenceCount_` accumulable, distinct
from the feature-based `stratify_exceptional_count`).

#### [`src/sim/MolecularOptics.cpp`](src/sim/MolecularOptics.cpp) · [`AnalyticCrossCheck.cpp`](src/sim/AnalyticCrossCheck.cpp) · [`MaterialProbe.cpp`](src/sim/MaterialProbe.cpp) · [`VizRecorder.cpp`](src/sim/VizRecorder.cpp)

The Geant4-data extraction surfaces:
- **MolecularOptics** — derives n/absorption/scatter from `G4EmCalculator` cross sections (photo +
  Compton + Rayleigh) via Beer-Lambert + discrete Kramers-Kronig; anchor-free (`optics.derive`).
- **AnalyticCrossCheck** — `evaluateBeerLambert` / `evaluateCsdaRange` / `photo_fraction` (shared
  `fillAttenuationBreakdown`); each pairs a closed-form prediction from Geant4's own data with a
  measured tally via `AnalyticCheckResult.measuredField` (new check types stay data-driven).
- **MaterialProbe** — reports Geant4's known composition per material → `ctx.materials` +
  `material_probes` (opt-in, mirrors the analytic-carrier pattern). Optional
  `materialProbe.interactions{particle,processes,energiesMeV}` samples `G4EmCalculator`
  responses after initialization for learning. These are Geant4 interaction-table data, not
  MC tallies; unavailable queries omit numeric values. Default probe/config bytes stay unchanged.
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
`helpers.beamProfiles.spread` presets, `observer.linearClock`, and the common-library entry point),
[`trech_math.js`](examples/experiments/trech_math.js) (`helpers.math`: numeric bounds/coercion,
interpolation, rounding and finite-output checks),
[`trech_random.js`](examples/experiments/trech_random.js) (`helpers.random`: Mulberry32,
two-draw Box–Muller and stateless parcel noise), and
[`trech_material_facts.js`](examples/experiments/trech_material_facts.js) (`helpers.materialFacts`:
recorded optics plus comparison-only PubChem identity/lexical element checks).
Imports consume no RNG; solver modules can load these dependencies independently. Mulberry32
remains callable and supplies `.uniform` for the same Gaussian sampler as `ctx.rng`; engine
methods retain their receiver and no spare Gaussian is cached. `observer.linearClock` retains
physical and playback clocks; piecewise clocks stay scenario-owned. Helper contracts are tested
through QuickJS in `tests/test_scenario_helpers.cpp`. No shared utility is a new material law.
[`trech_water_md.js`](examples/experiments/trech_water_md.js)
(`TRECH_WATER_MD.create(cfg)` — the shared rigid-SPC/E MD core: force loop, SHAKE/RATTLE,
velocity-Verlet; both bulk water and the D(T) sweep build on it), and
[`trech_foam_solver.js`](examples/experiments/trech_foam_solver.js) (`TRECH_FOAM.create(cfg)` — a
chemistry-agnostic **growing viscoelastic bonded-parcel network under standard gravity**: the
scenario supplies per-parcel `growthRatePerS`/`relaxRatePerS`/`strengthScale`/`dragPerS` and the
module grows bond rest lengths, creeps stress away, breaks bonds past the failure strain, solves
contact/wall/ground constraints, and lets detached fragments fall ballistically and land — so
leaning, cracking, shedding and where debris lands are consequences, never scheduled. Both foam
scenarios build on it; gravity enters as a labelled physical constant, every material coefficient
is cascade-inferred). Families (see
[Features](#features-and-recurring-development-pitfalls) for behavior/status):

| Family | Canonical scenarios | Guard (category) |
| --- | --- | --- |
| Fluids / H₂O MD | `h2o_molecule_stability`, `h2o_cluster_fluid`, `h2o_bulk_water`, `h2o_diffusion_temperature`, `glass_of_water_shaken`, `lava_lamp` | `*_stable`/`*_structure`/`*_trend`/`glass_of_water_shaken_waves`/`lava_lamp_inferred_thermofluid` (`fluid`) |
| Optics | `viz_refraction_demo`, `validation_glass_of_water`, `glass_of_water_varied`, `glass_of_water_spectral`, `optics_surrogate_demo` | glass-of-water + `optics_surrogate_transport_applied` |
| Chemistry cycles | `testscenario_h2o_electrolysis_combustion`, `config_nitrogen_carbon_cycle`, `briggs_rauscher_oscillator`, `polyurethane_foam`, `elephants_toothpaste`, `glass_from_sand` | `h2o_electrolysis_combustion_cycle` + `h2o_cycle_operator_matches_reference`, nuclear cycle checks, `briggs_rauscher_oscillation`, `polyurethane_foam_expansion`, `elephants_toothpaste_eruption`, `glass_from_sand_material_creation` + `glass_operator_matches_reference` |
| Molecular series | `molecular_01_ethane` through `molecular_06_acetamide` (incl. butane/dimethyl ether; shared `molecular_series.js`) | `test_molecular_series.py`, `test_particle_molecule.py`, `scripts/run_molecular_series.py` (12 runs), `scripts/validate_particle_molecule.py` (15 runs incl. 90,000 MC photons) |
| Biology / membranes | `testscenario_efflux`, `testscenario_osmotic`, `testscenario_pascal` | `efflux_first_order_kinetics` + `efflux_operators_match_reference`, `osmotic_shift_observed`, `pascal_principle_holds` |
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
  paths + planner are numpy-only, `.pt` needs the `[torch]` extra);
  [`distill_discrete_scenario_operators.py`](tools/torch/distill_discrete_scenario_operators.py)
  owns the validation-only H2O/efflux teachers and regenerates their portable models/manifests;
  `plan_experiments.py` (active-learning coverage → `geant4_experiment_plan.json`; `--models`
  reads a trained model's exported domain and names the **operating points to simulate next**
  in raw input units — per-feature empty bins and the joint gaps between the regions training
  actually covered).
- **[`tools/validation/trech_validation/`](tools/validation/)** — the regression suite
  (`python -m trech_validation`): [`cases.py`](tools/validation/trech_validation/cases.py) (per-scenario
  assertions incl. hook-emit reads), [`runner.py`](tools/validation/trech_validation/runner.py),
  [`report.py`](tools/validation/trech_validation/report.py) → [`docs/validation_report.md`](docs/validation_report.md).
- **[`tools/viz/trech_viz/`](tools/viz/)** — PyVista 3D viewer (console script `trech-viz`).
  [`animate.py`](tools/viz/trech_viz/animate.py) owns held `material_frame` replay incl. the 3D
  observer extensions (`render_material_animation`; radii/bonds/vectors/apparatus meshes +
  `vertex_rgba`/legend/HUD/streams/labels/phase `grid` surfaces) and the shared GIF/text helpers
  (Unicode font, boxed text, `draw_caption`); [`tracks_view.py`](tools/viz/trech_viz/tracks_view.py)
  owns recorded-Geant4-track replay (`render_tracks`: fading trails, history colouring,
  process-marked vertices, `find_reactions` nuclide labels, `bundle_optical`, composition glyphs,
  split panes); [`charts.py`](tools/viz/trech_viz/charts.py) is the side chart panel (frame
  `samples`/`charts`/`curves`) and [`track_charts.py`](tools/viz/trech_viz/track_charts.py) the
  recorded-track statistics (Kaplan–Meier attenuation, Bragg, dispersion, reaction timeline, …).
  [`demos/render_readme_3d.py`](tools/viz/demos/render_readme_3d.py) regenerates every README GIF
  from real runs — **no scripted 2D renderer remains; do not add one** (a figure that cannot come
  from emitted state is a gap in the scenario's emits, not a job for a drawing script).
- **[`tools/pubchem/trech_pubchem/`](tools/pubchem/)** — property + 2D-structure cache;
  `fetch --conformer` adds comparison-only 3D coordinates/bonds/MMFF94 charges with atom-ID joins,
  response hashes and explicit missing-data rejection (`conformers.py`). Molecular quantum models
  never fit PubChem targets. Ordinary caches remain build-local; the molecular series pins small
  normalized comparison fixtures under `data/molecular_series/`.
  (`python -m trech_pubchem fetch <names>`; `TRECH_PUBCHEM`/`TRECH_PUBCHEM_CACHE_DIR`). XLogP
  is an explicit input to the learned efflux crossing model; chemistry showcase scenarios that
  declare structure-only policy use only CID/SMILES/formula, never density/boiling-point/colour.

### Committed models & data — [`data/`](data/)

Source-of-truth learned models and fixtures (NOT generated build output): the bounded quantum-reference
models/rows and pinned PubChem comparison fixtures under [`data/molecular_series/`](data/molecular_series/)
(see `docs/molecular_series.md`), the Geant4-trained shared atom/molecular particle-response
models and pinned labels under [`data/particle_molecule/`](data/particle_molecule/)
(see `docs/particle_molecule.md`), and cascade stage models
([`data/cascade_demo/`](data/cascade_demo/), [`data/glass_cascade/`](data/glass_cascade/),
[`data/beaker_cascade/`](data/beaker_cascade/), [`data/lava_lamp_cascade/`](data/lava_lamp_cascade/),
[`data/briggs_rauscher_cascade/`](data/briggs_rauscher_cascade/),
[`data/polyurethane_cascade/`](data/polyurethane_cascade/),
[`data/elephants_toothpaste_cascade/`](data/elephants_toothpaste_cascade/)),
[`data/discrete_operators/`](data/discrete_operators/) (promoted H2O-cycle and efflux
transport/crossing distilled models + independent-holdout manifests),
[`data/glass_furnace_cascade/`](data/glass_furnace_cascade/) +
[`data/glass_furnace_operators/`](data/glass_furnace_operators/) (the illustrative teacher family
for `glass_from_sand.js`: property stages, per-material thermal/chemistry operators and the six
per-pair-material conduction maps) +
[`data/glass_furnace_operators_trained/`](data/glass_furnace_operators_trained/) (the five
**distilled** per-material operators + manifests — measured meso hull, occupancy, band and
independent held-out metrics; the promoted `physics_source=operator` default),
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
interaction data with measured domains/holdouts (see molecular track below). General learned
state/bond/electronic dynamics across bands remain open.
Tracked as the standing objective in [`ROADMAP.md`](ROADMAP.md).

The JS-law audit source is [`tools/validation/js_law_audit.json`](tools/validation/js_law_audit.json).
It must list every hook-bearing experiment and name any remaining authored state-law residual.
[`tests/test_js_law_audit.py`](tests/test_js_law_audit.py) prevents unregistered hook scenarios and
regressions of the retired H2O/efflux normal-path function names. The audit currently records
2 fully operator-backed hook experiments out of 24; `operator_partial`/`reference_only` entries are
active roadmap work, not an honesty waiver.

### Fluids / H₂O — Shipped

Rigid-SPC/E MD reproduces measured structure (O-O g(r) first peak 2.798 Å) and dynamics
(self-diffusion Einstein 2.57 vs Green-Kubo 2.79 ×10⁻⁹ m²/s; D(T) trend). `glass_of_water_shaken`
cascades nano facts → macro PBF fluid params with no hand-typed macro property; `lava_lamp` is a
duration-independent inferred 3D thermofluid (persistent parcels, four separate precision axes).
Honest scope: Geant4 is the per-tick clock; the MD/PBF/parcel solvers are hook-layer physics for
comparison.

### Molecular polarization/torsion — Experimental comparison prototypes

`molecular_series.js` selects six numbered scenarios: ethane, ethanol, formamide, butane,
dimethyl ether and acetamide. `ctx.predict` evaluates the **comparison** periodic models
fitted to PySCF RHF/STO-3G energies/Mulliken charges on an independently constructed fixed
scaffold (72 fitting / 24 withheld angles; butane uses 128 fitting angles). This branch uses elemental identity,
neutral-electron consistency and independent electron transport through a unit-density
homogeneous proxy, **not quantum electronic labels**. Models carry `geant4_trained:false` and
`measured:false`. Bubbles are atom-integrated partial-charge glyphs; positions are imposed
rigid torsion samples with no physical time, not orbitals/density or molecular dynamics.
PubChem is comparison-only (topology, aligned geometry, MMFF94 charge disagreement).
`tools/torch/build_molecular_series.py` rebuilds models/reference rows/JS fixtures;
`docs/molecular_series.md` owns quantitative scope and sources. Measured occupancy flags remain
visible even when hull/joint checks pass. This first atomic rung does **not** close the general
Geant4-linked inference-cascade gap. GenericSurrogate's named C++ API now also rejects missing
inputs, and every backend rejects non-finite inputs/outputs before publishing any output.

The second group also enables a **shared Geant4-trained atomic → molecular response** by default.
`trech_molecular_particle.js` uses `ctx.evolve` for each atom's photon interaction response and
`ctx.cascade` for the nano composition lift. Both models fit Geant4 `G4EmCalculator` labels,
not QM/PubChem; `geant4_trained:true`, `measured:false`, `mc_sampled:false` distinguish those
table labels from physical measurements/MC histories. Shared CHNO response is bounded to
1–30 keV and Geant4's independent-atom mixture approximation; it cannot distinguish isomers'
bond effects. Purple halo volume follows the learned atomic photoelectric response. Separate
torsion/particle-energy streams each emit 24 frames; photon-energy sweeps keep scaffold/QM
charges fixed. Strict mode disables every stage. Counts are `48 × (atom count + 2)` per new
predictive run. `tools/torch/build_particle_molecule_models.py` rebuilds the models/labels;
`scripts/validate_particle_molecule.py` covers mode/reproducibility, held-out responses,
particle-energy sensitivity and three 30,000-photon MC comparisons. Details:
[`docs/particle_molecule.md`](docs/particle_molecule.md). Particle-trained correlated electronic,
charge/bond/torsion inference remains the next lift; the external quantum fits do not fulfill it.

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

- **Scripted/planar animations.** Symptom: a README GIF shows motion no solver produced (targeted
  packets, a prescribed lobe pattern, a textbook curve being drawn) or a planar solver orbited in
  3D. Fix: emit the solver's own state as `material_frame` (or capture Geant4 tracks with
  `--viz-all`) and lift the solver to 3D; label any remaining representation kinematics.
- **Chart statistics revealed over playback must censor, not truncate.** Symptom: a survival
  curve dips far below the formula mid-GIF and recovers at the end. Cause: interacted photons are
  "known" early while survivors are only known when they exit. Fix: Kaplan–Meier with in-flight
  photons censored at the depth they have reached (`track_charts.attenuation_charts`); fractions
  of the whole population, never of the outcomes seen so far.
- **Classic-viewer axis for y-up geometry frames.** A frame emitted in a y-up Geant4 geometry frame
  must declare `up_axis: "y"`, or the z-up relabel lays it on the floor (glass_from_sand did).

- **MT nondeterminism in accumulating hooks.** Symptom: a fixed-seed hook scenario gives different
  tallies across runs. Cause: Geant4 MT event order. Fix: `run.threads: 1`. Prevention:
  cross-check reruns are byte-identical.
- **White-noise heterogeneity vanishes when you refine the mesh.** Symptom: a coarse run leans and
  cracks, a finer one is symmetric — the "precision" knob silently changed the physics. Cause:
  per-parcel independent noise averages out over more parcels. Fix: sample imperfection from a
  **spatially correlated field** with a physical correlation length (`makeSmoothField` in
  [`trech_foam_solver.js`](examples/experiments/trech_foam_solver.js)); real mixing/cell-size
  imperfection comes in patches, and patches survive refinement.
- **Gravity + inertia at a chemical-process timestep destroys a contact solver.** Symptom: a poured
  liquid free-falls a whole parcel diameter per step and the material collapses flat. Cause: a
  minutes-long process needs ~10⁻²·s steps, over which free-fall is ~15 mm. Fix: integrate the
  **overdamped** solution (terminal creep velocity under the material's own drag) for material
  inside the body, and keep ballistic integration only for detached pieces falling through air.
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
- **Emit guardrails silently truncate observer frames.** Symptom: a GIF ends early (MRI stage 3
  lost its reconstruction act). Cause: a callback emitting more than `hooks.maxEmitsPerCallback`
  frames — the excess is dropped and only counted in `hook_emit_dropped_count`. Fix: size the cap
  to the frames emitted per callback and check that counter is 0 after changing an emitter.
- **Hook-emit file is append-mode.** `trech_hook_emits.jsonl` appends; clean the `--output` dir
  between reruns or renderers read stale emits.
- **PyVista offscreen renders repeat frame 0.** Call `plotter.render()` before each `screenshot()`.
- **MD sampling lessons.** Single-origin MSD is too noisy for per-block D (use multi-time-origin);
  each block must equilibrate longer than water's ~2–3 ps structural relaxation or D is inflated.

## Interface ownership map

- **CLI:** `trech run <exp.js> [--macro --ui --output/-o --seed --events --param --viz
  --viz-all --viz-max-trajectories]`,
  `trech inspect <exp.js> [--param n=<json>]`, `trech lab [--config --commands --output --seed
  --events]` → [`apps/trech-cli/main.cpp`](apps/trech-cli/main.cpp) + `parseRunOptions`/`runUsage`
  in [`src/core/RunOptions.cpp`](src/core/RunOptions.cpp).
- **Hook `ctx` surface:** `config`/`runtime`/`event`/`step`/`state`/`rng`/`emit`/`predict`/
  `cascade`/`evolve`/`materials`/`optics` → [`src/js/JsRuntime.cpp`](src/js/JsRuntime.cpp).
  Authoring globals `TRECH_CONFIG`/`TRECH_HOOKS`/
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
# Geant4 from the submodule (once): configure thirds/geant4 into build/geant4-build with
#   -DCMAKE_INSTALL_PREFIX=build/geant4-install -DGEANT4_INSTALL_DATA=ON, build + install
cmake --preset dev -DCMAKE_PREFIX_PATH="$PWD/build/geant4-install"
cmake --build --preset dev
./build/dev/trech run examples/experiments/hello_world.js --output build/dev/out_hello
ctest --preset dev            # 28 CTest entries with Geant4, including Python gates
# the rel preset is ~3-5x faster for MD/PBF/osmotic runs and the README media driver
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
- **Adaptive precision/work:** [`tests/test_adaptive_precision.cpp`](tests/test_adaptive_precision.cpp)
  (budget feedback, config/strict guards, continuous JS refinement and bounded cascade counts);
  [`tests/test_evolvo_structure.py`](tests/test_evolvo_structure.py) (optional NumPy/Evolvo search,
  seeded bounds/time/RNG isolation; run with the tooling Python environment).
- **JS runtime & hook boundary:** [`test_js_runtime.cpp`](tests/test_js_runtime.cpp) (`ctx.predict`,
  two-stage `ctx.cascade`, ambient seed, `TRECH_INCLUDE`/`TRECH_FLOW`).
  [`test_scenario_helpers.cpp`](tests/test_scenario_helpers.cpp) covers standalone/shared import
  order, seeded sampling/draw counts, numeric helpers, clocks and missing/immutable source facts.
- **ML:** [`test_scale_cascade.cpp`](tests/test_scale_cascade.cpp), [`test_state_evolution.cpp`](tests/test_state_evolution.cpp), [`test_generic_surrogate.cpp`](tests/test_generic_surrogate.cpp),
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

- Default-thread strict transport replay currently varies for `hello_world.js` on the local
  dependency build, including with the pre-cleanup binary. Serial `run.threads:1` replay matches;
  MT seeding/replay diagnosis remains tracked in `ROADMAP.md`. Strict byte replay is still required.
- Some tests share fixed temporary filenames: run suites from different build trees serially
  until fixture isolation lands (`ROADMAP.md`).
- The first bounded Geant4-trained non-optics atomic/nano response is CHNO photon transport;
  general learned higher-scale state/bond/electronic dynamics remain open (the core objective).
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

**Occupied energy distributions:** the optional reference service evaluates all occupied-state
contributions directly on nonuniform nucleus-centred radial/diameter coordinates, groups only
numerically degenerate computed energies and retains occupations. TRECH validates membership,
geometry/units/counts and sums totals; complete small-system `energy_components` also sum to
the recorded 3D density. Studio's `ui/electron_levels.py` plots diameter density versus the
spherical radial measure (4πr²), while the Field explorer colors local energy contributions and
exposes cut faces. `chemistry_atomic_levels_reference.js` / `neon_atom.json` provide a Ne-20
core/valence comparison. No preset shell radii, linear electron distribution, atomic quantum-number
assignment or Geant4 bound-electron prediction is implied. See docs/chemistry_probability.md.

Electron-level and particle-detail panels scroll within the Chemistry dock so complete spectra/profiles do not force the native window beyond the screen. Native gradient/profile captures and their source/run hashes extend the documentation gallery.
