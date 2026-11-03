# Project workflow and shared status — roadmap

[Root principles](../../AGENTS.md) · [Root roadmap](../../ROADMAP.md) · [Parent](../ROADMAP.md) · [Handbook](AGENTS.md)

## Choose a subcategory

| Scope | Context | Work remaining |
| --- | --- | --- |
| Completed project milestones | [AGENTS.md](history/AGENTS.md) | [ROADMAP.md](history/ROADMAP.md) |
| Sputnik north star | [AGENTS.md](north-star/AGENTS.md) | [ROADMAP.md](north-star/ROADMAP.md) |

Dated records apply to their captured checkout. Current contracts, code and tests take precedence; these results do not validate later changes.

Shared priorities and structure belong here; component checklists live in the [roadmap index](../../ROADMAP.md).

## Short-term next steps

This retained shared planning snapshot includes steps with later landings. Check the current
[dependency/backend plan](../tooling/dependencies/ROADMAP.md) and
[runtime plan](../engine/runtime/ROADMAP.md) before treating an older item as still open.

- Extend analytic cross-checks beyond Beer-Lambert (the framework is data-driven via `AnalyticCheckResult.measuredField`). **[charged-particle CSDA range landed 2026-06-30]** `analytic_csda_range.js` derives the CSDA range from Geant4's own stopping power (`G4EmCalculator::GetCSDARange`) and compares it to a new `primary_mean_track_length_mm` tally — 20 MeV proton in water, derived 4.282 mm vs measured 4.266 mm (0.38%); guarded by `analytic_csda_range_cross_check`. **[photofraction landed 2026-07-02]** `analytic_photo_fraction.js` predicts the photoelectric process-branching ratio `sigma_phot/sigma_total` from the SAME per-process cross sections Beer-Lambert sums and compares it to a new `primaries_photoelectric_first_fraction` tally (the fraction of primaries whose first discrete interaction is photoelectric, classified through QBBC's `G4GammaGeneralProcess` wrapper by EM subtype) — 30 keV gamma in water, derived 0.3908 vs measured 0.3931 (0.59%); guarded by `analytic_photo_fraction_cross_check`. Unlike the two attenuation/range checks this one tests the process CHOICE (branching), and is slab-thickness independent. Next data-driven check types: the Compton edge / Klein-Nishina scattered-spectrum edge, or the photofraction's energy dependence (a sweep) — each a new closed-form prediction compared to the run's Monte-Carlo tally.
- Use `docs/validation_summary.md` to track baseline H2O run metrics and watch for regressions as physics/optics work expands.
- Refresh validation outputs after example refreshes (container volumes, explicit materials, nested geometry).
- Continue expanding hook runtime guardrails after `ctx` + deterministic patch/emit landing (next: patch whitelist growth). Stricter emit payload validation and per-callback emit caps are implemented via `hooks.maxEmitsPerCallback` and `hooks.maxEmitPayloadBytes`.
- Extend determinism controls beyond mode selection (strict/predictive implemented) and add guardrails for mixed runtime workflows.
- Define the TorchScript model output contract (label string or 1-2 value tensor) and add a LibTorch-backed smoke test once LibTorch is available.
- Expand system observables beyond current density + event energy moments (mean/variance/stddev) as new per-run accumulables land.
- Keep `CHARTS.md` aligned with runtime changes (workflow, Geant4 wiring, outputs, stratification/prediction).
- Stage a CNT milestone track in parallel to validate config/output coherence without diverging from the H2O baseline.
- Improve geometry authoring beyond primitive shapes: scene graph/nesting, imports (GDML), and procedural generators for complex assemblies.
- Continue de-colliderizing terminology: parser now accepts `environment`/`medium` aliases for `detector`; next extend alias visibility across examples/docs/CLI hints without breaking existing configs.
- Expand flow-oriented JS authoring (`TRECH_FLOW`) beyond current helpers (defaults/derive/normalize/finalize/require) with reusable validation presets while preserving the JS -> JSON boundary.
- Extend nuclear-cycle analysis beyond static consistency/Q-value checks by adding event-level transmutation/decay tallies (Geant process attribution) for scenario-level closure metrics.
- Bootstrap the real-time 3D lab runtime path: support a live command stream (`patch`, `simulate`, `snapshot`, `quit`) over canonical JSON config so users can interact without a fixed JS scenario.
- **Studio desktop UI:** continue the [shared desktop workstream](../studio/ROADMAP.md#studio-desktop-ui), especially
  [M2 visual editing](../studio/authoring/ROADMAP.md#milestone-2--real-time-scenario-editing) beyond bounded transport drafts: inspector → live `trech lab`
  patches, gizmos and `SceneModel → runnable .js`. The existing PySide6/wgpu client already reads
  runs, replays recorded state and exposes the cascade; [AGENTS.md](../studio/AGENTS.md#studio-desktop-ui)
  owns its client/layering contracts. Stack rationale and M0–M4 status are recorded in the [Studio roadmap](../studio/ROADMAP.md).
- Use LibTorch/TorchScript for fluid-scale statistical modeling; wire incremental learning as the runtime evolves.
- Long-term: keep the C++ config surface physics/chemistry agnostic, relying on JS scenarios and lab command streams to express combinations.

## Long-term structure

- core/ (config, provenance, storage)
- js/ (runtime + bindings)
- sim/ (Geant4 integration and scoring)
- chem/ (species registry, reaction network, RD engine, DNA bridge)
- ml/ (TorchScript runtime + feature pipelines)
- data/ (curated datasets; new PubChem runtime fetches should go to build-local cache dirs)
- bench/ (benchmarks, manifests, reproducible datasets)
- docs/ (architecture, APIs, user guides)
- thirds/ (submodules and vendored dependencies)
