// Expected output contract; numerical family tolerances remain in the referenced validators.
TRECH_VALIDATIONS["cascade_multiscale_demo"] = {
  "schema": "trech_scenario_validation_v1",
  "scenario": "cascade_multiscale_demo",
  "scope": "Multi-scale inference cascade demo: ctx.cascade chains scale-tagged models from the Geant4 particle/nano base up to an observer-scale number in ONE deterministic pass, WITHOUT the scenario hand-wiring \"call A, feed B\".",
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
