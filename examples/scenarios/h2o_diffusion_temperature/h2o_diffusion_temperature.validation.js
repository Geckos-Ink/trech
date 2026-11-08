// Expected output contract plus the exported suite family gate (family_checks).
TRECH_VALIDATIONS["h2o_diffusion_temperature"] = {
  "schema": "trech_scenario_validation_v1",
  "scenario": "h2o_diffusion_temperature",
  "scope": "Sputnik \"H2O fluid behavior\" -- DYNAMICS, temperature dependence.",
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
  "family_case": "h2o_diffusion_temperature_trend",
  "family_summary": "Scenario D(T) trend verdict.",
  "family_checks": [
    {"id": "diffusion_temperature_trend_ok", "tag": "diffusion_vs_temperature", "field": "validation.diffusion_temperature_trend_ok", "op": "eq", "expected": true}
  ],
  "physics_status": "reference_only",
  "limitations": "shared SPC/E pair-force evolution",
  "reference": "tools/validation/trech_validation/cases.py"
};

globalThis.TRECH_CHECKS = globalThis.TRECH_CHECKS || {};
TRECH_CHECKS["h2o_diffusion_temperature"] = Object.assign(TRECH_CHECKS["h2o_diffusion_temperature"] || {}, {
"checks0": function(allPhysical, monotonic, sim, trendMatches) { return {
          monotonic_increase: monotonic,
          all_diffusion_physical: allPhysical,
          trend_matches_experiment: trendMatches,
          rigid_constraints_held: sim.maxConstraintViol < 1e-6,
          diffusion_temperature_trend_ok: monotonic && allPhysical && trendMatches
        }; }
});
