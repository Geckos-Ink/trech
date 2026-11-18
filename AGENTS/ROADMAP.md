# Handbook tree — roadmap

[Root principles](../AGENTS.md) · [Root roadmap](../ROADMAP.md) · [Parent](../ROADMAP.md) · [Handbook](AGENTS.md)

## Choose a subcategory

| Scope | Context | Work remaining |
| --- | --- | --- |
| C++ engine | [AGENTS.md](engine/AGENTS.md) | [ROADMAP.md](engine/ROADMAP.md) |
| Project workflow and shared status | [AGENTS.md](project/AGENTS.md) | [ROADMAP.md](project/ROADMAP.md) |
| JavaScript scenarios and domain libraries | [AGENTS.md](scenarios/AGENTS.md) | [ROADMAP.md](scenarios/ROADMAP.md) |
| Studio desktop client | [AGENTS.md](studio/AGENTS.md) | [ROADMAP.md](studio/ROADMAP.md) |
| Python tools and scripts | [AGENTS.md](tooling/AGENTS.md) | [ROADMAP.md](tooling/ROADMAP.md) |

## Priority keys

- **P1** — on the implementation route now: the next work that advances a standing objective, or a
  defect in the replay/provenance/honesty contract. Pick from here first.
- **P2** — consolidation: closes a residual of landed work, validates it, or unblocks a P1.
- **P3** — later: depth, polish and long research tracks.
- **gated** — needs an owner decision, a heavy dependency build, external data or a media
  recapture. Do not start it without that go-ahead.

Every leaf roadmap opens with a **Priority queue** holding all of its open items with a key and a
route step. A residual found while delivering work goes into the owning queue in the same change;
a P1 also goes on the route below. Cross-branch items live in one queue and are pointed to from
the others.

## Implementation route

Steps are ordered: an earlier step protects the later ones (a learned cascade is only worth
promoting on a replayable, provenance-complete run). Work any step's P1 items, but do not let a
later step regress an earlier contract.

- **R1 Replay and provenance contract** — strict byte replay, typed configs, guardrails and recorded identities. Everything later relies on it.
- **R2 Trained multi-scale cascade** — learned, held-out-validated chains from Geant4 facts up to the observer scale, across every family (the engine thesis).
- **R3 Operator migration** — authored JavaScript state laws become learned engine operators behind paired observer gates.
- **R4 Trust and uncertainty** — held-out error metrics, coverage, lineage and resimulation, so a longer cascade cannot trade accuracy for reach.
- **R5 Geant4 base, anti-degeneration and validation** — the precise base itself, its diagnostics and the regression suite.
- **R6 Studio: observe and edit the cascade** — viewer/client work that makes recorded results legible and editable.
- **R7 Platform and backends** — Torch, V8, dependency builds and performance.
- **RX Research tracks** — long-horizon work outside the route (atomic stability, QM references).

### P1 items by route step

**R1 Replay and provenance contract**

