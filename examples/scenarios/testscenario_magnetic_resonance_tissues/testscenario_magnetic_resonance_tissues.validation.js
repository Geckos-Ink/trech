// Expected output contract plus the exported suite family gate (family_checks).
TRECH_VALIDATIONS["testscenario_magnetic_resonance_tissues"] = {
  "schema": "trech_scenario_validation_v1",
  "scenario": "testscenario_magnetic_resonance_tissues",
  "scope": "Validation scenario (Stage 2): virtual-tissue magnetic-resonance contrast.",
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
  "family_case": "magnetic_resonance_tissue_contrast",
  "family_summary": "Driver-recorded tissue contrast: every tissue detected (real receiver edep), emission follows the Geant4 proton prediction, signal-vs-proton Pearson r >= 0.7, distinct responses, no engine spin rule.",
  "family_checks": [
    {"id": "real_detection_all_tissues", "tag": "mr_tissue_contrast", "field": "validation.real_detection_all_tissues", "op": "eq", "expected": true},
    {"id": "emission_from_geant4_proton", "tag": "mr_tissue_contrast", "field": "validation.emission_from_geant4_proton", "op": "eq", "expected": true},
    {"id": "signal_tracks_proton_density", "tag": "mr_tissue_contrast", "field": "validation.signal_tracks_proton_density", "op": "eq", "expected": true},
    {"id": "distinct_tissue_responses", "tag": "mr_tissue_contrast", "field": "validation.distinct_tissue_responses", "op": "eq", "expected": true},
    {"id": "no_engine_spin_rule", "tag": "mr_tissue_contrast", "field": "validation.no_engine_spin_rule", "op": "eq", "expected": true},
    {"id": "tissues_recorded", "tag": "mr_tissue_contrast", "field": "tissues[*]", "aggregate": "count", "op": "ge", "expected": 2},
    {"id": "min_detected_signal", "tag": "mr_tissue_contrast", "field": "tissues[*].detected_signal_mev", "aggregate": "min", "op": "gt", "expected": 0},
    {"id": "signal_proton_correlation", "tag": "mr_tissue_contrast", "field": "corr_signal_vs_proton_density", "op": "ge", "expected": 0.7}
  ],
  "physics_status": "reference_only",
  "limitations": "shared tissue magnetic-resonance forward dynamics",
  "reference": "tools/validation/trech_validation/cases.py"
};
