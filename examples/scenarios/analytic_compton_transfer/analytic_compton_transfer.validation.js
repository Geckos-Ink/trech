// Expected output contract plus the exported suite family gate (family_checks).
TRECH_VALIDATIONS["analytic_compton_transfer"] = {
  "schema": "trech_scenario_validation_v1",
  "scenario": "analytic_compton_transfer",
  "scope": "Analytic cross-check scenario: Klein-Nishina Compton energy transfer and edge.",
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
  "family_case": "analytic_compton_transfer_cross_check",
  "family_summary": "Klein-Nishina mean transfer within tolerance and |z| < 4; max sampled transfer within [0.98, 1] x the Compton edge; binned u = T/T_max and cos(theta) spectra complete with chi-square p >= 0.001; <cos theta> |z| < 4; energy-angle closure residual <= 1e-9.",
  "family_checks": [
    {"id": "checks_present", "phase": "run_end", "field": "analytic_checks[?type=compton_energy_transfer]", "aggregate": "count", "op": "ge", "expected": 1},
    {"id": "all_available", "phase": "run_end", "field": "analytic_checks[?type=compton_energy_transfer].available", "aggregate": "all", "op": "eq", "expected": true},
    {"id": "all_within_tolerance", "phase": "run_end", "field": "analytic_checks[?type=compton_energy_transfer].within_tolerance", "aggregate": "all", "op": "eq", "expected": true},
    {"id": "compton_samples", "phase": "run_end", "field": "analytic_checks[?type=compton_energy_transfer].primaries_compton_first", "aggregate": "min", "op": "gt", "expected": 1},
    {"id": "mean_transfer_z", "phase": "run_end", "field": "analytic_checks[?type=compton_energy_transfer].z_score", "aggregate": "max_abs", "op": "lt", "expected": 4.0},
    {"id": "edge_defined", "phase": "run_end", "field": "analytic_checks[?type=compton_energy_transfer].compton_edge_fraction", "aggregate": "min", "op": "gt", "expected": 0.0},
    {"id": "edge_respected", "phase": "run_end", "field": "analytic_checks[?type=compton_energy_transfer]", "derive": {"fn": "ratio", "args": ["measured_max_transfer_fraction", "compton_edge_fraction"]}, "aggregate": "max", "op": "le", "expected": 1.000000001},
    {"id": "edge_reached", "phase": "run_end", "field": "analytic_checks[?type=compton_energy_transfer]", "derive": {"fn": "ratio", "args": ["measured_max_transfer_fraction", "compton_edge_fraction"]}, "aggregate": "min", "op": "ge", "expected": 0.98},
    {"id": "spectrum_bins", "phase": "run_end", "field": "analytic_checks[?type=compton_energy_transfer]", "derive": {"fn": "list_length", "args": ["measured_transfer_histogram"]}, "aggregate": "min", "op": "gt", "expected": 1},
    {"id": "spectrum_entries_match_samples", "phase": "run_end", "field": "analytic_checks[?type=compton_energy_transfer]", "derive": {"fn": "difference", "args": ["transfer_histogram_entries", "primaries_compton_first"]}, "aggregate": "max_abs", "op": "eq", "expected": 0},
    {"id": "spectrum_histogram_complete", "phase": "run_end", "field": "analytic_checks[?type=compton_energy_transfer]", "derive": {"fn": "difference", "args": [{"fn": "list_sum", "args": ["measured_transfer_histogram"]}, "transfer_histogram_entries"]}, "aggregate": "max_abs", "op": "eq", "expected": 0},
    {"id": "spectrum_shape_p", "phase": "run_end", "field": "analytic_checks[?type=compton_energy_transfer]", "derive": {"fn": "chi2_sf", "args": ["transfer_histogram_chi2", "transfer_histogram_dof"]}, "aggregate": "min", "op": "ge", "expected": 0.001},
    {"id": "angular_bins", "phase": "run_end", "field": "analytic_checks[?type=compton_energy_transfer]", "derive": {"fn": "list_length", "args": ["measured_cos_theta_histogram"]}, "aggregate": "min", "op": "gt", "expected": 1},
    {"id": "angular_entries_match_samples", "phase": "run_end", "field": "analytic_checks[?type=compton_energy_transfer]", "derive": {"fn": "difference", "args": ["cos_theta_histogram_entries", "primaries_compton_first"]}, "aggregate": "max_abs", "op": "eq", "expected": 0},
    {"id": "angular_histogram_complete", "phase": "run_end", "field": "analytic_checks[?type=compton_energy_transfer]", "derive": {"fn": "difference", "args": [{"fn": "list_sum", "args": ["measured_cos_theta_histogram"]}, "cos_theta_histogram_entries"]}, "aggregate": "max_abs", "op": "eq", "expected": 0},
    {"id": "angular_shape_p", "phase": "run_end", "field": "analytic_checks[?type=compton_energy_transfer]", "derive": {"fn": "chi2_sf", "args": ["cos_theta_histogram_chi2", "cos_theta_histogram_dof"]}, "aggregate": "min", "op": "ge", "expected": 0.001},
    {"id": "mean_cos_theta_z", "phase": "run_end", "field": "analytic_checks[?type=compton_energy_transfer].cos_theta_z_score", "aggregate": "max_abs", "op": "lt", "expected": 4.0},
    {"id": "energy_angle_closure", "phase": "run_end", "field": "analytic_checks[?type=compton_energy_transfer].measured_max_kinematic_residual", "aggregate": "max", "op": "le", "expected": 1e-09}
  ],
  "physics_status": "configuration_or_transport",
  "limitations": "",
  "reference": "tools/validation/trech_validation/cases.py"
};
