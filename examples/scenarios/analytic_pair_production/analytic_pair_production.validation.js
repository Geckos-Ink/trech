// Expected output contract plus the exported suite family gate (family_checks).
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
  "family_case": "analytic_pair_fraction_cross_check",
  "family_summary": "At the default 10 MeV run the pair-fraction check is available and within tolerance, conversions were classified, binomial |z| < 4, and the beam is above 2 m_e c^2.",
  "family_checks": [
    {"id": "check_available", "phase": "run_end", "field": "analytic_checks[type=pair_fraction].available", "op": "eq", "expected": true},
    {"id": "within_tolerance", "phase": "run_end", "field": "analytic_checks[type=pair_fraction].within_tolerance", "op": "eq", "expected": true},
    {"id": "conversions_classified", "phase": "run_end", "field": "analytic_checks[type=pair_fraction].primaries_pair_first", "op": "gt", "expected": 0},
    {"id": "binomial_z", "phase": "run_end", "field": "analytic_checks[type=pair_fraction]", "derive": {"fn": "abs", "args": ["z_score"]}, "op": "lt", "expected": 4.0},
    {"id": "above_pair_threshold", "phase": "run_end", "field": "analytic_checks[type=pair_fraction].below_pair_threshold", "op": "eq", "expected": false, "missing": false}
  ],
  "physics_status": "configuration_or_transport",
  "limitations": "Self-consistency of Geant4 process selection against its own conversion and photonuclear cross sections (photonuclear absorption is part of mu_total); not an independent XCOM/IAEA comparison.",
  "reference": "tools/validation/trech_validation/cases.py"
};
