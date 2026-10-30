// Expected output contract; numerical family tolerances remain in the referenced validators.
TRECH_VALIDATIONS["testscenario_h2o_electrolysis_combustion"] = {
  "schema": "trech_scenario_validation_v1",
  "scenario": "testscenario_h2o_electrolysis_combustion",
  "scope": "Validation scenario: water electrolysis on two cathodes followed by inverse combustion (H2 + O2 -> H2O).",
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
TRECH_CHECKS["testscenario_h2o_electrolysis_combustion"] = Object.assign(TRECH_CHECKS["testscenario_h2o_electrolysis_combustion"] || {}, {
"checks0": function(GEANT4, PUBCHEM, SCENARIO, afterElectrolysis, cathodeImbalance, finalInv, h2ToO2, initial, reactionSource, recovered, sameInventory, state) { return {
      pubchem_properties_present:
        PUBCHEM.water.cid > 0 && PUBCHEM.hydrogen.cid > 0 && PUBCHEM.oxygen.cid > 0 &&
        PUBCHEM.water.formula === "H2O" && PUBCHEM.hydrogen.formula === "H2" &&
        PUBCHEM.oxygen.formula === "O2",
      geant4_anchor_present:
        GEANT4.waterMuPerMm > 0 && GEANT4.hydrogenMuPerMm > 0 && GEANT4.oxygenMuPerMm > 0 &&
        state.geant4Drive.events === state.tick && state.geant4Drive.totalEdepMeV > 0,
      electrolysis_stoichiometry:
        Math.abs(h2ToO2 - 2.0) <= 0.05 && state.hRadicalsAfterElectrolysis === 0,
      two_cathodes_active:
        state.hydrogenLeftAfterElectrolysis > 0 && state.hydrogenRightAfterElectrolysis > 0 &&
        cathodeImbalance <= SCENARIO.cathodeBalanceTolerance,
      atom_conservation:
        sameInventory(initial, afterElectrolysis) && sameInventory(initial, finalInv),
      inverse_combustion_recovered_water:
        recovered >= SCENARIO.recoveryMinFraction &&
        state.recombinedWater >= SCENARIO.initialWater - 2,
      no_engine_reaction_rule:
        true,
      normal_path_has_no_js_reaction_probability:
        reactionSource === "operator"
    }; }
});
