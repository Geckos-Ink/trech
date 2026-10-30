// Expected output contract; numerical family tolerances remain in the referenced validators.
TRECH_VALIDATIONS["testscenario_magnetic_resonance_brain"] = {
  "schema": "trech_scenario_validation_v1",
  "scenario": "testscenario_magnetic_resonance_brain",
  "scope": "Validation scenario (Stage 4): virtual-brain MRI proton densities.",
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
  "limitations": "shared voxel/isochromat magnetic-resonance forward dynamics",
  "reference": "tools/validation/trech_validation/cases.py"
};
