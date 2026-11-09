# Tests and validation ownership — context and contracts

[Root principles](../../../AGENTS.md) · [Root roadmap](../../../ROADMAP.md) · [Parent](../AGENTS.md) · [Roadmap](ROADMAP.md)

## Choose a subcategory

| Scope | Context | Work remaining |
| --- | --- | --- |
| Recorded validation snapshots | [AGENTS.md](history/AGENTS.md) | [ROADMAP.md](history/ROADMAP.md) |

Read the root principles and the parent handbook first; then open only the subcategory relevant to the task. Source paths and shell commands in code spans/blocks are repository-relative unless stated otherwise; Markdown links resolve from this file.

- **[`tools/validation/trech_validation/`](../../../tools/validation)** — the regression suite
  (`python -m trech_validation`): [`cases.py`](../../../tools/validation/trech_validation/cases.py) (per-scenario
  assertions incl. hook-emit reads), [`runner.py`](../../../tools/validation/trech_validation/runner.py),
  [`report.py`](../../../tools/validation/trech_validation/report.py) → [`docs/validation_report.md`](../../../docs/validation_report.md).

- **Offline input preflight:** `scripts/run_validation_suite.sh` defaults to
  `PUBCHEM_MODE=refresh`; `cache-only` uses
  [`pubchem_inputs.py`](../../../tools/validation/trech_validation/pubchem_inputs.py) to check all
  required selected-cache records before builds or output deletion, never fetching or using the
  legacy fallback. Invalid/missing paths fail together. Skipped scenario groups do not require
  unused records. Use an existing binary with `SKIP_BUILD=1` for an offline invocation that also
  avoids CMake dependency fetching. `tests/test_validation_offline.py` covers local read-only
  checks, corrupt/incomplete caches, fail-before-mutation, selection and default online behavior.
  Cache-only preflight records `trech_pubchem_input_snapshot_v1` SHA-256 hashes of every record it
  read in `${RUNS_DIR}/pubchem_input_snapshot.json`; `PUBCHEM_SNAPSHOT=<manifest>` (cache-only
  only) fails with exit 3 before builds when any selected record's bytes differ, is unpinned, or
  the manifest's own digest does not match. Pinning proves byte identity, not PubChem provenance.
  `report.py` copies the self-verified snapshot digest/record count into the report metadata
  (`pubchem_inputs`: `recorded`/`invalid`/`absent`) via `pubchem_inputs.snapshot_summary`.
- **Bundle-declared family gates:** [`declarative.py`](../../../tools/validation/trech_validation/declarative.py)
  evaluates `family_checks` from scenario validation companions; `_declared_family_verdict` in
  `cases.py` takes the verdict from them and adds a `verdict: N/N family_checks …` note. A missing
  `trech` binary raises a case error, never a pass. `[*]`/`[?key=value]` projections must be
  reduced by an `aggregate`; every aggregate except `count` fails on an empty projection, a
  missing element field or a wrong type. `derive` (`abs`, `difference`, `ratio`, `list_sum`,
  `list_length`, `chi2_sf`; nestable) computes per-element statistics; `chi2_sf` is the one
  implementation `cases.py` also uses. Eighteen families are exported, including the
  Beer-Lambert/CSDA/photofraction/Compton/pair-fraction analytic checks and the driver-recorded
  MR tissue/brain gates. **Multi-run sweeps:** `family_sweeps` (`evaluate_sweep`) declare
  ordered `runs` (`id` + exact `params`, checked against each run's recorded `--param` set) and
  checks scoped by `run`, `each_run` (all or a subset) or `series_aggregate`
  (`strictly_increasing|strictly_decreasing|first_over_last|last_over_first|argmax|argmin` plus
  the ordinary aggregates) across runs; `binomial_z` joins the `derive` set.
  `_declared_sweep_verdict` maps run ids to suite run names; an unmapped or missing run fails.
  The photofraction energy sweep, pair threshold/energy sweep and photonuclear giant-dipole gates
  are exported (21 bundle-graded cases). `scripts/validate_scenario.py --sweep CASE --run ID=DIR`
  grades one sweep outside the suite; Studio's run summary reuses this evaluator (single-run
  checks only). Tests: [`tests/test_scenario_contracts.py`](../../../tests/test_scenario_contracts.py).

## Test ownership map

