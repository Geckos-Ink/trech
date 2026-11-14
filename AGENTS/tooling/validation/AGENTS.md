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
- **Scenario purity report:** [`purity.py`](../../../tools/validation/trech_validation/purity.py)
  (`PYTHONPATH=tools/validation python3 -m trech_validation.purity [--check|--explain NAME]`)
  writes [`docs/TRECH_current_scenarios_purity.md`](../../../docs/TRECH_current_scenarios_purity.md).
  It has one section per bundle with a purity grade (A Geant4-learned … E authored forward law;
  M/G/V/R for demo, transport-only, analytic and independent-reference roles). Inputs are
  committed only: the [JS-law ledger](../../../tools/validation/js_law_audit.json) is
  authoritative, with the companion `physics_status` as fallback. Static normal-path evidence
  comes from a comment/string/regex-masking JS lexer over the entry point and its non-utility
  includes; comparison/reference/teacher functions, `"reference"` branches and `*_reference.js`
  modules are excluded. Model provenance comes from model metadata, and performance from
  `docs/validation_report.json` cases mapped through suite run names plus other
  `docs/validation_*.json` reports. Output is deterministic. CTest
  `trech_scenario_purity_report` ([`test_scenario_purity_report.py`](../../../tests/test_scenario_purity_report.py))
  fails while the file is stale, checks lexer bracket balance on every analysed file, and pins
  zone exclusion with a fixture. `run_validation_suite.sh` regenerates the report after writing
  the default validation report. The opt-in hook [`scripts/git-hooks/pre-commit`](../../../scripts/git-hooks/pre-commit)
  (`git config core.hooksPath scripts/git-hooks`) runs `--pre-commit`, which regenerates and stages
  the report only when a staged path matches `is_relevant` or when the validation report is older
  than `TRECH_PURITY_MAX_AGE_DAYS` (default 30). Old benchmarks also print a refresh reminder.
  The hook never blocks a commit, and `TRECH_PURITY_HOOK=0` skips it. The static counts are a heuristic and flag disagreements; they
  never override the ledger.
- **Learned-model validation** is owned by [training tools](../training/AGENTS.md): the committed
  [`docs/ml_model_audit.md`](../../../docs/ml_model_audit.md) is regenerated by
  `trech_torch.validate_model --scan` and guarded by CTest `trech_ml_model_audit`, the same
  staleness pattern as the purity report. It audits model files statically; it is not a
  physics validation and does not refresh `docs/validation_report.*`.

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
- **Event-deposit shape gate:** `system_event_edep_shape_consistent` (category `engine`, run
  `out_analytic_beer_lambert`) checks min ≤ mean ≤ max, stderr against variance, the kurtosis
  admissibility bound and that zero-deposit events cover every uncollided primary.
- **Event-multiplicity gate:** `system_event_multiplicity_consistent` (category `engine`, same run)
  checks count-valued secondaries (integer total and extremes), the dispersion index against the
  reported moments, kurtosis admissibility, zero-secondary events covering uncollided primaries,
  events with secondaries covering photoelectric-first primaries, a positive track length in
  every event, and the per-species split (species means sum to the total, count-valued species,
  electron events covering photoelectric-first primaries, no positrons below the pair threshold). [`tests/test_system_observable_cases.py`](../../../tests/test_system_observable_cases.py)
  feeds it synthetic scores (pass, skip, missing fields, one failure per corrupted invariant).
