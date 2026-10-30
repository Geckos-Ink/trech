// Expected output contract; numerical family tolerances remain in the referenced validators.
TRECH_VALIDATIONS["glass_of_water_spectral"] = {
  "schema": "trech_scenario_validation_v1",
  "scenario": "glass_of_water_spectral",
  "scope": "Chromatic-dispersion demo: a *white* (blackbody) source through the glass of water. Where glass_of_water_varied.js fires a narrow green band, this scenario fires the full visible spectrum, so each photon's wavelength is sampled across 380-750 nm and refracts at its OWN angle through the derived n(lambda) tables.",
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
