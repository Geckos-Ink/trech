# C++ engine — context and contracts

[Root principles](../../AGENTS.md) · [Root roadmap](../../ROADMAP.md) · [Parent](../AGENTS.md) · [Roadmap](ROADMAP.md)

## Choose a subcategory

| Scope | Context | Work remaining |
| --- | --- | --- |
| Configuration, CLI and provenance | [AGENTS.md](core/AGENTS.md) | [ROADMAP.md](core/ROADMAP.md) |
| Multi-scale inference | [AGENTS.md](inference/AGENTS.md) | [ROADMAP.md](inference/ROADMAP.md) |
| Learned state and pair operators | [AGENTS.md](operators/AGENTS.md) | [ROADMAP.md](operators/ROADMAP.md) |
| Precision profiles and runtime budgets | [AGENTS.md](precision/AGENTS.md) | [ROADMAP.md](precision/ROADMAP.md) |
| JavaScript host and live lab | [AGENTS.md](runtime/AGENTS.md) | [ROADMAP.md](runtime/ROADMAP.md) |
| Geant4 transport and diagnostics | [AGENTS.md](simulation/AGENTS.md) | [ROADMAP.md](simulation/ROADMAP.md) |

Read the root principles and the parent handbook first; then open only the subcategory relevant to the task. Source paths and shell commands in code spans/blocks are repository-relative unless stated otherwise; Markdown links resolve from this file.

## Critical implementation contracts

Named invariants include enforcing code and tests in their owning handbooks:
[configuration and hashes](core/AGENTS.md), [strict hooks and input completeness](runtime/AGENTS.md),
[learned operators](operators/AGENTS.md), [precision](precision/AGENTS.md) and
[Geant4 diagnostics](simulation/AGENTS.md). Violating one silently corrupts reproducibility or physics honesty.

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
[`CHARTS.md`](../../CHARTS.md).

## Linked source tree and file reference

Use the category table to find the owning source map, key symbols, focused tests and common
regressions. Engine entry points and registries live in the linked engine branches; grouped
[scenarios](../scenarios/AGENTS.md), [Python packages and model data](../tooling/AGENTS.md),
[Studio modules](../studio/AGENTS.md) and [documentation](../project/AGENTS.md) have separate owners.
