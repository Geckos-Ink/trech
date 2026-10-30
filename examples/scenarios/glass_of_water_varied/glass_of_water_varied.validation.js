// Expected output contract; numerical family tolerances remain in the referenced validators.
TRECH_VALIDATIONS["glass_of_water_varied"] = {
  "schema": "trech_scenario_validation_v1",
  "scenario": "glass_of_water_varied",
  "scope": "Anti-degeneration demo scenario: the same glass-of-water optics as validation_glass_of_water.js, but with a *varied* source so the run samples a real distribution of photons instead of one repeated primary.",
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
