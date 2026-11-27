# TRECH — essential agent reference

This is the shared entry point for the C++/Geant4 engine, JavaScript scenarios, Python tools and Studio client.
Detailed context and plans live in the categorized [AGENTS/ tree](AGENTS/AGENTS.md); each directory pairs an `AGENTS.md` with a `ROADMAP.md`.

## Read only the relevant branch

Read this file, choose an owner below, then follow its subcategory links. Open the matching roadmap when planning or changing that area.
These handbooks live outside source-directory ancestry: agents working in `src/`, `js/`, `studio/` or `tools/` must explicitly open the applicable branch. Directory nesting here organizes context; it does not change source ownership or automatic instruction discovery.
Cross-component tasks follow each affected branch. [The full tree index](AGENTS/AGENTS.md) links to all top-level categories.

| Work area | Context and source ownership | Plan and gaps |
| --- | --- | --- |
| Engine: core, JS host, inference, operators, Geant4, precision, lattice methods, field-evolution arbitration and optional Lean formal laws | [Engine handbook](AGENTS/engine/AGENTS.md) | [Engine roadmap](AGENTS/engine/ROADMAP.md) |
| Scenarios: bundles, processes, chemistry, fluids, CNT, MRI | [Scenario handbook](AGENTS/scenarios/AGENTS.md) | [Scenario roadmap](AGENTS/scenarios/ROADMAP.md) |
| Studio: layers, panels, engine bridge, rendering, editing, export | [Studio handbook](AGENTS/studio/AGENTS.md) | [Studio roadmap](AGENTS/studio/ROADMAP.md) |
| Tools: builds/dependencies, training/data, media, validation | [Tooling handbook](AGENTS/tooling/AGENTS.md) | [Tooling roadmap](AGENTS/tooling/ROADMAP.md) |
| Project: workflow, shared status, north star, long-term structure | [Project handbook](AGENTS/project/AGENTS.md) | [Project roadmap](AGENTS/project/ROADMAP.md) |

## The roadmap 12 implementations to do bucket

When no task is named and you choose the next roadmap implementation, take it from this bucket
rather than from whichever queue you happen to be reading. The bucket keeps the choice spread
across the whole project: it holds **5 high (P1), 4 medium (P2) and 3 low (P3)** items, drawn at
random from every leaf roadmap's **Priority queue** ([keys](AGENTS/ROADMAP.md#priority-keys)),
with no two slots from the same roadmap. Gated items and one-line pointers to another queue are
never drawn.

- **The owning queue stays the source of truth.** A slot only points to an item; read the full
  item and its detail link in the owning roadmap before starting.
- **Replace a slot in the change that completes it.** When the item lands and leaves its queue,
  draw its successor at the same priority with
  `python3 scripts/draw_roadmap_bucket.py --draw P1` (or `P2`, `P3`) and put the printed row in
  the freed slot. Never hand-pick a successor: the random draw is what keeps the distribution
  even. Redraw a slot the same way if its item is re-keyed, gated or turned into a pointer. A
  partly delivered item that is still queued keeps its slot.
- **Keep it valid.** `python3 scripts/draw_roadmap_bucket.py --check` confirms each slot is still
  an open item at its key, and that the 5/4/3 split and one-slot-per-roadmap rule hold. A slot's
  text must be a verbatim prefix of its queue item. Run the check in any change that edits a roadmap queue.

