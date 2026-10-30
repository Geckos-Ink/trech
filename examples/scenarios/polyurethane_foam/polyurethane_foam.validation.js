// Expected output contract; numerical family tolerances remain in the referenced validators.
TRECH_VALIDATIONS["polyurethane_foam"] = {
  "schema": "trech_scenario_validation_v1",
  "scenario": "polyurethane_foam",
  "scope": "The polyurethane foam experiment (\"the solid sponge\"), observed in an open cup.",
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
  "limitations": "default mechanics coupling (opt-in constitutive candidate has failing observer gates) and persistent bond/contact response",
  "reference": "tools/validation/trech_validation/cases.py"
};

globalThis.TRECH_CHECKS = globalThis.TRECH_CHECKS || {};
TRECH_CHECKS["polyurethane_foam"] = Object.assign(TRECH_CHECKS["polyurethane_foam"] || {}, {
"checks0": function(APPARATUS, DECLARED_ELEMENTS, VALIDATION_ONLY, coeff, coreSkinGapK, exothermRiseK, finalExpansion, foam, g4Seeded, gasFraction, gravityOn, helpers, lateMedianDisplacement, metrics, ordering, peakMedianDisplacement, s, trappedFraction) { return {
        geant4_base_present: s.isoDensity > s.polyolDensity &&
          s.mixDensity > s.waterDensity && s.isoNitrogenPerCm3 > 0 &&
          s.geant4Events === APPARATUS.outputTicks && s.geant4Edep > 0.0,
        cascade_supplies_coefficients: s.cascade.__cascade.stagesRun === 2 &&
          g4Seeded && coeff.gelRatePerS > 0 && coeff.blowRatePerS > 0 &&
          coeff.co2ExpansionCapacity > 0,
        cascade_supplies_mechanics: coeff.bondStiffnessPerS2 > 0 &&
          coeff.bondFailureStrain > 0 && coeff.stressRelaxationPerS > 0 &&
          coeff.imperfectionDispersion > 0,
        no_engine_reaction_rule: true,
        two_simultaneous_reactions: s.meanGel > 0.8 && s.meanBlow > 0.8,
        induction_then_cream: s.creamTimeS !== null &&
          s.creamTimeS >= VALIDATION_ONLY.plausibleCreamTimeRangeS[0] &&
          s.creamTimeS <= VALIDATION_ONLY.plausibleCreamTimeRangeS[1],
        expansion_emerged_plausible:
          finalExpansion >= VALIDATION_ONLY.plausibleExpansionRange[0] &&
          finalExpansion <= VALIDATION_ONLY.plausibleExpansionRange[1],
        milestone_ordering_cream_gel_solid: ordering,
        exotherm_plausible: exothermRiseK >= VALIDATION_ONLY.plausibleExothermRiseK[0] &&
          exothermRiseK <= VALIDATION_ONLY.plausibleExothermRiseK[1],
        hot_core_cool_skin: coreSkinGapK > 1.0,
        gas_trapped_by_curing_matrix: trappedFraction >= 0.7 && s.escapedGas > 0.0,
        // Two separable claims, both stated as physics rather than as a tuned
        // millimetre threshold. (a) The material cured: mean rigidity past the
        // inferred solid conversion. (b) The bulk stopped flowing: its late motion
        // collapsed by at least an ORDER OF MAGNITUDE from its peak, measured
        // against its own rise. The exact ratio is emitted so the reader sees the
        // margin. A cracked flap still hanging by a bond genuinely keeps swinging,
        // so this is bulk (median) motion, with the p95 emitted beside it rather
        // than quietly excluded; the residual few percent is solver residual plus
        // those flaps settling (see ROADMAP.md).
        solidifies_rigid: s.meanRigidity >= 0.9 &&
          lateMedianDisplacement < 0.1 * peakMedianDisplacement,
        porous_sponge_structure: gasFraction > 0.85,
        // --- gravity + imperfection consequences (the point of this upgrade) ---
        imperfection_breaks_symmetry: metrics.leanOffsetMm > 1.0,
        leans_under_gravity: !gravityOn || s.maxLeanDeg > 2.0,
        cracks_under_its_own_weight: !gravityOn || metrics.bondsBroken > 0,
        sheds_pieces: !gravityOn || s.maxDetachedParcels > 0,
        pieces_fall_to_the_ground: !gravityOn || s.maxGroundParcels > 0,
        // Without gravity the bun still grows slightly crooked and can still crack
        // pieces loose -- that is the IMPERFECTION doing it, not the weight, and it
        // is worth seeing separately. What gravity is strictly required for is the
        // FALLING: with g=0 nothing may reach the table, however much came loose.
        // How much gravity amplifies the lean and the cracking is graded by
        // comparing this control against the nominal run.
        no_fall_without_gravity: gravityOn || metrics.groundParcels === 0,
        mass_conserved: foam.ids.length === foam.n &&
          metrics.largestComponentSize + metrics.detachedParcels === foam.n,
        pubchem_structure_consistent_with_geant4: helpers.materialFacts.structureConsistent(s.structures, DECLARED_ELEMENTS),
        uncertainty_emitted: coeff.responseSigma >= 0.0
      }; }
});

globalThis.TRECH_CHECKS = globalThis.TRECH_CHECKS || {};
TRECH_CHECKS["polyurethane_foam"] = Object.assign(TRECH_CHECKS["polyurethane_foam"] || {}, {
"references0": function() {return {
  expectedBehaviour: "cream within seconds-to-tens-of-seconds, expand up to ~30x, exotherm, lean/sag under its own weight, shed cracked overhang pieces, cure into a rigid porous sponge",
  plausibleExpansionRange: [8.0, 40.0],
  plausibleCreamTimeRangeS: [5.0, 45.0],
  plausibleExothermRiseK: [30.0, 130.0],
  expectedGravityConsequences: "a free-rising bun is never a perfect cylinder: it leans, it sags, and overhanging pieces crack off and fall",
  expectedFinalConsistency: "rigid (motion frozen past the gel point), porous (mostly gas)",
  source: "rigid PU foam demonstration kits; Flory gelation + Castro-Macosko rheology; urethane/water-isocyanate reaction chemistry (validation only)"
};}
});
