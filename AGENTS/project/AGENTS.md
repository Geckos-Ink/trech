# Project workflow and shared status — context and contracts

[Root principles](../../AGENTS.md) · [Root roadmap](../../ROADMAP.md) · [Parent](../AGENTS.md) · [Roadmap](ROADMAP.md)

## Choose a subcategory

| Scope | Context | Work remaining |
| --- | --- | --- |
| Completed project milestones | [AGENTS.md](history/AGENTS.md) | [ROADMAP.md](history/ROADMAP.md) |
| Sputnik north star | [AGENTS.md](north-star/AGENTS.md) | [ROADMAP.md](north-star/ROADMAP.md) |

Related owners: [Multi-scale inference](../engine/inference/AGENTS.md) · [Optics and nondegenerate transport](../engine/simulation/optics/AGENTS.md) · [Scenario and process editing](../studio/authoring/AGENTS.md).

Read the root principles and the parent handbook first; then open only the subcategory relevant to the task. Source paths and shell commands in code spans/blocks are repository-relative unless stated otherwise; Markdown links resolve from this file.

## Collaboration and maintenance rules

- **Update markdowns as you go.** Every action that changes durable facts updates the owning
  `AGENTS/<category>/AGENTS.md` and its paired `ROADMAP.md`. Keep the root
  [principles](../../AGENTS.md) and [roadmap index](../../ROADMAP.md) current when shared rules,
  objectives or navigation change; keep detailed contracts and backlog items in their owning branch.
  Update [`README.md`](../../README.md) for user-facing changes and [`CHARTS.md`](../../CHARTS.md)
  when architecture / dataflow / Geant4 integration changes. Keep
  [`studio/README.md`](../../studio/README.md) current when desktop usage changes.
- **Track every unfinished edge in its owning `AGENTS/<category>/ROADMAP.md`** (residual,
  scaffold, missing validation/coverage, TODO) **in the same change**. Use the
  [roadmap tree](../ROADMAP.md) to find its owner; link shared work across affected branches.
  Never leave unfinished work discoverable only from code comments or handoff prose.
- **Implementation changes the owning source.** Engine work requires C++ changes under
  [`src/`](../../src) (high priority); Studio work changes Python/WGSL under
  [`studio/trech_studio/`](../../studio/trech_studio). Documentation-only updates do not count as
  implementing a roadmap capability.
- **Predictions come from Geant4-driven data + learned/validated inference**, not fixed classical
  formulas. Formulas are comparison/validation only unless documented as an analytic cross-check.
- **Generated / runtime data is not source.** Everything under `build/` is gitignored and
  local-only; the engine emits run outputs (`trech_*.jsonl`, `trech_viz_*`) into a `--output`
  dir. `data/` cascade/ridge models ARE committed source of truth. Note: `trech_provenance.jsonl`
  / `trech_scores.jsonl` at the repo root are **tracked committed sample outputs** (a normal run
  targets a `--output` directory, not the repo root) — treat them as regenerable artefacts, not
  authoritative source, and don't wire tooling to them.
- **Determinism & honesty are visible.** Keep strict runs byte-reproducible; label inferred /
  hook-layer / rendering-choice results as such and measure the gap-to-truth.

### Docs — [`docs/`](../../docs)

[`output_schema.md`](../../docs/output_schema.md) (the output contracts Studio/viz depend on — update in
lock-step with `Config.cpp`/parsers), [`structure.md`](../../docs/structure.md),
[`scenario_hooks.md`](../../docs/scenario_hooks.md), [`viz_refraction.md`](../../docs/viz_refraction.md),
[`validation_report.md`](../../docs/validation_report.md)/`.json` + [`validation_summary.md`](../../docs/validation_summary.md)
(committed for regression tracking), [`CNT/BackToTheCarbon.md`](../../docs/CNT/BackToTheCarbon.md),
[`implementation.md`](../../docs/implementation.md), [`notes.md`](../../docs/notes.md), and the reference-only
[`trech-roadmap.md`](../../docs/trech-roadmap.md). `docs/geant4-docs/` is a vendored HTML copy of the
Geant4 manuals.

### Recurring pitfalls (do not reintroduce)

Pitfalls follow their owning source: [engine](../engine/AGENTS.md),
[scenario libraries](../scenarios/AGENTS.md), [Studio](../studio/AGENTS.md) and
[media tooling](../tooling/media/AGENTS.md). Open the relevant branch with its focused tests.

## Data, security, privacy, and compatibility boundaries

- **Canonical vs derived:** committed `data/` models + scenarios + validation reports are
  canonical; `build/**` and `--output` `trech_*` files are derived/regenerable. Never treat run
  output as source.
