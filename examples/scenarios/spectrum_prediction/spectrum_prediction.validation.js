// Expected output contract; numerical spectrum checks live in scripts/validate_spectrum_prediction.py.
TRECH_VALIDATIONS["spectrum_prediction"] = {
  "schema": "trech_scenario_validation_v1",
  "scenario": "spectrum_prediction",
  "scope": "Learned atomic line-strength and molecular UV/Vis envelope predictions from measured PubChem/NIST spectra, evaluated by GenericSurrogate through ctx.cascade.",
  "checks": [
    {"file": "trech_scores.jsonl", "phase": "run_end", "field": "n_events", "op": "gt", "expected": 0},
    {"file": "trech_scores.jsonl", "phase": "run_end", "field": "hook_emit_dropped_count", "op": "eq", "expected": 0, "missing": 0}
  ],
  "physics_status": "no_active_material_law",
  "limitations": "Labels are measured spectra represented on fixed grids; models are learned comparisons with small held-out sets, not Geant4 results.",
  "reference": "scripts/validate_spectrum_prediction.py"
};
