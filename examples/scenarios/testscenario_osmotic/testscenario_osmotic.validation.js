// Expected output contract plus the exported suite family gate (family_checks).
TRECH_VALIDATIONS["testscenario_osmotic"] = {
  "schema": "trech_scenario_validation_v1",
  "scenario": "testscenario_osmotic",
  "scope": "Validation scenario: Osmotic Dehydration via Dimensional & Polarity Exclusion. See docs/testscenario_osmotic-todo.md.",
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
  "family_case": "osmotic_shift_observed",
  "family_summary": "All nine selective-membrane, flux, thermostat, pressure and crenation flags.",
  "family_checks": [
    {"id": "dimensional_exclusion_holds", "tag": "final_summary", "field": "validation.dimensional_exclusion_holds", "op": "eq", "expected": true},
    {"id": "polarity_exclusion_holds", "tag": "final_summary", "field": "validation.polarity_exclusion_holds", "op": "eq", "expected": true},
    {"id": "osmotic_shift_observed", "tag": "final_summary", "field": "validation.osmotic_shift_observed", "op": "eq", "expected": true},
    {"id": "early_crossovers_observed", "tag": "final_summary", "field": "validation.early_crossovers_observed", "op": "eq", "expected": true},
    {"id": "macroscopic_flux_observed", "tag": "final_summary", "field": "validation.macroscopic_flux_observed", "op": "eq", "expected": true},
    {"id": "thermal_energy_bounded", "tag": "final_summary", "field": "validation.thermal_energy_bounded", "op": "eq", "expected": true},
    {"id": "pressure_response_observed", "tag": "final_summary", "field": "validation.pressure_response_observed", "op": "eq", "expected": true},
    {"id": "membrane_crenation_observed", "tag": "final_summary", "field": "validation.membrane_crenation_observed", "op": "eq", "expected": true},
    {"id": "membrane_stable", "tag": "final_summary", "field": "validation.membrane_stable", "op": "eq", "expected": true}
  ],
  "physics_status": "reference_only",
  "limitations": "3D particle transport/crossing and pressure-driven area-conserving membrane response",
  "reference": "tools/validation/trech_validation/cases.py"
};

globalThis.TRECH_CHECKS = globalThis.TRECH_CHECKS || {};
TRECH_CHECKS["testscenario_osmotic"] = Object.assign(TRECH_CHECKS["testscenario_osmotic"] || {}, {
"checks0": function(dimensionalExclusionHolds, earlyCrossoversObserved, macroscopicFluxObserved, membraneCrenationObserved, membraneStable, osmoticShiftObserved, polarityExclusionHolds, pressureResponseObserved, thermalEnergyBounded) { return {
        dimensional_exclusion_holds: dimensionalExclusionHolds,
        polarity_exclusion_holds: polarityExclusionHolds,
        osmotic_shift_observed: osmoticShiftObserved,
        early_crossovers_observed: earlyCrossoversObserved,
        macroscopic_flux_observed: macroscopicFluxObserved,
        thermal_energy_bounded: thermalEnergyBounded,
        pressure_response_observed: pressureResponseObserved,
        membrane_crenation_observed: membraneCrenationObserved,
        membrane_stable: membraneStable
      }; }
});