- **Event-histogram gate:** `system_event_histogram_consistent` (category `engine`, run
  `out_analytic_beer_lambert`) checks the deposit, track-length (since 2026-11-12) and
  multiplicity histograms (the two log10 ones through the shared `_log_histogram_checks`): fixed scheme, non-negative counts
  summing to `system_event_count`, edges on the fixed grid (log10 deposit grid; unit then doubling
  multiplicity steps), a trimmed populated span, zero slot / zero-secondary bin equal to the
  matching zero fraction × events, max (and min when no zero/underflow events) inside the end bins,
  the run mean × events between the lower- and upper-edge sums, and, when a `run_end` provenance
  record exists, a verbatim copy there. Since 2026-11-12 every
  `system_event_secondaries_<species>_histogram` gets the multiplicity checks (shared
  `_multiplicity_histogram_checks`, prefixed `species_<species>_`, max but no min since species
  summaries carry none) plus `species_zero_bins_cover_total_zero` (an event with no secondaries
  has none of any species). Synthetic pass/skip/missing/per-invariant failure tests
  are in `tests/test_system_observable_cases.py`.
- **Geometry refusal gate (2026-11-14):** `geometry_refusal_guard_refuses_defects` (category
  `engine`, runs `out_geometry_refusal_clean` / `out_geometry_refusal_injected`, both from
  `geometry_refusal_guard.js`) checks the armed-but-clean run (run_start/run_end, `refuseOn` all
  four kinds in the recorded config, overlap check clean, no issues or refusal block, every event
  scored) and the `inject_defects=true` run (one `geometry_refused` record with 0 events and the
  param in `cli_args`, `trech_geometry_refusal_v1` with the canonical kinds, `refused_count` equal
  to the listed refusable issues, the shield's `material_fallback` and the target/probe
  `overlaps_sibling`, no scores, exit status 1). `scripts/run_validation_suite.sh` tolerates that
  run's non-zero exit and records it in `suite_exit_status.txt`, which the case requires. Offline
  tests: `tests/test_geometry_refusal_case.py`.
- **Per-volume event-deposit gate:** `system_volume_event_edep_consistent` (category `engine`, run
  `out_geometry_procedural_assembly`, added to `scripts/run_validation_suite.sh`) checks, per
  `scoreEdep` volume, `mean_mev · events = volume_edep_mev`, min ≤ mean ≤ max, non-negative
  deposits, max ≤ the whole-event maximum, an unhit volume being all-zero, skewness/kurtosis present
  exactly when defined and kurtosis admissibility, plus (since 2026-11-12) the shared log10
  histogram checks on each volume's `histogram` (prefixed `histogram_`, reported as
  `<volume>:<check>`); globally, the same volume set in both blocks and
  the disjoint scored volumes summing to no more than `total_edep_mev`. Since 2026-11-12 it also
  grades `volume_event_track_length` and `volume_event_secondaries` per volume (presence,
  non-negative length, maxima within the event maxima, integer secondaries, the shared histogram
  checks prefixed `track_length_histogram_` / `secondaries_histogram_`, `secondaries_need_steps`,
  and the `species` split: present, summing to the total, integer-valued, within the volume)
  and globally their mean sums against `system_event_track_length_mean_mm` /
  `system_event_secondaries_mean` (and per species against `system_event_secondaries_<species>_mean`).
  Since 2026-11-14 it also grades the stepping-particle `species` splits of each volume's deposit
  and step length (`edep_species_*` / `track_length_species_*`: present, summing to the volume
  mean, non-negative, per-class max and zero fraction within the volume's) and
  `edep_species_need_steps` (a class's deposit zero fraction ≥ its step-length zero fraction);
  `measured.scored_deposit_mev_per_event_by_class` reports the scored deposit per class. Synthetic tests live in the
  same `tests/test_system_observable_cases.py`.
- **Flow-preset authoring audit:** [`scripts/audit_flow_presets.py`](../../../scripts/audit_flow_presets.py)
  wraps each scenario in a temporary entry, runs `trech inspect` and reports `TRECH_FLOW.check`
  issues (`--all`, `--presets`, `--json`); [`tests/test_flow_preset_audit.py`](../../../tests/test_flow_preset_audit.py)
  covers a clean scenario and seeded defects. PubChem-backed scenarios need `TRECH_PUBCHEM_CACHE_DIR`.
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
