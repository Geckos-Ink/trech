# TRECH — roadmap index

This is the shared editable roadmap for the engine, JavaScript scenarios, tools and Studio.
Detailed checklists and validation records live in the categorized [AGENTS/ roadmap tree](AGENTS/ROADMAP.md), paired with context and contracts in each directory.
Track every gap in its owning workstream and link other affected owners. Keep plans updated as items land or are re-scoped; keep this root focused on shared objectives and navigation.
The [root principles](AGENTS.md) govern every branch. `docs/trech-roadmap.md` remains the reference-only initial concept (do not edit).
Dated verification records describe their recorded checkout, not validation of later changes; a roadmap entry never proves a feature exists.

> ## ⭐ Engine thesis — the "why" behind every milestone (keep this alive)
>
> Everything in this file serves one goal: **turn a precise Geant4 particle/nano base into
> predictions at the scale a human observes, by inferring UP the dimension ladder
> (atomic → nano → micro → meso → macro) with statistics/ML** — a general-purpose,
> context-driven predictor, not narrow per-output models the user must wire by hand. A user
> should be able to ask a macroscopic question (a stirred glass of water → fluid motion + waves)
> and have it inferred from the microscopic truth by default.
>
> [Sputnik](AGENTS/project/north-star/ROADMAP.md) is the concrete milestone; the
> [Multi-scale statistical inference objective](AGENTS/engine/inference/ROADMAP.md) is the doctrine + the plan to get there. This callout is intentionally redundant with
> that section (and with the AGENTS.md thesis callout) so the intent survives even if the file is
> trimmed or an agent starts with no memory — **if you ever prune ROADMAP, keep that standing
> objective and this callout.**

## Standing objectives

1. Grow a general-purpose, context-driven inference cascade from Geant4 to the observer scale, across several families. Follow the [inference workstreams](AGENTS/engine/inference/ROADMAP.md) and [trust/uncertainty requirements](AGENTS/engine/inference/trust/ROADMAP.md).
2. Replace authored evolution laws with learned, validated engine operators through the [migration contract](AGENTS/engine/operators/migration/ROADMAP.md), [prerequisites](AGENTS/engine/operators/prerequisites/ROADMAP.md) and [scenario ledger](AGENTS/scenarios/migrations/ROADMAP.md). Reference solvers stay labelled comparisons.
3. Reduce [simulation degeneration](AGENTS/engine/simulation/optics/ROADMAP.md), preserve strict replay and provenance, and quantify the gap to independent truth.
4. Make the cascade observable and editable in [Studio](AGENTS/studio/ROADMAP.md), while displaying only recorded results and clearly labelled representation choices.

## Find the owning workstream

| Work area | Context and source ownership | Plan and gaps |
| --- | --- | --- |
| Engine: core, JS host, inference, operators, Geant4, precision | [Engine handbook](AGENTS/engine/AGENTS.md) | [Engine roadmap](AGENTS/engine/ROADMAP.md) |
| Scenarios: bundles, processes, chemistry, fluids, CNT, MRI | [Scenario handbook](AGENTS/scenarios/AGENTS.md) | [Scenario roadmap](AGENTS/scenarios/ROADMAP.md) |
| Studio: layers, panels, engine bridge, rendering, editing, export | [Studio handbook](AGENTS/studio/AGENTS.md) | [Studio roadmap](AGENTS/studio/ROADMAP.md) |
| Tools: builds/dependencies, training/data, media, validation | [Tooling handbook](AGENTS/tooling/AGENTS.md) | [Tooling roadmap](AGENTS/tooling/ROADMAP.md) |
| Project: workflow, shared status, north star, long-term structure | [Project handbook](AGENTS/project/AGENTS.md) | [Project roadmap](AGENTS/project/ROADMAP.md) |

The [project plan](AGENTS/project/ROADMAP.md) retains Sputnik, shared short/long-term planning and completed project milestones. Component delivery records remain with their owners; older cross-family verification is indexed under [validation history](AGENTS/tooling/validation/history/ROADMAP.md).
