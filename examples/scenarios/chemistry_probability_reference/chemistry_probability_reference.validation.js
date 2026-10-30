// Expected output contract; numerical family tolerances remain in the referenced validators.
TRECH_VALIDATIONS["chemistry_probability_reference"] = {
  "schema": "trech_scenario_validation_v1",
  "scenario": "chemistry_probability_reference",
  "scope": "Joint electronic comparison and Geant4 nuclear initial-state ensembles. The approach is a declared parameter scan, not inferred dynamics.",
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
