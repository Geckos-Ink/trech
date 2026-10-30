# Output Schema

TRECH writes JSONL (one JSON object per line). The current schema is small and stable,
so this file documents the exact fields emitted by the runtime.

## trech lab stdout

`trech lab` accepts one command object per input line. `simulate` without `events` selects a
round count from the current session's measured seconds/round EWMA; `simulate.events` is a
one-command override and positive `lab.roundsPerTick` is the persistent config override.
After each completed batch the CLI writes a machine-readable object:

- `phase`: `"lab_round_plan"`.
- `adaptive`: whether the completed batch count was selected by the planner.
- `target_hz`, `target_seconds`: configured real-time target.
- `planned_rounds`: actual Geant4 event/round count used for the batch.
- `observations`: timing observations incorporated so far.
- `last_wall_seconds`, `seconds_per_round_ewma`, `achieved_hz`: measured throughput.

`snapshot` returns canonical config JSON with the same object nested at `lab.roundPlanner`.
These values report scheduling/precision; they do not change or claim learned physics.
The first observation includes full Geant4 initialization. Compatible later batches reuse the
initialized kernel, so the EWMA adapts toward steady-state cost. Event count, seed and planner
settings may change between batches; kernel-bound changes are rejected with a restart-required
error. `achieved_hz` remains the authoritative measured rate.

## trech_provenance.jsonl

Each run emits at least two records (`run_start`, `run_end`). Fields:

- `phase` (string): `"run_start"` or `"run_end"`.
- `config_json` (string): full config JSON string from the JS experiment.
- `config_hash` (string): 64-bit FNV-1a hash of `config_json` in hex.
- `geant4_version` (string): version string from the active Geant4 build.
- `physics_list` (string): physics list name (e.g., `"QBBC"`, `"QBBC+Optical"`, or `"QBBC+DNA"`); a scenario may select another Geant4 reference list through the conditionally serialized config block `physics: {list, radioactiveDecayThresholdYears}` (e.g. `"QGSP_BIC_HP"` for thermal-neutron reactions).
- `rng_engine` (string): CLHEP RNG engine name.
- `cli_args` (array[string]): argv snapshot used to start the run.
- `macro_path` (string): macro file path if provided, otherwise empty.
- `output_dir` (string): output directory path.
- `n_events` (number): event count used for the run.
- `seed` (number): RNG seed used for the run.
- `determinism_mode` (string): normalized determinism mode (`"strict"` or `"predictive"`).
- `predictive_mode` (boolean): whether predictive mode was active for the run.
- `stratify_enabled` (boolean): whether stratification was enabled.
- `stratify_model_path` (string): configured model path (`stratify.modelPath`) if present.
- `stratify_model_hash` (string): 64-bit FNV-1a hash of model bytes when readable, otherwise empty.
- `stratify_model_hash_available` (boolean): whether model hash capture succeeded.
- `precision_profile` (string, optional): the precision profile the scenario resolved for this run (`preview`/`balanced`/`high`/`convergence`, or `custom` when an explicit control overrode the profile). Written only when the scenario declares a profile, so runs without one keep their historical record shape.
- `precision_axis_count` (number, optional): how many precision axes the scenario mapped onto that profile (the axes themselves travel in `config_json` and in `trech_scores.jsonl`).
- `stratify_total_count` (number): total stratified events (run-end record).
- `stratify_predictable_count` (number): predictable events (run-end record).
- `stratify_exceptional_count` (number): exceptional events (run-end record).
- `stratify_low_confidence_count` (number): events routed to the resim queue because their `onEventEnd` inference ran outside its model's trained domain (`stratify.resimOnLowConfidence`) — distinct from the feature-based `stratify_exceptional_count`.
- `stratify_unclassified_count` (number): unclassified events (run-end record).
- `stratify_source_thresholds_count` (number): threshold-classified events (run-end record).
- `stratify_source_model_count` (number): model-classified events (run-end record).
- `stratify_source_unknown_count` (number): unknown-source events (run-end record).
- `hooks_enabled` (boolean): whether any recognized hook callback was registered.
- `hooks_registered` (array[string]): registered hook names captured from config/runtime.
- `hooks_guardrail_max_step_callbacks` (number): configured `hooks.maxStepCallbacks` guardrail.
- `hooks_guardrail_max_emits_per_callback` (number): configured `hooks.maxEmitsPerCallback` guardrail.
- `hooks_guardrail_max_emit_payload_bytes` (number): configured `hooks.maxEmitPayloadBytes` guardrail.
- `hook_on_init_count` (number): run-level count for `onInit` dispatch points.
- `hook_on_run_start_count` (number): run-level count for `onRunStart` dispatch points.
- `hook_on_event_start_count` (number): run-level count for `onEventStart` dispatch points.
- `hook_on_step_count` (number): guardrail-clamped count for `onStep` dispatch points.
- `hook_on_step_raw_count` (number): raw `onStep` dispatch count before guardrail clamp.
- `hook_on_step_dropped_count` (number): dropped `onStep` count (`raw - clamped`).
- `hook_on_event_end_count` (number): run-level count for `onEventEnd` dispatch points.
- `hook_on_run_end_count` (number): run-level count for `onRunEnd` dispatch points.
- `hook_unknown_registered_count` (number): number of unrecognized hook names in registration.
- `hook_patch_count` (number): number of hook override patches applied during the run (`onInit` + runtime dispatch accounting).
- `hook_emit_count` (number): total number of `ctx.emit(...)` records emitted during the run (`onInit` + runtime dispatch accounting).
- `hook_emit_dropped_count` (number): total number of dropped `ctx.emit(...)` records due to guardrails or payload validation.
- `hook_predict_count` (number): total learned inferences run (`ctx.predict` calls + each
  `ctx.cascade` stage that ran + **N×K** for a `ctx.evolve` or `ctx.react` operator over N
  elements and K stages + **P×K** for a `ctx.interact` pair operator over P pairs and K stages);
  always 0 in strict mode. Batching never hides per-element inference.
- `hook_predict_out_of_domain_count` (number): subset of `hook_predict_count` whose inputs fell
  **outside the model's trained domain** — the auditable low-confidence / extrapolation tally (a
  cascade contributes its extrapolating stages, a `ctx.predict` contributes 1, and
  `ctx.evolve`/`ctx.react` contribute each out-of-domain element-stage, `ctx.interact` each
  out-of-domain pair-stage).
- `nuclear_enabled` (boolean): whether nuclear cycle analysis was enabled.
- `nuclear_cycle_count` (number): number of configured/analyzed nuclear cycles.
- `nuclear_consistent_cycle_count` (number): number of nuclear cycles that passed all consistency checks.
- `system_event_count` (number): number of event summaries aggregated at run end.
- `system_event_edep_mean_mev` (number): mean event energy deposit (MeV).
- `system_event_edep_variance_mev2` (number): variance of event energy deposit (MeV^2).
- `system_event_edep_stddev_mev` (number): standard deviation of event energy deposit (MeV).
- `models_loaded` (array[string]): names of successfully loaded scenario-registry models, sorted.
- `model_artifacts` (object, optional): the scenario model registry snapshot described below.
  Present on both provenance phases when a nonempty registry was supplied by `JsRuntime`.

Example:

```json
{"phase":"run_start","config_json":"{\"run\":{\"nEvents\":100}}","config_hash":"f74a5db5b0f602a7","geant4_version":"geant4-11-1","physics_list":"QBBC","rng_engine":"HepJamesRandom","cli_args":["trech","run","exp.js"],"macro_path":"","output_dir":".","n_events":100,"seed":424242,"determinism_mode":"strict","predictive_mode":false,"stratify_enabled":false,"stratify_model_path":"","stratify_model_hash":"","stratify_model_hash_available":false,"stratify_total_count":0,"stratify_predictable_count":0,"stratify_exceptional_count":0,"stratify_unclassified_count":0,"stratify_source_thresholds_count":0,"stratify_source_model_count":0,"stratify_source_unknown_count":0,"hooks_enabled":false,"hooks_registered":[],"hooks_guardrail_max_step_callbacks":100000,"hooks_guardrail_max_emits_per_callback":0,"hooks_guardrail_max_emit_payload_bytes":0,"hook_on_init_count":0,"hook_on_run_start_count":0,"hook_on_event_start_count":0,"hook_on_step_count":0,"hook_on_step_raw_count":0,"hook_on_step_dropped_count":0,"hook_on_event_end_count":0,"hook_on_run_end_count":0,"hook_unknown_registered_count":0,"hook_patch_count":0,"hook_emit_count":0,"hook_emit_dropped_count":0}
```

