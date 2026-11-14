// Expected output contract plus the exported suite family gate (family_checks).
TRECH_VALIDATIONS["hooks_track_ledger"] = {
  "schema": "trech_scenario_validation_v1",
  "scenario": "hooks_track_ledger",
  "scope": "hooks_track_ledger: 1.25 MeV gamma through a water cube with onTrackStart/onStep/onTrackEnd bookkeeping. Checks the track-hook contract: every Geant4 track starts and ends once, matches the engine's track count, and its ctx.track step count and length agree with its onStep calls.",
  "checks": [
    {"file": "trech_scores.jsonl", "phase": "run_end", "field": "n_events", "op": "eq", "expected": 300},
    {"file": "trech_scores.jsonl", "phase": "run_end", "field": "hook_emit_dropped_count", "op": "eq", "expected": 0, "missing": 0},
    {"tag": "track_ledger", "field": "events", "op": "eq", "expected": 300}
  ],
  "family_case": "hooks_track_ledger_consistent",
  "family_checks": [
    {"id": "all_identities_hold", "tag": "track_ledger", "field": "consistent", "op": "eq", "expected": true},
    {"id": "every_start_ends", "tag": "track_ledger", "field": "ends", "op": "eq",
     "reference": {"tag": "track_ledger", "field": "starts"}},
    {"id": "starts_match_engine_track_count", "tag": "track_ledger", "field": "starts", "op": "eq",
     "reference": {"tag": "track_ledger", "field": "tracksFromEvents"}},
    {"id": "one_primary_per_event", "tag": "track_ledger", "field": "primaries", "op": "eq",
     "reference": {"tag": "track_ledger", "field": "events"}},
    {"id": "secondaries_created", "tag": "track_ledger", "field": "creators.compt", "op": "gt", "expected": 0},
    {"id": "step_counts_agree", "tag": "track_ledger", "field": "stepMismatch", "op": "eq", "expected": 0},
    {"id": "lengths_agree", "tag": "track_ledger", "field": "lengthMismatch", "op": "eq", "expected": 0},
    {"id": "no_energy_gain", "tag": "track_ledger", "field": "energyGain", "op": "eq", "expected": 0},
    {"id": "engine_start_counter_matches", "file": "trech_scores.jsonl", "phase": "run_end",
     "field": "hook_on_track_start_count", "op": "eq",
     "reference": {"tag": "track_ledger", "field": "starts"}},
    {"id": "engine_end_counter_matches", "file": "trech_scores.jsonl", "phase": "run_end",
     "field": "hook_on_track_end_count", "op": "eq",
     "reference": {"tag": "track_ledger", "field": "ends"}},
    {"id": "no_track_callbacks_dropped", "file": "trech_scores.jsonl", "phase": "run_end",
     "field": "hook_on_track_end_dropped_count", "op": "eq", "expected": 0}
  ],
  "physics_status": "no_active_material_law",
  "limitations": "Hook-layer bookkeeping of Geant4 transport; the identities test the onTrackStart/onTrackEnd contract, not physics. Single-threaded: multi-worker hook order is not deterministic.",
  "reference": "tools/validation/trech_validation/cases.py"
};
