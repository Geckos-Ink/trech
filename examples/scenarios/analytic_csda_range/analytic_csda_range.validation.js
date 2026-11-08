// Expected output contract plus the exported suite family gate (family_checks).
TRECH_VALIDATIONS["analytic_csda_range"] = {
  "schema": "trech_scenario_validation_v1",
  "scenario": "analytic_csda_range",
  "scope": "Analytic cross-check scenario: charged-particle CSDA range.",
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
  "family_case": "analytic_csda_range_cross_check",
  "family_summary": "The CSDA-range check is available and within tolerance (worst relative error at most 5%) and every primary stops inside the block.",
  "family_checks": [
    {"id": "checks_present", "phase": "run_end", "field": "analytic_checks[?type=csda_range]", "aggregate": "count", "op": "ge", "expected": 1},
    {"id": "all_available", "phase": "run_end", "field": "analytic_checks[?type=csda_range].available", "aggregate": "all", "op": "eq", "expected": true},
    {"id": "all_within_tolerance", "phase": "run_end", "field": "analytic_checks[?type=csda_range].within_tolerance", "aggregate": "all", "op": "eq", "expected": true},
    {"id": "worst_relative_error", "phase": "run_end", "field": "analytic_checks[?type=csda_range].relative_error", "aggregate": "max", "op": "le", "expected": 0.05},
    {"id": "primaries_contained", "phase": "run_end", "field": "analytic_checks[?type=csda_range].primaries_transmitted", "aggregate": "max", "op": "eq", "expected": 0}
  ],
  "physics_status": "configuration_or_transport",
  "limitations": "",
  "reference": "tools/validation/trech_validation/cases.py"
};
