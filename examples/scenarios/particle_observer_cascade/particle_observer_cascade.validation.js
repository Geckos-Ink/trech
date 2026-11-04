// Output integrity only. Held-out response/Monte Carlo acceptance lives in the
// dedicated particle-observer validator, not in production inference.
TRECH_VALIDATIONS.particle_observer_cascade = {
  schema: "trech_scenario_validation_v1", scenario: "particle_observer_cascade",
  scope: "An experimental Geant4-trained atomic/nano/meso candidate predicts before an independent Monte Carlo run; model acceptance remains gated by independent holdouts.",
  checks: [
    {file: "trech_scores.jsonl", phase: "run_end", field: "n_events", op: "gt", expected: 0},
    {file: "trech_scores.jsonl", phase: "run_end", field: "hook_emit_dropped_count", op: "eq", expected: 0, missing: 0}
  ],
  physics_status: "learned_geant4_transport_candidate",
  limitations: "Unit-density CHNO homogeneous cube, central gamma +z, QBBC_LIV, 10–30 keV. Not measured matter density, chemical bonding or independently validated experimental physics.",
  reference: "scripts/validate_particle_observer.py"
};
