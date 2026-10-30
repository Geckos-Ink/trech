// Expected output contract; numerical family tolerances remain in the referenced validators.
TRECH_VALIDATIONS["molecular_06_acetamide"] = {
  "schema": "trech_scenario_validation_v1",
  "scenario": "molecular_06_acetamide",
  "scope": "Group 6: substituted amide + shared particle-to-molecule inference.",
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
  "limitations": "",
  "reference": "tools/validation/trech_validation/cases.py"
};
