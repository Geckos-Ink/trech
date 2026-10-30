// Expected output contract; numerical family tolerances remain in the referenced validators.
TRECH_VALIDATIONS["config_flow_language"] = {
  "schema": "trech_scenario_validation_v1",
  "scenario": "config_flow_language",
  "scope": "config_flow_language: configured e- transport in G4_AIR. Check completed output and the declared physics/inference scope.",
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
