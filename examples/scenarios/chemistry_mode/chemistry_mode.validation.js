// Expected output contract; numerical family tolerances remain in the referenced validators.
TRECH_VALIDATIONS["chemistry_mode"] = {
  "schema": "trech_scenario_validation_v1",
  "scenario": "chemistry_mode",
  "scope": "Initial Chemistry workspace: authored molecular graph + live isotope-resolved Geant4 material response + bounded learned response. No imposed stability law.",
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
  "physics_status": "operator_native",
  "limitations": "",
  "reference": "tools/validation/trech_validation/cases.py"
};
