# Run and reproduce checks

[Documentation home](../README.md) · [Validation index](README.md) · [Scenario catalog](../scenarios/catalog.md)

Start with the check that matches your claim. A unit test can verify conservation
accounting or a lattice update. A scenario check compares a run to a named reference
and tolerance. The [validation index](README.md) explains the evidence categories.

## Tests with an existing build

```sh
ctest --preset dev
```

To focus on specific mechanisms, use `ctest --preset dev -R <pattern>`. The
[lattice handbook](../../AGENTS/engine/lattice/AGENTS.md#source-map) and
[model backend checks](../../tools/torch/README.md#c-backend-checks) identify
the field and Torch regression fixtures. Use
[the first run](../first_run.md) for a short end-to-end transport check with an explicit
output directory.

## Scenario and benchmark runs

| Script | What it runs or writes |
| --- | --- |
| [`run_smoke.sh`](../../scripts/run_smoke.sh) | Configure, build, run CTest and run the small electron-in-water scenario. The scenario writes to the current directory. |
| [`run_validation.sh`](../../scripts/run_validation.sh) | Build, run CTest and run the brine baseline. The script defaults to the root output files and refreshes `docs/validation/validation_summary.md`. |
| [`run_validation_suite.sh`](../../scripts/run_validation_suite.sh) | Run scenarios and regenerate their report and selected benchmarks. The script documents `SKIP_*`, report paths, cache settings and event-count controls. |

For a scoped benchmark, use its driver directly. For example, the
[glass-of-water validator](../../scripts/validate_glass_of_water.py)
checks refractive indices recovered from Geant4 trajectories. Its
[report](validation_glass_of_water.md) records the geometry, captured tracks,
metrics and the scope of the comparison. [Benchmark files and conventions](benchmarks/README.md)

For suite development, start with the matching case in
[`tools/validation/trech_validation/cases.py`](../../tools/validation/trech_validation/cases.py).
Use separate run and report directories for experimental runs. The suite also accepts
overrides for the optics artifact and its report paths. See the
[validation handbook](../../AGENTS/tooling/validation/AGENTS.md) for the complete
isolation notes. Reserve committed reports and reference media for deliberate refreshes.
