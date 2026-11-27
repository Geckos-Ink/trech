# trech-torch

The molecular track also has two standalone builders:
[`build_particle_molecule_models.py`](build_particle_molecule_models.py) learns a shared
atomic/nano response from Geant4 particle-interaction probes (NumPy + Geant4; no QM/PubChem
training labels). [`build_molecular_series.py`](build_molecular_series.py) builds the separate
RHF/STO-3G charge/torsion comparison fixtures (RDKit + PySCF). Their sources and scientific
limits are documented in [`docs/inference/particle_molecule.md`](../../docs/inference/particle_molecule.md) and
[`docs/scenarios/molecular_series.md`](../../docs/scenarios/molecular_series.md).

Torch-side companion tools for TRECH: harvest Geant4 run outputs into training
sets, fit the surrogate/stratifier models the engine runs inference with, and
plan which Geant4 experiments to run next. Install:

```bash
cd tools/torch
python -m venv .venv
source .venv/bin/activate
pip install -e .          # numpy-only: dataset harvester, ridge/logistic
                          # .json trainers, and the experiment planner
pip install -e '.[torch]' # adds torch for the TorchScript (.pt) exports
```

The `.json` model paths (optics ridge, event-stratifier logistic) and the
experiment planner are **numpy-only**, so they work in a stock environment;
only the TorchScript `.pt` exports need `torch`. All tools share one
schema-checked harvester, `trech_torch/dataset.py`, whose schemas are locked to
the C++ side (`FeaturePipeline` `trech_event_features_v1` and
`OpticsSurrogate::kCompositionElements`).

## Tracing training (torch and numpy)