| # | Key | Route | Owning queue | Item |
| --- | --- | --- | --- | --- |
| 1 | **P1** | R8 | [engine/formal](AGENTS/engine/formal/ROADMAP.md#priority-queue) | Law inventory, continued. Done: Compton kinematics, Beer–Lambert attenuation, lattice mass conservation, scalar-lattice conservation, `ctx.react` step probabilities, the arbiter's proper squared score. |
| 2 | **P1** | R2 | [project/north-star](AGENTS/project/north-star/ROADMAP.md#priority-queue) | Sputnik water molecule: thermal ensembles, more atoms and a force field graded against measured spectroscopy, on the way to a particle-derived (Geant4-trained) water operator. |
| 3 | **P1** | R2 | [scenarios/fluids](AGENTS/scenarios/fluids/ROADMAP.md#priority-queue) | A particle-derived (Geant4-trained) water operator that freezes, replacing the literature mW potential |
| 4 | **P1** | R2 | [scenarios/chemistry](AGENTS/scenarios/chemistry/ROADMAP.md#priority-queue) | Next learned lift: geometry/charge/isotope-conditioned electronic and bond response trained on Geant4 particle/ionization histories |
| 5 | **P1** | R3 | [scenarios/migrations](AGENTS/scenarios/migrations/ROADMAP.md#priority-queue) | Row 6 remainder — osmosis membrane response: replace the authored `integrateMembrane` pressure/area/bending law with membrane-node operators |
| 6 | **P2** | R3 | [engine/inference](AGENTS/engine/inference/ROADMAP.md#priority-queue) | Closed-loop deployment of learned-domain operators beyond the furnace thermal law |
| 7 | **P2** | R6 | [studio/authoring](AGENTS/studio/authoring/ROADMAP.md#priority-queue) | Inspector extensions: nested primitive creation and reparenting, custom materials, per-field engine diagnostics. |
| 8 | **P2** | R6 | [scenarios/references](AGENTS/scenarios/references/ROADMAP.md#priority-queue) | JS workflow execution: editable training/harvest/inference jobs with provenance, progress/cancellation and safe model activation. |
| 9 | **P2** | R3 | [tooling/training](AGENTS/tooling/training/ROADMAP.md#priority-queue) | Next set-network users: efflux/foam parcel operators, an MPNN where neighbour-of-neighbour structure matters, a conservative set operator through `ctx.interact`. |
| 10 | **P3** | R2 | [scenarios/resonance](AGENTS/scenarios/resonance/ROADMAP.md#priority-queue) | T1/T2-weighted sequences (needs a Geant4-anchored relaxation proxy), 2D phase encoding from acquired k-space, real BrainWeb ingestion. |
| 11 | **P3** | R4 | [studio/workspace](AGENTS/studio/workspace/ROADMAP.md#priority-queue) | Automatic accuracy/convergence control (needs engine error estimates) |
| 12 | **P3** | R3 | [scenarios/processes](AGENTS/scenarios/processes/ROADMAP.md#priority-queue) | Coupled thermal/latent energy, mass transport and 3D solution state |

## Maintenance and task workflow

- Check `git status`, preserve unrelated changes, and find the owning source and focused tests before editing. Verify handbook claims against current code.
- **Update human-facing documentation in the same change as every code or project change.**
  Start at the [documentation index](docs/README.md), update the guide or reference in its
  owning topic, and keep the topic index and related links current. Explain what changed,
  why it matters, and what readers need to do or understand. Define unfamiliar terms and
  use a concrete example when it helps readers apply or verify the change.
- Update durable facts in the owning `AGENTS/…/AGENTS.md` and unfinished work in its paired `ROADMAP.md` in the same change. Parent/root files hold shared principles and navigation; update them when those change. Keep README/schema/dataflow docs aligned when their facts change.
- **Keep the [scenario categories](docs/scenarios/categories.md) current.** When a scenario bundle is created, removed, or changed in content (physics, purity grade, validation cases, tests or the planned work that names it), update its category, rank, evidence and verdict, plus the summary counts, in the same change.
- The [project workflow](AGENTS/project/AGENTS.md) owns detailed maintenance and handoff rules; references there to the shared handbook/roadmap mean this categorized collection. Do not grow the root files with component status or delivery history.
- Documentation alone does not implement a capability. Change the owning C++ or Studio source, retain honest maturity labels, and record every residual/scaffold/missing validation in the owning roadmap's **Priority queue** with a priority key ([keys and implementation route](AGENTS/ROADMAP.md#priority-keys)).
- Every caveat or gap in a final report is also a queued roadmap item (see the [project workflow](AGENTS/project/AGENTS.md)); chat is not tracking.
- Run relevant checks and report tests run/skipped and remaining gaps. Documentation-only work needs link/reference checks; engine work follows the CTest/validation guidance and Studio work its focused pytest coverage.
- Never implicitly trigger heavy dependency builds or bumps. Preserve the [reference-media gates](AGENTS/tooling/media/AGENTS.md) and [dependency rules](AGENTS/tooling/dependencies/AGENTS.md).
- `thirds/evolvo` is first-party, lightweight Python and the exception to that rule. Every time a task uses it (for Torch, V8 or Geant4 work alike), first fast-forward it with `git -C thirds/evolvo pull --ff-only`. When the task needs a general-purpose Evolvo change, implement or fix it in `thirds/evolvo` itself, following its own `AGENTS.md`. Commit it on Evolvo's `main` with no co-author trailer, then commit the new submodule pointer in TRECH (see the [Evolvo workflow](AGENTS/tooling/dependencies/AGENTS.md)).
- `thirds/lean4` and `thirds/mathlib4` are pulled before every use (`scripts/pull_lean.sh`); building them stays gated. Lean is optional for now: laws keep their classic C++/JS implementation, with a Lean definition beside it for validation, and Mathlib is searched before any theorem is declared ([formal-laws handbook](AGENTS/engine/formal/AGENTS.md)).

TRECH is a **C++/Geant4 simulation and learning toolkit**: experiments are authored in
**JavaScript** (QuickJS, or V8 in a `TRECH_ENABLE_V8` build), which computes and composes a config that is handed as JSON to a
**deterministic-by-default C++ runtime** that drives Geant4 and writes a provenance-first data
trail. Its reason to exist is the **multi-scale inference cascade** — take a precise Geant4
particle/nano base and lift its behaviour, via statistical/ML inference, *scale by scale up the
dimension ladder* (atomic → nano → micro → meso → macro) to the scale a human observes.

This file is the fast-access operational map for agents. It is not the README (user-facing) and
not a changelog (git owns chronology). Maturity: **active H2O/optics baseline** with landed
tracks for fluids, chemistry cycles, biology, CNT electronics, magnetic resonance/MRI, analytic
cross-checks, the ML cascade, and a desktop UI ([`studio/`](studio)).

**What TRECH is NOT:** it is **not a classical-formula physics engine** — closed-form laws are
*comparison/validation references only* and MUST NOT drive scenario behaviour unless explicitly
documented as an analytic cross-check. Hook-layer MD/Bloch/fluid solvers are labelled "physics
for comparison," not Geant4 results. [`studio/`](studio) is a **viewer/client, never a second
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
> `DiscreteTransition` + `ctx.react` (integer stochastic state), `PairInteraction` +
> `ctx.interact` (pair/neighbour interaction), `GroupHierarchy` + `ctx.lift` (recursive
> elements → groups → observer lifting through trained set models), and `DomainLearner` +
> `ctx.learnDomains` (online emergence of response domains with per-domain learned laws), and
> `FieldEvolution` + `ctx.evolveField` (engine-owned methods for a continuum field, declared today only by
> validation companions, the
> best one chosen per context domain by prequential error). This callout is deliberately
> redundant with those sections so
> the thesis survives even if one place is trimmed — keep it.

## Read order and sources of truth

Authority order when sources disagree (inspect and fix the mismatch within task scope, updating
stale docs in the same change; if unsafe to resolve, record it as a gap and ask):

1. **Honesty + engine-thesis principles** (this file's [Essential principles](#essential-project-principles)) — a running result never overrides "grade the gap / Geant4 is the base of truth."
2. **Executable specs & tests** — [`docs/engine/output_schema.md`](docs/engine/output_schema.md) (output contracts), [`tests/`](tests) (esp. `test_config_roundtrip.cpp`), [`CMakeLists.txt`](CMakeLists.txt).
3. **Current source** — C++ under [`src/`](src) + [`include/trech/`](include/trech), JS under [`js/`](js) + [`examples/scenarios/`](examples/scenarios) + JS subprojects in [`projects/`](projects), Python/WGSL under [`studio/trech_studio/`](studio/trech_studio) + [`tools/`](tools), and build config.
4. **User docs** — [documentation index](docs/README.md), [`README.md`](README.md), [`CHARTS.md`](CHARTS.md) (Mermaid dataflow), [`docs/architecture/structure.md`](docs/architecture/structure.md), [`docs/engine/scenario_hooks.md`](docs/engine/scenario_hooks.md), [`docs/studio/viz_refraction.md`](docs/studio/viz_refraction.md), [`studio/README.md`](studio/README.md) (desktop use), [`studio/tests/reference/README.md`](studio/tests/reference/README.md) (committed reference-GIF policy).
5. **Roadmap / backlog / validation reports** — [`ROADMAP.md`](ROADMAP.md) (the shared editable source of truth, including [Studio milestones](AGENTS/studio/ROADMAP.md#studio-desktop-ui)), [`docs/validation/validation_report.md`](docs/validation/validation_report.md) + [`docs/validation/validation_summary.md`](docs/validation/validation_summary.md). [`docs/project/trech-roadmap.md`](docs/project/trech-roadmap.md) is the **reference-only** initial concept (do not edit).
6. **Historical notes & git history** — the full chronology of landed work (this file records current state, not the timeline).

Rules: a roadmap does not prove a feature exists; a README does not prove a command still works;
a test proves only what it asserts.

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

### Scenarios declare systems; prediction methods emerge from the engine

A scenario declares **what the system is**: the materials, their composition and structure,
geometry, conditions, the state it hands to the engine, and references it wants graded. It
never decides **how the system is predicted**. Every prediction method (Geant4 transport, learned surrogates and operators, the
lattice Boltzmann continuum method, any future solver) belongs to the engine. The engine
selects among them statistically, by context domain, from prequential evidence. If a scenario
imports, constructs or wires a method so that the method can be used, the engine is bypassed,
and TRECH has no reason to exist. Reject such a change. A scenario may name or force a method
or law only to **validate** it, or to **force** a specific feature or functionality under test.
It must then label that purpose in code and records (`reference`, `validation`, `teacher`,
`forced`), and keep it off the decision path.

- **A scenario forces nothing; the organisation of the system emerges.** A scenario states the
  physical setup: the materials, their composition and structure (geometry), and the
  conditions. How the engine organises that setup emerges from TRECH: which elements group into
  kinds or domains, which systems they form and, possibly, the continuum fields it evolves.
  Anything else a scenario writes is for validation, UI data categorization or rendering:
  element-kind labels, group names, field layouts, categories, display hints. Validation
  belongs in `<name>.validation.js`. Data categorization and rendering indications (how to
  group, label, colour or draw recorded data) belong in the UI companions, `<name>.ui.js` and
  `<name>.view.js`. The engine must not need any of it to run and must not take it as an
  instruction; a rendering indication never changes physics, RNG or emitted physical fields. Where a scenario still forces such a choice, that is debt in
  the owning roadmap, never a pattern to copy. Today:
  - **Grouping:** domain routing lets grouping emerge. The furnace defaults to
    `grouping: "domain"` (thermal, chemistry and pair conduction), and declared grouping is its
    validation reference. Single-population scenarios select operators by role, with no kind
    label. The furnace's opt-in set conduction still passes cell materials; this is queued in the
    [inference roadmap](AGENTS/engine/inference/ROADMAP.md#priority-queue).
  - **Fields:** no scenario declares a continuum field. The lamp's and the furnace's
    declarations live in their `.validation.js` companions (moved 2026-11-20), which grade the
    engine's methods against a reference; nothing feeds back. The scenario calls a generic
    per-frame observer in its companion and passes only its observed state. Whether fields
    should emerge from the engine in general is an open question in the
    [lattice roadmap](AGENTS/engine/lattice/ROADMAP.md#priority-queue).
- **Wrong:** the lava lamp's first lattice Boltzmann companion
  (commits `916a60d` and earlier). It imported the LBM module and built the lattice in the
  scenario, so the scenario decided where LBM ran. This was replaced by the engine-owned
  `ctx.evolveField` (see the [lattice handbook](AGENTS/engine/lattice/AGENTS.md)).
- **Also wrong:** the lamp and furnace scenarios declaring their carrier and charge fields in
  the physics script (until 2026-11-20), and any scenario that makes the engine depend on its
  labels (a declared kind that selects the operator).
- **Right:** the lamp's validation companion declares the carrier column only to grade the
  engine's methods against the lamp's authored column. The engine runs the methods it owns and
  records which one wins where. The scenario only hands over its observed state. By default
  the furnace's engine routes every cell's thermal and chemistry operators without a material
  label.
- **Every multi-method path selects the same way.** Where the engine owns more than one way to
  predict a quantity (lattice methods, learned operators, surrogate networks, baselines, and any
  algorithm or model added later), the domain-free `MethodArbiter` chooses per context domain
  from prequential evidence. A new method registers in its path's registry (for fields,
  `registerFieldMethod`) and joins the arbitration. It is never special-cased or wired by a
  scenario.
- **Residual authored laws** in scenarios (the migration ledger) are tracked as debt. They are
  never a pattern to copy: new behaviour enters as an engine method or operator plus a
  declaration.

### Determinism is explicit; strict mode disables inference

`determinism.mode` is `strict` or `predictive`. Strict runs are byte-reproducible and **disable
all model inference** (`ctx.predict` and `ctx.cascade` return `null`); `predictive` enables it
with provenance capture. Log stage/predict counts.

### Physics-agnostic C++; physics lives in JS

No domain switch (H2O/CNT/MRI/…) enters C++. Scales are ordered band names; models carry their
own named IO; scenarios declare physics classes/properties/extensions in JS. General-purpose
*methods* that name no material, scenario or domain belong to the engine: Geant4 transport,
learned operators, and lattice continuum transport over declared properties. The C++ never
picks one per scenario; the engine's statistics do. Keep the
JS → JSON → C++ boundary stable; hooks are a deterministic sideband, never direct Geant4 access.

### Provenance-first & reproducible

Every run writes config JSON + hash + seed + Geant4/runtime versions + determinism mode + hook/
stratify/predict counters to [`trech_provenance.jsonl`](docs/engine/output_schema.md). New config fields
are **conditionally serialized** so byte-identical config hashes hold for scenarios that don't use
them (round-trip in [`tests/test_config_roundtrip.cpp`](tests/test_config_roundtrip.cpp)).
