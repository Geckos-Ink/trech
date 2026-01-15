# Output Schema

TRECH writes JSONL (one JSON object per line). The current schema is small and stable,
so this file documents the exact fields emitted by the runtime.

## trech_provenance.jsonl

Each run emits at least two records (`run_start`, `run_end`). Fields:

- `phase` (string): `"run_start"` or `"run_end"`.
- `config_json` (string): full config JSON string from the JS experiment.
- `config_hash` (string): 64-bit FNV-1a hash of `config_json` in hex.
- `geant4_version` (string): version string from the active Geant4 build.
- `physics_list` (string): physics list name (e.g., `"QBBC"` or `"QBBC+Optical"`).
- `rng_engine` (string): CLHEP RNG engine name.
- `cli_args` (array[string]): argv snapshot used to start the run.
- `macro_path` (string): macro file path if provided, otherwise empty.
- `output_dir` (string): output directory path.
- `n_events` (number): event count used for the run.
- `seed` (number): RNG seed used for the run.

Example:

```json
{"phase":"run_start","config_json":"{\"run\":{\"nEvents\":100}}","config_hash":"f74a5db5b0f602a7","geant4_version":"geant4-11-1","physics_list":"QBBC","rng_engine":"HepJamesRandom","cli_args":["trech","run","exp.js"],"macro_path":"","output_dir":".","n_events":100,"seed":424242}
```

## trech_scores.jsonl

Each run emits a single `run_end` record with run-level scoring summaries.

- `phase` (string): `"run_end"`.
- `total_edep_mev` (number): total energy deposit (MeV).
- `optics_enabled` (boolean): whether optical physics was enabled.
- `optical_photon_tracks` (number): number of optical photon tracks created.
- `optical_photon_steps` (number): number of optical photon steps recorded.
- `optical_photon_track_length_mm` (number): total optical photon track length (mm).
- `n_events` (number): event count used for the run.
- `seed` (number): RNG seed used for the run.
- `physics_list` (string): physics list name used for the run.
- `multiscale_enabled` (boolean): whether multi-scale stubs were enabled.
- `multiscale_method` (string): multi-scale method label (config).
- `multiscale_mode` (string): multi-scale mode label (config).

Example:

```json
{"phase":"run_end","total_edep_mev":12.34,"optics_enabled":true,"optical_photon_tracks":42,"optical_photon_steps":512,"optical_photon_track_length_mm":987.6,"n_events":100,"seed":424242,"physics_list":"QBBC+Optical","multiscale_enabled":false,"multiscale_method":"stub","multiscale_mode":"auto"}
```

## trech_event_scores.jsonl

When event stratification is enabled (`stratify.enable: true`), each event emits
an `event_end` record with per-event scoring summaries.

- `phase` (string): `"event_end"`.
- `event_id` (number): Geant4 event ID.
- `total_edep_mev` (number): total energy deposit (MeV) for the event.
- `optical_photon_tracks` (number): number of optical photon tracks created.
- `optical_photon_steps` (number): number of optical photon steps recorded.
- `optical_photon_track_length_mm` (number): total optical photon track length (mm).
- `total_track_length_mm` (number): total track length across all tracks (mm).
- `total_step_count` (number): total step count across all tracks.
- `total_track_count` (number): total track count.
- `optics_enabled` (boolean): whether optical physics was enabled.
- `stratification` (object):
  - `enabled` (boolean): whether stratification was enabled.
  - `label` (string): `"predictable"`, `"exceptional"`, or `"unclassified"` (defaults; configurable via `stratify.label*`).
  - `reason` (string): short reason tag when exceptional, or empty.
  - `source` (string): `"thresholds"`, `"model"`, or `"disabled"`.
  - `exceptional` (boolean): whether the event is classified as exceptional.

Example:

```json
{"phase":"event_end","event_id":0,"total_edep_mev":0.12,"total_track_length_mm":14.2,"total_step_count":120,"total_track_count":8,"optical_photon_tracks":3,"optical_photon_steps":42,"optical_photon_track_length_mm":5.6,"optics_enabled":true,"stratification":{"enabled":true,"label":"predictable","reason":"","source":"thresholds","exceptional":false}}
```

## trech_event_features.jsonl

When `stratify.dumpFeatures` is enabled, each event emits an `event_features`
record with the raw feature set and labels useful for offline training.

- `phase` (string): `"event_features"`.
- `event_id` (number): Geant4 event ID.
- `features` (object): feature values keyed by name.
- `label` (string): stratification label.
- `exceptional` (boolean): whether the event is exceptional.
- `source` (string): stratifier source (`thresholds`, `model`, `disabled`).

Example:

```json
{"phase":"event_features","event_id":0,"features":{"total_edep_mev":0.12,"total_track_length_mm":14.2,"total_step_count":120,"total_track_count":8,"optical_photon_steps":42,"optical_photon_tracks":3,"optical_photon_track_length_mm":5.6},"label":"predictable","exceptional":false,"source":"thresholds"}
```

## trech_resim_queue.jsonl

When `stratify.dumpResimQueue` is enabled, exceptional events are queued for
re-simulation.

- `phase` (string): `"resim_candidate"`.
- `event_id` (number): Geant4 event ID.
- `label` (string): stratification label.
- `reason` (string): reason tag for the exceptional classification.
- `source` (string): stratifier source (`thresholds`, `model`, `disabled`).

Example:

```json
{"phase":"resim_candidate","event_id":7,"label":"exceptional","reason":"edep_mev_threshold","source":"thresholds"}
```