- **Filesystem fixtures:** [`tests/TemporaryDirectory.hpp`](../../../tests/TemporaryDirectory.hpp)
  atomically reserves a unique directory and removes its contents on scope exit. C++ tests write
  generated scripts, models and provenance beneath that directory, including relative-path model
  bundles. Do not use fixed names in the working directory or shared temporary root, or rely on a
  timestamp without atomically reserving it. `test_provenance_writer.cpp` checks same-name file
  isolation and recursive cleanup; keep fixture lifetimes longer than all readers/writers.
- **Config/CLI/lab/provenance** (`trech_core`): [`test_config_roundtrip.cpp`](../../../tests/test_config_roundtrip.cpp)
  (byte-stable hashes — the conditional-serialization guard), [`test_cli_parse.cpp`](../../../tests/test_cli_parse.cpp),
  [`test_lab_session.cpp`](../../../tests/test_lab_session.cpp), [`test_provenance_writer.cpp`](../../../tests/test_provenance_writer.cpp).
- **Adaptive precision/work:** [`tests/test_adaptive_precision.cpp`](../../../tests/test_adaptive_precision.cpp)
  (budget feedback, config/strict guards, continuous JS refinement and bounded cascade counts);
  [`tests/test_evolvo_structure.py`](../../../tests/test_evolvo_structure.py) (optional NumPy/Evolvo search,
  seeded bounds/time/RNG isolation; run with the tooling Python environment).
- **JS runtime & hook boundary:** [`test_js_runtime.cpp`](../../../tests/test_js_runtime.cpp) (`ctx.predict`,
  two-stage `ctx.cascade`, ambient seed, `TRECH_INCLUDE`/`TRECH_FLOW`).
  [`test_scenario_helpers.cpp`](../../../tests/test_scenario_helpers.cpp) covers standalone/shared import
  order, seeded sampling/draw counts, numeric helpers, clocks and missing/immutable source facts.
- **ML:** [`test_scale_cascade.cpp`](../../../tests/test_scale_cascade.cpp), [`test_state_evolution.cpp`](../../../tests/test_state_evolution.cpp), [`test_generic_surrogate.cpp`](../../../tests/test_generic_surrogate.cpp),
  [`test_optics_surrogate.cpp`](../../../tests/test_optics_surrogate.cpp), [`test_stratifier.cpp`](../../../tests/test_stratifier.cpp).
  Torch-enabled builds also register [`test_torch_backends.cpp`](../../../tests/test_torch_backends.cpp),
  which creates real synthetic modules without Python Torch and checks loaders/lifecycle,
  positional finite-output publication, snapshot identities and strict classifier gating.
- **Chem/nuclear:** [`test_dna_chemistry_bridge.cpp`](../../../tests/test_dna_chemistry_bridge.cpp),
  [`test_nuclear_cycle_analyzer.cpp`](../../../tests/test_nuclear_cycle_analyzer.cpp) (Geant4-gated).
- **Scenario physics regression:** the Python suite in [`tools/validation/`](../../../tools/validation)
  (per-family guards named in the scenario table), report committed to
  [`docs/validation_report.md`](../../../docs/validation_report.md). **Known gap:** no in-CI end-to-end
  Geant4 run — the physics suite is run manually and its report committed.
- **Inference resim policy gate:** [`scripts/validate_inference_resim.py`](../../../scripts/validate_inference_resim.py)
  runs isolated synthetic point/cascade fixtures through serial Geant4, checking policies, exact
  cause accounting, strict/disabled behavior, event/callback isolation and byte replay. Optional
  `--baseline-binary` compares legacy scores/events/emits/queue and config hashes. Artifacts live
  in a unique `build/inference_resim_checks/validation_*` directory. This is a manual diagnostics
  gate, not physical model validation or an automatic resimulation executor.
- **Strict worker transport gate:** [`scripts/validate_strict_worker_transport.py`](../../../scripts/validate_strict_worker_transport.py)
  verifies exact event/trajectory identities across real Tasking/MT workers and optionally checks
  old/new one-worker bytes. It records unrounded run reduction differences and append-order byte
  mismatches explicitly; passing transport checks does not establish full strict MT byte replay.
- **Particle observer gate:** [`tests/test_particle_observer.py`](../../../tests/test_particle_observer.py)
  checks committed raw labels, hashes/freeze evidence, all fit/development/final split boundaries,
  unchanged error gates, baseline improvement, failed-attempt archive and future cache identities.
  [`scripts/validate_particle_observer.py`](../../../scripts/validate_particle_observer.py) checks
  real C++ inference/replay/strict behavior, engine-carried RMSE and independent MC fractions,
  preserving sparse-coverage warnings. Failed scientific gates return failure separately from
  software checks. No experimental measurement accuracy follows from this Geant4 reference.
