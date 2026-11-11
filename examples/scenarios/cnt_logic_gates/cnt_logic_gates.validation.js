// Expected output contract plus the exported suite family gate (family_checks).
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
  "family_case": "cnt_logic_gates",
  "family_summary": "Scenario logic verdict (truth tables, adders, latch/flip-flop/counter memory, noise margin, metallic-tube failure and chirality-distribution circuit yield).",
  "family_checks": [
    {"id": "cnt_logic_gates_ok", "tag": "cnt_gates_summary", "field": "validation.cnt_logic_gates_ok", "op": "eq", "expected": true},
    {"id": "cnt_sequential_logic_ok", "tag": "cnt_gates_summary", "field": "validation.sequential_logic_ok", "op": "eq", "expected": true},
    {"id": "cnt_chirality_yield_ok", "tag": "cnt_gates_summary", "field": "validation.chirality_yield_ok", "op": "eq", "expected": true},
    {"id": "cnt_yield_mc_respects_bound", "tag": "cnt_gates_summary", "field": "validation.chirality_yield_mc_respects_bound", "op": "eq", "expected": true},
    {"id": "cnt_yield_all_usable_work", "tag": "cnt_gates_summary", "field": "validation.chirality_yield_all_usable_draws_work", "op": "eq", "expected": true}
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
      }; },
"checks1": function(counterCorrect, dFlipFlopEdgeTriggered, metallicLosesMemory, round4, semiSeq, sequentialLogicOk, sequentialNoiseHealthy, srLatchCorrect) { return {
        sr_latch_bistable_correct: srLatchCorrect,
        d_flip_flop_edge_triggered: dFlipFlopEdgeTriggered,
        counter_2bit_correct: counterCorrect,
        sequential_noise_margin_healthy: sequentialNoiseHealthy,
        metallic_tube_loses_memory: metallicLosesMemory,
        sequential_worst_rail_closeness: round4(semiSeq.worst_rail_closeness),
        sequential_logic_ok: sequentialLogicOk
      }; },
"checks2": function(chiralityYield) {
      const c = chiralityYield.checks;
      return {
        chirality_metallic_fraction: chiralityYield.metallic_fraction,
        chirality_metallic_fraction_near_one_third: c.metallic_fraction_near_one_third,
        chirality_no_metallic_tube_usable: c.no_metallic_tube_usable,
        chirality_yield_fet_slots_consistent: c.fet_slot_count_consistent,
        chirality_yield_all_usable_draws_work: c.all_usable_draws_always_work,
        chirality_yield_mc_respects_bound: c.mc_respects_independent_bound,
        chirality_yield_rises_with_purity: c.yield_rises_with_purity,
        chirality_unsorted_full_adder_fails: c.unsorted_full_adder_fails,
        chirality_purity_needed_for_target: chiralityYield.purity_needed_for_target_ripple_adder,
        chirality_yield_ok: chiralityYield.chirality_yield_ok
      }; }
});
