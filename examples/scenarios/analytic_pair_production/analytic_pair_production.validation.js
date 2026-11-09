// Expected output contract plus the exported suite family gate (family_checks) and the
// multi-run threshold/energy and giant-dipole sweep gates (family_sweeps).
TRECH_VALIDATIONS["analytic_pair_production"] = {
  "schema": "trech_scenario_validation_v1",
  "scenario": "analytic_pair_production",
  "scope": "Analytic cross-check scenario: pair-production and photonuclear branching fractions, the 2 m_e c^2 threshold and the oxygen giant-dipole resonance.",
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
  "family_case": "analytic_pair_fraction_cross_check",
  "family_summary": "At the default 10 MeV run the pair-fraction check is available and within tolerance, conversions were classified, binomial |z| < 4, and the beam is above 2 m_e c^2.",
  "family_checks": [
    {"id": "check_available", "phase": "run_end", "field": "analytic_checks[type=pair_fraction].available", "op": "eq", "expected": true},
    {"id": "within_tolerance", "phase": "run_end", "field": "analytic_checks[type=pair_fraction].within_tolerance", "op": "eq", "expected": true},
    {"id": "conversions_classified", "phase": "run_end", "field": "analytic_checks[type=pair_fraction].primaries_pair_first", "op": "gt", "expected": 0},
    {"id": "binomial_z", "phase": "run_end", "field": "analytic_checks[type=pair_fraction]", "derive": {"fn": "abs", "args": ["z_score"]}, "op": "lt", "expected": 4.0},
    {"id": "above_pair_threshold", "phase": "run_end", "field": "analytic_checks[type=pair_fraction].below_pair_threshold", "op": "eq", "expected": false, "missing": false}
  ],
  "family_sweeps": [
    {
      "family_case": "analytic_pair_fraction_energy_sweep",
      "summary": "Rerun at 1.0/1.5/2/5/15/23/30 MeV and joined with the default 10 MeV run (no --param): below 2 m_e c^2 (1.0 MeV) the derived fraction is exactly zero and no conversion is tallied; above it every point classifies conversions with a binomial |z| < 4, and the measured fraction rises strictly with energy and spans at least 10x. The 6% relative flag is reported, not gated near threshold.",
      "runs": [
        {"id": "e1000keV", "params": {"energy_mev": 1.0}},
        {"id": "e1500keV", "params": {"energy_mev": 1.5}},
        {"id": "e2000keV", "params": {"energy_mev": 2.0}},
        {"id": "e5000keV", "params": {"energy_mev": 5.0}},
        {"id": "e10000keV", "params": {}},
        {"id": "e15000keV", "params": {"energy_mev": 15.0}},
        {"id": "e23000keV", "params": {"energy_mev": 23.0}},
        {"id": "e30000keV", "params": {"energy_mev": 30.0}}
      ],
      "checks": [
        {"id": "available", "each_run": true, "phase": "run_end", "field": "analytic_checks[?type=pair_fraction].available", "aggregate": "all", "op": "eq", "expected": true},
        {"id": "below_threshold_flag", "run": "e1000keV", "phase": "run_end", "field": "analytic_checks[?type=pair_fraction].below_pair_threshold", "aggregate": "all", "op": "eq", "expected": true},
        {"id": "derived_zero_below_threshold", "run": "e1000keV", "phase": "run_end", "field": "analytic_checks[?type=pair_fraction].classical_predicted", "aggregate": "max_abs", "op": "eq", "expected": 0},
        {"id": "no_conversion_below_threshold", "run": "e1000keV", "phase": "run_end", "field": "analytic_checks[?type=pair_fraction].primaries_pair_first", "aggregate": "max", "op": "eq", "expected": 0},
        {"id": "primaries_interacted_below_threshold", "run": "e1000keV", "phase": "run_end", "field": "analytic_checks[?type=pair_fraction].primaries_first_interaction", "aggregate": "min", "op": "gt", "expected": 0},
        {"id": "within_tolerance_below_threshold", "run": "e1000keV", "phase": "run_end", "field": "analytic_checks[?type=pair_fraction].within_tolerance", "aggregate": "all", "op": "eq", "expected": true},
        {"id": "above_threshold_flag", "each_run": ["e1500keV", "e2000keV", "e5000keV", "e10000keV", "e15000keV", "e23000keV", "e30000keV"], "phase": "run_end", "field": "analytic_checks[?type=pair_fraction].below_pair_threshold", "aggregate": "any", "op": "eq", "expected": false},
        {"id": "conversions_classified", "each_run": ["e1500keV", "e2000keV", "e5000keV", "e10000keV", "e15000keV", "e23000keV", "e30000keV"], "phase": "run_end", "field": "analytic_checks[?type=pair_fraction].primaries_pair_first", "aggregate": "min", "op": "gt", "expected": 0},
        {"id": "binomial_z", "each_run": ["e1500keV", "e2000keV", "e5000keV", "e10000keV", "e15000keV", "e23000keV", "e30000keV"], "phase": "run_end", "field": "analytic_checks[?type=pair_fraction]", "derive": {"fn": "abs", "args": [{"fn": "binomial_z", "args": ["geant4_measured", "classical_predicted", "primaries_first_interaction"]}]}, "aggregate": "max", "op": "lt", "expected": 4.0},
        {"id": "strictly_increasing", "runs": ["e1500keV", "e2000keV", "e5000keV", "e10000keV", "e15000keV", "e23000keV", "e30000keV"], "phase": "run_end", "field": "analytic_checks[?type=pair_fraction].geant4_measured", "aggregate": "max", "series_aggregate": "strictly_increasing", "op": "eq", "expected": true},
        {"id": "span_last_over_first", "runs": ["e1500keV", "e2000keV", "e5000keV", "e10000keV", "e15000keV", "e23000keV", "e30000keV"], "phase": "run_end", "field": "analytic_checks[?type=pair_fraction].geant4_measured", "aggregate": "max", "series_aggregate": "last_over_first", "op": "ge", "expected": 10.0}
      ]
    },
    {
      "family_case": "analytic_photonuclear_fraction_giant_dipole",
      "summary": "The 5/10/15/23/30 MeV pair runs also carry the photonuclear_fraction check: where Geant4 has no photonuclear cross section (5, 10 MeV) prediction and measurement are exactly zero; elsewhere absorptions are classified with a binomial |z| < 4; the derived and measured maxima both sit at the interior 23 MeV point (the giant-dipole peak) with a measured fraction of at least 2%.",
      "runs": [
        {"id": "e5000keV", "params": {"energy_mev": 5.0}},
        {"id": "e10000keV", "params": {}},
        {"id": "e15000keV", "params": {"energy_mev": 15.0}},
        {"id": "e23000keV", "params": {"energy_mev": 23.0}},
        {"id": "e30000keV", "params": {"energy_mev": 30.0}}
      ],
      "checks": [
        {"id": "available", "each_run": true, "phase": "run_end", "field": "analytic_checks[?type=photonuclear_fraction].available", "aggregate": "all", "op": "eq", "expected": true},
        {"id": "derived_zero", "each_run": ["e5000keV", "e10000keV"], "phase": "run_end", "field": "analytic_checks[?type=photonuclear_fraction].classical_predicted", "aggregate": "max_abs", "op": "eq", "expected": 0},
        {"id": "no_absorption", "each_run": ["e5000keV", "e10000keV"], "phase": "run_end", "field": "analytic_checks[?type=photonuclear_fraction].primaries_photonuclear_first", "aggregate": "max", "op": "eq", "expected": 0},
        {"id": "primaries_interacted", "each_run": ["e5000keV", "e10000keV"], "phase": "run_end", "field": "analytic_checks[?type=photonuclear_fraction].primaries_first_interaction", "aggregate": "min", "op": "gt", "expected": 0},
        {"id": "within_tolerance_zero", "each_run": ["e5000keV", "e10000keV"], "phase": "run_end", "field": "analytic_checks[?type=photonuclear_fraction].within_tolerance", "aggregate": "all", "op": "eq", "expected": true},
        {"id": "absorptions_classified", "each_run": ["e15000keV", "e23000keV", "e30000keV"], "phase": "run_end", "field": "analytic_checks[?type=photonuclear_fraction].primaries_photonuclear_first", "aggregate": "min", "op": "gt", "expected": 0},
        {"id": "binomial_z", "each_run": ["e15000keV", "e23000keV", "e30000keV"], "phase": "run_end", "field": "analytic_checks[?type=photonuclear_fraction]", "derive": {"fn": "abs", "args": [{"fn": "binomial_z", "args": ["geant4_measured", "classical_predicted", "primaries_first_interaction"]}]}, "aggregate": "max", "op": "lt", "expected": 4.0},
        {"id": "derived_peak", "runs": ["e15000keV", "e23000keV", "e30000keV"], "phase": "run_end", "field": "analytic_checks[?type=photonuclear_fraction].classical_predicted", "aggregate": "max", "series_aggregate": "argmax", "op": "eq", "expected": "e23000keV"},
        {"id": "measured_peak", "runs": ["e15000keV", "e23000keV", "e30000keV"], "phase": "run_end", "field": "analytic_checks[?type=photonuclear_fraction].geant4_measured", "aggregate": "max", "series_aggregate": "argmax", "op": "eq", "expected": "e23000keV"},
        {"id": "peak_fraction", "runs": ["e15000keV", "e23000keV", "e30000keV"], "phase": "run_end", "field": "analytic_checks[?type=photonuclear_fraction].geant4_measured", "aggregate": "max", "series_aggregate": "max", "op": "ge", "expected": 0.02}
      ]
    }
  ],
  "physics_status": "configuration_or_transport",
  "limitations": "Self-consistency of Geant4 process selection against its own conversion and photonuclear cross sections (photonuclear absorption is part of mu_total); not an independent XCOM/IAEA comparison.",
  "reference": "tools/validation/trech_validation/cases.py"
};