### Scenario model artifact manifest

`model_artifacts` has `schema: "trech_model_artifacts_v1"` and `models: [...]`, sorted by
registry name. It snapshots **all** scenario-declared registry models, including ordinary
point/cascade models, operators, and failed loads. GeantRunner captures the registry before
constructing run actions; the same snapshot enters `run_start`, `run_end` and run-end scores.
No registry means no field. Config JSON and its legacy FNV-1a-64 hash are unchanged.

Each entry carries the same fields as `ctx.operatorCatalog()`:

- `name`, authored `path`, `scale`, `operator_role`, `element_kind`, `required_context_keys`.
- `loaded` (boolean), `load_note` (loader diagnostic), `model_id` (loader format ID, empty on failure).
- `content_id`: `fnv1a64:<16 lowercase hex digits>`, or null on failed load.
- `sha256`: SHA-256 as 64 lowercase hex digits, or null on failed load.
- `size_bytes`: exact artifact byte count, or null on failed load.
- Named `inputs`/`outputs` (empty on failure), `feature_units` (complete maps or null),
  `domain_measured`, `trained_scale_bands`, `holdout` (`{r2_min,samples}` or null),
  `output_accuracy` (available per-output `r2`/`mae`/`rmse`; unknown metrics absent).

Both identities hash the **same byte snapshot consumed by the loader**, including whitespace,
once on successful load. Reading metadata never reopens paths, performs inference or draws RNG.
Replacing/deleting a file cannot relabel already-loaded weights; an explicit reload observes the
new bytes. Failed reloads clear identities and size. Entries describe availability, not whether
inference ran, compatible runtime inputs, authenticity or physical validation. Carried metrics
remain model declarations. Separate stratifier and optics-surrogate loaders are outside this
registry manifest; their existing reporting is unchanged. Older output can lack the manifest and
must not receive reconstructed identities from current files. Optional Torch snapshot loading has
not been runtime-validated while the separately tracked Torch integration blockers remain.

## trech_scores.jsonl

Each run emits a single `run_end` record with run-level scoring summaries.

- `phase` (string): `"run_end"`.
- `total_edep_mev` (number): total energy deposit (MeV).
- `volume_edep_mev` (object): per-volume energy deposit map keyed by volume name (MeV, only present when at least one volume has `scoreEdep` enabled).
- `optics_enabled` (boolean): whether optical physics was enabled.
- `optical_photon_tracks` (number): number of optical photon tracks created.
- `optical_photon_steps` (number): number of optical photon steps recorded.
- `optical_photon_track_length_mm` (number): total optical photon track length (mm).
- `n_events` (number): event count used for the run.
- `seed` (number): RNG seed used for the run.
- `physics_list` (string): physics list name used for the run (e.g., `"QBBC+DNA+Chem"`).
- `determinism_mode` (string): normalized determinism mode (`"strict"` or `"predictive"`).
- `predictive_mode` (boolean): whether predictive mode was active for the run.
- `hooks_enabled` (boolean): whether any recognized hook callback was registered.
- `hooks_registered` (array[string]): registered hook names captured from config/runtime.
- `hooks_guardrail_max_step_callbacks` (number): configured `hooks.maxStepCallbacks` guardrail.
- `hooks_guardrail_max_emits_per_callback` (number): configured `hooks.maxEmitsPerCallback` guardrail.
- `hooks_guardrail_max_emit_payload_bytes` (number): configured `hooks.maxEmitPayloadBytes` guardrail.
- `hook_on_init_count` (number): run-level count for `onInit` dispatch points.
- `hook_on_run_start_count` (number): run-level count for `onRunStart` dispatch points.
- `hook_on_event_start_count` (number): run-level count for `onEventStart` dispatch points.
- `hook_on_step_count` (number): guardrail-clamped count for `onStep` dispatch points.
- `hook_on_step_raw_count` (number): raw `onStep` dispatch count before guardrail clamp.
- `hook_on_step_dropped_count` (number): dropped `onStep` count (`raw - clamped`).
- `hook_on_event_end_count` (number): run-level count for `onEventEnd` dispatch points.
- `hook_on_run_end_count` (number): run-level count for `onRunEnd` dispatch points.
- `hook_unknown_registered_count` (number): number of unrecognized hook names in registration.
- `hook_patch_count` (number): number of hook override patches applied during the run (`onInit` + runtime dispatch accounting).
- `hook_emit_count` (number): total number of `ctx.emit(...)` records emitted during the run (`onInit` + runtime dispatch accounting).
- `hook_emit_dropped_count` (number): total number of dropped `ctx.emit(...)` records due to guardrails or payload validation.
- `hook_predict_count` (number): total learned inferences run (`ctx.predict` calls + each
  `ctx.cascade` stage that ran + **N×K** for a `ctx.evolve` or `ctx.react` operator over N
  elements and K stages + **P×K** for a `ctx.interact` pair operator over P pairs and K stages);
  always 0 in strict mode. Batching never hides per-element inference.
- `hook_predict_out_of_domain_count` (number): subset of `hook_predict_count` whose inputs fell
  **outside the model's trained domain** — the auditable low-confidence / extrapolation tally (a
  cascade contributes its extrapolating stages, a `ctx.predict` contributes 1, and
  `ctx.evolve`/`ctx.react` contribute each out-of-domain element-stage, `ctx.interact` each
  out-of-domain pair-stage).
