// Expected output contract; numerical family tolerances remain in the referenced validators.
TRECH_VALIDATIONS["h2o_cluster_fluid"] = {
  "schema": "trech_scenario_validation_v1",
  "scenario": "h2o_cluster_fluid",
  "scope": "Sputnik item: \"Simulate H2O fluid behavior\". Next step after the single stable molecule (h2o_molecule_stability.js): a small ENSEMBLE of water molecules that attract each other and settle into a stable, liquid-like hydrogen-bonded droplet at ~300 K -- emergent fluid behavior from molecular interactions, not one isolated molecule.",
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
  "limitations": "flexible-water bond, angle and intermolecular force laws",
  "reference": "tools/validation/trech_validation/cases.py"
};

globalThis.TRECH_CHECKS = globalThis.TRECH_CHECKS || {};
TRECH_CHECKS["h2o_cluster_fluid"] = Object.assign(TRECH_CHECKS["h2o_cluster_fluid"] || {}, {
"checks0": function(collapsed, evaporated, hbondsPresent, tempControlled) { return {
          stable_cluster: !evaporated && !collapsed,
          temperature_controlled: tempControlled,
          hydrogen_bonding_present: hbondsPresent,
          fluid_stable: !evaporated && !collapsed && tempControlled && hbondsPresent
        }; }
});
