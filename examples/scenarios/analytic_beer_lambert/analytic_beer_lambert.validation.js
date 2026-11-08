// Expected output contract plus the exported suite family gate (family_checks).
TRECH_VALIDATIONS["analytic_beer_lambert"] = {
  "schema": "trech_scenario_validation_v1",
  "scenario": "analytic_beer_lambert",
  "scope": "Analytic cross-check scenario: Beer-Lambert photon attenuation.",
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
  "family_case": "analytic_beer_lambert_cross_check",
  "family_summary": "Every Beer-Lambert analytic check is available and within the scenario tolerance; worst relative error at most 5%.",
  "family_checks": [
    {"id": "checks_present", "phase": "run_end", "field": "analytic_checks[*]", "aggregate": "count", "op": "ge", "expected": 1},
    {"id": "all_available", "phase": "run_end", "field": "analytic_checks[*].available", "aggregate": "all", "op": "eq", "expected": true},
    {"id": "all_within_tolerance", "phase": "run_end", "field": "analytic_checks[*].within_tolerance", "aggregate": "all", "op": "eq", "expected": true},
    {"id": "worst_relative_error", "phase": "run_end", "field": "analytic_checks[*].relative_error", "aggregate": "max", "op": "le", "expected": 0.05}
  ],
  "physics_status": "configuration_or_transport",
  "limitations": "",
  "reference": "tools/validation/trech_validation/cases.py"
};
