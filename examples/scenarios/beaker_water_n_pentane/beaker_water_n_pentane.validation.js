// Expected output contract; numerical family tolerances remain in the referenced validators.
TRECH_VALIDATIONS["beaker_water_n_pentane"] = {
  "schema": "trech_scenario_validation_v1",
  "scenario": "beaker_water_n_pentane",
  "scope": "Water + n-pentane poured into an open beaker at 30 C, observed for 60 minutes.",
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
  "physics_status": "operator_partial",
  "limitations": "time-resolved evaporation/dissolution/phase-transfer operator",
  "reference": "tools/validation/trech_validation/cases.py"
};

globalThis.TRECH_CHECKS = globalThis.TRECH_CHECKS || {};
TRECH_CHECKS["beaker_water_n_pentane"] = Object.assign(TRECH_CHECKS["beaker_water_n_pentane"] || {}, {
"checks0": function(STRUCTURES, TIMELINE, densityPentane, densityWater, evaporatedMassG, frameClock, pentaneChroma, remainingMassG, state, vpRelGap, waterChroma) { return {
        geant4_base_present: densityWater > densityPentane && state.geant4Events === 60 &&
          state.geant4Steps > 0,
        pubchem_structure_only: STRUCTURES.water.smiles.length > 0 &&
          STRUCTURES.nPentane.smiles.length > 0,
        colour_from_geant4: waterChroma < 0.12 && pentaneChroma < 0.12,
        immiscible_layers_inferred: state.phaseSeparated && state.pentaneOnTop,
        volatility_holdout_close: vpRelGap < 0.15,
        evaporation_mass_conserved: Math.abs(state.initialPentaneMassG -
          evaporatedMassG - remainingMassG) < 1e-9,
        sixty_minutes_reached: state.lastMinute === 60,
        pour_mix_evaporate_sequence: state.phaseOrderValid && state.lastPhaseOrdinal === 4 &&
          state.phaseFrames.empty === 1 && state.phaseFrames.water_pour > 0 &&
          state.phaseFrames.pentane_pour > 0 && state.phaseFrames.intermix_and_separate > 0 &&
          state.phaseFrames.accelerated_evaporation > 0,
        vapour_plume_moves: state.maxVaporMotionMm > 1.0,
        accelerated_clock_declared: frameClock(TIMELINE.finalFrame).timeScale > 100.0 &&
          frameClock(TIMELINE.finalFrame).physicalTimeS > 3600.0
      }; }
});

globalThis.TRECH_CHECKS = globalThis.TRECH_CHECKS || {};
TRECH_CHECKS["beaker_water_n_pentane"] = Object.assign(TRECH_CHECKS["beaker_water_n_pentane"] || {}, {
"references0": function() {return {
  pentaneDensityGPerCm3: 0.626,
  pentaneVapourPressureKpaAt303K: 81.9789,
  pentaneVapourPressureSource:
    "NIST Chemistry WebBook SRD 69 Antoine parameters; validation only",
  expectedAppearance: "colourless",
  expectedDisposition: "immiscible n-pentane upper layer"
};},
"opticsReferences1": function(PENTANE, WATER) {return {
        enable: true,
        references: [
          { material: WATER, energyEv: 2.25, refractiveIndex: 1.333,
            source: "validation-only handbook reference" },
          { material: PENTANE, energyEv: 2.25, refractiveIndex: 1.358,
            source: "validation-only handbook reference" }
        ]
      };}
});
