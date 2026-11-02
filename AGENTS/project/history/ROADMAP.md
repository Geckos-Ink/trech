# Completed project milestones — roadmap

[Root principles](../../../AGENTS.md) · [Root roadmap](../../../ROADMAP.md) · [Parent](../ROADMAP.md) · [Handbook](AGENTS.md)

Dated records apply to their captured checkout. Current contracts, code and tests take precedence; these results do not validate later changes.

## Completed

- Mermaid architecture charts added in `CHARTS.md` (workflow, Geant4 wiring, outputs, stratification/prediction).
- Geant4 submodule initialized and documented.
- Dependency acquisition decision: default FetchContent via presets, with vendoring optional.
- CLI flags for macro execution, output directory, seed override, and event count.
- Provenance logging expanded (physics list, RNG engine, CLI args).
- First scoring output (total energy deposit summary).
- Event-level scoring and stratification hooks added (`trech_event_scores.jsonl`, `stratify.enable`).
- Stratification expanded with richer event features, thresholds, labels, and ML hook stubs.
- ML feature pipeline + TorchScript stub added for event stratification.
- Chemistry/DNA wiring stub added (`chemistry.enable`, `chemistry.model`, `chemistry.solver`).
- Multi-scale wiring stub added (`multiscale.enable`, `multiscale.method`, `multiscale.mode`).
- Initial Geant4-DNA wiring added (`chemistry.enable`, `TRECH_ENABLE_DNA_CHEM`, solver-gated chemistry stage).
- Run-level scoring now includes chemistry/DNA flags and option metadata.
- Run-level scoring now includes stratification summary counts.
- CTest presets added to avoid passing `--test-dir` flags.
- Stratification feature dumps + resim queue outputs added (`trech_event_features.jsonl`, `trech_resim_queue.jsonl`).
- Unit tests for CLI parsing, JS config evaluation, and provenance output.
- Stratification unit tests and smoke script now run `ctest`.
- Draft initial H2O experiment spec (`examples/scenarios/h2o_fluid/h2o_fluid_spec.md`).
- Initial H2O experiment stub (`examples/scenarios/h2o_fluid/h2o_fluid.js`).
- H2O single-molecule proxy stub (`examples/scenarios/h2o_single_molecule/h2o_single_molecule.js`).
- H2O optics beam stub (`examples/scenarios/h2o_optics_beam/h2o_optics_beam.js`).
- H2O config schema extended (medium box, environment, beam direction, optics) with updated spec and stub.
- Detector now supports medium box geometry, environment settings, and optical material properties.
- Optical physics wiring and photon scoring fields (tracks, steps, track length) added.
- Spectral optics support added for energy/wavelength dependent refractive index, absorption, and scattering.
- Optics spectrum example added in `examples/scenarios/config_optics/config_optics.js`.
- Geometry volumes and custom materials added (`geometry.volumes`, `materials`) to keep the schema agnostic.
- Per-volume energy deposit scoring added (`volume_edep_mev`), keyed by volume name.
- CNT stubs now model tube-shell geometry volumes with `scoreEdep` enabled; examples cover medium, world, and container placements with explicit materials.
- LibTorch/TorchScript selected as the ML runtime for online learning from detailed simulations.
- CNT optics stub added to validate optics + volume scoring on the same engine.
- H2O single-molecule proxy and optics-beam stubs run; baseline scores/provenance captured in `build/dev/out_h2o_single` and `build/dev/out_h2o_optics`.
- TorchScript feature schema defined (`FeaturePipeline::kSchemaId = trech_event_features_v1`) and a minimal LibTorch inference hook added behind `TRECH_ENABLE_TORCH`.
- ML scale-up flowchart added to `CHARTS.md` (Geant4 -> Torch training -> inference gate).
- System config block (`system.*`) added with point-agnostic aggregation, and `trech_scores.jsonl` now emits `system_*` density metrics.
- Event summary accumulables now feed system moment metrics (event count + energy mean/variance/stddev) in `trech_scores.jsonl` and `trech_provenance.jsonl`.
- Generic nuclear cycle config + Geant-backed analyzer added (`nuclear.cycles`): reaction participant mass/Q evaluation, charge/baryon conservation checks, and macro phase/density consistency metrics in scores/provenance.
- Validation automation script added (`scripts/run_validation.sh`).
- Validation summary template + updater script added (`docs/validation_summary.md`, `scripts/update_validation_summary.py`) and wired into `scripts/run_validation.sh`.
- Smoke test script added (`scripts/run_smoke.sh`).
- Output JSON schema documented (`docs/output_schema.md`).
- Minimal batch macro example added (`examples/macros/minimal.mac`) and `--ui` flag implemented.
- Config example experiments added (optics, stratify, ML stub, chemistry stub, multiscale stub, nitrogen-carbon cycle).
- Hook API proposal documented (`docs/scenario_hooks.md`).
- JS helper module and multi-beam unit conversion example added (`js/trech_helpers.js`, `examples/scenarios/config_multi_beam_units/config_multi_beam_units.js`).
- JS helpers expanded with physical constants + material presets (including SMILES placeholders).
- JS include helper (`TRECH_INCLUDE`) added to load scenario modules with stable file/line references.
- JS runtime now accepts object-based `TRECH_CONFIG` and registers `TRECH_HOOKS`; error stacks still surface include filenames/line numbers with test coverage in `tests/test_js_runtime.cpp`.
- Hook dispatcher telemetry is wired at init/run/event/step boundaries with deterministic run-level counters and `hooks.maxStepCallbacks` guardrails in scores/provenance outputs.
- Hook runtime extension now dispatches deterministic `ctx` payloads (`config/runtime/event/step/state/rng`), supports whitelisted `onInit` override patching, records `hook_patch_count`/`hook_emit_count` in scores+provenance, and writes `trech_hook_emits.jsonl`.
- Hook runtime guardrails now include per-callback emit caps + payload-size caps (`hooks.maxEmitsPerCallback`, `hooks.maxEmitPayloadBytes`) with dropped emit telemetry in scores/provenance.
- JS runtime now bootstraps `TRECH_FLOW` (fluent `set`/`defaults`/`merge`/`push`/`ensureArray`/`derive`/`selectBeam`/`normalizeDetectorAliases`/`finalize`/`require`/`assert`/`when`/`tap`/`build`) and accepts function-based `TRECH_CONFIG` for flow-like scenario authoring.
- Core runtime now supports a lab-session command channel (`trech lab`) for real-time JSON-driven interaction without fixed JS scenarios; config schema includes `lab.*` metadata (`enable`, `mode`, command schema/channel, targetHz).
- Determinism config added (`determinism.mode`: `strict`/`predictive`) with stratifier gating (`strict` disables model inference path even when `stratify.modelPath` is set) and provenance/scores metadata (`stratify_model_hash`, source counts, predictive flags).
- Beams array normalization added in the config loader (`beams` array selects active/first; `beam` remains an alias).
- Config loader now accepts top-level `environment` and `medium` aliases for `detector` (canonical serialization remains `detector`).
- Collection normalization expanded beyond `beams` (materials/components/tags/optics.spectrum/hooks accept single object/string forms).
- Material registry fields extended with optional `smiles` metadata for future schema expansion.
- Include error demo added (`tests/fixtures/js/include_error_demo.js`, `tests/fixtures/js/include_error_helper.js`).
- Example scenarios refreshed with container volumes, explicit substances, nested geometry, and system volume declarations.
- Master run action now initializes in MT mode; accumulables merge from workers and provenance captures Geant4 version.
- Geant4 build/install completed under `build/geant4-install` and H2O validation run succeeded.
- Build outputs under `build/` are gitignored and treated as local-only artifacts.
