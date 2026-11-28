// Expected output contract plus the exported suite family gate (family_checks).
TRECH_VALIDATIONS["h2o_molecule_stability"] = {
  "schema": "trech_scenario_validation_v1",
  "scenario": "h2o_molecule_stability",
  "scope": "Sputnik north-star item: simulate a single H2O molecule and show that its bonds are STABLE OVER TIME -- it oscillates around its equilibrium geometry without \"exploding\" (atoms flying apart).",
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
  "family_case": "h2o_molecule_bonds_stable",
  "family_summary": "Scenario stability verdict (bounded bonds near r0, total-energy drift below 2%) plus the 300 K thermal ensemble: its MD spectrum matches the force field's harmonic modes within 1%, keeps measured water's mode order, holds its temperature within 10% and conserves energy in every replica. The gap to measured fundamentals is reported, not gated.",
  "family_checks": [
    {"id": "stable_without_exploding", "tag": "molecule_summary", "field": "validation.stable_without_exploding", "op": "eq", "expected": true},
    {"id": "md_matches_force_field_modes", "tag": "molecule_spectrum", "field": "validation.md_matches_force_field_modes", "op": "eq", "expected": true},
    {"id": "mode_order_as_measured", "tag": "molecule_spectrum", "field": "validation.mode_order_as_measured", "op": "eq", "expected": true},
    {"id": "ensemble_temperature_ok", "tag": "molecule_spectrum", "field": "validation.ensemble_temperature_ok", "op": "eq", "expected": true},
    {"id": "replicas_energy_conserved", "tag": "molecule_spectrum", "field": "validation.replicas_energy_conserved", "op": "eq", "expected": true}
  ],
  "physics_status": "reference_only",
  "limitations": "flexible-water bond and angle force laws",
  "reference": "tools/validation/trech_validation/cases.py"
};

globalThis.TRECH_CHECKS = globalThis.TRECH_CHECKS || {};
TRECH_CHECKS["h2o_molecule_stability"] = Object.assign(TRECH_CHECKS["h2o_molecule_stability"] || {}, {
"checks0": function(bondsStable, energyConserved, exploded) { return {
          stable_without_exploding: bondsStable && energyConserved,
          bonds_stable: bondsStable,
          energy_conserved: energyConserved,
          exploded: exploded
        }; },
// Validation only: grades the thermal-ensemble spectrum twice. (1) Against this force field's own
// harmonic normal modes (Wilson GF method for a bent XY2 molecule with bond and angle force
// constants only), which checks the integrator and the spectral analysis. (2) Against measured
// gas-phase H2O fundamentals, which grades the classical force field itself. Neither feeds back.
"spectrum0": function(md, ff) {
  const muH = 1 / ff.mass.H, muO = 1 / ff.mass.O, a = ff.theta0, r = ff.r0;
  const g11 = muH + muO * (1 + Math.cos(a)), g12 = -Math.SQRT2 * muO * Math.sin(a) / r;
  const g22 = 2 / (r * r) * (muH + muO * (1 - Math.cos(a))), g33 = muH + muO * (1 - Math.cos(a));
  const tr = g11 * ff.kb + g22 * ff.ka, det = (g11 * g22 - g12 * g12) * ff.kb * ff.ka;
  const disc = Math.sqrt(tr * tr - 4 * det);
  const cm1 = (lambda) => Math.sqrt(lambda) / (2 * Math.PI * ff.cCmPerFs);
  const harmonic = { symmetric_stretch: cm1((tr + disc) / 2), bend: cm1((tr - disc) / 2),
                     antisymmetric_stretch: cm1(g33 * ff.kb) };
  // Measured gas-phase fundamentals (Shimanouchi, NIST CCCBDB): nu1, nu2, nu3.
  const measured = { symmetric_stretch: 3657.05, bend: 1594.75, antisymmetric_stretch: 3755.93 };
  const modes = Object.keys(measured);
  const gapForceField = {}, gapMeasured = {};
  for (const m of modes) {
    gapForceField[m] = (md.peaks_cm1[m] - harmonic[m]) / harmonic[m];
    gapMeasured[m] = (md.peaks_cm1[m] - measured[m]) / measured[m];
  }
  const worst = (gaps) => Math.max(...modes.map((m) => Math.abs(gaps[m])));
  const p = md.peaks_cm1;
  return {
    harmonic_reference_cm1: harmonic,
    measured_reference_cm1: measured,
    relative_gap_to_harmonic: gapForceField,
    relative_gap_to_measured: gapMeasured,
    max_abs_gap_to_harmonic: worst(gapForceField),
    max_abs_gap_to_measured: worst(gapMeasured),
    // The MD spectrum reproduces the force field's normal modes (within one percent).
    md_matches_force_field_modes: worst(gapForceField) <= 0.01,
    // Same mode order as measured water: antisymmetric stretch > symmetric stretch > bend.
    mode_order_as_measured: p.antisymmetric_stretch > p.symmetric_stretch && p.symmetric_stretch > p.bend,
    ensemble_temperature_ok: Math.abs(md.temperature_kinetic_k / md.temperature_target_k - 1) <= 0.1,
    replicas_energy_conserved: md.worst_energy_drift_fraction < 0.02
  };
}
});
