// Expected output contract; numerical family tolerances remain in the referenced validators.
TRECH_VALIDATIONS["water_salt_recipe"] = {
  "schema": "trech_scenario_validation_v1",
  "scenario": "water_salt_recipe",
  "scope": "water_salt_recipe: configured gamma transport in G4_WATER. Check completed output and the declared physics/inference scope.",
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
  "physics_status": "no_active_material_law",
  "limitations": "",
  "reference": "tools/validation/trech_validation/cases.py"
};
