# JavaScript scenarios and domain libraries — context and contracts

[Root principles](../../AGENTS.md) · [Root roadmap](../../ROADMAP.md) · [Parent](../AGENTS.md) · [Roadmap](ROADMAP.md)

## Choose a subcategory

| Scope | Context | Work remaining |
| --- | --- | --- |
| Scenario bundles and shared helpers | [AGENTS.md](bundles/AGENTS.md) | [ROADMAP.md](bundles/ROADMAP.md) |
| Chemistry and molecular response | [AGENTS.md](chemistry/AGENTS.md) | [ROADMAP.md](chemistry/ROADMAP.md) |
| CNT electronics | [AGENTS.md](electronics/AGENTS.md) | [ROADMAP.md](electronics/ROADMAP.md) |
| Water and fluid comparisons | [AGENTS.md](fluids/AGENTS.md) | [ROADMAP.md](fluids/ROADMAP.md) |
| Scenario law migration ledger | [AGENTS.md](migrations/AGENTS.md) | [ROADMAP.md](migrations/ROADMAP.md) |
| Reusable solution and material processes | [AGENTS.md](processes/AGENTS.md) | [ROADMAP.md](processes/ROADMAP.md) |
| Independent process references | [AGENTS.md](references/AGENTS.md) | [ROADMAP.md](references/ROADMAP.md) |
| Magnetic resonance and MRI | [AGENTS.md](resonance/AGENTS.md) | [ROADMAP.md](resonance/ROADMAP.md) |
| Spectrum prediction (JS subproject) | [AGENTS.md](spectra/AGENTS.md) | [ROADMAP.md](spectra/ROADMAP.md) |

Read the root principles and the parent handbook first; then open only the subcategory relevant to the task. Source paths and shell commands in code spans/blocks are repository-relative unless stated otherwise; Markdown links resolve from this file.

## Features and recurring development pitfalls

- **Never import, build or wire a prediction method in a scenario so that it can be used.** That
  includes a solver, a lattice, a learned model or a hand-written law on the decision path. A
  scenario declares its system (geometry, materials, conditions, state, references) and hands
  the state to an engine operator; the engine chooses the method statistically (root principle
  [*Scenarios declare systems*](../../AGENTS.md#scenarios-declare-systems-prediction-methods-emerge-from-the-engine)).
  Code that names a method only to validate it, or to force a feature under test, must say so
  (`reference` / `validation` / `teacher` / `forced`) and stay off the decision path. The lava
  lamp's first lattice Boltzmann companion broke this rule and was moved into the engine as
  `ctx.evolveField`. Before adding any `TRECH_INCLUDE` of a physics or solver module, ask which
  engine operator should own it.
- **Force nothing about how the engine organises the system.** A scenario states materials,
  composition, structure and conditions. Grouping (kinds, domains), systems and possibly fields
  emerge from the engine (root principle *A scenario forces nothing*). Labels a scenario writes,
  such as `element_kind`, group names or categories, are for validation, UI data
  categorization and rendering. The `.ui.js` and `.view.js` companions may carry
  categorization and rendering indications; they never feed physics. The engine must not need them: prefer domain routing over declared kinds, and
  treat a declared kind that selects the operator as debt. A scenario never declares a
  continuum field. Only a `<name>.validation.js` companion may call `ctx.evolveField`, to grade
  the engine's methods against a reference. The physics script calls the companion's generic
  per-frame observer (`TRECH_CHECKS[name].observeFrame`) with its observed state, and nothing
  returned feeds back. `lava_lamp` and `glass_from_sand` follow this pattern.

Each family's physical basis and observable are mapped in the
[scenario catalog](../../docs/scenarios/catalog.md) and per-scenario notes. The linked category handbooks carry family status and reusable lessons;
[scenario bundles](bundles/AGENTS.md) list canonical scenarios and their regression guards.
