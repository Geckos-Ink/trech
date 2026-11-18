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

Each family's micro-base → observer-target and honest scope is in [`README.md`](../../README.md)
and the per-scenario notes. The linked category handbooks carry family status and reusable lessons;
[scenario bundles](bundles/AGENTS.md) list canonical scenarios and their regression guards.
