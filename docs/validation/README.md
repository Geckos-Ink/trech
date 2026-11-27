# Validation reports

[Documentation index](../README.md)

Committed regression reports, machine-readable sidecars, model audits and benchmark snapshots. Reports apply to the checkout and data they record; moving them does not revalidate their results.

## What does a passing check establish?

| Evidence | What a pass supports |
| --- | --- |
| Reproducibility or accounting check | The recorded inputs replay or an invariant such as energy or inventory accounting closes. |
| Analytic consistency check | Sampled transport agrees with an equation evaluated under the same assumptions, often using Geant4's own tables. |
| Teacher fidelity | A learned law agrees with its comparison solver or operator teacher on the graded cases. |
| Independent Geant4 holdout | A learned estimate agrees with separately sampled Geant4 outcomes under the tested conditions. |
| Independent physical or quantum reference | Agreement with the stated measurements or calculation, in the range and units reported by the check. |

Identify the observable and its producer before quoting an error. Check the reference,
run conditions, model coverage and acceptance rule. One-step agreement and a test
that lets the predictor drive a full run grade different things. A plot can show any
of these results. Its camera, clock or color mapping can come from the viewer.
[Mathematical foundations](../research/foundations.md#learning-error-and-trust) ·
[Run provenance and artifact identities](../engine/output_schema.md#trech_provenancejsonl) ·
[Run a check](running_checks.md)

## Folders

| Folder | Contents |
| --- | --- |
| [Benchmark snapshots](benchmarks/README.md) | Diff-friendly text snapshots paired with the optical validation reports in the parent folder. |

## Files

| Document or asset | Purpose |
| --- | --- |
| [Run and reproduce checks](running_checks.md) | CTest, validators and regenerable reports. |
| [TRECH_current_scenarios_purity.json](TRECH_current_scenarios_purity.json) | Machine-readable sidecar for the corresponding Markdown report. |
| [Scenario purity report](TRECH_current_scenarios_purity.md) | Generated inference/authored-law evidence and recorded validation. |
| [ml_model_audit.json](ml_model_audit.json) | Machine-readable sidecar for the corresponding Markdown report. |
| [Static model audit](ml_model_audit.md) | Committed-model structure and carried trust checks. |
| [ml_model_recheck.json](ml_model_recheck.json) | Machine-readable sidecar for the corresponding Markdown report. |
| [Fresh-run model rechecks](ml_model_recheck.md) | Independent seed checks and producer-replay results. |
| [search_comparison_particle_observer.json](search_comparison_particle_observer.json) | Architecture-search strategies compared on the Geant4 particle-observer runs; explained in [evolved architectures](../inference/evolvo_architectures.md#search-quality-on-geant4-runs-2026-11-27). |
| [validation_glass_of_water.json](validation_glass_of_water.json) | Machine-readable sidecar for the corresponding Markdown report. |
| [Glass-of-Water validation](validation_glass_of_water.md) | Optical inverse checks against recorded trajectories. |
| [validation_optics_surrogate.json](validation_optics_surrogate.json) | Machine-readable sidecar for the corresponding Markdown report. |
| [Optics surrogate validation](validation_optics_surrogate.md) | Held-out material predictions and comparison scope. |
| [validation_report.json](validation_report.json) | Machine-readable sidecar for the corresponding Markdown report. |
| [Scenario validation report](validation_report.md) | Generated suite results for the recorded checkout. |
| [Validation summary](validation_summary.md) | Retained baseline metrics and pointers to suite results. |
