// Expected output contract; numerical family tolerances remain in the referenced validators.
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
