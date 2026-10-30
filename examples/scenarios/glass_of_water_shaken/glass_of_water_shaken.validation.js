// Expected output contract; numerical family tolerances remain in the referenced validators.
TRECH_VALIDATIONS["glass_of_water_shaken"] = {
  "schema": "trech_scenario_validation_v1",
  "scenario": "glass_of_water_shaken",
  "scope": "Sputnik / multi-scale-cascade CANONICAL demo: a GLASS OF WATER BEING SHAKEN.",
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
  "physics_status": "operator_partial",
  "limitations": "PBF neighbour pressure, viscosity and cohesion response",
  "reference": "tools/validation/trech_validation/cases.py"
};

globalThis.TRECH_CHECKS = globalThis.TRECH_CHECKS || {};
TRECH_CHECKS["glass_of_water_shaken"] = Object.assign(TRECH_CHECKS["glass_of_water_shaken"] || {}, {
"checks0": function(cascadeReachedMacro, contained, pouredOk, splashPresent, stable, wavesPresent) { return {
          water_poured_in: pouredOk,
          waves_present: wavesPresent,
          splash_present: splashPresent,
          water_contained: contained,
          stable_no_explosion: stable,
          cascade_drove_macro: cascadeReachedMacro,
          glass_of_water_from_nano:
            pouredOk && wavesPresent && splashPresent && contained && stable && cascadeReachedMacro
        }; }
});
