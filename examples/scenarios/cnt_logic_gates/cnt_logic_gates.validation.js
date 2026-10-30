// Expected output contract; numerical family tolerances remain in the referenced validators.
TRECH_VALIDATIONS["cnt_logic_gates"] = {
  "schema": "trech_scenario_validation_v1",
  "scenario": "cnt_logic_gates",
  "scope": "Vostok milestone (CNT parallel track): carbon-nanotube LOGIC GATES + CIRCUITS.",
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
  "limitations": "CNTFET conductance and Fermi turn-on forward laws",
  "reference": "tools/validation/trech_validation/cases.py"
};

globalThis.TRECH_CHECKS = globalThis.TRECH_CHECKS || {};
TRECH_CHECKS["cnt_logic_gates"] = Object.assign(TRECH_CHECKS["cnt_logic_gates"] || {}, {
"checks0": function(allGatesCorrect, cntLogicGatesOk, fermiTrendOk, fullAdderCorrect, geant4DrivePresent, halfAdderCorrect, metallicBreaksLogic, noiseMarginHealthy, onOffGapControlled, rippleAdderCorrect, round4, semiWorstRail, swingNear60) { return {
        all_gate_truth_tables_correct: allGatesCorrect,
        half_adder_correct: halfAdderCorrect,
        full_adder_correct: fullAdderCorrect,
        ripple_carry_adder_2bit_correct: rippleAdderCorrect,
        noise_margin_healthy: noiseMarginHealthy,
        metallic_tube_breaks_logic: metallicBreaksLogic,
        subthreshold_swing_near_60mV: swingNear60,
        on_off_ratio_gap_controlled: onOffGapControlled,
        fermi_temperature_trend: fermiTrendOk,
        geant4_event_drive_present: geant4DrivePresent,
        semiconducting_worst_rail_closeness: round4(semiWorstRail),
        cnt_logic_gates_ok: cntLogicGatesOk
      }; }
});
