# Engine contracts

[Documentation index](../README.md)

Configuration, hook APIs, runtime backends, precision and the Geant4 base of truth.

## Files

| Document or asset | Purpose |
| --- | --- |
| [CLI and live lab](cli.md) | Command-line usage, modes and JSON Lines sessions, including re-tuning a scenario's hooks between live batches. |
| [Engine trace](engine_trace.md) | Turn on the verbose engine log (`--trace`) and read its attribution summary: which results came from the engine, which were null, and which emits had no engine result behind them. |
| [Fields and field evolution](field_evolution.md) | Scalar fields, candidate methods and how the engine grades them. |
| [Formal laws with Lean](formal_laws.md) | The optional Lean 4 / Mathlib route: why laws get Lean definitions next to their classic code, how to pull the sources and search Mathlib, what is not done yet. |
| [Geant4 features and limits](GEANT4_features_and_limits.md) | Pinned-version capabilities and responsibilities above the particle base. |
| [Adaptive precision](adaptive_precision.md) | Commands, budgets, refinement and limits. |
| [Output schema](output_schema.md) | JSON/JSONL contracts consumed by Studio and analysis tools. |
| [Scenario hook API](scenario_hooks.md) | Hook context, allowed operations and inference/provenance contracts. |
| [V8 JavaScript backend](v8.md) | Run scenarios and hooks on V8 instead of QuickJS: build, select, verify identical results, measure speed, limits. |