- `nuclear_enabled` (boolean): whether nuclear cycle analysis was enabled.
- `nuclear_cycle_count` (number): number of configured/analyzed nuclear cycles.
- `nuclear_consistent_cycle_count` (number): number of nuclear cycles that passed all consistency checks.
- `nuclear_cycles` (array[object]): per-cycle details including source/target isotope hints, macro phase/density deltas, forward/backward reaction Q-values, and charge/baryon conservation checks.
- `models_loaded` (array[string]): successfully loaded scenario-registry model names, sorted.
- `model_artifacts` (object, optional): the same [scenario registry snapshot](#scenario-model-artifact-manifest)
  recorded in provenance; omitted when no registry was supplied.
- `system_enabled` (boolean): whether system-level aggregation is enabled.
- `system_mode` (string): system aggregation mode label (config).
- `system_frame` (string): system frame label (config, point-agnostic by default).
- `system_ensemble` (string): free-form system/ensemble label (config).
- `system_volume_mm3` (number): reference volume used for system densities (mm^3).
- `system_volume_source` (string): `"config"`, `"medium_box"`, `"world"`, `"disabled"`, or `"unknown"`.
- `system_edep_mev_per_mm3` (number): total energy deposit density (MeV/mm^3).
- `system_optical_track_length_mm_per_mm3` (number): optical photon track length density (mm/mm^3).
- `system_optical_tracks_per_mm3` (number): optical photon track density (tracks/mm^3).
- `system_optical_steps_per_mm3` (number): optical photon step density (steps/mm^3).
- `system_event_count` (number): number of events included in run-level moment summaries.
- `system_event_edep_mean_mev` (number): mean event energy deposit (MeV).
- `system_event_edep_variance_mev2` (number): variance of event energy deposit (MeV^2).
- `system_event_edep_stddev_mev` (number): standard deviation of event energy deposit (MeV).
- `multiscale_enabled` (boolean): whether multi-scale stubs were enabled.
- `multiscale_method` (string): multi-scale method label (config).
- `multiscale_mode` (string): multi-scale mode label (config).
- `chemistry_enabled` (boolean): whether chemistry config was enabled.
- `chemistry_model` (string): chemistry model label (config).
- `chemistry_solver` (string): chemistry solver label (config).
- `dna_physics_enabled` (boolean): whether DNA physics replacement was activated.
- `dna_physics_option` (number): DNA physics option number (0 for default).
- `dna_chemistry_enabled` (boolean): whether DNA chemistry stage was activated.
- `dna_chemistry_option` (number): DNA chemistry option number (0 for default).
- `stratify_enabled` (boolean): whether stratification was enabled.
- `stratify_total_count` (number): number of events evaluated for stratification.
- `stratify_predictable_count` (number): events labeled as predictable.
- `stratify_exceptional_count` (number): events labeled as exceptional.
- `stratify_low_confidence_count` (number): events routed to resim because their inference ran out-of-domain (`stratify.resimOnLowConfidence`), distinct from the feature-based exceptional count.
- `stratify_unclassified_count` (number): events labeled as unclassified.
- `stratify_source_thresholds_count` (number): events classified by thresholds.
- `stratify_source_model_count` (number): events classified by ML model.
- `stratify_source_unknown_count` (number): events with unknown stratifier source.
- `stratify_model_path` (string): configured stratify model path.
- `stratify_model_hash` (string): 64-bit FNV-1a model file hash when readable, otherwise empty.
- `stratify_model_hash_available` (boolean): whether model hash capture succeeded.

Example:

```json
{"phase":"run_end","total_edep_mev":12.34,"volume_edep_mev":{"cnt_stub":0.56},"optics_enabled":true,"optical_photon_tracks":42,"optical_photon_steps":512,"optical_photon_track_length_mm":987.6,"n_events":100,"seed":424242,"physics_list":"QBBC+Optical","determinism_mode":"predictive","predictive_mode":true,"hooks_enabled":true,"hooks_registered":["onStep"],"hooks_guardrail_max_step_callbacks":2000,"hooks_guardrail_max_emits_per_callback":4,"hooks_guardrail_max_emit_payload_bytes":512,"hook_on_init_count":1,"hook_on_run_start_count":1,"hook_on_event_start_count":100,"hook_on_step_count":2000,"hook_on_step_raw_count":2500,"hook_on_step_dropped_count":500,"hook_on_event_end_count":100,"hook_on_run_end_count":1,"hook_unknown_registered_count":0,"hook_patch_count":1,"hook_emit_count":2403,"hook_emit_dropped_count":12,"system_enabled":true,"system_mode":"steady_state","system_frame":"point_agnostic","system_ensemble":"h2o_bulk","system_volume_mm3":1000000.0,"system_volume_source":"medium_box","system_edep_mev_per_mm3":0.00001234,"system_optical_track_length_mm_per_mm3":0.0009876,"system_optical_tracks_per_mm3":0.000042,"system_optical_steps_per_mm3":0.000512,"multiscale_enabled":false,"multiscale_method":"stub","multiscale_mode":"auto","chemistry_enabled":false,"chemistry_model":"dna_water","chemistry_solver":"stub","dna_physics_enabled":false,"dna_physics_option":0,"dna_chemistry_enabled":false,"dna_chemistry_option":0,"stratify_enabled":true,"stratify_total_count":100,"stratify_predictable_count":96,"stratify_exceptional_count":3,"stratify_unclassified_count":1,"stratify_source_thresholds_count":70,"stratify_source_model_count":30,"stratify_source_unknown_count":0,"stratify_model_path":"models/stratify.pt","stratify_model_hash":"9f0a4ac8a57c0f31","stratify_model_hash_available":true}
```

## Material probes and optional particle-interaction samples

`materialProbe.enable` reports referenced materials under scores `material_probes[]` and hooks
`ctx.materials[name]`: `available`, density/electron density, mean excitation energy, radiation
length, total/per-element number densities and `elements[]` (symbol, Z, atomic mass, mass fraction).
Composition probes describe the constructed Geant4 material, not atomistic molecular bonding.

Optional config `materialProbe.interactions` declares `particle`, `processes[]` and positive
finite `energiesMeV[]`. All three are required when that object is present. It is serialized
only when requested, preserving existing config bytes/hashes. After initialization each material
optionally carries `interactions[]`: `{particle,energy_mev,available,source,cross_sections_per_mm}`.
The numeric object is keyed by declared process names. Unavailable particles/processes or failed
queries carry `available:false` plus `note` and **omit** numeric results. Genuine zero cross sections
remain valid. These are `G4EmCalculator` particle-response data, **not Monte Carlo tallies**.
No interaction samples are added to historical composition-only outputs.

Optional `materialProbe.includeIsotopes:true` adds `elements[].isotopes[]` records:
`{z,a,neutrons,abundance,atomic_mass_amu,atoms_per_cm3}` from constructed Geant4 isotope
tables. With these records, `elements[].natural_isotopic_composition` distinguishes natural
composition from explicitly selected isotopes, including mixtures of the same element.
`a` is the nucleon count and `neutrons=a-z`; abundance is an atom fraction within
that element component. `numberDensityPerCm3.<symbol>` sums **all** isotope components
with that symbol. Isotope records are absent without the option. Presence in a Geant4 mass
table does not establish nuclear stability or a supported isotope-dependent process.
The generic inference seed exposes recorded isotope fields at
`material.<name>.isotope.Z<z>.A<a>.{neutrons,atomic_mass_amu,number_density_per_cm3}`;
same-nuclide number densities are summed. Missing fields/nuclides remain absent.

Optional `materialProbe.nuclearSamples:{configurations,seed}` conditionally serializes a
1–32 configuration request and enables isotope inventories. Explicit-isotope element entries
carry `nuclear_samples:{z,a,available,length_unit:"fm",time_kind:"ensemble_index",seed,source,
configurations:[{protons:[[x,y,z],...],neutrons:[[x,y,z],...]}]}`. `source` names Geant4's
`G4Fancy3DNucleus` and its initial-state scope. Unsupported requests (including A=1 or A>250)
carry `available:false`/`note` and omit configurations. No natural isotope is silently selected.
An isolated CLHEP engine preserves transport RNG state. Samples are initial configurations,
not nuclear wavefunctions or physical-time trajectories. No field is emitted without opt-in.

Material component config accepts positive integer `atoms` instead of mass `fraction`;
all components in a stoichiometric material must use `element` + `atoms`. Optional positive
integer `massNumber` selects a pure isotope with Geant4's mass, in either element mode.
`atoms`/`fraction` are mutually exclusive. Unsupported stoichiometric elements/isotopes
fail closed. New fields are conditionally serialized; legacy mass-fraction config stays stable.

Optional generic config `hooks.inputs` is an object snapshot of authored scenario state,
included in canonical config JSON/hash/provenance. It is absent by default and does not
apply physics or expose new hook operations. Chemistry mode records its canonical explicit
structure and reaction plan here, so position/connectivity edits are reproducible even at
unchanged transport composition.

### Chemistry workspace sideband

`chemistry_mode.js` emits `chemistry_state` with schema `trech_chemistry_state_v1`:
`structure:{atoms:[{element,position:[x,y,z],massNumber?}],bonds:[[a,b,order?]],charge}`,
live `atoms` facts (Z, requested A, neutron count or null for natural mixtures, atomic
mass/isotope inventory), electron bookkeeping, mode, capability availability/reasons,
`geant4_material`, nullable `particle_response` and optional canonical `reaction_plan`.
Positions are Å and bonds/orders/charge are authored, not predicted. An omitted order stays
unknown (the existing scaffold fixtures record connectivity only). The material is a
homogeneous transport proxy; this graph does not replace Geant4 transport geometry.
`expected_particle_model_sha256` identifies the pinned expected models when inference runs.
Natural-neutral CHNO can use existing photon models; unsupported isotope/ion/non-CHNO and
strict-mode results remain null. General stability/polarization remain unavailable.

Its `material_frame` uses the existing native-unit contract (`length_unit:"angstrom"`,
`up_axis:"y"`, zero physical/playback time, emitted display radii/colors and declared bond
pairs). No product motion or stability is inferred from that frame.

Optional `chemistry_reaction_step` carries zero-based `step`, one-element-array species
`inventory`, nullable `ctx.react` `result` (including selection/stage/conservation/RNG
trace), `status` (`strict_disabled`, `model_unavailable`, `supplied_model`, `blocked`),
`physical_time_s:null` and a scope label. Species structures derive element/isotope/net-charge
conservation; missing models/inputs and strict mode cannot mutate/draw. Supplied-model
execution is not a scientific-validation claim. There is no calibrated physical reaction
clock or atomistic path. Studio shows these payloads in Chemistry/Emits and feeds the held
structure frame to the existing renderer. See [`chemistry_mode.md`](chemistry_mode.md).

The workbench additionally accepts `trech_chemistry_scene_v1` JSON scenes through `scene_json`
or `scene_file`/`TRECH_READ_JSON`. Canonical `hooks.inputs.scene` contains placed/rotated named
molecules, explicit links, a time kind and optional geometry-bound density frames. Named owners
and `(molecule,local atom index)` endpoints preserve multiple distinct molecular descriptions;
the homogeneous Geant4 transport proxy remains separate. See the full
[`scene/field contract`](chemistry_probability.md).

`quantum_frame` schema `trech_quantum_frame_v1` carries `time_kind` (`snapshot`, `physical`,
`parameter_scan`), explicit `cursor`, nullable `physical_time_s`, placed `structure` (including
parallel `molecule_ids`), `fields[]`, `omitted_fields[]` and `scope`. Each field has `id`,
`particle`, shared `owner_ids`, explicit spatial/density units, declared `source`, `grid`
(`shape`, `origin`, isotropic `spacing`, C-order x/y/z `values`), display `isovalue`, optional
supplied point `samples` and `sampling_note`. Source declarations are externally supplied;
they are not authenticated by parsing. Electron fields require explicit `geometry` binding
to the placed owner atoms/isotopes/net charge; editing geometry rejects stale fields. Repeated
field IDs cannot change particle or units. Strict mode omits imported `inferred` fields and
discloses each omission; independent comparisons remain labelled and carry no inference count.
Missing fields clear the previous density at that cursor instead of silently carrying it forward.

`quantum_frame.particle_inventory` reports integer `protons`, `electrons` (live Geant4 Z minus
net charge), and `neutrons` (null when any isotope is unresolved). Optional `electronic_structure`
contains geometry binding, source, electron_count, total_energy_hartree, optional dipole_debye
and complete `orbitals:[{index,energy_hartree,occupation,field_id?}]`. Occupations in [0,2] sum
to electron_count. A referenced field must agree in index/energy/occupation/source and joint
geometry. Each orbital field has `orbital` metadata and `density_unit:probability/angstrom^3`:
its grid is |ψ|², not occupation-weighted total number density. The engine compares the supplied
electron count with live Geant4 facts. Strict suppresses inferred electronic structures as well
as inferred fields. Independent quantum references remain comparisons, with zero inference count.

`chemistry_state.scene` now carries initial entities/links and empty frames; full grid sequences
remain in hashed `provenance.config_json.hooks.inputs.scene`, named by `scene_restore_source`.
This avoids exceeding one capped emit by repeating the full sequence; Studio restores via
provenance. Old run summaries with inline full scenes remain readable.

Scalar fields optionally add `quantity` (`number_density`, `orbital_probability`,
`density_difference`). Negative grid values are accepted only for `density_difference`, which
requires `comparison.definition`. Optional real-orbital `amplitude:{unit:"angstrom^-3/2",values}`
must have the same finite point count/grid geometry and requires orbital metadata. Signed
amplitude is distinct from the cell-average probability grid; global sign is not charge.

The engine recomputes `statistics` from grid values via generic C++ `TRECH_FIELD_STATS`:
`integral`, `absolute_integral`, `positive_integral`, `negative_integral`, `minimum`, `maximum`
and 99 `mass_levels:[{fraction,threshold,enclosed_fraction,voxel_count}]`. Levels rank absolute
values, include all threshold ties, and use spacing³ cell quadrature. Zero fields have no levels.
Imported statistics are not trusted. These diagnostics are not inference and do not normalize
values. Source claims and comparison definitions remain externally supplied metadata.
Chemistry explicitly caps each emit at 8 MiB to carry phase/difference records.

Optional total-electron fields carry `energy_components:[{energy_hartree,occupation,
orbital_indices,values,...}]`. Values are occupation-weighted nonnegative electron densities on
the same grid and must sum to its values (relative tolerance 1e-4). Components must exactly
cover the complete occupied spectrum without duplicate members; energies agree within 1e-8 Eh,
occupations sum, source kind and joint geometry agree. They require `electrons/angstrom^3` and
an electronic spectrum; inspection rejects components when that spectrum is absent or null.
Degenerate-state grouping is a solver result, not a principal-shell label.

Optional `electronic_structure.radial_profiles` contains up to eight geometry-bound nucleus
centres (`atom_index`, `owner_id`, `element`, `centre_angstrom`), strictly increasing finite
`radii_angstrom` (starting at zero) and `diameter_angstrom`, plus complete occupied `levels`.
Each level has spectrum-matching `orbital_indices`, `energy_hartree`, `occupation`, nonnegative
`density_average_per_angstrom3`, `radial_probability_per_angstrom` arrays on the radial axis,
and three `diameter_density_per_angstrom3` arrays on the diameter axis. TRECH recomputes
`total_radial_probability_per_angstrom` and `total_diameter_density_per_angstrom3` from levels.
The reference generator records spherical-average density and its 4πr² radial measure;
profiles are joint-system contributions about a nucleus, not atom-owned electron populations.
Imported profile source/method/quadrature/finite-integral metadata are supplied claims, not
independently verified accuracy. Profile axes cap at 2049 points, groups at 32. Strict-mode
suppression follows the containing electronic structure's source.

`chemistry_nuclear_ensemble` carries `{ensembles:[{element,data:<nuclear_samples>}],scope}`.
Each available `data` additionally carries `inventory:{protons,neutrons,nucleons,nuclei_per_configuration:1}`.
Each configuration's `statistics` has `centre_fm` and per-species `count`, nullable
`rms_radius_fm` (null for absent species), `max_radius_fm`. `radial_distribution` reports
`bin_width_fm:0.5`, 16 integer proton_counts/neutron_counts bins across all configurations,
`last_bin_overflow:true`, configuration count and sampled max radius. Radii are distances from
each configuration's nucleon centroid; these are finite counts, not shell occupation or volume
normalized density. Position arrays are unchanged by diagnostics.
Studio offers separate fm views of both/proton/neutron initial states per nuclide. Ensemble
indices and parameter values are explicitly nonphysical clocks; physical density frames retain
their supplied seconds. Neither particle-sample index nor density isosurface implies a persistent
electron trajectory, a hard molecular boundary, or a predicted atomistic reaction.

## trech_hook_emits.jsonl

When hooks call `ctx.emit(tag, payload)`, records are appended at run end.

- `phase` (string): `"hook_emit"`.
- `hook` (string): callback name (`onInit`, `onRunStart`, `onEventStart`, `onStep`, `onEventEnd`, `onRunEnd`).
- `event_id` (number): event id when emitted from event/step callbacks, otherwise `-1`.
- `step_index` (number): step index when emitted from `onStep`, otherwise `-1`.
- `tag` (string): user-provided emit tag.
- `payload` (object/string/array/number/boolean/null): parsed JSON payload when possible; raw string fallback if payload was not valid JSON.

The reusable solution recipe emits `process_recipe_state`: detached inventory/thermal `state`,
stage/call/elapsed clock, completion/status and the active process report. Shared operator bindings
report `{ran,accepted,contract_id,error,engine}`; `engine` holds the original operator selection,
trace and inference/RNG accounting. A rejected proposal may have `ran:true,accepted:false`:
state/clock were not committed, but inference/draws remain counted. Missing operators/inputs
block without synthetic motion. `hooks.inputs.recipe.operator_contracts` records data-only
`trech_process_operator_v1` unit/role/kind/topology/provenance declarations in the config/hash.
See [process contracts and error codes](solution_processes.md#shared-operator-contracts).

The glass-furnace scenario (`glass_from_sand.js`) emits `glass_furnace_scenario` (Geant4 material
probes, cascade-inferred onsets, declared channels/conserved elements), a `material_frame` per tick
whose per-cell colour encodes that cell's CURRENT material class (a labelled representation
choice), and `glass_furnace_summary` (created-product inventory, per-material and per-pair-material
selection, accepted channel counts, coldest reaction temperatures vs the inferred onsets, exact
per-element atom balance, the operator/cascade inference split, and the shared
`trech_operator_reference_pair_v1` block that grades its distilled trained operators against the
illustrative family they came from). With `emit_training_rows` it also emits the deterministic
harvest sidebands `thermal_sample_<kind>` / `chemistry_sample_<kind>`, each carrying the teacher
name and an expandable `samples[]` of that teacher's exact inputs/outputs for the states the run
visited.

The molecular comparison series emits `molecular_prediction` per held-out scan angle
(`molecule`, `group`, `angle_deg`, live-probe-derived `inputs`, `charges_e`,
`relative_energy_kcal_mol`, independently calculated `reference_*`, engine `coverage` /
`accuracy`, `geant4_edep_mev`, `expected_model_sha256` and explicit `physics_scope`). In strict mode
predicted charges/energy and coverage/accuracy are null. `molecular_summary` carries the
mode/sample count and pinned quantum/PubChem comparisons. Its `material_frame` uses Å
coordinates, `physical_time_s:0`, a separate playback clock and `clock_text` identifying an
imposed torsion parameter scan. Bubble radius/colour are partial-charge representations,
not electronic density; Geant4 transport deposits do not determine the QM-trained response.
See [`molecular_series.md`](molecular_series.md) for the complete scope.

The second molecular group also emits `particle_response` within `molecular_prediction`:
query `energy_ev`, per-atom response arrays, atomic inference count/trace, pooled learned
embeddings, molecular `sigma_barn` (ordered phot/compt/Rayl), molecular cascade trace and
explicit Geant4-trained label source/scope. Strict mode leaves it null. Independent held-out
Geant4 comparison values travel separately as `particle_reference_sigma_barn`; fixture hashes
are labelled `expected_particle_model_sha256`. The new group has 48 frames in separate
`torsion` and `particle_response` streams (24 each). A photon-energy inference sweep holds
scaffold/quantum charges fixed; its queried energy differs from the run's fixed 3 keV beam.
Purple halo volume encodes learned atomic photoelectric response with a fixed display scale.
It is not electronic density or a predicted orbital dimension. Full training/MC scope:
[`particle_molecule.md`](particle_molecule.md).

Scenario-specific tags are intentionally sideband data, not core schema fields.
Current validation/viz tags include `md_snapshot`, `osmotic_particles`,
`efflux_snapshot`, `efflux_summary`, `electrolysis_snapshot`,
`h2o_cycle_summary`, and the Briggs–Rauscher oscillator's `br_frame` (payload:
`time_s`/`physical_time_s`, `tau`, `phase`, `beaker_rgb`/`color_rgba`, amber/blue
`intensities`, emergent `concentrations` [I₂/I⁻/HIO₂/Mn(III)/reservoir], `cycle_index`)
and `briggs_rauscher_summary`.

