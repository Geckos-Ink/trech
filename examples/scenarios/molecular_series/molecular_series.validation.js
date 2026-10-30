// Expected output contract; numerical family tolerances remain in the referenced validators.
TRECH_VALIDATIONS["molecular_series"] = {
  "schema": "trech_scenario_validation_v1",
  "scenario": "molecular_series",
  "scope": "First bounded electronic/torsional prediction group. See docs/molecular_series.md. Geant4 supplies live elemental identity + neutral-electron bookkeeping and actual particle transport. QM-trained surfaces supply charges/energies. Coordinates are imposed rigid scan samples, NOT predicted molecular dynamics.",
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
