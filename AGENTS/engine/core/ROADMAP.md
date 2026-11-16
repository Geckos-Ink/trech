# Configuration, CLI and provenance — roadmap

[Root principles](../../../AGENTS.md) · [Root roadmap](../../../ROADMAP.md) · [Parent](../ROADMAP.md) · [Handbook](AGENTS.md)

Related owners: [Precision profiles and runtime budgets](../precision/ROADMAP.md) · [JavaScript host and live lab](../runtime/ROADMAP.md) · [Tests and validation ownership](../../tooling/validation/ROADMAP.md).

Maintain work in its owning branch. Dated results apply to the recorded checkout; they do not validate subsequent changes.

For config serialization and reporting changes, follow [precision profiles and runtime budgets](../precision/ROADMAP.md). CLI, inspected metadata and live-session changes belong to the [runtime workstream](../runtime/ROADMAP.md); regression and schema gates belong to [validation](../../tooling/validation/ROADMAP.md). Add new core-only gaps here when they do not belong to one of those workstreams.

## Priority queue

Every open item of this branch, highest priority first. The dated records below are delivery
history: the "Residual" and "Next" notes inside them are tracked here, and this queue wins
where they disagree. Keys and route steps: [priority keys](../../ROADMAP.md#priority-keys) ·
[implementation route](../../ROADMAP.md#implementation-route). When an item lands, delete it here, add a
dated record below, and queue its residuals in the same change.

- **P2** · R1 · Lab command-stream `patch` payloads are neither re-typed by the integer/field readers nor checked for unknown keys; `--strict-config` covers JSON configs and `onInit` overrides only. (dated records below)
- **P2** · R1 · Runtime (non-`onInit`) hooks cannot patch config, so ignored-override reporting covers `onInit` only; decide whether later hooks may patch at all before extending it. (dated records below)
- **P2** · R5 · Sweep the three PubChem-dependent scenarios (`beaker_water_n_pentane`, its Studio variant, `testscenario_h2o_electrolysis_combustion`) through inspect/type/unknown-key checks once a PubChem cache is present. (dated records below)

## Delivery records

- [x] Independent `stratify.resimOnStarvation` / `resimOnScaleMismatch` opt-ins round-trip
  without changing absent/false legacy config bytes or hashes. Routing and remaining gaps are
  tracked in the [trust roadmap](../inference/trust/ROADMAP.md).
- [x] Named parse errors across the scalar config blocks (2026-11-15). `Config.cpp` gains shared
  typed readers (`fieldOr`/`fieldValue`, a `FieldError` type) and a `located()` wrapper that adds
  one path segment per level, replacing the geometry- and beam-local wrappers (their messages are
  unchanged). `environment`/`medium`/`detector`, every `beam(s)` field (incl. `spread`,
  `polarization`, `spectrum[i]`, `active`), `run`, `physics`, `determinism`, `system`, `optics`
  (incl. `spectrum[i]` in both array and object form), `optics.derive`/`opticsDerive` (incl.
  `validate.references[i]`), `viz`, `chemistry` and the volume `name`/`material`/`scoreEdep` now
  name the field (e.g. `opticsDerive.validate.references[1].energyEv must be a number`); every
  other top-level block, `materials[i]` and `models[i]` prefix the library message with their
  location. Behaviour change: a boolean where a number goes is now an error instead of 0/1.
  Compatibility: an inspect sweep of 67 example scenarios parses with no error, and
  `configToJsonString` of every one is byte-identical to the previous parser's (config hashes
  unchanged). Verification: Release and Debug CTest 53/53 (`trech_config_roundtrip`: 19 named
  field errors, 2 block prefixes, a pass-through range error, integer-valued numbers;
  `trech_geometry_resolution`: 4 volume scalar errors replace the old library-message check).
  Residual: ~~`nuclear`, `multiscale`, `analytic`, `materialProbe`, `precision`, `materials`,
  `models`, `hooks`, `stratify` and `lab` fields are not typed yet (block-level location only);
  `hooks`/`lab` integer limits and `determinism.predictive` still silently ignore a wrong type;
  `geometry.volumes[i].tags` silently drops non-string entries~~ (second pass below); three scenarios
  (`beaker_water_n_pentane`, its Studio variant, `testscenario_h2o_electrolysis_combustion`) were
  not swept because their inspect needs the PubChem cache.
- [x] Every config block typed (2026-11-15, second pass). `nuclear` (incl. `cycles[i]`,
  `source`/`target`, `forward`/`backward`, `reactants[i]`/`products[i]`), `multiscale`,
  `analytic` (`checks[i]`), `precision` (`profile`, `axes[i]`), `materialProbe` (incl.
  `interactions` particle/processes/energies), `materials[i]` (incl. `components[i]`),
  `models[i]`, `hooks`, `stratify`, `lab` and `geometry.overlapCheck.enable` read through the
  field readers. Former silent ignores are now named errors: the `hooks`/`lab` integer limits
  (`integerFieldOr`: `hooks.maxStepCallbacks must be an integer`), `determinism.predictive` and
  `precision.profile` of the wrong type, and non-string entries of every string list (`tags`,
  `materialProbe.materials`, `models[i].required_context_keys`, `hooks.registered`/`names`, a bare
  `hooks` array: `geometry.volumes[0] ('v').tags[1] must be a string`). A missing
  `materialProbe.interactions` key now gives the existing "requires particle, processes and
  energiesMeV" message instead of a JSON `out_of_range`. Compatibility: the 67-scenario inspect
  sweep and `examples/lab/realtime_lab_bootstrap.json` parse with no error, and every config's
  canonical serialization is byte-identical to the pre-session parser's. Verification: Release
  and Debug CTest 53/53 (`trech_config_roundtrip`: 23 more named errors replacing the two
  block-prefix cases, accepted list/limit forms). Residual: ~~floats still truncate into the
  remaining non-limit integer fields (`run.nEvents`, `optics.derive.nEnergyBins`,
  `lab.minRoundsPerTick`, ...) as nlohmann always did~~ (closed 2026-11-16, entry below); ~~unknown keys are still ignored, so a
  misspelled field is silent~~ (reported since 2026-11-15, entry below); the three
  PubChem-dependent scenarios remain unswept.
- [x] Unknown config keys reported (2026-11-15). `configFromJsonString` keeps a key-read ledger
  (`has` replaces all 79 `json::contains` calls in the parse section) and fills
  `TrechConfig::unknownKeys` with every key of a queried object the parser never read; it is not
  serialized, so config hashes are unchanged. `trech run`/`lab` warn on stderr, `trech inspect`
  adds `config_unknown_keys` (when the config parses), and `run_start`, `run_end` and
  `geometry_refused` provenance carry `config_unknown_keys` when non-empty. **Finding (67-scenario
  sweep):** 3 scenarios had 5 unknown keys. `aerodynamics_reference` and
  `nacl_dehydration_reference` set `beam.positionMm`, which the engine never read, so their beam
  started at the origin inside the probe volume instead of 250/40 mm upstream; both now use
  `originMm` (see the [process roadmap](../../scenarios/processes/ROADMAP.md)). They and
  `water_salt_recipe` also set a meaningless `hooks.enable`, now removed. After the fix the sweep
  finds no unknown key. Verification: Release and Debug CTest 53/53 (`trech_config_roundtrip`:
  every serialized key of the full fixture is read; six reported paths over root, nested, array
  and model entries; free-form `hooks.inputs`, hook toggles and aliases are not reported;
  `trech_geometry_resolution`: conditional provenance field), a scratch run with `run.nEvent` and
  `beam.positionMm` warns twice and records both in each provenance record. Residual: ~~unknown
  keys never fail a run (no strict opt-in)~~; ~~the onInit patcher's own whitelist ignores unknown
  patch keys without reporting them~~ (both closed 2026-11-15, entry below); unknown keys are not
  in `trech_scores.jsonl`; a key read
  only by another consumer would be reported (~~`TRECH_ML.modelEntry()`'s `models[i].registry`~~,
  accepted since 2026-11-16, entry below).
- [x] `--strict-config` and unapplied `onInit` override paths (2026-11-15). The new CLI flag
  (run, inspect, lab) makes unknown config keys an error before any output is written
  (`requireNoUnknownConfigKeys`: `--strict-config: config has 2 key(s) the engine never reads:
  beam.positionMm, run.nEvent`); without it they remain warnings. `JsRuntime::dispatchHook` now
  reports the leaf paths of an `override` that no patchable field applied (unknown,
  non-patchable or wrong-typed: `HookDispatchReport::ignoredPatchPaths`); the CLI warns per path,
  `--strict-config` refuses them, and `run_start`/`run_end`/`geometry_refused` provenance carry
  `hook_patch_ignored_paths` when non-empty. `scripts/audit_flow_presets.py` gained a `keys`
  check (in `all`) that reports `trech inspect`'s `config_unknown_keys`: `--all` gives 67 pass, 0
  issues, 3 not audited (PubChem cache). Spot runs (Release): a scratch config with
  `beam.positionMm`/`run.nEvent` exits 1 under `--strict-config` with no output directory and
  runs (with two warnings) without it; an `onInit` override `{run: {nEvents: 3, nEvent: 9},
  beam: {energyMeV: "2"}}` runs 3 events with `hook_patch_ignored_paths` `["beam.energyMeV",
  "run.nEvent"]` and is refused under the flag; `hello_world` passes with the flag.
  Verification: Release and Debug CTest 53/53 (`trech_cli_parse`, `trech_config_roundtrip`,
  `trech_js_runtime`, `trech_geometry_resolution`), `tests/test_flow_preset_audit.py` 3/3, Studio
  pytest 301/301. Residual: the validation suite does not run with `--strict-config`; runtime
  (non-`onInit`) hooks cannot patch, so only `onInit` is covered; a lab command-stream patch's
  unknown keys are not reported.
- [x] Integer fields take only integers; `models[i].registry` accepted (2026-11-16). Every
  integral field read through `fieldOr`/`fieldValue`/`integerFieldOr` now goes through
  `integerFieldValue`: a fractional or float-typed number (`run.nEvents: 2.5` or `10.0`) is
  `run.nEvents must be an integer`, a negative `run.seed` is `must be a non-negative integer`
  (it used to wrap to 2^64-1) and `run.nEvents: 3000000000` is `is out of range` (it used to
  overflow). Signed fields still accept negatives where they clamp (`hooks.maxTrackCallbacks:
  -5` → 0). Messages that named a type (`run.nEvents must be a number`, `nuclear` `z`/`a`) now
  say "integer". **Finding:** a scenario that loads a registered checkpoint through
  `TRECH_ML.modelEntry()` carries `models[i].registry`, which the parser never read, so
  `--strict-config` refused it; `registry` is now an accepted annotation (an object; not
  serialized, so hashes are unchanged) and such a scenario inspects strictly. Verification:
  Debug CTest (`trech_config_roundtrip`: ten integer cases incl. edges `2147483647`,
  `18446744073709551615`, `-1`, the registry type error, unchanged bytes with/without
  `registry`); the 68-scenario `audit_flow_presets.py --all` (inspect + keys) passes with 3
  PubChem bundles not audited; `trech lab` with `realtime_lab_bootstrap.json` and its command
  stream runs. Residual: a lab command-stream patch is not re-typed by this reader; the three
  PubChem-dependent scenarios remain unswept.