The independent initial references add `crystallization_reference` (comparison step, conserved
Na/Cl/solvent parcel inventory, occupied lattice sites, separately labelled Geant4 material/event
facts) and `aerodynamics_reference` (SI time, CFL step count, declared cell columns and numeric
rows, conserved integrals per unit span, integrated boundary/wall exchange and balance residual).
Euler conservation vectors are ordered mass, x momentum, y momentum, total energy; they describe
the gas domain, including external wall momentum exchange. Both records declare their comparison
scope and `learned_prediction_available:false`; neither is a strict Geant4 higher-scale tally.
See [process reference scope](process_references.md).

Observer-scale particle scenarios use `material_frame` (payload:
physical `time_s`/`physical_time_s`, observer `playback_time_s`, explicit `time_scale`,
`minute`, ordered `phase`, `positions_mm[]`, matching `colors_rgba[]`, material
`counts`, `clock`, `motion_scope`, and the explicit `representation_override`). Stateful material
solvers may additionally emit stable ordered `particle_ids[]` and a `physics_state` snapshot;
consumers must preserve that ordering rather than treating every frame as newly generated points. Positions are
currently emitted z-up; Studio and classic `trech-viz` perform the same axis relabel to their
y-up view. Optional `up_axis` overrides that convention. `stream` identifies independent timelines;
Studio's Processes selector chooses one stream for held-frame replay. Nonphysical comparison
clocks may use numeric `time` plus `time_unit:"step"`, omitting physical seconds. Studio preserves
that clock unit; classic captures use the supplied `clock_text`. Optional
`show_geant4_scene:false` hides unrelated Geant4 probe geometry in Studio/classic captures and is
reported as a representation choice, without altering transport. Default visibility is unchanged.
Optional `clock_text`, `hud_lines[]` and `legend:[{label,color_rgba}]` supply textual inspection
and display annotations. Studio retains bounded strings from each held frame (six HUD rows,
twelve legend entries); Processes and optional capture footers show the same recorded text.
Captions do not infer a physical clock or convert comparison inventories into Geant4 tallies.
Frames are held, never interpolated. The beaker additionally emits
`rendered_layer_order` + `beaker_summary`; the lava-lamp default emits 121 frames spanning 0–600
physical seconds from the same persistent parcel state, while typed duration/tick overrides change
only the integration horizon and output cadence. It also emits
`lava_lamp_scenario`/`lava_lamp_summary`, including conditions, inferred coefficients, solver
metrics, stable parcel identity, and a `precision` split across spatial parcel discretisation,
maximum physics step, output tick cadence, and representation-only surface grid. Lava frames also
carry an optional `render_surface` contract (`mode=metaball`, Gaussian `sigma_mm`, `iso_level`,
`grid_spacing_mm`, clip cylinder, optical surface values, `positions_unmodified=true`). Viewers may
reconstruct a fused surface from it, but must not move/interpolate centres or feed the field back
into simulation. The optional `fluid_necking` sub-object declares `mode=pair_gaussian`, minimum
and maximum pair distances, samples per pair, weight, and
`preserves_component_topology=true`. Eligible in-gap splats must fade to zero at the maximum
distance and may be generated only between centres already connected by the declared observer
interface radius; consumers must not use them to join components. Frames without this optional
contract retain their normal point/sprite rendering. Lava frames additionally report
`counts.parcel_surface_components` (the retained fine interface) and
`counts.rendered_surface_components` (the observer fluid interface), plus `topology_events` with
`merges_since_prior_frame`/`splits_since_prior_frame`. These are computed by matching component
membership across stable `particle_ids`, using the analytically derived connection radius of the
declared Gaussian isosurface. `parcel_surface_merges_since_prior_frame` and
`parcel_surface_splits_since_prior_frame` preserve the prior fine-interface lineage independently.
The summary aggregates both component ranges, merge/split totals, and frames containing merged
bodies; renderers must not synthesize or rewrite either lineage.
`physics_state` also exposes `wax_centroid_xy_mm` and
`mean_horizontal_speed_mm_per_s`. The lava summary aggregates
`centroid_x_range_mm`/`centroid_y_range_mm`, `centroid_xy_path_mm`,
`centroid_azimuth_bins_occupied`, maximum mean horizontal speed, the initial microstate-selected
convection axis, and handedness. These values make volumetric motion falsifiable independently of
camera orbit; a renderer must not add x/y movement to satisfy them.
Validation cases should treat these
payloads as scenario contracts and keep them documented near each scenario.
Inference stage traces report missing dependencies through `missingInputs`. A cascade stage
missing a required input publishes no outputs. Batched stages skip only affected elements/pairs;
`ran` means at least one actual evaluation and `elementsMatched`/`pairsMatched` count evaluations.
Blocked evaluations add no `hook_predict_count`, OOD count, state mutation or discrete RNG draw.
A supplied numeric zero remains a valid input. Point prediction returns `null` when inputs are absent.

