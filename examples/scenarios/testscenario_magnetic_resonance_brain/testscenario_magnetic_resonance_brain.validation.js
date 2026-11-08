// Expected output contract plus the exported suite family gate (family_checks).
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
  "family_case": "magnetic_resonance_brain_image",
  "family_summary": "Driver-recorded brain image: the seven validation flags plus explicit intensity/proton r >= 0.95, reconstruction r >= 0.9, grey above white, skull below half of grey and air below 0.12.",
  "family_checks": [
    {"id": "intensity_tracks_proton_density", "tag": "mr_brain_image", "field": "validation.intensity_tracks_proton_density", "op": "eq", "expected": true},
    {"id": "csf_brightest_soft_tissue", "tag": "mr_brain_image", "field": "validation.csf_brightest_soft_tissue", "op": "eq", "expected": true},
    {"id": "grey_brighter_than_white", "tag": "mr_brain_image", "field": "validation.grey_brighter_than_white", "op": "eq", "expected": true},
    {"id": "skull_dark", "tag": "mr_brain_image", "field": "validation.skull_dark", "op": "eq", "expected": true},
    {"id": "background_black", "tag": "mr_brain_image", "field": "validation.background_black", "op": "eq", "expected": true},
    {"id": "reconstruction_faithful", "tag": "mr_brain_image", "field": "validation.reconstruction_faithful", "op": "eq", "expected": true},
    {"id": "no_engine_spin_rule", "tag": "mr_brain_image", "field": "validation.no_engine_spin_rule", "op": "eq", "expected": true},
    {"id": "intensity_proton_correlation", "tag": "mr_brain_image", "field": "corr_intensity_proton", "op": "ge", "expected": 0.95},
    {"id": "reconstruction_correlation", "tag": "mr_brain_image", "field": "recon_phantom_corr", "op": "ge", "expected": 0.9},
    {"id": "grey_above_white", "tag": "mr_brain_image", "field": "tissues.grey.mean_intensity", "op": "gt", "reference": {"tag": "mr_brain_image", "field": "tissues.white.mean_intensity"}},
    {"id": "skull_below_half_grey", "tag": "mr_brain_image", "field": "tissues.skull.mean_intensity", "op": "lt", "reference": {"tag": "mr_brain_image", "field": "tissues.grey.mean_intensity"}, "scale": 0.5},
    {"id": "air_background", "tag": "mr_brain_image", "field": "tissues.air.mean_intensity", "op": "lt", "expected": 0.12}
  ],
  "physics_status": "reference_only",
  "limitations": "shared voxel/isochromat magnetic-resonance forward dynamics",
  "reference": "tools/validation/trech_validation/cases.py"
};
