# TRECH — essential agent reference

This is the shared entry point for the C++/Geant4 engine, JavaScript scenarios, Python tools and Studio client.
Detailed context and plans live in the categorized [AGENTS/ tree](AGENTS/AGENTS.md); each directory pairs an `AGENTS.md` with a `ROADMAP.md`.

## Read only the relevant branch

Read this file, choose an owner below, then follow its subcategory links. Open the matching roadmap when planning or changing that area.
These handbooks live outside source-directory ancestry: agents working in `src/`, `js/`, `studio/` or `tools/` must explicitly open the applicable branch. Directory nesting here organizes context; it does not change source ownership or automatic instruction discovery.
Cross-component tasks follow each affected branch. [The full tree index](AGENTS/AGENTS.md) links to all top-level categories.

| Work area | Context and source ownership | Plan and gaps |
| --- | --- | --- |
| Engine: core, JS host, inference, operators, Geant4, precision, lattice methods and field-evolution arbitration | [Engine handbook](AGENTS/engine/AGENTS.md) | [Engine roadmap](AGENTS/engine/ROADMAP.md) |
| Scenarios: bundles, processes, chemistry, fluids, CNT, MRI | [Scenario handbook](AGENTS/scenarios/AGENTS.md) | [Scenario roadmap](AGENTS/scenarios/ROADMAP.md) |
| Studio: layers, panels, engine bridge, rendering, editing, export | [Studio handbook](AGENTS/studio/AGENTS.md) | [Studio roadmap](AGENTS/studio/ROADMAP.md) |
| Tools: builds/dependencies, training/data, media, validation | [Tooling handbook](AGENTS/tooling/AGENTS.md) | [Tooling roadmap](AGENTS/tooling/ROADMAP.md) |
| Project: workflow, shared status, north star, long-term structure | [Project handbook](AGENTS/project/AGENTS.md) | [Project roadmap](AGENTS/project/ROADMAP.md) |

## Maintenance and task workflow

- Check `git status`, preserve unrelated changes, and find the owning source and focused tests before editing. Verify handbook claims against current code.
- Update durable facts in the owning `AGENTS/…/AGENTS.md` and unfinished work in its paired `ROADMAP.md` in the same change. Parent/root files hold shared principles and navigation; update them when those change. Keep README/schema/dataflow docs aligned when their facts change.
- The [project workflow](AGENTS/project/AGENTS.md) owns detailed maintenance and handoff rules; references there to the shared handbook/roadmap mean this categorized collection. Do not grow the root files with component status or delivery history.
- Documentation alone does not implement a capability. Change the owning C++ or Studio source, retain honest maturity labels, and record every residual/scaffold/missing validation in the owning roadmap's **Priority queue** with a priority key ([keys and implementation route](AGENTS/ROADMAP.md#priority-keys)).
- Run relevant checks and report tests run/skipped and remaining gaps. Documentation-only work needs link/reference checks; engine work follows the CTest/validation guidance and Studio work its focused pytest coverage.
- Never implicitly trigger heavy dependency builds or bumps. Preserve the [reference-media gates](AGENTS/tooling/media/AGENTS.md) and [dependency rules](AGENTS/tooling/dependencies/AGENTS.md).
- `thirds/evolvo` is first-party, lightweight Python and the exception to that rule. Every time a task uses it (for Torch, V8 or Geant4 work alike), first fast-forward it with `git -C thirds/evolvo pull --ff-only`. When the task needs a general-purpose Evolvo change, implement or fix it in `thirds/evolvo` itself, following its own `AGENTS.md`. Commit it on Evolvo's `main` with no co-author trailer, then commit the new submodule pointer in TRECH (see the [Evolvo workflow](AGENTS/tooling/dependencies/AGENTS.md)).

TRECH is a **C++/Geant4 simulation and learning toolkit**: experiments are authored in
**JavaScript** (QuickJS), which computes and composes a config that is handed as JSON to a
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
> `FieldEvolution` + `ctx.evolveField` (engine-owned methods for a declared continuum field, the
> best one chosen per context domain by prequential error). This callout is deliberately
> redundant with those sections so
> the thesis survives even if one place is trimmed — keep it.

## Read order and sources of truth

Authority order when sources disagree (inspect and fix the mismatch within task scope, updating
stale docs in the same change; if unsafe to resolve, record it as a gap and ask):

1. **Honesty + engine-thesis principles** (this file's [Essential principles](#essential-project-principles)) — a running result never overrides "grade the gap / Geant4 is the base of truth."
2. **Executable specs & tests** — [`docs/output_schema.md`](docs/output_schema.md) (output contracts), [`tests/`](tests) (esp. `test_config_roundtrip.cpp`), [`CMakeLists.txt`](CMakeLists.txt).
3. **Current source** — C++ under [`src/`](src) + [`include/trech/`](include/trech), JS under [`js/`](js) + [`examples/scenarios/`](examples/scenarios) + JS subprojects in [`projects/`](projects), Python/WGSL under [`studio/trech_studio/`](studio/trech_studio) + [`tools/`](tools), and build config.
4. **User docs** — [`README.md`](README.md), [`CHARTS.md`](CHARTS.md) (Mermaid dataflow), [`docs/structure.md`](docs/structure.md), [`docs/scenario_hooks.md`](docs/scenario_hooks.md), [`docs/viz_refraction.md`](docs/viz_refraction.md), [`studio/README.md`](studio/README.md) (desktop use), [`studio/tests/reference/README.md`](studio/tests/reference/README.md) (committed reference-GIF policy).
5. **Roadmap / backlog / validation reports** — [`ROADMAP.md`](ROADMAP.md) (the shared editable source of truth, including [Studio milestones](AGENTS/studio/ROADMAP.md#studio-desktop-ui)), [`docs/validation_report.md`](docs/validation_report.md) + [`docs/validation_summary.md`](docs/validation_summary.md). [`docs/trech-roadmap.md`](docs/trech-roadmap.md) is the **reference-only** initial concept (do not edit).
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

A scenario declares **what the system is**: geometry, materials, conditions, the state it hands
to the engine, and references it wants graded. It never decides **how the system is
predicted**. Every prediction method (Geant4 transport, learned surrogates and operators, the
lattice Boltzmann continuum method, any future solver) belongs to the engine. The engine
selects among them statistically, by context domain, from prequential evidence. If a scenario
imports, constructs or wires a method so that the method can be used, the engine is bypassed,
and TRECH has no reason to exist. Reject such a change. A scenario may name or force a method
or law only to **validate** it, or to **force** a specific feature or functionality under test.
It must then label that purpose in code and records (`reference`, `validation`, `teacher`,
`forced`), and keep it off the decision path.

- **Wrong:** the lava lamp's first lattice Boltzmann companion
  (commits `916a60d` and earlier). It imported the LBM module and built the lattice in the
  scenario, so the scenario decided where LBM ran. This was replaced by the engine-owned
  `ctx.evolveField` (see the [lattice handbook](AGENTS/engine/lattice/AGENTS.md)).
- **Right:** the lamp declares its carrier field and passes its authored column as the
  validation reference. The engine runs the methods it owns and records which one wins where.
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
stratify/predict counters to [`trech_provenance.jsonl`](docs/output_schema.md). New config fields
are **conditionally serialized** so byte-identical config hashes hold for scenarios that don't use
them (round-trip in [`tests/test_config_roundtrip.cpp`](tests/test_config_roundtrip.cpp)).
