# Benchmark snapshots

[Parent index](../README.md) · [Documentation index](../../README.md)

Diff-friendly text snapshots paired with the optical validation reports in the parent folder.

Each snapshot accompanies a human-readable report and a JSON sidecar in the
[parent directory](../README.md). Text snapshots are for inspecting numerical
changes in code review. The report identifies which quantities have tolerance
gates and which are informational. Drivers and output controls are in
[Run and reproduce checks](../running_checks.md).

When adding a benchmark, link the scenario bundle, validator, Markdown report,
JSON sidecar and deterministic text snapshot. Wire it into the suite with a
scoped skip control if it needs a separate run.

## Files

| Document or asset | Purpose |
| --- | --- |
| [validation_glass_of_water.txt](validation_glass_of_water.txt) | Diff-friendly benchmark snapshot. |
| [validation_optics_surrogate.txt](validation_optics_surrogate.txt) | Diff-friendly benchmark snapshot. |
