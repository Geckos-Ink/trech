// Expected output contract; numerical family tolerances remain in the referenced validators.
TRECH_VALIDATIONS["cnt_band_structure"] = {
  "schema": "trech_scenario_validation_v1",
  "scenario": "cnt_band_structure",
  "scope": "Vostok milestone (CNT parallel track): carbon-nanotube ELECTRONIC STRUCTURE.",
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
  "limitations": "chirality-to-band-structure forward law",
  "reference": "tools/validation/trech_validation/cases.py"
};

globalThis.TRECH_CHECKS = globalThis.TRECH_CHECKS || {};
TRECH_CHECKS["cnt_band_structure"] = Object.assign(TRECH_CHECKS["cnt_band_structure"] || {}, {
"checks0": function(anchorsOk, armchairProtected, curvatureLawOk, gapLawOk, metalRuleOk, nonArmchairSmallGaps) { return {
        metallicity_rule_holds: metalRuleOk,
        gap_inverse_diameter_law_holds: gapLawOk,
        curvature_secondary_gap_law_holds: curvatureLawOk,
        armchair_curvature_gap_zero: armchairProtected,
        quasi_metallic_small_gaps: nonArmchairSmallGaps,
        measured_anchors_within_15pct: anchorsOk,
        cnt_band_structure_ok: metalRuleOk && gapLawOk && curvatureLawOk && anchorsOk
      }; }
});
