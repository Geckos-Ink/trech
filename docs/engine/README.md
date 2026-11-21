# Engine contracts

[Documentation index](../README.md)

Configuration, hook APIs, runtime backends, precision and the Geant4 base of truth.

## Files

| Document or asset | Purpose |
| --- | --- |
| [CLI and live lab](cli.md) | Command-line usage, modes and JSON Lines sessions, including re-tuning a scenario's hooks between live batches. |
| [Fields and field evolution](field_evolution.md) | Scalar fields, candidate methods and how the engine grades them. |
| [Geant4 features and limits](GEANT4_features_and_limits.md) | Pinned-version capabilities and responsibilities above the particle base. |
| [Adaptive precision](adaptive_precision.md) | Commands, budgets, refinement and limits. |
| [Output schema](output_schema.md) | JSON/JSONL contracts consumed by Studio and analysis tools. |
| [Scenario hook API](scenario_hooks.md) | Hook context, allowed operations and inference/provenance contracts. |
| [V8 embedding foundation](v8.md) | Optional backend foundation, QuickJS-identical `Math.*` for V8 and current limitations. |
