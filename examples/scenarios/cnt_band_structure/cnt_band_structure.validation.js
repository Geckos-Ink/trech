// Expected output contract plus the exported suite family gate (family_checks).
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
  "family_case": "cnt_band_structure",
  "family_summary": "Scenario band-structure verdict (metallicity rule and gap scaling).",
  "family_checks": [
    {"id": "cnt_band_structure_ok", "tag": "cnt_panel", "field": "validation.cnt_band_structure_ok", "op": "eq", "expected": true},
    {"id": "tb_full_metallicity_consistent", "tag": "cnt_panel", "field": "tubes[*].tb_metallicity_consistent",
     "aggregate": "all", "op": "eq", "expected": true},
    {"id": "tb_full_matches_leading_order", "tag": "cnt_panel", "field": "tubes[?metallic=False].tb_full_rel_dev_from_leading",
     "aggregate": "max_abs", "op": "lt", "expected": 0.04},
    {"id": "warping_family1_above_two", "tag": "cnt_panel", "field": "tubes[?kataura_branch=family1].tb_e22_over_e11",
     "aggregate": "min", "op": "gt", "expected": 2.0},
    {"id": "warping_family2_below_two", "tag": "cnt_panel", "field": "tubes[?kataura_branch=family2].tb_e22_over_e11",
     "aggregate": "max", "op": "lt", "expected": 2.0},
    {"id": "warping_split_shrinks_with_diameter", "tag": "cnt_panel",
     "field": "validation.trigonal_warping_split_shrinks_with_diameter", "op": "eq", "expected": true},
    {"id": "kataura_tb_family_ordering", "tag": "cnt_panel", "field": "kataura_tb_family_ratio_margin", "op": "gt", "expected": 0},
    {"id": "kataura_measured_family_ordering", "tag": "cnt_panel", "field": "kataura_measured_family_ratio_margin", "op": "gt", "expected": 0}
  ],
  "physics_status": "reference_only",
  "limitations": "chirality-to-band-structure forward law; single-particle nearest-neighbour tight binding (no excitons, no curvature-modified hopping)",
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

Object.assign(TRECH_CHECKS["cnt_band_structure"], {
"checks1": function(katauraOrderingOk, maxTbLeadingDev, tbMetallicityOk, warpingShrinkOk, warpingSignOk) { return {
        tb_full_metallicity_consistent: tbMetallicityOk,
        tb_full_matches_leading_order_within_4pct: maxTbLeadingDev < 0.04,
        trigonal_warping_family_split: warpingSignOk,
        trigonal_warping_split_shrinks_with_diameter: warpingShrinkOk,
        kataura_family_ordering_matches_measured: katauraOrderingOk,
        cnt_trigonal_warping_ok: tbMetallicityOk && maxTbLeadingDev < 0.04 && warpingSignOk && warpingShrinkOk && katauraOrderingOk
      }; }
});
