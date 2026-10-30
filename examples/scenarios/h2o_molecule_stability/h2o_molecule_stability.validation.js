// Expected output contract; numerical family tolerances remain in the referenced validators.
TRECH_VALIDATIONS["h2o_molecule_stability"] = {
  "schema": "trech_scenario_validation_v1",
  "scenario": "h2o_molecule_stability",
  "scope": "Sputnik north-star item: simulate a single H2O molecule and show that its bonds are STABLE OVER TIME -- it oscillates around its equilibrium geometry without \"exploding\" (atoms flying apart).",
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
  "limitations": "flexible-water bond and angle force laws",
  "reference": "tools/validation/trech_validation/cases.py"
};

globalThis.TRECH_CHECKS = globalThis.TRECH_CHECKS || {};
TRECH_CHECKS["h2o_molecule_stability"] = Object.assign(TRECH_CHECKS["h2o_molecule_stability"] || {}, {
"checks0": function(bondsStable, energyConserved, exploded) { return {
          stable_without_exploding: bondsStable && energyConserved,
          bonds_stable: bondsStable,
          energy_conserved: energyConserved,
          exploded: exploded
        }; }
});
