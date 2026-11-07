// Expected output contract; numerical family tolerances remain in the referenced validators.
TRECH_VALIDATIONS["analytic_pair_production"] = {
  "schema": "trech_scenario_validation_v1",
  "scenario": "analytic_pair_production",
  "scope": "Analytic cross-check scenario: pair-production and photonuclear branching fractions, the 2 m_e c^2 threshold and the oxygen giant-dipole resonance.",
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
  "limitations": "Self-consistency of Geant4 process selection against its own conversion and photonuclear cross sections (photonuclear absorption is part of mu_total); not an independent XCOM/IAEA comparison.",
  "reference": "tools/validation/trech_validation/cases.py"
};
