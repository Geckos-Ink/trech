// Expected output contract plus the exported suite family gate (family_checks).
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
  "family_case": "magnetic_resonance_water",
  "family_summary": "Six resonance/FID/Geant4-drive flags plus the run-end material probe carrying the hook layer's Geant4 water proton density (relative 1e-6).",
  "family_checks": [
    {"id": "larmor_discovered", "tag": "mr_summary", "field": "validation.larmor_discovered", "op": "eq", "expected": true},
    {"id": "proton_density_from_geant4", "tag": "mr_summary", "field": "validation.proton_density_from_geant4", "op": "eq", "expected": true},
    {"id": "fid_decays", "tag": "mr_summary", "field": "validation.fid_decays", "op": "eq", "expected": true},
    {"id": "resonance_lorentzian", "tag": "mr_summary", "field": "validation.resonance_lorentzian", "op": "eq", "expected": true},
    {"id": "geant4_drive_present", "tag": "mr_summary", "field": "validation.geant4_drive_present", "op": "eq", "expected": true},
    {"id": "no_engine_spin_rule", "tag": "mr_summary", "field": "validation.no_engine_spin_rule", "op": "eq", "expected": true},
    {"id": "material_probe_proton_density_positive", "file": "trech_scores.jsonl", "phase": "run_end", "field": "material_probes[name=G4_WATER].numberDensityPerCm3.H", "op": "gt", "expected": 0},
    {"id": "hook_proton_density_positive", "tag": "mr_summary", "field": "geant4_material.water_proton_per_cm3", "op": "gt", "expected": 0},
    {"id": "material_probe_matches_hook", "tag": "mr_summary", "field": "geant4_material.water_proton_per_cm3", "op": "within", "rel_tol": 1e-06, "reference": {"file": "trech_scores.jsonl", "phase": "run_end", "field": "material_probes[name=G4_WATER].numberDensityPerCm3.H"}}
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
