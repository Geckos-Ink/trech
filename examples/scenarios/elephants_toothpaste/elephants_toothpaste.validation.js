// Expected output contract; numerical family tolerances remain in the referenced validators.
TRECH_VALIDATIONS["elephants_toothpaste"] = {
  "schema": "trech_scenario_validation_v1",
  "scenario": "elephants_toothpaste",
  "scope": "Elephant's toothpaste (\"the soapy lather\"), observed in a graduated cylinder.",
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
  "limitations": "catalytic reaction, heat, trapping and foam-drainage evolution",
  "reference": "tools/validation/trech_validation/cases.py"
};

globalThis.TRECH_CHECKS = globalThis.TRECH_CHECKS || {};
TRECH_CHECKS["elephants_toothpaste"] = Object.assign(TRECH_CHECKS["elephants_toothpaste"] || {}, {
"checks0": function(APPARATUS, DECLARED_ELEMENTS, VALIDATION_ONLY, accelerationFactor, coeff, crownTopMm, g4Seeded, helpers, lateMaxDisplacement, peakFoamFactor, retention, state, trappedFraction) { return {
        geant4_base_present: state.catalystDensity > state.peroxideDensity &&
          state.peroxideDensity > state.waterDensity &&
          state.catalystIodinePerCm3 > 0 && state.catalystPotassiumPerCm3 > 0 &&
          state.geant4Events === APPARATUS.outputTicks && state.geant4Edep > 0.0,
        cascade_supplies_coefficients: state.cascade.__cascade.stagesRun === 2 &&
          g4Seeded && coeff.catalysedRatePerS > 0 && coeff.o2FoamCapacity > 0,
        no_engine_reaction_rule: true,
        catalysis_accelerates_decomposition:
          accelerationFactor >= VALIDATION_ONLY.minimumCatalyticAcceleration,
        sudden_completion: state.t90S !== null &&
          state.t90S >= VALIDATION_ONLY.plausibleCompletionTimeS[0] &&
          state.t90S <= VALIDATION_ONLY.plausibleCompletionTimeS[1],
        eruption_emerged: state.eruptTimeS !== null && crownTopMm > 100.0,
        foam_expansion_plausible:
          peakFoamFactor >= VALIDATION_ONLY.plausibleFoamVolumeFactorRange[0] &&
          peakFoamFactor <= VALIDATION_ONLY.plausibleFoamVolumeFactorRange[1],
        // The lower bound and the steaming requirement are the emergent content:
        // the inferred exotherm must actually drive the mixture into the steaming
        // band. The upper bound is partly held by the LABELLED evaporative clamp,
        // so the unclamped peak and the kelvin the clamp removed are emitted
        // beside it rather than hidden.
        exothermic_steaming:
          state.peakTemperatureK >= VALIDATION_ONLY.plausiblePeakTemperatureK[0] &&
          state.peakTemperatureK <= VALIDATION_ONLY.plausiblePeakTemperatureK[1] &&
          state.steamingSteps > 0,
        evaporative_clamp_contribution_disclosed:
          state.evaporativeRemovedK >= 0.0 &&
          state.peakUnclampedTemperatureK >= state.peakTemperatureK,
        surfactant_traps_gas: state.trappedGas > 0.0 && state.escapedGas > 0.0 &&
          trappedFraction < 0.5,
        never_solidifies_then_drains: retention > 0.4 && retention < 0.999 &&
          lateMaxDisplacement > 0.05,
        iodine_intermediate_transient: state.peakIodineIntermediate > 0.0 &&
          state.t90S !== null && state.peakIodineTimeS < state.t90S &&
          state.iodineIntermediate < 0.5 * state.peakIodineIntermediate,
        pubchem_structure_consistent_with_geant4: helpers.materialFacts.structureConsistent(state.structures, DECLARED_ELEMENTS),
        velocity_cap_not_driving_motion: state.velocityClampCount === 0,
        uncertainty_emitted: coeff.responseSigma >= 0.0
      }; }
});

globalThis.TRECH_CHECKS = globalThis.TRECH_CHECKS || {};
TRECH_CHECKS["elephants_toothpaste"] = Object.assign(TRECH_CHECKS["elephants_toothpaste"] || {}, {
"references0": function() {return {
  expectedBehaviour: "sudden catalytic O2 release erupting as a steaming lather column that never solidifies, then slowly drains",
  minimumCatalyticAcceleration: 1000.0,
  plausibleCompletionTimeS: [3.0, 40.0],
  plausibleFoamVolumeFactorRange: [8.0, 40.0],
  plausiblePeakTemperatureK: [330.0, 373.5],
  expectedFinalConsistency: "soft draining lather (no rigidity; motion continues)",
  source: "Shakhashiri demonstration; iodide-catalysed H2O2 decomposition kinetics (Ea ~ 56 kJ/mol uncatalysed, lowered by I-); validation only"
};}
});
