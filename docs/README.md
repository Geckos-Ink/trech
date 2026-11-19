# TRECH documentation

[Repository README](../README.md) · [Project principles](../AGENTS.md) · [Active roadmaps](../AGENTS/ROADMAP.md)

Browse by topic below. Every folder has a README with links to its files, child folders
and parent index. Keep new documents with their owning topic and update that folder’s index.
Generated reports and JSON sidecars stay together under `validation/`; screenshot captures
and provenance stay together under `media/`. Vendored Geant4 manuals retain their internal layout.

## Start here

- [Scenario bundles](scenarios/scenario_bundles.md): how runnable JavaScript experiments are organized.
- [Studio authoring](studio/studio_authoring.md): edit scenarios and their companion files.
- [Engine output schema](engine/output_schema.md) and [hook API](engine/scenario_hooks.md): runtime contracts.
- [Validation report](validation/validation_report.md): results and provenance for the recorded checkout.
- [Preview gallery](previews.md): annotated images and animations not displayed elsewhere.

## Topics

| Folder | Contents |
| --- | --- |
| [Architecture](architecture/README.md) | Repository structure, implementation design and the JS → JSON → C++ boundary. |
| [Engine contracts](engine/README.md) | Configuration, hook APIs, runtime backends, precision and the Geant4 base of truth. |
| [Inference and models](inference/README.md) | Learned particle-to-observer responses, recursive lifting, domain learning and model tooling. |
| [Scenarios and processes](scenarios/README.md) | JavaScript bundles, reusable processes, molecular examples and scenario validation designs. |
| [Studio and visualization](studio/README.md) | Scenario editing, Chemistry workspace views and faithful visualization of recorded engine output. |
| [Validation reports](validation/README.md) | Committed regression reports, machine-readable sidecars, model audits and benchmark snapshots. Reports apply to the checkout and data they record; moving them does not revalidate their results. |
| [Research](research/README.md) | Experimental research tools and their scientific scope. Read each document’s maturity and validation labels before interpreting results. |
| [Project context](project/README.md) | Planning, funding discussion drafts and historical notes. The active implementation backlog lives in the repository’s categorized AGENTS roadmaps; the original trech-roadmap.md is reference-only. |
| [Documentation media](media/README.md) | Documentation images and their capture provenance. The broader preview gallery is linked from the documentation index. |
| [External references](reference/README.md) | Vendored documentation kept separate from TRECH-authored contracts and research. |

## Reading results

Geant4 particle transport is the base of truth. Learned higher-scale predictions,
independent quantum references, authored comparison solvers and rendering choices keep their
own labels. A roadmap, research study or gallery image does not prove a capability exists.
Use the [categorized handbooks and roadmaps](../AGENTS/AGENTS.md) for source ownership,
current contracts and unfinished work.
