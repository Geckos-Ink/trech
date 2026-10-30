// Expected output contract; numerical family tolerances remain in the referenced validators.
TRECH_VALIDATIONS["validation_glass_of_water"] = {
  "schema": "trech_scenario_validation_v1",
  "scenario": "validation_glass_of_water",
  "scope": "Validation scenario: a beam of light enters a glass slab containing a water bulk, then exits back into air -- the \"glass of water\" cross section, modeled with planar (axis-aligned) interfaces so that the surface normal at every refraction is exactly one of +/- x, y, z. Planar normals are what lets the companion validator (scripts/validate_glass_of_water.py) invert the classical optics formulas with no ambiguity.",
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
  "physics_status": "configuration_or_transport",
  "limitations": "",
  "reference": "tools/validation/trech_validation/cases.py"
};

globalThis.TRECH_CHECKS = globalThis.TRECH_CHECKS || {};
TRECH_CHECKS["validation_glass_of_water"] = Object.assign(TRECH_CHECKS["validation_glass_of_water"] || {}, {
"opticsReferences0": function(beamEnergyEv) {return {
        enable: true,
        // Handbook references the run records (the validator reads
        // these back and compares against its own inverse-solved
        // values, so they double as the "expected" column of the
        // report).
        references: [
          { material: "air",   energyEv: beamEnergyEv, refractiveIndex: 1.000293, source: "CRC Handbook, dry air @ STP" },
          { material: "water", energyEv: beamEnergyEv, refractiveIndex: 1.333,    source: "CRC Handbook, water @ 589 nm" },
          { material: "glass", energyEv: beamEnergyEv, refractiveIndex: 1.46,     source: "Schott BK7 typical n @ 589 nm" }
        ]
      };}
});
