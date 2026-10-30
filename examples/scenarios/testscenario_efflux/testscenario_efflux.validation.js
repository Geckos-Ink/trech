// Expected output contract; numerical family tolerances remain in the referenced validators.
TRECH_VALIDATIONS["testscenario_efflux"] = {
  "schema": "trech_scenario_validation_v1",
  "scenario": "testscenario_efflux",
  "scope": "Validation scenario: passive membrane efflux (clearance of a lipophilic \"waste\" molecule from a cell), cross-checked against the classical first-order / Fick's-law clearance kinetics.",
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
  "physics_status": "operator_backed",
  "limitations": "",
  "reference": "tools/validation/trech_validation/cases.py"
};

globalThis.TRECH_CHECKS = globalThis.TRECH_CHECKS || {};
TRECH_CHECKS["testscenario_efflux"] = Object.assign(TRECH_CHECKS["testscenario_efflux"] || {}, {
"checks0": function(essentialsRetained, firstOrderKinetics, geant4EventDrivePresent, geant4ParamPresent, lipophilicitySelectivity, physicsSource, wasteCleared) { return {
        first_order_kinetics: firstOrderKinetics,
        waste_cleared: wasteCleared,
        essentials_retained: essentialsRetained,
        geant4_param_present: geant4ParamPresent,
        geant4_event_drive_present: geant4EventDrivePresent,
        lipophilicity_selectivity: lipophilicitySelectivity,
        normal_path_has_no_js_transport_or_crossing_law:
          physicsSource === "operator"
      }; }
});
