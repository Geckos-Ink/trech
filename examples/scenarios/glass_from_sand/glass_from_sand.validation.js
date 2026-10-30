// Expected output contract; numerical family tolerances remain in the referenced validators.
TRECH_VALIDATIONS["glass_from_sand"] = {
  "schema": "trech_scenario_validation_v1",
  "scenario": "glass_from_sand",
  "scope": "Making glass: a material that does not exist when the run starts.",
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
  "physics_status": "operator_backed",
  "limitations": "",
  "reference": "tools/validation/trech_validation/cases.py"
};
globalThis.TRECH_CHECKS = globalThis.TRECH_CHECKS || {};
TRECH_CHECKS["glass_from_sand"] = {
"expectations0": function(CHARGE_HEIGHT_MM, KIND_MELT, allConserved, materialKinds, pairKinds, state, summary, totalInferences) { return {
        geant4_material_base_present:
          Object.keys(state.probes).length === 4 &&
          Object.values(state.probes).every((p) => p.density_g_per_cm3 > 0.0),
        cascade_supplied_conditions:
          isFinite(state.params.calcination_onset_k) &&
          state.params.calcination_onset_k > 0.0 &&
          state.params.calcination_onset_k < state.params.melt_onset_k &&
          state.params.melt_onset_k < state.params.fusion_onset_k,
        // The point of the scenario: the product did not exist at t=0.
        product_material_created:
          state.history.length > 0 && state.history[0].glass_units === 0 &&
          summary.glass_units > 0,
        material_class_changed_during_run:
          state.transitions.toMelt > 0 && state.transitions.toGlass > 0 &&
          materialKinds.length === 3,
        // Per-material inference actually happened, in all three operators.
        per_material_operator_selection:
          state.selection.evolve.length > 0 && state.selection.react.length > 0 &&
          state.selection.interact.length > 0 &&
          state.selection.evolve.some((s) => s.indexOf(KIND_MELT) >= 0) &&
          state.selection.react.some((s) => s.indexOf(KIND_MELT) >= 0),
        per_pair_material_conduction: pairKinds.length >= 3,
        formed_glass_has_no_further_chemistry: state.unclaimedGlassCells > 0,
        exact_atom_conservation: allConserved,
        chemistry_respects_inferred_onsets:
          state.accepted.soda_calcination > 0 && state.accepted.lime_calcination > 0 &&
          state.accepted.glass_fusion > 0 &&
          state.minCalcinationTemperatureK >= state.params.calcination_onset_k &&
          state.minFusionTemperatureK >= state.params.fusion_onset_k,
        // Heat only enters at the floor, so the first glass must appear low.
        conversion_follows_the_thermal_gradient:
          state.firstGlassHeightMm !== null &&
          state.firstGlassHeightMm < 0.5 * CHARGE_HEIGHT_MM,
        every_inference_accounted: totalInferences > 0 &&
          state.inference.draws > 0 && state.inference.draws <= state.inference.react
      }; }
};