**3D observer contract extensions (optional, all consumers must ignore what they do not draw).**
Every hook-layer README scenario uses them so its classic 3D replay is its own solver state:

- `length_unit` (string, default `"mm"`): unit of the positions. A non-mm frame (`"angstrom"`,
  `"nm"`, `"sim_unit"`) is scale-independent of the Geant4 mm scene, which is then not drawn
  around it. Such frames may name the array `positions` instead of `positions_mm`.
- `up_axis` (`"z"` default, relabelled z-up → y-up as before; `"y"`: already in the viewer's y-up
  frame, used verbatim — e.g. molecules, or cells emitted in a y-up Geant4 geometry frame).
- `radii` (array[number], one per point): true-size spheres (atoms, parcels) in `length_unit`.
- `bonds` (array[[i, j]]): point-index pairs drawn as bonds; out-of-range pairs are dropped.
- `vectors` (array[[x,y,z]], one per point): arrows anchored at the point (magnetization, drift).
- `apparatus` (array[object]): scenario-owned, possibly MOVING geometry in the frame's units and
  axis convention: `{shape: "box"|"cylinder"|"sphere"|"segment"|"mesh", center, size, radius,
  height, axis, from/to (segment), vertices/faces (mesh), color_rgba, style ("wire"|"open"|
  surface), label}` — a shaken glass, a piston, a periodic cell, a deforming triangulated membrane.