Every trainer here logs to the [engine trace](../../docs/engine/engine_trace.md#python-tools-torch-and-numpy)
through `trech_torch.trace` when `TRECH_TRACE` is set: the numerical runtime, the arrays a fit
saw, each training loop's model, optimizer and loss per epoch, numpy least-squares fits, and
every exported model with its SHA-256. For example:

```bash
TRECH_TRACE=debug TRECH_TRACE_FILE=build/train_trace.jsonl \
  build/render-venv/bin/python -m trech_torch.train_surrogate --help
```

The trace never changes the trained weights (`tests/test_python_trace.py` checks this). Off
by default.

## C++ backend checks

LibTorch is a required engine dependency, and this package's environment is the required
`TRECH_ML_PYTHON`. Every configure needs both. A Geant4-free check build, from the repository
root with LibTorch at `thirds/torch`:

```bash
cmake -S . -B build/torch-check -G Ninja -DTRECH_ENABLE_GEANT4=OFF
cmake --build build/torch-check
ctest --test-dir build/torch-check --output-on-failure
```

`trech_ml` and its consumers compile as C++20.
`trech_torch_backends` authors synthetic TorchScript fixtures in C++ (no Python torch needed),
then tests generic positional inference/snapshot identities, classifier tensor/string outputs,
strict stratification, optics outputs, failed reloads and interpreter errors. Generic positional
APIs reject nonfinite or float-overflowing inputs and validate the full output tensor before
publication. These checks establish numerical backend behavior, not physical model accuracy.

A raw `.pt` module has no feature names, so on its own it serves only positional inference. To use
it from `ctx.predict`/cascade/operator calls, put a `<model>.pt.io.json` sidecar next to it:

```json
{"schema": "trech_torchscript_io_v1", "model_sha256": "<SHA-256 of the .pt bytes>",
 "input_features": ["a", "b"], "output_features": ["y"],
 "feature_units": {"inputs": {"a": "MeV", "b": "mm"}, "outputs": {"y": "1"}},
 "trained_scale_bands": ["nano"], "holdout": {"r2_min": 0.9, "n": 40, "rmse": {"y": 0.1}}}
```

`train_surrogate.py --out` writes it from the JSON twin (`trech_torch.torchscript_io`). The engine
refuses a sidecar whose `model_sha256` does not match the module, so a retrained `.pt` cannot
inherit stale names or accuracy; provenance records its hash as `io_sidecar_sha256`. No training
domain is read from it, so coverage reports the domain as unmeasured. Cross-platform/accelerator
and production-model validation remain separate from the local macOS ARM64 CPU integration checks.

Tools provided:

## Generic surrogate trainer (any scenario)

`trech-train-surrogate` is the scenario-agnostic trainer: name any numeric
input and output columns and it fits a model that any scenario can call via
`ctx.predict`. Columns come from the shared harvester, so the same tool serves
optics (`--source scores`), event/stratify data (`--source event_features`),
and arbitrary scenario observables emitted as hook payloads
(`--source hook_emits --tag <tag>`) — present or future.

```bash
# discover columns
trech-train-surrogate --runs build/dev/out_myscenario --source hook_emits \
  --tag my_observable --list-columns

# train (MLP with torch, or add --linear for a numpy-only linear model)
trech-train-surrogate \
  --runs build/dev/out_myscenario \
  --source event_features \
  --inputs total_edep_mev,total_track_length_mm \
  --outputs total_step_count \
  --out-json build/dev/my_surrogate.json \
  --out build/dev/my_surrogate.pt \
  --manifest build/dev/my_surrogate.manifest.json
```

The MLP shape is `--hidden W --depth D` (uniform) or `--widths 32,16,8` (per
layer), with `--activation` / `--activations tanh,tanh,relu` choosing silu
(default), tanh, relu or sigmoid — the activations the C++ `GenericSurrogate`
evaluates. The manifest records the trained `structure`.

It exports the portable `generic_surrogate_v1` JSON (LibTorch-free; the
deployable artefact) with input/output standardisation baked in, an optional
TorchScript `.pt` twin with its named-IO sidecar (`<out>.io.json`), and a manifest with model
size + held-out metrics.
Deploy it by adding `{ name, path }` to a scenario's `models: [...]` and calling
`ctx.predict(name, features)` from a hook (predictive mode only). Demo:
`examples/scenarios/surrogate_generic_demo/surrogate_generic_demo.js`. See `CHARTS.md` →
"Generic surrogate" for the full flow.

For per-element operators, emit one bounded record with a `samples` list and
use `--source hook_emits --tag <tag> --expand samples`; scalar fields on the
emit become shared inputs on every expanded row. Prefer independent
operating-point validation:

```bash
trech-train-surrogate \
  --runs build/dev/operator_harvest/train_* \
  --validation-runs build/dev/operator_harvest/valid_* \
  --source hook_emits --tag operator_sample --expand samples \
  --inputs gel,blow,temperature_k,...,initial_temperature_k,dt \
  --outputs d_gel_dt,d_blow_dt,...,set_inverse_relative_viscosity \
  --teacher "reduced law in polyurethane_foam.js" --measured false \
  --out-json data/polyurethane_cascade/meso_reaction_operator.json
```

`--validation-runs` excludes those runs from fitting and replaces the random row split, avoiding
optimistic leakage between neighbouring parcels from the same simulation. `--note`, `--teacher`
and `--measured` travel with the deployable model as audit metadata. The committed polyurethane
operator and its metrics manifest are under `data/polyurethane_cascade/`.

For positive targets spanning orders of magnitude, add `--log-outputs drag_per_s,...`.
Only those outputs are fitted in log space; training and validation targets must be finite and
strictly positive. The exporter writes `generic_surrogate_v2` with nested `network.layers` and
one `identity`/`exp`/`sigmoid` `output_transforms` entry per output. C++ and optional TorchScript decode
after destandardisation; manifest MAE/RMSE/R² remain in physical output units. Older C++ readers
reject v2 rather than interpreting logarithms as physical values. Without links, v1 is preserved.
`--lr-final-factor` optionally decays the MLP learning rate; its default of 1 keeps prior behavior.

For probabilities or fractions, use `--logit-outputs uncollided_fraction,...`. Targets in both
training and holdout must be finite and strictly inside (0,1); endpoints are rejected instead
of silently clipped or smoothed. Any finite-Monte-Carlo continuity correction belongs in the
dataset builder's explicit provenance, alongside unchanged observed labels. Sigmoid decoding
is stable for extreme finite logits and numerically bounds outputs to [0,1], while rejecting
non-finite encoded values before publication. This bounds values, not model error or physical
validity. It may coexist with `--log-outputs` on different targets; held-out metrics remain in
decoded units. Existing identity/exp arithmetic and unlinked v1 export remain unchanged.

**Set networks.** `--network deepsets|mpnn --set-elements E [--set-context C] [--mask-feature f]
--phi-widths 32,32 --rho-widths 32 [--pool sum|mean|max]` trains a permutation-invariant model
over E element blocks of the inputs (element-major, then C global inputs); MPNN adds
`--rounds T --message-widths ... --relative-features 0,1 --aggregate mean|sum`. It exports
`generic_surrogate_v3` (nested `network.kind`; one arithmetic contract for C++, NumPy, pure
Python and the TorchScript twin: [`set_networks.py`](trech_torch/set_networks.py)). It needs
torch and never falls back to another structure. First scenario user:
`build_glass_conduction_set_models.py` runs the recorded `glass_from_sand` harvests (pair
conduction teacher) and trains one DeepSets conduction model per cell material into
`data/glass_furnace_conduction_set/`, writing every engine/trainer command to its
`build_record.json` (`PYTHONPATH=tools/torch build/render-venv/bin/python
tools/torch/build_glass_conduction_set_models.py --python build/render-venv/bin/python`).

**Error bars on separate runs.** `--calibration-runs DIR...` (disjoint from `--runs` and
`--validation-runs`) set the carried `prediction_interval` at `--interval-coverage` (default
0.9) and the calibration RMSE, with the runs listed. The half-width is a run-level (grouped)
conformal quantile: runs, not their correlated rows, are the units; `run_level_guarantee` holds
with ≥ c/(1−c) calibration runs (9 at 0.9), otherwise the worst run's own quantile is carried.
The engine reports the half-width with each prediction; the validator then checks it on test
runs that never set it.

**Fresh-run re-checks of committed models.** `python -m trech_torch.recheck_models` reads
[`data/ml_recheck_recipes.json`](../../data/ml_recheck_recipes.json), produces new runs with seeds
the model never saw (a Python producer such as
`distill_discrete_scenario_operators.fresh_run`, or `trech run <scenario> --seed` with per-seed
operating points `seed_params` and an optional `env`), regenerates
the original holdout to prove the producer has not drifted, and grades the committed model with
the validator ([report](../../docs/validation/ml_model_recheck.md)).

`PYTHONPATH=tools/torch python tools/torch/distill_foam_mechanics.py` reproduces the experimental
foam constitutive model from independent synthetic teacher samples (18,006 fitting / 6,006 held
out). Three constitutive heads are fused into one portable named-IO network. This is explicitly
`measured:false`, not training on independently observed foam mechanics. Even its ≥0.998 held-out
R² is insufficient for promotion: `bash scripts/validate_foam_mechanics.sh` checks complete
nominal/zero-g/hot trajectories and currently fails observer gaps. `mechanics_source=reference`
remains the scenario default; `mechanics_source=operator` is opt-in. Train only to a build-local
`--model-root` when experimenting, then evaluate before replacing the committed candidate.

The three trainers below are specialised presets over the same machinery, kept
because their deployed models are validated/committed.

## Optics surrogate trainer

`trech-train-optics-surrogate` reads `trech_viz_scene.json` files (output of
`trech run` with `optics.derive.enable: true`), builds a training set mapping
**(element mass fractions + density) → (mean refractive index, mean absorption
length, mean scatter length)** from the `derived_optics` block, trains a small
MLP with input standardization baked into the exported module, and writes a
TorchScript model + manifest (with model size and leave-one-out validation
metrics). With `--anchors` the handbook n overrides the extractor's n target so
the surrogate learns the measured residual.

```bash
trech-train-optics-surrogate \
  --scenes build/dev/out_optics_panel \
  --anchors ../../data/optics_handbook_anchors.json \
  --out build/dev/optics_surrogate.pt \
  --manifest build/dev/optics_surrogate.manifest.json \
  --epochs 200 --seed 1234
```

The input vector layout matches `OpticsSurrogate::kCompositionElements` in
`include/trech/ml/OpticsSurrogate.hpp` — keep them in lock-step. The **deployed
composition→n model is the ridge `.json`** exported by
`scripts/validate_optics_surrogate.py --export` (LibTorch-free,
`data/optics_surrogate_ridge.json`), which passes the LOO promotion gate on the
current 15-material panel where the MLP does not; the MLP path is available for
multi-output (abs, scat) models once the panel grows.

## Event stratifier trainer

`trech-train-event-stratifier` reads run directories with
`trech_event_features.jsonl` dumps (`stratify.enable` + `stratify.dumpFeatures`)
and fits a **standardised logistic regression** mapping the 7-feature
`trech_event_features_v1` vector → p(exceptional). The teacher labels are the
engine's deterministic thresholds (later: resim-confirmed labels). It exports
the LibTorch-free logistic `.json` the C++ `TorchScriptStub` json backend loads
via `stratify.modelPath`, plus an optional bit-parity TorchScript `.pt`.

```bash
trech-train-event-stratifier \
  --runs build/dev/out_stratify_* \
  --out-json build/dev/stratify_logistic.json \
  --out build/dev/stratify_logistic.pt \
  --manifest build/dev/stratify_model.manifest.json
```

Deploy the `.json` only when the manifest's `beats_majority_baseline` gate is
true; the engine additionally requires `determinism.mode: "predictive"`.

## Discrete-scenario operator distillation

`distill_discrete_scenario_operators.py` reproducibly generates build-local,
run-shaped training/independent-holdout datasets for the retired H2O-cycle,
efflux and osmotic JS teachers, then invokes the generic trainer for:

- `h2o_cycle_transition_operator` (`ctx.react`, meso);
- `efflux_transport_operator` (`ctx.evolve`, micro);
- `efflux_crossing_operator` (`ctx.react`, micro);
- `osmotic_thermostat_operator` (`ctx.evolve`, micro): the per-tick velocity change, trained
  on mirrored (−v, −noise) row pairs because the bath's velocity memory turns any bias into a
  drift;
- `osmotic_crossing_operator` (`ctx.react`, micro): channel passage, with certain passage and
  blocking written 0.25 past the [0,1] hazard bound so the engine clamp makes them exact.

`--only <name>` (repeatable) retrains a subset.

```bash
PYTHONPATH=tools/torch python3 tools/torch/distill_discrete_scenario_operators.py
```

The formulas in that tool are validation/distillation references only. Normal
scenario execution loads the generated JSON models under
`data/discrete_operators/`; each model and manifest says `measured:false` and
names its teacher.

## Geant4 experiment planner

`trech-plan-geant4-experiments` is the active-learning half of the loop: it
diagnoses where the trained models are starved (optics element/density coverage
gaps, LOO hotspots, event label balance, degenerate features, beam-energy and
dimension-scale coverage) and emits a ranked `geant4_experiment_plan.json` of
concrete simulation requests, each naming a scenario + config levers to run.

```bash
trech-plan-geant4-experiments \
  --optics-run build/dev/out_optics_panel \
  --anchors ../../data/optics_handbook_anchors.json \
  --runs build/dev/out_stratify_* \
  --out build/dev/geant4_experiment_plan.json
```

### When to retrain

The optics surrogate predicts what the C++ `MolecularOpticsExtractor` would
compute (shifted toward handbook anchors), so retrain when the extractor (KK
window, cross-section sources) changes or the material panel grows. The event
stratifier retrains when the threshold teacher, feature schema, or the set of
Geant4 scenarios feeding it changes. See `CHARTS.md` →
"Geant4 → training → inference linkage" for the full per-prediction map.

## Independent model validation

`trech-validate-surrogate` (`python -m trech_torch.validate_model`) grades a
trained model with named gates (`pass`/`warn`/`fail`/`skip`): engine-loadable
structure, finite outputs over the trained domain, trust-profile completeness,
the model's own carried accuracy, TorchScript twin parity, and — given
independent `--test-runs` — evaluator parity, run leakage (directories and
replayed provenance configurations), test accuracy against `--min-r2`, holdout
reproduction, a ridge baseline fitted on the same training runs, σ calibration
and test-set domain coverage:

```bash
trech-validate-surrogate --model build/dev/my_surrogate.json \
  --test-runs build/dev/test_* --training-runs build/dev/train_* \
  --source event_features --out build/dev/my_surrogate.validation.json
```

`--scan data projects --audit-json … --audit-md …` audits every committed
model statically (pure Python). The gates and the committed audit are described
in [`docs/inference/ml_models.md`](../../docs/inference/ml_models.md#validating-a-model);
`trech-ml validate` runs the same validator on store checkpoints.

## Evolvo structure search

Initialize `thirds/evolvo` and install the optional Torch dependency, then use
`python -m trech_torch.evolve_structure` (or `trech-evolve-structure` after reinstalling the package).
The CLI requires disjoint `--runs`, `--validation-runs`, and `--test-runs`, named inputs/outputs and
`--out-json`; generation/population, width/depth, parameter and soft time bounds control work.
It exports the existing portable GenericSurrogate format with final untouched-test accuracy.
The ordinary trainer also accepts `--depth N` instead of fixing two hidden layers. See
[the full contract and examples](../../docs/engine/adaptive_precision.md#evolvo-model-definitions-and-search).

## Routing domains

`python -m trech_torch.routing_domain` (`trech-measure-routing-domain`) measures a model's
`routing_domain` from harvested rows: the min/max/std of per-element facts the law does not read
(a phase fraction, a composition ratio) over the population it was trained on. The engine's
domain routing uses it to tell which elements a law applies to when rival laws read the same
inputs ([contract](../../docs/engine/scenario_hooks.md)). Example (glass from sand, teacher harvest):

```bash
PYTHONPATH=tools/torch python -m trech_torch.routing_domain --runs build/glass_routing/train_* \
  --tag thermal_sample_melt --expand samples --features melt_fraction,glass_silica_fraction \
  --model data/glass_furnace_operators_trained/thermal_melt.json
```

## Evolved architectures (GFSL-NN)

`python -m trech_torch.evolve_architecture` (`trech-evolve-arch`) searches whole torch
architectures in Evolvo's GFSL-NN language (primitives plus `mlp`/`resmlp`/`transformer`/
`deepsets` macros). It uses learned choice weights, learned size pressure and learned epoch
stopping, on disjoint train/selection/test runs. Dense chains export as native
`generic_surrogate_v1` JSON; anything else exports as TorchScript + sidecar. `--knowledge`
carries what one search learned into the next. Contract, outputs and the synthetic
demonstration: [`docs/inference/evolvo_architectures.md`](../../docs/inference/evolvo_architectures.md).

`python -m trech_torch.compare_search` (`trech-compare-search`) compares grid, random, the
Evolvo width/depth search, random GFSL-NN genomes, the learned GFSL-NN search and its
knowledge-reuse variant on one rows table, with one shared trainer and equal budgets of distinct
trained candidates. Measured result on the Geant4 particle-observer runs:
[search quality](../../docs/inference/evolvo_architectures.md#search-quality-on-geant4-runs-2026-11-27).
