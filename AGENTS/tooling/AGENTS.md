# Python tools and scripts — context and contracts

[Root principles](../../AGENTS.md) · [Root roadmap](../../ROADMAP.md) · [Parent](../AGENTS.md) · [Roadmap](ROADMAP.md)

## Choose a subcategory

| Scope | Context | Work remaining |
| --- | --- | --- |
| Builds, dependencies and optional backends | [AGENTS.md](dependencies/AGENTS.md) | [ROADMAP.md](dependencies/ROADMAP.md) |
| Classic and Studio media refresh | [AGENTS.md](media/AGENTS.md) | [ROADMAP.md](media/ROADMAP.md) |
| Training tools, model data and feature schemas | [AGENTS.md](training/AGENTS.md) | [ROADMAP.md](training/ROADMAP.md) |
| Tests and validation ownership | [AGENTS.md](validation/AGENTS.md) | [ROADMAP.md](validation/ROADMAP.md) |

Read the root principles and the parent handbook first; then open only the subcategory relevant to the task. Source paths and shell commands in code spans/blocks are repository-relative unless stated otherwise; Markdown links resolve from this file.

### Python tooling — [`tools/`](../../tools)

Four installable packages each have their own `pyproject.toml` / `README.md`. Their detailed
source maps follow their owners:

- [Training](training/AGENTS.md): `tools/torch/`.
- [Regression validation](validation/AGENTS.md): `tools/validation/`.
- [Classic rendering and media](media/AGENTS.md): `tools/viz/`.
- [Chemistry comparison data](../scenarios/chemistry/AGENTS.md): `tools/pubchem/`.

### Scripts — [`scripts/`](../../scripts)

Orchestration (not source): [`run_validation.sh`](../../scripts/run_validation.sh),
[`run_smoke.sh`](../../scripts/run_smoke.sh), [`run_validation_suite.sh`](../../scripts/run_validation_suite.sh)
(the full slow suite with `SKIP_*` gates), `update_validation_summary.py`,
`validate_glass_of_water.py`, `validate_optics_surrogate.py`, `degeneration_metrics.py`, and the
MRI multi-run drivers `run_magnetic_resonance_{tissues,brain}.py`.
