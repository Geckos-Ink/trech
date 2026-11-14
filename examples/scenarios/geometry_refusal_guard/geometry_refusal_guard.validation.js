// Expected output contract; numerical family tolerances remain in the referenced validators.
TRECH_VALIDATIONS["geometry_refusal_guard"] = {
  "schema": "trech_scenario_validation_v1",
  "scenario": "geometry_refusal_guard",
  "scope": "geometry_refusal_guard: 662 keV gamma transport through a clean two-volume geometry authored with geometry.refuseOn \"any\". The default run must pass the guard and complete; the injected-defect run (graded by geometry_refusal_guard_refuses_defects) must be refused before any event.",
  "checks": [
    {"file": "trech_scores.jsonl", "phase": "run_end", "field": "n_events", "op": "eq", "expected": 200},
    {"file": "trech_scores.jsonl", "phase": "run_end", "field": "hook_emit_dropped_count", "op": "eq", "expected": 0, "missing": 0},
    {"file": "trech_scores.jsonl", "phase": "run_end", "field": "volume_edep_mev.target", "op": "gt", "expected": 0},
    {"file": "trech_provenance.jsonl", "phase": "run_end", "field": "geometry_resolution.schema", "op": "eq", "expected": "none", "missing": "none"},
    {"file": "trech_provenance.jsonl", "phase": "run_end", "field": "geometry_overlap_check.clean", "op": "eq", "expected": true}
  ],
  "physics_status": "configuration_or_transport",
  "limitations": "Configuration/provenance guard over Geant4 transport, not a physics model. The overlap check samples solid surfaces, so a clean report is a bound, not a proof.",
  "reference": "tools/validation/trech_validation/cases.py"
};
