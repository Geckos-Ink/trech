// Expected output contract; numerical family tolerances remain in the referenced validators.
TRECH_VALIDATIONS["testscenario_pascal"] = {
  "schema": "trech_scenario_validation_v1",
  "scenario": "testscenario_pascal",
  "scope": "Validation scenario: Pascal's Principle & Material Deformation. See docs/testscenario_pascal-todo.md.",
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
  "limitations": "3D particle bath and tensioned sensor-wall patch constitutive response",
  "reference": "tools/validation/trech_validation/cases.py"
};

globalThis.TRECH_CHECKS = globalThis.TRECH_CHECKS || {};
TRECH_CHECKS["testscenario_pascal"] = Object.assign(TRECH_CHECKS["testscenario_pascal"] || {}, {
"checks0": function(results) { return {
        pascal_principle_holds: results[0].verdict === "pass",
        plastic_damping_observed: results[1].verdict === "pass",
        macro_mesh_consistent: results[2].verdict === "pass",
        rigid_wall_displacement: Math.abs(results[0].mean_wall_displacement),
        deformable_wall_displacement: results[1].mean_wall_displacement,
        macro_mesh_wall_displacement: results[2].mean_wall_displacement
      }; }
});