- `legend` (array[{label, color_rgba}]), `hud_lines` (array[string], ≤ 6): scenario-emitted
  observables printed by the viewer (emergent values, never typed targets).
- `clock_text` (string): the solver's own clock label when its time is not SI seconds (ticks, a
  gate-voltage sweep, a truth-table row); the viewer shows it instead of a formatted time.
- `stream` (string): an independent timeline inside one run (e.g. `cnt_transfer_sweep` and
  `cnt_cmos_gates`); viewers replay one stream at a time (default: the first emitted).
- `render_surface.clip_cylinder.center_mm` (optional): the radial clip centre (z-up frame) for a
  container that moves.
- `apparatus[].vertex_rgba` (mesh only, array[[r,g,b,a]] one per vertex): a surface coloured by the
  scenario's own per-vertex quantity (Pascal's sensor-wall displacement).
- `samples` (object `{name: number}`): scalar observables of this frame. The side chart panel plots
  them against `physical_time_s` (`x: "time"`) or against another sample key.
- `charts` (array[object], usually on the first frame only; the latest declaration wins): side-panel
  declarations `{id, title, x ("time"|sample key), x_scale?, x_label, y_label, log_x?, log_y?,
  x_range?, y_range?, cursor?, categories?, note?, series: [{key, label, color, dashed?, style?}],
  reference: [{label, color, x[], y[], style?, dashed?}], vlines: [{x, label, color}]}`.
  `reference` lines are comparison data (a measured table, a formula value) and are labelled as
  such; they never widen a time-series chart's x range.
- `curves` (array[{chart, label, color, x[], y[], style?}]): per-frame curve snapshots for a chart
  (an accumulating g(r), each block's MSD, the received MRI signal); the panel draws the latest
  snapshot at or before the playback time.
- `labels` (array[{position, text, color_rgba}], ≤ 48): 3D text anchored in the frame's units.
- `grid` (object): a solver cell grid drawn as a continuum — `{origin, spacing (number or [3]),
  shape [nx, ny, nz], values (class id per cell, x fastest), classes: [{id, label, color_rgba,
  style: "solid"|"liquid"|"grains"}], replaces_points?}`. One smooth surface (or grain cloud) per
  class; smoothing only shapes the boundary between cell centres. `replaces_points: true` tells the
  classic viewer not to also draw the per-cell point glyphs (Studio still draws points).

Studio consumes `radii` as depth-tested, instanced sphere meshes and `bonds` as lines between the
same held centres (line width/shading are rendering choices). Invalid radii fall back to the normal
sprite representation; invalid bond rows are dropped without inventing indices. A non-mm stream
retains its native coordinates and excludes the Geant4 mm scene from rendering and camera bounds.
Studio also draws `vectors` as arrows from the same held centres, with unchanged magnitude and
the same axis remapping as positions. Zero vectors draw nothing; malformed/non-finite arrays
are ignored. Camera bounds include every vector frame. Capture metadata records the length unit,
sphere/sprite representation, bond/vector counts and arrowhead/tint display choices. Moving
apparatus, labels, charts and grid surfaces remain classic-viewer-only.

Scenario emitters: `h2o_molecule_stability` / `h2o_cluster_fluid` / `h2o_bulk_water` /
`h2o_diffusion_temperature` (Å atoms + bonds; contacts, restraint sphere, periodic cell, 480 fs O
displacement trails, live g(r)/D HUD), `glass_of_water_shaken` (mm PBF particles + the glass at its
shaken position + Gaussian surface), `testscenario_osmotic` (3D particles + the membrane `mesh` +
pore spheres), `testscenario_efflux` (3D molecules + membrane sphere), `testscenario_pascal` (3D
baths + pistons + sensor-wall patch meshes, vessels laid out along x), `testscenario_h2o_electrolysis_combustion`
(packet molecules + electrode rods + spark; kinematics labelled representation), `briggs_rauscher_oscillator`
(the beaker's well-mixed liquid body in the emergent colour), `cnt_band_structure` (26 tubes rolled
from (n,m)), `cnt_logic_gates` (two streams), `testscenario_magnetic_resonance` (Bloch M vector +
B0 + measured spectrum/FID traces), `testscenario_magnetic_resonance_imaging` (per-voxel rotating-frame
M, summed signal, reconstructed line), and `glass_from_sand` (y-up 6³ cells with radii).

Planar solvers were lifted to 3D in the same change, so several sideband payloads gained a `z`:
`osmotic_particles.particles[].z`, `osmotic_particles.membrane` (now one radius per icosphere
vertex, 642 at the default), `osmotic_snapshot.membrane_volume_fraction`/`membrane_area_fraction`,
`final_summary.membrane.{vertices, volume_shrink_fraction, area_drift_fraction, clamp_hits}` and
`final_summary.shrinking_pressure_bias`; `efflux_snapshot.particles[].z` (the efflux transport
operator now carries `z`/`rvz`/`noise_z` → `set_rvz`/`d_z_dt`, comparison key
`efflux_v2_sphere:…`); `electrolysis_snapshot.sample_*_packets[].z` and `reaction_zone.z`;
`pascal_snapshot.wall_profile` is the mid-z column of the patch grid.

Viewer captures may select a documented physical-time excerpt by mapping the paired emitted
physical/playback clocks; selection must retain held frames and must not rewrite payload times.
An excerpt does **not** create temporal resolution. If documentation needs more dynamic states,
rerun a typed scenario with the required physical horizon and simulation-tick count. The lava-lamp
README run demonstrates this: at the default 333.15 K heater condition, 100 Geant4 ticks produce
101 unique frames over the complete 600 s horizon, then each ten-second GIF consumes 100 post-tick
states directly without optical flow or interpolation.
An independent 60 s horizon must match the first 60 s of a longer run at the same internal step; a
low-heater control must change
the emitted thermodynamic state without changing parcel IDs.
The reactive-foam scenarios reuse the same `material_frame` contract: `polyurethane_foam.js`
(tags `polyurethane_foam_scenario`/`polyurethane_foam_summary`) and `elephants_toothpaste.js`
(tags `elephants_toothpaste_scenario`/`elephants_toothpaste_summary`) emit persistent-parcel
frames whose per-frame `render_surface.sigma_mm` tracks the emergent parcel spacing
(`positions_unmodified` stays true). `polyurethane_foam.js` is integrated by the shared
bonded-parcel foam solver
([`js/trech_foam_solver.js`](../js/trech_foam_solver.js)) —
the toothpaste port is deferred (see `ROADMAP.md`) — so its frames additionally report the
**network and gravity state**: `counts` carries
`bonds_intact`/`bonds_broken`, `connected_components`, `detached_parcels` and
`parcels_on_ground`/`parcels_on_tray` (a detached parcel counts as fallen only once it is down on
the table AND outside the vessel footprint), while `physics_state` carries the emergent reaction
state (conversions or remaining peroxide, core/skin temperature, trapped/escaped gas, rigidity or
drainage), the body's own `foam_top_mm`/`lather_max_radius_mm` (excluding debris, with
`debris_top_mm` beside it), the `lean_deg`/`lean_offset_mm` least-squares tilt of the body axis,
and the per-frame motion distribution (`body_median_/body_p95_displacement_since_prior_emit_mm`),
whose collapse relative to its own peak is how "it cured rigid" is measured. Both summaries carry
the declared recipe, the precision axes, the Geant4 probe facts, the inferred coefficients, PubChem
structure identity (CID/SMILES/formula only), the emergent milestones and the run-end validation
flags; the polyurethane summary adds `conditions.gravity_scale` and the gravity consequences, and
its `gravity_scale=0` control run is compared against by the validation case, so
lean/cracking/falling are shown to be caused by gravity rather than scripted.
It also carries:

