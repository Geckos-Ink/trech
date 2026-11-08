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
It also fetches PubChem records needed by reaction scenarios into a build-local
cache (`PUBCHEM_CACHE`, default `${RUNS_DIR}/pubchem_cache`) and sets
`TRECH_PUBCHEM_CACHE_DIR` for those runs.

Use an existing complete cache without refreshing it:

```bash
PUBCHEM_MODE=cache-only PUBCHEM_CACHE=build/rel/pubchem_cache \
  BUILD_PRESET=rel SKIP_BUILD=1 bash scripts/run_validation_suite.sh
```

`cache-only` validates every PubChem input needed by the selected scenario groups before
building or deleting run outputs. Missing or malformed records fail together with their paths;
the mode never falls back to another cache or fetches replacements. `SKIP_FLUID=1` or
`SKIP_SCENARIOS=1` avoids preflighting unused inputs. Default `PUBCHEM_MODE=refresh` retains
online fetching. `SKIP_BUILD=1` with an existing binary also avoids build-system dependency
fetches; cache-only controls PubChem access, not CMake networking. The checker can be run alone:

```bash
PYTHONPATH=tools/validation python3 -m trech_validation.pubchem_inputs \
  --cache-dir build/rel/pubchem_cache --all
```

Every cache-only suite run records what it read in `${RUNS_DIR}/pubchem_input_snapshot.json`
(SHA-256 per record plus a manifest digest). Keep that file and pass it back to pin a later run;
any changed, missing or unpinned selected record then fails (exit 3) before building or running:

```bash
PUBCHEM_MODE=cache-only PUBCHEM_CACHE=build/rel/pubchem_cache \
  PUBCHEM_SNAPSHOT=pins/pubchem_input_snapshot.json BUILD_PRESET=rel SKIP_BUILD=1 \
  bash scripts/run_validation_suite.sh
```

The checker accepts the same `--snapshot PATH` / `--write-snapshot PATH` options directly. A
snapshot proves byte identity with the pinned records; it does not authenticate them.

Cases whose scenario companion declares `family_checks` take their verdict from those
declarations (see [`docs/scenario_bundles.md`](../../docs/scenario_bundles.md)); the runner reads
them through `RUNS_DIR/trech inspect` or `TRECH_BIN`. Aggregated list checks
(`list[*]`, `list[?key=value]` with `aggregate: count|min|max|max_abs|sum|mean|all|any`) let
a companion grade every analytic check or driver-recorded tissue row; `derive`
(`abs|difference|ratio|list_sum|list_length|chi2_sf`) computes per-element statistics such as
the Compton χ² p-value. When `RUNS_DIR/pubchem_input_snapshot.json` exists, the report metadata
(Markdown and `pubchem_inputs` in JSON) records its verified digest and record count, or marks
an edited/unreadable snapshot `invalid`; without one it says no snapshot was recorded.

## Adding a case

Each case is a subclass of `trech_validation.cases.ValidationCase`. Override `evaluate(self, ctx)` and return a `CaseResult`. Register the case by appending to `ALL_CASES` in `cases.py`. Keep the case's `name` stable — the Markdown row order is alphabetical, so renaming a case is a diff-noisy operation.

Operator/reference migrations use the reusable `OperatorReferencePairSpec` and
`OperatorReferencePairCase` instead of a scenario-specific evaluator. Declare the two run aliases,
summary emit, pair payload key, observer fields, and trust thresholds once. Both runs emit the same
`trech_operator_reference_pair_v1` comparison key, teacher, tolerances, and observables; the
operator run additionally emits normalized selection/model/inference trust. The common evaluator
checks observer gaps, context equivalence, model fidelity and exact run-level inference accounting.

Experimental foam mechanics has a separate promotion suite, because it is not the default:

```bash
bash scripts/validate_foam_mechanics.sh
# Evaluate existing pairs without rerunning the simulations:
PYTHONPATH=tools/validation python -m trech_validation \
  --suite foam-mechanics-candidate --runs-dir build/rel/foam_mechanics_candidate \
  --report build/rel/foam_mechanics_candidate/promotion_report.md \
  --json build/rel/foam_mechanics_candidate/promotion_report.json
```

The driver needs an existing binary and PubChem cache (`TRECH_BIN`, `PUBCHEM_CACHE`); set a fresh
`RUNS_DIR` for each attempt. It holds chemistry, seed, precision and conditions fixed across
reference/operator runs at nominal gravity, zero gravity and 305 K. Height, lean, expansion,
fracture, detachment, ground fraction and settling gaps use unchanged promotion tolerances.
Failed gates produce a failing report and exit status; they must pass before changing the
scenario's default mechanics source. Missing candidate runs also prevent promotion. Candidate
reports default to `RUNS_DIR/promotion_report.{md,json}`, keeping the default report separate.
The ordinary suite continues to grade promoted defaults.
