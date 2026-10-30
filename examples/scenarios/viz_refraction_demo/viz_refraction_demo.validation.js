// Expected output contract; numerical family tolerances remain in the referenced validators.
TRECH_VALIDATIONS["viz_refraction_demo"] = {
  "schema": "trech_scenario_validation_v1",
  "scenario": "viz_refraction_demo",
  "scope": "3D refraction demo: a monochromatic optical-photon beam enters a glass slab containing a water cube, then exits back into air. The point of this scenario is to *show* refraction in a 3D viewer where every material's optical response (n, absorption, scatter) was derived by TRECH from Geant4-level particle interaction cross sections, not from hardcoded classical optics.",
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
TRECH_CHECKS["viz_refraction_demo"] = Object.assign(TRECH_CHECKS["viz_refraction_demo"] || {}, {
"opticsReferences0": function() {return {
        enable: true,
        references: [
          { material: "water", energyEv: 2.25, refractiveIndex: 1.333, source: "CRC Handbook" },
          { material: "glass", energyEv: 2.25, refractiveIndex: 1.46, source: "Schott BK7 typical" },
          { material: "air", energyEv: 2.25, refractiveIndex: 1.000293, source: "CRC Handbook" }
        ]
      };}
});
