// Expected output contract; numerical family tolerances remain in the referenced validators.
TRECH_VALIDATIONS["nacl_dehydration_reference"] = {
  "schema": "trech_scenario_validation_v1",
  "scenario": "nacl_dehydration_reference",
  "scope": "Validation fixture, not a validated crystallization prediction or metal temper model.",
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
  "physics_status": "reference_only",
  "limitations": "Inventory diagnostic and optional measured-interface replay only; no calibrated interface sequence bundled. Calibrated kinetics, transport, particle-derived phase lift and metal heat-treatment response remain unavailable.",
  "reference": "tools/validation/trech_validation/cases.py"
};