- Finish strict multi-thread byte replay for JavaScript hook dispatch and emits. — [engine/runtime](engine/runtime/ROADMAP.md#priority-queue)

**R2 Trained multi-scale cascade**

- Close residual CHNO observer coverage holes and validate transfer across composition, geometry and source context. — [engine/inference](engine/inference/ROADMAP.md#priority-queue)
- Worked cascades for the families that still have none: biology (efflux/osmosis cell observables), CNT electronics (gap → device → logic) and magnetic resonance (proton density → image). — [engine/inference](engine/inference/ROADMAP.md#priority-queue)
- Graduate the illustrative stage maps (Briggs–Rauscher, polyurethane, elephant's toothpaste, glass from sand, glass of water) to trained, held-out-validated per-band chains. — [engine/inference](engine/inference/ROADMAP.md#priority-queue)
- Sputnik water molecule: thermal ensembles, more atoms and a force field graded against measured spectroscopy, on the way to a particle-derived (Geant4-trained) water operator. — [project/north-star](project/north-star/ROADMAP.md#priority-queue)
- Next learned lift: geometry/charge/isotope-conditioned electronic and bond response trained on Geant4 particle/ionization histories, with molecule/geometry/energy holdouts and independent quantum/experimental gaps. — [scenarios/chemistry](scenarios/chemistry/ROADMAP.md#priority-queue)
- A particle-derived (Geant4-trained) water operator that freezes, replacing the literature mW potential (closes the engine-thesis gap of the freeze/boil program). — [scenarios/fluids](scenarios/fluids/ROADMAP.md#priority-queue)
- Particle-trained atomic rung: feed Geant4 material/atomic response (mean excitation energy, photo-absorption) as atomic inputs and re-grade the cascade ablation. — [scenarios/spectra](scenarios/spectra/ROADMAP.md#priority-queue)

**R3 Operator migration**

- Row 2 — CNT material → device → circuit cascade (cheap deterministic scenarios with validation cases). — [scenarios/migrations](scenarios/migrations/ROADMAP.md#priority-queue)
- Row 3 — magnetic-resonance forward dynamics. — [scenarios/migrations](scenarios/migrations/ROADMAP.md#priority-queue)
- Row 6 remainder — osmosis (efflux promoted 2026-07-26). — [scenarios/migrations](scenarios/migrations/ROADMAP.md#priority-queue)
- Engine method selection for declared fields (`ctx.evolveField`): make learned arbitration beat the best single method on the lava lamp. — [engine/lattice](engine/lattice/ROADMAP.md#priority-queue)

**R6 Studio: observe and edit the cascade**

- Safe `trech lab` reinitialization of geometry/beam/physics/scoring patches (now restart-required), then the restart handshake through Studio. — [engine/runtime](engine/runtime/ROADMAP.md#priority-queue)
- Real-time lab loop: Inspector edits become `patch` commands to a live `trech lab` and `simulate` streams snapshots back (engine reinitialization is a runtime P1). — [studio/authoring](studio/authoring/ROADMAP.md#priority-queue)
- Complete the `SceneModel → scenario .js` round-trip for source dependencies and volume hierarchy. — [studio/authoring](studio/authoring/ROADMAP.md#priority-queue)

### Gated items (need a go-ahead)

- Research sponsorship: scope a pilot observable/domain with named owners, validate credit allocations and staffing/compute estimates, establish partner interest (owner decisions, not agent work). — [project](project/ROADMAP.md#priority-queue)
- Calibrated microscope-scale interface data (no calibrated 3D sequence is bundled; external data needed). — [scenarios/processes](scenarios/processes/ROADMAP.md#priority-queue)
- NaCl and aerodynamics quantitative validation need independent external anchors (concentration/evaporation data; shock/flow data) before any learned phase/continuum lift. — [scenarios/references](scenarios/references/ROADMAP.md#priority-queue)
- V8: heavy upstream GN build, probe link/run, host API/RNG/emit parity and benchmarks (needs an explicit decision to build). — [scenarios/references](scenarios/references/ROADMAP.md#priority-queue)
- Native screenshots of the Models and Spectra docks (media gates). — [studio/workspace](studio/workspace/ROADMAP.md#priority-queue)
- Rebuild/install Geant4 11.5 and rebuild TRECH, then CTest and physics regression; then a real `TRECH_ENABLE_DNA_CHEM` build, G4EMLOW 9.0 and the revalidation list (heavy build: needs an explicit go-ahead). — [tooling/dependencies](tooling/dependencies/ROADMAP.md#priority-queue)
- Recapture media that predate fixes (Briggs–Rauscher and MR-tissues geometry, aerodynamics/NaCl beam origin) and refresh historical native screenshots deliberately (media gates). — [tooling/media](tooling/media/ROADMAP.md#priority-queue)

Maintain work in its owning branch. Dated results apply to the recorded checkout; they do not validate subsequent changes.

