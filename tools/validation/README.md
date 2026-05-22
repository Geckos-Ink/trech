# trech-validation

Validation suite for TRECH. Runs a battery of physics consistency checks against the JSONL/JSON artefacts the engine emits, then writes a stable Markdown report to `docs/validation_report.md` (plus a `docs/validation_report.json` sidecar for tooling). The Markdown layout is deterministic so `git diff` between commits shows clean validation deltas.

## Install

Standard library only — no extra dependencies. You can run the package directly:

```bash
python -m trech_validation \
  --runs-dir build/dev \
  --report docs/validation_report.md \
  --json docs/validation_report.json
```

Optional `pip install -e tools/validation` exposes a `trech-validation` console script.

## Workflow

1. Run the scenarios listed in `trech_validation.cases.REQUIRED_RUNS` (e.g. `viz_refraction_demo.js`, `config_nitrogen_carbon_cycle.js`, plus a `determinism_replay` second copy). Each must be invoked with the expected output directory name under `--runs-dir`.
2. Invoke `python -m trech_validation`. The runner loads the relevant JSONL/JSON files, evaluates each case, and writes the report.
3. Commit the regenerated `docs/validation_report.md` and `docs/validation_report.json`. The committed history is the regression record.

The orchestrator script `scripts/run_validation_suite.sh` does steps 1 and 2 in one shot.

## Adding a case

Each case is a subclass of `trech_validation.cases.ValidationCase`. Override `evaluate(self, ctx)` and return a `CaseResult`. Register the case by appending to `ALL_CASES` in `cases.py`. Keep the case's `name` stable — the Markdown row order is alphabetical, so renaming a case is a diff-noisy operation.