- **Compatibility:** config hashes are a compatibility promise — preserve them via conditional
  serialization; keep the JS → JSON → C++ boundary and the `docs/output_schema.md` contracts
  stable (update parser + schema + Studio together). Feature/composition ML schemas are versioned
  (`trech_event_features_v1`, `ridge_optics_n_v1`, `logistic_stratifier_v1`).
- **Determinism:** strict mode is the reproducibility contract; predictive mode must log every
  relaxation in provenance.
- **Secrets/privacy:** none in-repo; PubChem fetches hit a public API and cache under `build/`.
  No credentials or personal data belong in configs, provenance, or this handbook.
- **Kernel-bound live edits:** `trech lab` accepts live event-count/seed/planner changes but MUST
  reject a geometry/beam/physics/scoring patch after Geant4 init with a restart-required error
  until safe reinitialization lands (**Known gap**, tracked in the [runtime roadmap](../engine/runtime/ROADMAP.md)).

## Current status, known gaps, and roadmap snapshot

Chronology lives in git and [`docs/validation_report.md`](../../docs/validation_report.md). Current
labels:

### Shipped

- Deterministic JS→JSON→C++ engine, provenance, QBBC Geant4 transport, optics derivation, event
  stratification, analytic cross-checks, material-probe + optics `ctx` surfaces, nuclear cycles.
- The cascade mechanism (`ScaleCascade`/`ctx.cascade`) + `ctx.predict` + committed optics ridge.
- Fluids/H₂O MD ladder, magnetic-resonance 4-stage track, CNT band-structure + logic gates,
  chemistry cycles, biology membrane scenarios, the `lava_lamp` inferred thermofluid.
- Typed authoring (`TRECH_VALUE` + `trech inspect` + `--param`), real-time `trech lab` bootstrap,
  [`studio/`](../../studio) viewer basis.

### Experimental / scaffold

- Most cascade **stage models** are illustrative hand-authored maps, not broadly trained.
- `MultiscaleBridge` (`multiscale.enable`) is stubbed and does not alter physics.
- Hook-layer MD/Bloch/PBF/parcel/reaction solvers are labelled "physics for comparison," not
  Geant4-computed.
- Studio scaffolds: property-driven scene editor and gizmos. Transport-scene JS export is
  available; callback/companion reconstruction and dependency packaging remain open.

### Known gaps

- Default-thread strict transport replay currently varies for `hello_world.js` on the local
  dependency build, including with the pre-cleanup binary. Serial `run.threads:1` replay matches;
  MT seeding/replay diagnosis remains tracked in the [runtime roadmap](../engine/runtime/ROADMAP.md). Strict byte replay is still required.
- The first bounded Geant4-trained non-optics atomic/nano response is CHNO photon transport;
  general learned higher-scale state/bond/electronic dynamics remain open (the core objective).
- `trech lab` cannot yet safely reinitialize a kernel-bound geometry/beam/physics/scoring change.
- No in-CI Geant4 end-to-end run; the physics regression suite is manual.

### Near-term priorities

1. Grow the cascade toward a **general-purpose, context-driven predictor** — a trained per-band
   chain in fluids/chemistry/biology/electronics/resonance (standing objective, [inference roadmap](../engine/inference/ROADMAP.md)).
2. Constantly **reduce simulation degeneration** (real sampled distributions; convergence to
   measured behaviour) — tracked by `sampling_diversity_non_degenerate` in the [transport roadmap](../engine/simulation/optics/ROADMAP.md).
3. Studio: property-driven editing + `SceneModel → .js` round-trip ([desktop milestones](../studio/authoring/ROADMAP.md#milestone-2--real-time-scenario-editing)).

## Task start and handoff checklist

**Start:** read the [root principles](../../AGENTS.md), then use the
[handbook tree](../AGENTS.md) to read the relevant category and its owning `AGENTS.md` / `ROADMAP.md`
pair. Include the [Studio contracts](../studio/AGENTS.md#studio-desktop-ui) for `studio/**` work
and dependency-specific instructions for dependency work. Check `git status` and preserve unrelated
changes; find the owning source + focused test from the selected source map; compare handbook
claims with current code before relying on them; note which sections the task will change.

**Handoff:** update changed durable facts in the owning handbook (owners, symbols, contracts,
feature status) and add any residual/scaffold/TODO to its paired roadmap in the same change.
Update the root files when shared principles, objectives or routing change; keep
[`README.md`](../../README.md)/[`CHARTS.md`](../../CHARTS.md)/[`docs/output_schema.md`](../../docs/output_schema.md)
consistent; run `ctest --preset dev` for engine changes (and the relevant validation/smoke script if
physics/output changed); report tests run, tests skipped, and remaining gaps accurately;
never label incomplete work Shipped. For Studio changes, also run the relevant `studio/tests/` pytest coverage;
keep parsers aligned with the schema, label rendering choices and preserve the reference-GIF gate.
Documentation-only changes need link/reference checks rather than simulation or GPU runs.
