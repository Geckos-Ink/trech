// Expected output contract; numerical family tolerances remain in the referenced validators.
TRECH_VALIDATIONS["geometry_procedural_assembly"] = {
  "schema": "trech_scenario_validation_v1",
  "scenario": "geometry_procedural_assembly",
  "scope": "geometry_procedural_assembly: 1.25 MeV gamma transport through a TRECH_GEOMETRY-generated layer stack, dosimeter grid and NaI ring. Checks the generated volumes are built and scored without substitution and the onStep step-detail tally covers every event.",
  "checks": [
    {"file": "trech_scores.jsonl", "phase": "run_end", "field": "n_events", "op": "eq", "expected": 400},
    {"file": "trech_scores.jsonl", "phase": "run_end", "field": "hook_emit_dropped_count", "op": "eq", "expected": 0, "missing": 0},
    {"file": "trech_scores.jsonl", "phase": "run_end", "field": "volume_edep_mev.phantom", "op": "gt", "expected": 0},
    {"file": "trech_scores.jsonl", "phase": "run_end", "field": "volume_edep_mev.cell_1_1_0", "op": "gt", "expected": 0},
    {"file": "trech_scores.jsonl", "phase": "run_end", "field": "volume_edep_mev.window_pb", "op": "gt", "expected": 0},
    {"file": "trech_provenance.jsonl", "phase": "run_end", "field": "geometry_resolution.schema", "op": "eq", "expected": "none", "missing": "none"},
    {"tag": "procedural_assembly_summary", "field": "volumes", "op": "eq", "expected": 20},
    {"tag": "procedural_assembly_summary", "field": "auditOverlaps", "op": "eq", "expected": 0},
    {"tag": "procedural_assembly_summary", "field": "events", "op": "eq", "expected": 400},
    {"tag": "procedural_assembly_summary", "field": "firstInteraction.phantom", "op": "gt", "expected": 0},
    {"tag": "procedural_assembly_summary", "field": "firstInteraction.cell", "op": "gt", "expected": 0}
  ],
  "physics_status": "configuration_or_transport",
  "limitations": "Procedural authoring and Geant4 transport only; the first-interaction tally is bookkeeping of Geant4 steps, not a physics model. Rotated-volume overlap audit is conservative (axis-aligned bounds).",
  "reference": "tools/validation/trech_validation/declarative.py"
};
