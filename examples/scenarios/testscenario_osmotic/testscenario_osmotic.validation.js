// Expected output contract; numerical family tolerances remain in the referenced validators.
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