- `chemistry_inference`: `source` (`reference` or `operator`), whether the rate law was authored,
  operator model/teacher/`measured:false`, declared state fields, honest parcel-step inference and
  out-of-domain counts/fraction, and the final aggregated operator stage trace.
- `operator_vs_reference`: the stable `trech_operator_reference_pair_v1` comparison key,
  distilled-teacher honesty fields, promotion tolerances, comparable observer observables and a
  normalized trust record. Current consumers are polyurethane chemistry, the discrete H2O cycle,
  and efflux transport/crossing. Their generic pair cases compare reference/operator runs and
  enforce gaps, contextual selection, scale/domain/holdout trust, missing/starved/OOD state and
  exact run-level inference accounting.
- `mechanics_inference` and `mechanics_operator_vs_reference`: the experimental local
  creep/drag/strength candidate's source, `measured:false`, promotion status, teacher, stage trace
  and exact inference counts; the pair uses the same schema with chemistry/gravity/temperature/
  precision held fixed and seven mechanical observer gaps. `mechanics_source=reference` remains
  the default because full-run candidate gaps fail. The explicit `foam-mechanics-candidate`
  validation suite grades these pairs without changing the promoted-default suite.
- `operator_sample` (opt-in training sideband): scalar shared coefficients plus `dt` and an
  expanded `samples[]` list. Each sample carries all eight pre-step state inputs, `reactivity` /
  `exposure`, six observed rates, and the post-step `set_rigidity` /
  `set_inverse_relative_viscosity` assignments. Regular striding bounds the payload; actual
  reactivity/exposure boundary parcels extend the measured hull to the live population.

Hook `ctx.event` payloads are available for event callbacks. On `onEventEnd`,
the object includes Geant4 event metrics that scenarios can use for
simulation-driven inference: `edepMeV`, `totalTrackLengthMm`, `totalStepCount`,
`totalTrackCount`, `opticalPhotonSteps`, `opticalPhotonTracks`, and
`opticalPhotonTrackLengthMm`.

`TRECH_PUBCHEM(name)` is a JS runtime helper, not an output record. It reads a
PubChem JSON cache from `TRECH_PUBCHEM_CACHE_DIR` first, then the legacy
`data/pubchem` cache, so validation can fetch PubChem records into build-local
directories without committing them.

Example:

```json
{"phase":"hook_emit","hook":"onStep","event_id":7,"step_index":3,"tag":"step","payload":{"edep":0.25,"len":1.5}}
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
  - `low_confidence_inference` (boolean): whether this event's `onEventEnd` inference ran outside its model's trained domain (only true under `stratify.resimOnLowConfidence`).
  - `inference_out_of_domain_count` (number): out-of-domain predictions this event's `onEventEnd` hook made.

Example:

```json
{"phase":"event_end","event_id":0,"total_edep_mev":0.12,"total_track_length_mm":14.2,"total_step_count":120,"total_track_count":8,"optical_photon_tracks":3,"optical_photon_steps":42,"optical_photon_track_length_mm":5.6,"optics_enabled":true,"stratification":{"enabled":true,"label":"predictable","reason":"","source":"thresholds","exceptional":false,"low_confidence_inference":false,"inference_out_of_domain_count":0}}
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

TorchScript feature schema: `FeaturePipeline::kSchemaId` is `trech_event_features_v1`, and the ordered vector matches `FeaturePipeline::FeatureNames()`:
`total_edep_mev`, `total_track_length_mm`, `total_step_count`, `total_track_count`, `optical_photon_steps`, `optical_photon_tracks`, `optical_photon_track_length_mm`.

### Run-level fields added with the viz / optics-derive / engine extensions

