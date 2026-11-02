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

## Test ownership map

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
