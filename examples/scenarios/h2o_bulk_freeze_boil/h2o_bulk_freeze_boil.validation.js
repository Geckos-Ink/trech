// Expected output contract, comparison references and the scenario's own verdict.
TRECH_VALIDATIONS["h2o_bulk_freeze_boil"] = {
  "schema": "trech_scenario_validation_v1",
  "scenario": "h2o_bulk_freeze_boil",
  "scope": "600 coarse-grained mW water molecules (Tm 274.6 K) on a fixed ice Ih basal floor with a free surface, driven through 10 °C -> -1 °C -> 100 °C. At 10 °C the water is liquid apart from at most one ordered contact bilayer on the floor. At -1 °C it really freezes: an ice front grows from the floor (CHILL+ detects every molecule's phase). On heating the ice melts; at 100 °C it is a hot liquid with a free surface (evaporation is reported, not required).",
  "checks": [
    {"file": "trech_scores.jsonl", "phase": "run_end", "field": "n_events", "op": "gt", "expected": 0},
    {"file": "trech_scores.jsonl", "phase": "run_end", "field": "hook_emit_dropped_count", "op": "eq", "expected": 0, "missing": 0},
    {"tag": "freeze_boil_summary", "field": "mobile_molecules", "op": "eq", "expected": 600},
    {"tag": "freeze_boil_summary", "field": "validation.temperature_program_followed", "op": "eq", "expected": true},
    {"tag": "freeze_boil_summary", "field": "validation.froze_at_minus_1C", "op": "eq", "expected": true},
    {"tag": "freeze_boil_summary", "field": "validation.ice_melted_at_100C", "op": "eq", "expected": true},
    {"tag": "freeze_boil_summary", "field": "validation.freeze_melt_cycle_reproduced", "op": "eq", "expected": true}
  ],
  "physics_status": "reference_only",
  "limitations": "mW three-body force field (coarse-grained, no hydrogens; dynamics ~3x faster than real water). The ice floor is an ideal fixed nucleation template, so nucleation is heterogeneous by construction; growth, melting and evaporation are emergent. The thermostat imposes the program and removes latent heat instantly. Evaporation into vacuum over the 120 ps 100 °C hold is counted but not required: real water's kinetic flux at 1 atm would release only ~3 molecules from this surface in that time.",
  "reference": "tools/validation/trech_validation/declarative.py"
};

globalThis.TRECH_CHECKS = globalThis.TRECH_CHECKS || {};
TRECH_CHECKS["h2o_bulk_freeze_boil"] = Object.assign(TRECH_CHECKS["h2o_bulk_freeze_boil"] || {}, {
// What real water does at 1 atm at this temperature (reference, not a model input).
"realPhase": function(targetK) {
  if (targetK < 273.15) return "ice Ih at equilibrium (freezes from walls/impurities)";
  if (targetK < 373.15 - 0.5) return "liquid";
  return "boiling point: liquid-vapour coexistence";
},
// Phase of the box from its own CHILL+ census (fraction of mobile molecules in
// hexagonal or cubic ice) and the measured growth of the ice front.
"phaseVerdict": function(h) {
  const f = h.crystal_fraction_end;
  if (f > 0.7) return "frozen (ice grew from the floor through the water)";
  // The floor templates one contact bilayer even above the melting point;
  // anything up to 1.5 bilayers is that layer, not freezing.
  if (h.ice_thickness_end_A > 1.5 * h.contact_bilayer_A)
    return h.ice_growth_A_per_ns > 0 ? "freezing (ice front advancing)" : "partly frozen";
  if (h.target_K >= 373.15 - 0.5)
    return h.vapour > 0 ? "hot liquid, evaporating at the free surface" : "hot liquid";
  return "liquid (at most one ordered contact bilayer on the floor)";
},
"checks0": function(holds, neighborOverflow) {
  const by = {};
  for (const h of holds) by[h.stage] = h;
  const w = by.hold_10C, c = by.hold_m1C, hot = by.hold_100C;
  const complete = !!(w && c && hot);
  const tempOk = complete && holds.every((h) => Math.abs(h.mean_temperature_K - h.target_K) < 3.0);
  // Liquid at 10 °C: no ice beyond the floor's ordered contact bilayer.
  const liquidAt10 = complete && w.ice_thickness_end_A <= 1.5 * w.contact_bilayer_A;
  // Freezing: the crystalline fraction rose well above the 10 °C baseline and
  // the measured ice front advanced (positive growth velocity).
  const froze = complete && c.crystal_fraction_end > w.crystal_fraction_end + 0.3 &&
                c.ice_growth_A_per_ns > 0;
  const fullyFrozen = complete && c.crystal_fraction_end > 0.7;
  const melted = complete && hot.ice_thickness_end_A <= 1.5 * hot.contact_bilayer_A;
  const neighborsOk = neighborOverflow === 0;
  return {
    temperature_program_followed: tempOk,
    neighbor_lists_complete: neighborsOk,
    liquid_at_10C: liquidAt10,
    froze_at_minus_1C: froze,
    fully_frozen_at_minus_1C: fullyFrozen,
    ice_melted_at_100C: melted,
    evaporation_at_100C: complete && hot.vapour > 0,
    // A free surface at fixed thermostat temperature: no pressure control, so
    // this is evaporation into vacuum, not a boiling point measurement.
    boiling_point_measured: false,
    freeze_melt_cycle_reproduced: tempOk && neighborsOk && liquidAt10 && froze && melted
  };
}
});