- `primaries_emitted` (number): primary-particle count emitted across the run (sum across events of vertex × particle count).
- `primaries_transmitted` (number): primaries that exited the world via `fWorldBoundary`.
- `primaries_absorbed` (number): primaries killed inside the world (any other StopAndKill status).
- `primaries_uncollided` (number): primaries that exited the world having undergone **no discrete interaction** (only pure transport steps) — the uncollided beam. This is the Monte-Carlo counterpart of the Beer-Lambert `exp(-mu*x)` analytic prediction.
- `primaries_transmitted_fraction` (number): `primaries_transmitted / primaries_emitted` (0 when no primaries).
- `primaries_uncollided_fraction` (number): `primaries_uncollided / primaries_emitted` (0 when no primaries).
- `analytic_checks` (array, optional): present when `analytic.enable` with checks configured. Each entry pairs a **classical-formula prediction** (computed from Geant4's own particle-level data) with this run's **Monte-Carlo statistical** tally. Fields: `type`, `label`, `available`, `formula`, `note`, `particle`, `material`, `energy_mev`, `path_length_mm`, `measured_field`, `classical_predicted` (the closed-form expected value), `geant4_measured` (the run's measured value for `measured_field`), `delta`, `relative_error`, `tolerance_rel`, `within_tolerance`. For `type == "beer_lambert"` it also carries the attenuation breakdown `mu_total_per_mm`, `mu_photoelectric_per_mm`, `mu_compton_per_mm`, `mu_rayleigh_per_mm`, `mu_pair_per_mm`, `mean_free_path_mm`.
- `analytic_checks_within_tolerance` (boolean, optional): true when every available analytic check is within its relative tolerance.
- `precision_profile` (string, optional) / `precision_note` (string, optional) / `precision_axes` (array[object], optional): the run's **precision profile** and the concrete axes it moved. Present only when the scenario declares a profile (`config.precision`). TRECH deliberately publishes no single "quality" number — a Geant4 event, an MD step, a PBF particle, a chemistry tick and a replay frame are different knobs — so each axis carries `name`, physics-agnostic `role` (`spatial`/`temporal`/`output`/`statistical`/`representation`), the scenario `control` it drives, `unit`, resolved `value`, the `baseline_value` at the `balanced` rung, `representation_only` (display-only: it changes no simulated state) and `overridden` (an explicit control value beat the profile, which is why the profile then reports `custom`). The profile *ladder* lives in scenario JS (`helpers.precision`), because only the scenario knows what refining its own axis means; the engine owns the vocabulary and the reporting.
- `event_feature_stats` (object): per-event-feature running moments produced by `OnlineEventStats`. Each key matches a `FeaturePipeline::FeatureNames()` entry; each value carries `{count, mean, variance, stddev, min, max}`.
- `event_feature_stats_torch_backed` (boolean): true if the engine was built with `TRECH_ENABLE_TORCH`, so the tensor accumulator mirror is active.
- `viz_enabled`, `viz_trajectories`, `viz_segments`, `viz_dropped`, `viz_capped`: viz recorder bookkeeping (only present when `viz.enable`). `viz_segments` is the legacy field name for recorded polyline **points/vertices**; Studio reports actual drawable line segments separately as adjacent-point pairs.

## trech_viz_scene.json

Emitted at run-start when `viz.enable: true` — or when a run is captured with the observation-only
CLI override `trech run … --viz` (recorder on, scenario's own `includeNonOptical`) / `--viz-all`
(also non-optical particles) / `--viz-max-trajectories N`. A capture never alters transport, but
the captured run's `config_json` (and hash) honestly records `viz` as enabled. Single JSON document (not JSONL). Lets a viewer reconstruct geometry, beams, and per-material derived optics without needing to read the engine config.

Top-level fields:

- `schema` (string): `"trech_viz_scene_v1"`.
- `seed` (number), `n_events` (number), `determinism_mode` (string): run metadata.
- `world` (object): `{size_mm, material, temperature_k, pressure_atm}`.
- `medium` (object, optional): `{size_mm, material}` when `detector.mediumBoxMm > 0`.
- `volumes` (array[object]): each entry includes `name`, `material`, `parent`, `position_mm`, `rotation_deg`, `shape{type, size_mm, outer_radius_mm, inner_radius_mm, length_mm}`, `tags`, `score_edep`. The `tags` list is the visualization channel: `viz_emitter` / `viz_forced_white` make a volume render with a forced look in `tools/viz/`; everything else takes its color and opacity from `derived_optics`.
- `materials` (array[object]): config-level composition `{name, smiles?, density_gcm3, components[]}`.
- `derived_optics` (array[object], present when `optics.derive.enable`): per-material derived optical constants. Each entry:
  - `material_name` (string), `config_material_key` (string), `density_gcm3` (number), `mean_molar_mass_g_per_mol` (number), `number_density_per_cm3` (number).
  - `mean_refractive_index`, `mean_absorption_length_mm`, `mean_scatter_length_mm` (numbers): scalar reporting fields across the visible band.
  - `display_rgb` (array[3]): relative visible-transmission RGB hint for the viewer, normalized
    against the same spectral integrator under flat transmission so a clear flat spectrum is
    neutral `[1,1,1]`; absolute brightness is not a material colour.
  - `available` (boolean), `note` (string): provenance/diagnostic.
  - `samples` (array[object], when `optics.derive.writeSpectrum`): visible-band spectrum, each entry `{energy_ev, wavelength_nm, refractive_index, extinction_k, absorption_length_mm, scatter_length_mm, mu_abs_per_mm, mu_scat_per_mm}`.
  - `reference_deltas` (array[object], when validation refs are supplied): each entry compares the derived value at the closest sample energy to the reference (`refractive_index_delta` = derived − reference). The reference values are logged only — never used in transport.
- `beams` (array[object]): `{name?, particle, energy_mev, energy_ev, direction[3], active}`.
- `viz` (object): the sampling parameters used (`max_trajectories`, `sample_every_nth`, `max_segments_per_trajectory`, `include_non_optical`, `trajectories_path`).

## trech_viz_trajectories.jsonl

One JSON object per sampled trajectory; written at run end when `viz.enable: true` (or a `--viz`
capture). Sampling is deterministic (seeded stride on `event_id * prime + track_id`) so reruns with identical seed produce the same polyline set; the trajectory cap is first-come, so whole early events are kept.

- `phase` (string): `"trajectory"`.
- `event_id` (number): Geant4 event id.
- `track_id` (number): Geant4 track id within the event.
- `particle` (string): Geant4 particle name (e.g., `"opticalphoton"`).
- `capped` (boolean): true when `maxSegmentsPerTrajectory` truncated the polyline.
- `points` (array[object]): each entry `{x_mm, y_mm, z_mm, dx, dy, dz, energy_ev, time_ns, step_length_mm, volume?, material?, process?, interaction?}` — one record per recorded vertex. `volume` / `material` describe the medium of the **outgoing** segment from that point (the birth point uses its source medium). `process` is the Geant4 process that ended the incoming segment; `interaction` is the compact engine class: `emission` at birth, then `transport`, `boundary`, `world_boundary`, `scatter` (Rayleigh/Compton), or generic `interaction`. A viewer must not classify a geometric boundary bend as scattering. Optical photons additionally carry `boundary` on geometry-boundary points: the `G4OpBoundaryProcess` outcome (`refraction`, `reflection`, `total_internal_reflection`, `absorption`, `detection`), so a viewer can tell a reflected ray from a refracted one. The birth point's `energy_ev` is the emission (pre-step) kinetic energy, so the first step's energy loss is visible.

## Studio capture provenance sidecar

`trech_studio.capture` writes `<capture>.json` beside PNG/MP4/GIF artifacts. Its `precision`
object separates:

- `simulation`: MC event count, recorded trajectory/segment counts and caps/drops,
  medium/process label coverage/counts, binomial standard errors, and configured sampling limits;
- `representation`: playback source and exact hold/prefix policy, ribbon/sprite display choices,
  native mean segment length, frame/particle counts, output/internal raster sizes and supersampling.

The sidecar is the rendering-precision contract. Coordinates/times/RGBA are engine outputs;
ribbon width/alpha, sprite radius, air styling and raster choices are labelled representation.

## trech_resim_queue.jsonl

When `stratify.dumpResimQueue` is enabled, exceptional events are queued for
re-simulation. With `stratify.resimOnLowConfidence`, events whose `onEventEnd` inference ran
outside its model's trained domain are queued too (even when the feature-based stratifier labels
them predictable) — acting on the coverage flag.

- `phase` (string): `"resim_candidate"`.
- `event_id` (number): Geant4 event ID.
- `label` (string): stratification label.
- `reason` (string): reason tag — the stratifier's reason when feature-exceptional, or `"inference_out_of_domain"` when queued only by the coverage flag.
- `source` (string): `"thresholds"`/`"model"`/`"disabled"` for a feature-exceptional event, or `"cascade_coverage"` when queued only by the coverage flag.
- `low_confidence_inference` (boolean): whether the coverage flag contributed to queuing this event.
- `inference_out_of_domain_count` (number): out-of-domain predictions this event's `onEventEnd` hook made.

Example (queued by the coverage flag, not the feature stratifier):

```json
{"phase":"resim_candidate","event_id":7,"label":"predictable","reason":"inference_out_of_domain","source":"cascade_coverage","low_confidence_inference":true,"inference_out_of_domain_count":2}
```

## Optional adaptive work metadata

`run.timeBudgetSeconds` is a conditionally serialized positive predictive batch-run budget.
Absent/zero preserves historical config bytes. Timed runs record serial `run.threads: 1`. In
provenance, `requested_events` and `time_budget_seconds` occur on both phases; `run_start.n_events`
is requested and `run_end.n_events` is completed. Run-end provenance and scores additionally carry
`simulation_wall_seconds` and `stop_reason` (`time_budget` / `event_limit`); scores also carry the
requested count and budget. The visualization scene's `n_events` is updated to completed events.
Config JSON/hash retains the requested workload. The time bound is soft and excludes Geant4
initialization/model loading; full events/hooks and output work can exceed it.

With third-argument options, `ctx.cascade` metadata adds `stagesLimited` (unexecuted limited
stages), `targetsReached` and `stopReason` (`complete`, `stage_budget`, `targets_reached`,
`targets_unavailable`). Each limited trace entry has `ran:false` and `skipReason` equal to
`stage_budget` or `targets_reached`, with no predicted outputs. Missing inputs retain the existing
blocking contract. No-options calls retain their metadata shape. Studio reports limit badges
without treating missing/limited stages as predictions.

Continuous refinement is recorded through the existing resolved precision axes/profile/note,
without additional unconditional config fields. Studio adaptive preview settings are representation
metadata only, including actual/requested detail, sphere sectors, GPU cache frame limit, CPU frame
cost and target FPS, estimated working allowance and explicit GPU-timing-unmeasured label. Fixed
capture sidecars record track/segment limits and optional detail overrides; a zero limit means all
recorded samples. See [adaptive precision](adaptive_precision.md) for the control contract.
