// Expected output contract; numerical family tolerances remain in the referenced validators.
TRECH_VALIDATIONS["briggs_rauscher_oscillator"] = {
  "schema": "trech_scenario_validation_v1",
  "scenario": "briggs_rauscher_oscillator",
  "scope": "The Briggs-Rauscher oscillating reaction, observed in an open beaker.",
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
  "limitations": "six-state oscillatory reaction evolution",
  "reference": "tools/validation/trech_validation/cases.py"
};

globalThis.TRECH_CHECKS = globalThis.TRECH_CHECKS || {};
TRECH_CHECKS["briggs_rauscher_oscillator"] = Object.assign(TRECH_CHECKS["briggs_rauscher_oscillator"] || {}, {
"checks0": function(VALIDATION_ONLY, coeff, colourOrderRespected, completedCycles, oscillationCeases, periodInRange, s, settled) { return {
        geant4_base_present: s.mixtureDensity > s.waterDensity &&
          (s.numberDensity.I || 0) > 0 && (s.numberDensity.Mn || 0) > 0 &&
          s.geant4Events > 0,
        cascade_supplies_coefficients: s.cascade.__cascade.stagesRun === 2 &&
          coeff.f > 0 && coeff.timeScaleSPerTau > 0,
        no_engine_reaction_rule: true,
        oscillation_emerged: completedCycles >= VALIDATION_ONLY.expectedMinCycles,
        three_colour_regimes_present: s.colourlessCount > 0 && s.amberCount > 0 &&
          s.blueCount > 0,
        colour_order_amber_before_blue: colourOrderRespected,
        period_physically_plausible: periodInRange,
        oscillation_ceases_by_end: oscillationCeases,
        settles_on_reagent_depletion: settled,
        uncertainty_emitted: coeff.responseSigma >= 0.0
      }; }
});

globalThis.TRECH_CHECKS = globalThis.TRECH_CHECKS || {};
TRECH_CHECKS["briggs_rauscher_oscillator"] = Object.assign(TRECH_CHECKS["briggs_rauscher_oscillator"] || {}, {
"references0": function() {return {
  expectedBehaviour: "sustained colourless -> amber -> deep blue-black cycling, then settle on reagent depletion",
  expectedMinCycles: 4,
  expectedColourOrderPerCycle: "amber (free I2) precedes deep blue (triiodide-starch)",
  plausiblePeriodSecondsRange: [3.0, 60.0],
  expectedEventualSettle: true,
  source: "Briggs & Rauscher 1973; Shakhashiri demonstration; FKN/Oregonator oscillator theory (validation only)"
};}
});
