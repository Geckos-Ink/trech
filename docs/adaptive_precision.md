# Adaptive precision and work budgets

TRECH has no fixed three-level simulation or inference limit. Scale bands describe physical
scales; each band can contain any number of models. Precision presets remain convenient
starting points, with continuous refinement and explicit work bounds alongside them.

## Scenario precision

For scenarios using `TRECH_HELPERS.precision.resolve`, pass any finite positive factor relative
to the balanced reference:

```sh
build/dev/trech inspect examples/scenarios/lava_lamp/lava_lamp.js --refinement 1.375
build/dev/trech run examples/scenarios/lava_lamp/lava_lamp.js --refinement 1.375 --output build/refined_lamp
```

The same helper accepts `factor: 1.375` in its JS specification. Counts multiply and time/grid
steps divide by the factor according to the scenario's axis declarations. Scenario minima,
maxima, integer rounding and explicit per-axis overrides still apply. The actual axes travel
in config/provenance/scores; a factor differing from the requested preset is labelled `custom`.
A CLI request on a scenario that does not use the helper fails explicitly. Refinement cannot
add absent physics or turn an illustrative model into a validated model.

## Prediction depth

`ctx.cascade(seed?, modelNames?, options?)` accepts optional deterministic limits:

```js
const prediction = ctx.cascade(undefined, undefined, {
  maxStages: 24,                 // 0 or omitted: all declared stages
  targetOutputs: ["response"]  // optional: stop when all these facts exist
});
ctx.emit("prediction", prediction);
```

Stages execute in ascending scale bands. Within each band the first dependency-ready model
runs next, preserving registration order among ready peers; reverse-declared chains work too.
Each model runs at most once. Cycles and absent inputs remain blocked, and higher-band facts
cannot feed a lower band. `maxStages` counts successful model evaluations. Skipped stages publish
no synthetic output and add no inference count. The trace records `skipReason`; `__cascade`
adds `stagesLimited`, `targetsReached` and `stopReason` when options are supplied. Missing target
facts are reported as `targets_unavailable` when no work limit stopped execution. Strict mode
still returns `null` before inference. These limits apply to `ctx.cascade`; batched operators
retain their existing material-selection and complete-call semantics.

## Predictive simulation time

```sh
build/dev/trech run experiment.js --events 100000 --time-budget 2.5 --output build/timed
```

The scenario must select `determinism.mode: "predictive"`. The equivalent config field is
`run.timeBudgetSeconds`; zero/absent keeps fixed work and historical config serialization.
Timed runs use a serial Geant4 manager and record `run.threads: 1`. Strict runs reject timing
budgets; a machine-dependent stopping decision cannot satisfy their fixed-work reproducibility.
UI/macro runs and persistent lab kernels reject this batch-only option.

`SimulationBudget` measures full event cost and uses an EWMA to stop before starting an event
estimated not to fit. At least one event completes. It is a **soft** bound: Geant4 initialization
and model loading are excluded, and one long event or hook callback can exceed the allowance.
Run-end hooks/output flushing also take time. No physics or inference result is replaced with
an approximation to meet a deadline.

Run-start metadata retains the requested count. Run-end scores and provenance report actual
`n_events`, `requested_events`, `time_budget_seconds`, `simulation_wall_seconds`, and
`stop_reason` (`time_budget` or `event_limit`). The scene manifest is updated to the actual
count. Config JSON/hash retains the requested workload and budget. Studio displays both counts.
The live lab's existing measured rounds-per-tick planner remains available independently.

## Studio and captures

The **Precision and resources** dock exposes continuous scenario refinement, predictive time
budgets, a render detail factor, target frame rate and a preview working-memory allowance.
Automatic rendering adjusts detail smoothly from measured CPU preparation/submission cost,
with an eight-observation cadence and hysteresis. Viewport pixel area, particle count and the
working allowance also bound tessellation. Sphere/tube meshes and surface extraction grids
change detail; emitted positions, radii, bonds, vectors and time remain unchanged. Surface
kernel width and threshold remain authored values. The panel reports actual detail and timing;
GPU execution time is currently unmeasured.

The default working allowance uses physical RAM where available (portable fallback: 256 MiB).
It determines trajectory loading/segment limits and GPU cache lengths. This is an estimate,
not a hard RSS/VRAM cap: hook emits and particle frames are still loaded in memory. Changing
this allowance affects trajectory loading the next time output is opened. Truncation remains
visible in the precision report. Capture settings are fixed for reproducibility:

```sh
PYTHONPATH=studio python -m trech_studio.capture --run build/run --out build/capture \
  --trajectory-limit 12000 --segment-budget 1200000 --render-detail 1.75 --render-memory-mib 512
```

Zero trajectory/segment limits request all recorded samples. Omitting the new capture options
keeps the historical capture detail and limits. Fixed representation choices enter the sidecar;
ordinary captures do not adapt to transient frame timings or update reference GIFs.

## Evolvo model definitions and search

[Evolvo](https://github.com/Geckos-Ink/evolvo) is pinned as `thirds/evolvo`, an optional Python
source dependency (MIT). Initialize it with `git submodule update --init thirds/evolvo`.
The C++ runtime and Studio do not import it. The generic `search_structure(score, ...)` adapter
accepts a validation-loss callback and evolves bounded MLP width/depth definitions using actual
GFSL genomes, mutation and crossover. The caller can set generation, population, depth, width
and soft time bounds. Fixed-work searches preserve seeded Python/NumPy RNG state. Evolved
control-flow programs are rejected before execution.

With NumPy and optional PyTorch installed, the offline trainer harvests TRECH outputs, trains
candidate structures, selects on validation runs and tests the selected weights on untouched
runs. The three sets must contain disjoint run directories. Use Geant4-driven training labels
for learned physical predictions; comparison-only teachers remain comparison data.

```sh
PYTHONPATH=tools/torch python -m trech_torch.evolve_structure \
  --runs build/training --validation-runs build/selection --test-runs build/test \
  --source hook_emits --tag observations --inputs input_a,input_b --outputs response \
  --max-depth 16 --max-width 128 --max-parameters 200000 --time-budget 60 \
  --out-json build/evolved_response.json
```

Candidate fitting is atomic, so the search time bound can overrun by one candidate. The exported
portable `generic_surrogate_v1` includes the selected structure/search provenance, measured input
domain and final test accuracy, and is usable by the existing C++ loader. Search loss is
selection data, never reported as independent test accuracy. This is an offline tool; it does
not replace running models automatically. The ordinary surrogate trainer also supports
`--depth N` (default 2) for any positive hidden-layer count.
