// Expected output contract; numerical family tolerances remain in the referenced validators.
TRECH_VALIDATIONS["h2o_bulk_water"] = {
  "schema": "trech_scenario_validation_v1",
  "scenario": "h2o_bulk_water",
  "scope": "Sputnik \"H2O fluid behavior\", completed toward true BULK: the cluster (h2o_cluster_fluid.js) is a finite droplet with a surface; this is bulk liquid water in a PERIODIC box, so there is no surface and the structure can be compared to the measured liquid. The headline observable is the O-O radial distribution function g(r): real liquid water has a sharp first peak at ~2.8 A (the hydrogen-bond distance) and tetrahedral coordination ~4-4.5.",
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
  "limitations": "SPC/E pair forces; SHAKE/RATTLE and integration are numerical prerequisites",
  "reference": "tools/validation/trech_validation/cases.py"
};

globalThis.TRECH_CHECKS = globalThis.TRECH_CHECKS || {};
TRECH_CHECKS["h2o_bulk_water"] = Object.assign(TRECH_CHECKS["h2o_bulk_water"] || {}, {
"checks0": function(coordReasonable, diffusionPhysical, greenKuboConsistent, peakOk, rigidOk, shell2Ok, tempOk) { return {
          first_peak_near_experiment: peakOk,
          coordination_reasonable: coordReasonable,
          temperature_controlled: tempOk,
          second_shell_near_tetrahedral: shell2Ok,
          rigid_constraints_held: rigidOk,
          self_diffusion_physical: diffusionPhysical,
          green_kubo_consistent_with_einstein: greenKuboConsistent,
          // The headline claim: a periodic bulk-water structure that reproduces
          // the measured hydrogen-bond peak at a controlled temperature, with
          // the rigid-body constraints provably held.
          bulk_water_stable: peakOk && tempOk && rigidOk
        }; }
});
