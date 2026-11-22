# Explore TRECH

[Project home](../README.md) · [Build instructions](build.md) · [Scenario catalog](scenarios/catalog.md) · [Preview gallery](previews.md)

## Follow a first experiment

1. [Run and inspect electrons in water](first_run.md). Trace one JavaScript input into a scored result.
2. [Learn the core concepts](concepts.md). Connect the physical system, state, observables, fields and sources of evidence.
3. [Follow a run through the engine](architecture/runtime.md). See when Geant4 is called, where its results go and how LibTorch and Studio use them.
4. [Follow a prediction across scales](inference/multiscale.md). Compare named-feature chains, recursively grouped populations and context-dependent routing.
5. [See how a field evolves](engine/field_evolution.md). Follow one lava-lamp frame through the candidate methods and their evidence.
6. [Work through the science and math](research/foundations.md). Connect transport, coarse-graining, field discretization and prediction errors to runnable checks.

<details>
<summary>I want to write or modify an experiment</summary>

Start with [scenario authoring](scenarios/authoring.md), then choose [JavaScript bundle and
companion contracts](scenarios/scenario_bundles.md), [Studio authoring](studio/studio_authoring.md)
or the [hook API](engine/scenario_hooks.md). [Live lab and CLI](engine/cli.md) explains
session commands and when the Geant4 kernel can be reused.

</details>

<details>
<summary>I want to check or reproduce a claim</summary>

Open [validation](validation/README.md) for the evidence categories and retained reports.
Find the scenario, its source and its evidence path in the [catalog](scenarios/catalog.md).
Use [the output schema](engine/output_schema.md) to locate the exact record in a run.
To see whether a rendered result came from the engine or from a law the scenario wrote,
run it with the [engine trace](engine/engine_trace.md) (`--trace debug`).

</details>

<details>
<summary>I want to train or inspect a model</summary>

Read [model training and LibTorch deployment](inference/libtorch.md), then the
[model definitions and checkpoint store](inference/ml_models.md). The
[particle-to-observer study](inference/particle_observer.md) follows a frozen model
through held-out Geant4 runs.

</details>

## Reference by topic

| Topic | Contains |
| --- | --- |
| [Architecture](architecture/README.md) | Runtime data flow, source ownership and original design notes. |
| [Engine and APIs](engine/README.md) | CLI and lab, hooks, output schema, precision, Geant4 and JavaScript backends. |
| [Inference and models](inference/README.md) | Cascades, group hierarchies, response domains, model formats and training. |
| [Scenarios and processes](scenarios/README.md) | Runnable examples, authoring, reusable processes and physical comparisons. |
| [Studio and visualization](studio/README.md) | Playback, editing, Chemistry workspace and refraction. |
| [Validation](validation/README.md) | How to run checks, read evidence and inspect recorded results. |
| [Science and research](research/README.md) | Mathematical foundations, atomic and spectral studies and CNT background. |
| [Media](media/README.md) | Capture collections and reproducibility metadata. |
| [External references](reference/README.md) | Vendored Geant4 manuals. |
| [Project context](project/README.md) | Original concept and historical notes. The [active roadmap](../ROADMAP.md) tracks remaining work. |
