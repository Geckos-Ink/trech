// Expected output contract; numerical family tolerances remain in the referenced validators.
TRECH_VALIDATIONS["surrogate_generic_demo"] = {
  "schema": "trech_scenario_validation_v1",
  "scenario": "surrogate_generic_demo",
  "scope": "Generic Torch-surrogate demo: any scenario can attach a learned model and call it deterministically from a hook via ctx.predict.",
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
