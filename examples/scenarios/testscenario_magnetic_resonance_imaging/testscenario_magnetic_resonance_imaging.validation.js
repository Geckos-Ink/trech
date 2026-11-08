// Expected output contract plus the exported suite family gate (family_checks).
TRECH_VALIDATIONS["testscenario_magnetic_resonance_imaging"] = {
  "schema": "trech_scenario_validation_v1",
  "scenario": "testscenario_magnetic_resonance_imaging",
  "scope": "Validation scenario (Stage 3): 1D magnetic-resonance IMAGING via frequency encoding -- turning the tissue contrast into an actual image line.",
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
  "family_case": "magnetic_resonance_image_line",
  "family_summary": "Six localisation, proton-density amplitude, dark-voxel and Geant4-transport flags.",
  "family_checks": [
    {"id": "position_recovered", "tag": "mr_image_line", "field": "validation.position_recovered", "op": "eq", "expected": true},
    {"id": "amplitude_tracks_proton_density", "tag": "mr_image_line", "field": "validation.amplitude_tracks_proton_density", "op": "eq", "expected": true},
    {"id": "air_gap_is_dark", "tag": "mr_image_line", "field": "validation.air_gap_is_dark", "op": "eq", "expected": true},
    {"id": "cortical_bone_is_dark", "tag": "mr_image_line", "field": "validation.cortical_bone_is_dark", "op": "eq", "expected": true},
    {"id": "geant4_transport_present", "tag": "mr_image_line", "field": "validation.geant4_transport_present", "op": "eq", "expected": true},
    {"id": "no_engine_spin_rule", "tag": "mr_image_line", "field": "validation.no_engine_spin_rule", "op": "eq", "expected": true}
  ],
  "physics_status": "reference_only",
  "limitations": "voxel excitation and synthesized readout forward dynamics",
  "reference": "tools/validation/trech_validation/cases.py"
};

globalThis.TRECH_CHECKS = globalThis.TRECH_CHECKS || {};
TRECH_CHECKS["testscenario_magnetic_resonance_imaging"] = Object.assign(TRECH_CHECKS["testscenario_magnetic_resonance_imaging"] || {}, {
"checks0": function(airDark, amplitudeTracksProton, boneDark, geant4Present, positionRecovered) { return {
        position_recovered: positionRecovered,
        amplitude_tracks_proton_density: amplitudeTracksProton,
        air_gap_is_dark: !!airDark,
        cortical_bone_is_dark: !!boneDark,
        geant4_transport_present: geant4Present,
        no_engine_spin_rule: true
      }; }
});
