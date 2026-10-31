// Expected output contract; numerical family tolerances remain in the referenced validators.
TRECH_VALIDATIONS["aerodynamics_reference"] = {
  "schema": "trech_scenario_validation_v1",
  "scenario": "aerodynamics_reference",
  "scope": "Independent Euler comparison for a fixed blunt body; not a Geant4 aero prediction.",
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
  "limitations": "Independent 3D ideal-gas Euler comparison only. Exact periodic entropy/shear grid/CFL verification exists; obstacle/shock/acoustic accuracy, external anchors with uncertainty, particle-derived aerodynamic scale lift, thermal coupling and structural failure remain unavailable.",
  "reference": "tools/validation/trech_validation/cases.py"
};
