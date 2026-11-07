// Expected output contract; numerical family tolerances remain in the referenced validators.
TRECH_VALIDATIONS["analytic_pair_production"] = {
  "schema": "trech_scenario_validation_v1",
  "scenario": "analytic_pair_production",
  "scope": "Analytic cross-check scenario: pair-production branching fraction and 2 m_e c^2 threshold.",
  "checks": [
    {
      "file": "trech_scores.jsonl",
      "phase": "run_end",
      "field": "n_events",
      "op": "gt",
      "expected": 0
    },
    {
      "file": "trech_scores.jsonl",
      "phase": "run_end",
      "field": "hook_emit_dropped_count",
      "op": "eq",
      "expected": 0,
      "missing": 0
    }
  ],
  "physics_status": "configuration_or_transport",
  "limitations": "Self-consistency of Geant4 process selection against its own conversion cross section; photonuclear absorption is excluded from mu_total, so probe energies stay below ~14 MeV.",
  "reference": "tools/validation/trech_validation/cases.py"
};
