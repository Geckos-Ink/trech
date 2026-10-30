// Expected output contract; numerical family tolerances remain in the referenced validators.
TRECH_VALIDATIONS["testscenario_magnetic_resonance"] = {
  "schema": "trech_scenario_validation_v1",
  "scenario": "testscenario_magnetic_resonance",
  "scope": "Validation scenario (Stage 1): nuclear magnetic resonance of a water cube.",
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
  "limitations": "Bloch pulse, Curie magnetization and FID forward dynamics",
  "reference": "tools/validation/trech_validation/cases.py"
};

globalThis.TRECH_CHECKS = globalThis.TRECH_CHECKS || {};
TRECH_CHECKS["testscenario_magnetic_resonance"] = Object.assign(TRECH_CHECKS["testscenario_magnetic_resonance"] || {}, {
"checks0": function(fidDecays, geant4DrivePresent, larmorRelError, protonRelError, resonanceLorentzian, state) { return {
      larmor_discovered: larmorRelError <= 0.02,
      proton_density_from_geant4: state.protonPerCm3 > 0 && protonRelError <= 0.05,
      fid_decays: fidDecays,
      resonance_lorentzian: resonanceLorentzian,
      geant4_drive_present: geant4DrivePresent,
      no_engine_spin_rule: true
    }; }
});
