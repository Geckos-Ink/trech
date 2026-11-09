// Expected output contract plus the exported suite family gate (family_checks) and the
// multi-run energy sweep gate (family_sweeps).
TRECH_VALIDATIONS["analytic_photo_fraction"] = {
  "schema": "trech_scenario_validation_v1",
  "scenario": "analytic_photo_fraction",
  "scope": "Analytic cross-check scenario: photoelectric process-branching fraction.",
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
  "family_case": "analytic_photo_fraction_cross_check",
  "family_summary": "The photofraction check is available and within tolerance (worst relative error at most 6%) and the photoelectric first-interaction classifier fired.",
  "family_checks": [
    {"id": "checks_present", "phase": "run_end", "field": "analytic_checks[?type=photo_fraction]", "aggregate": "count", "op": "ge", "expected": 1},
    {"id": "all_available", "phase": "run_end", "field": "analytic_checks[?type=photo_fraction].available", "aggregate": "all", "op": "eq", "expected": true},
    {"id": "all_within_tolerance", "phase": "run_end", "field": "analytic_checks[?type=photo_fraction].within_tolerance", "aggregate": "all", "op": "eq", "expected": true},
    {"id": "worst_relative_error", "phase": "run_end", "field": "analytic_checks[?type=photo_fraction].relative_error", "aggregate": "max", "op": "le", "expected": 0.06},
    {"id": "classifier_fired", "phase": "run_end", "field": "analytic_checks[?type=photo_fraction].primaries_photoelectric_first", "aggregate": "min", "op": "gt", "expected": 0}
  ],
  "family_sweeps": [
    {
      "family_case": "analytic_photo_fraction_energy_sweep",
      "summary": "Rerun at 10/20/30/50/100 keV (--param energy_mev): at every energy the check is available, the classifier fired and the measured photoelectric first-interaction fraction agrees with the Geant4-derived branching within a binomial |z| < 4; the measured fraction falls strictly with energy and spans at least 10x. The 6% relative flag is reported, not gated (low counts are Poisson-limited).",
      "runs": [
        {"id": "e10keV", "params": {"energy_mev": 0.01}},
        {"id": "e20keV", "params": {"energy_mev": 0.02}},
        {"id": "e30keV", "params": {"energy_mev": 0.03}},
        {"id": "e50keV", "params": {"energy_mev": 0.05}},
        {"id": "e100keV", "params": {"energy_mev": 0.1}}
      ],
      "checks": [
        {"id": "available", "each_run": true, "phase": "run_end", "field": "analytic_checks[?type=photo_fraction].available", "aggregate": "all", "op": "eq", "expected": true},
        {"id": "classifier_fired", "each_run": true, "phase": "run_end", "field": "analytic_checks[?type=photo_fraction].primaries_photoelectric_first", "aggregate": "min", "op": "gt", "expected": 0},
        {"id": "binomial_z", "each_run": true, "phase": "run_end", "field": "analytic_checks[?type=photo_fraction]", "derive": {"fn": "abs", "args": [{"fn": "binomial_z", "args": ["geant4_measured", "classical_predicted", "primaries_first_interaction"]}]}, "aggregate": "max", "op": "lt", "expected": 4.0},
        {"id": "strictly_decreasing", "phase": "run_end", "field": "analytic_checks[?type=photo_fraction].geant4_measured", "aggregate": "max", "series_aggregate": "strictly_decreasing", "op": "eq", "expected": true},
        {"id": "span_first_over_last", "phase": "run_end", "field": "analytic_checks[?type=photo_fraction].geant4_measured", "aggregate": "max", "series_aggregate": "first_over_last", "op": "ge", "expected": 10.0}
      ]
    }
  ],
  "physics_status": "configuration_or_transport",
  "limitations": "",
  "reference": "tools/validation/trech_validation/cases.py"
};
