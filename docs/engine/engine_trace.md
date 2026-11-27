# Engine trace: see what the engine decided

[Documentation home](../README.md) · [Engine index](README.md) · [CLI and live lab](cli.md) · [Hook API](scenario_hooks.md) · [Output schema](output_schema.md#trech_tracejsonl)

A rendered scenario shows you a result. It does not show you where that result came from.
A frame of the lava lamp may come from the engine's statistical layers, such as a learned
cascade, an operator or a method chosen by the arbiter. It may instead come from a law the
scenario wrote itself, often a fallback that runs when the engine returns nothing. The
**engine trace** is a verbose log that you can configure. It records these decisions while the
run happens. At the end it prints an *attribution summary*: how many inference calls the engine
answered, how many returned nothing, and how many emitted records had no engine result behind
them. It also records the libraries underneath: when Geant4 simulated what, with which
physics, process by process; which learned models Torch loaded and ran; and how and on what data
the engine and the Python tools trained (Torch and numpy).

The trace only observes. It never changes physics, random-number streams, emitted payloads, the
config JSON or the config hash. A traced run's `run_end` provenance record gains a `trace`
reference (level, file, summary hash, totals, verdict), so a run's record says how it was
traced; untraced records are unchanged. It is off by default. You turn it on from the command line or
the environment, never from the scenario.

## Turn it on

```sh
./build/rel/trech run examples/scenarios/briggs_rauscher_oscillator/briggs_rauscher_oscillator.js \
  --output build/out_br --events 2 --trace debug
```

The run writes `build/out_br/trech_trace.jsonl` and prints a summary on stderr:

```text
TRECH trace summary: 1 of 1 ctx inference calls returned an engine result. 5 of 8 emits came from hook calls with no engine-backed inference.
  ctx.cascade: engine=1
  hook onEventEnd: invocations=2 emits=4 emits_without_inference=4
  hook onRunEnd: invocations=1 emits=1 emits_without_inference=1
  hook onRunStart: invocations=1 emits=3 emits_without_inference=0
```

Here is how to read it. `onRunStart` asked the engine for its cascade, and its three emits rest
on that result. The `onEventEnd` and `onRunEnd` emits did not call the engine in the same
invocation. Their values came from Geant4 tallies on `ctx`, from state carried over from an
earlier hook, or from JavaScript the scenario wrote. Use the debug records and the
[scenario purity report](../validation/TRECH_current_scenarios_purity.md) to tell these apart.

| Option | Meaning |
| --- | --- |
| `--trace <level>[:<cat>,...]` | Level and optional category filter, e.g. `trace:predict,evolve` or `trace:geant4_track`. `run`, `lab` and `arch` (`arch` also copies in its Python worker's records). |
| `--trace-file <path>` | Write the JSONL somewhere other than `<output>/trech_trace.jsonl`. |
| `--trace-stderr` | Also print every record as one line on stderr (`[trech:debug] hook onEventEnd#3 …`). |
| `TRECH_TRACE`, `TRECH_TRACE_FILE`, `TRECH_TRACE_STDERR=1` | The same settings from the environment. CLI flags take precedence. Useful when Studio or a script launches `trech`. |

### Levels

Each level includes everything below it.

| Level | Records |
| --- | --- |
| `off` | Nothing (default). |
| `summary` | Only the attribution summaries: one per batch and one for the run (counters are kept, no per-call records). |
| `info` | Run start (mode, models declared and loaded), each model load **or miss**, method-arbiter leader changes, lattice law-hypothesis checks, hook exceptions, `ctx.log`/`TRECH_LOG` notes. |
| `debug` | One record per hook invocation (engine calls, engine-backed calls, emits by tag, `ctx.authored` reports) and per method-arbiter step (policy, leader, methods selected, RMSE). |
| `trace` | One record per `ctx.*` inference call with digests of its arguments and result. This level is large: filter it by category. |

### Categories

`run`, `model`, `hook`, `scenario`, `authored`, `arbiter`, `formal` (law-hypothesis checks the engine runs
once per built lattice; see [formal laws](formal_laws.md)), and one per inference entry point:
`predict`, `cascade`, `evolve`, `react`, `interact`, `lift`, `detectDomains`, `learnDomains`,
`evolveField`. The simulation and learning libraries have their own: `geant4`, `geant4_track`
and `geant4_step` ([Geant4](#geant4-what-was-simulated-and-how)), `torch`
([learned models and training](#torch-what-was-inferred-and-trained)), and from the Python
tools `torch`, `numpy`, `arch` and `python` ([Python tools](#python-tools-torch-and-numpy)). Script records use `script`, `console` or the name of a
[`TRECH_TRACE.channel`](#log-from-any-javascript-trech_trace-and-console). The category filter limits the records written. It never limits the summary
counters, and the summary record is always written.

Each category writes at most 20000 records. Records beyond that are counted under
`suppressed_records` in the summary.

## Attribution outcomes

Every `ctx.*` inference call is classified from its own result:

| Outcome | Meaning |
| --- | --- |
| `engine` | The engine returned a result from learned inference or one of its own methods. |
| `engine_extrapolated` | An engine result produced outside the trained domain (`__coverage.inDomain: false`, `stagesExtrapolating > 0` or `outOfDomainInferences > 0`). Treat it as low-confidence. |
| `engine_not_ran` | An object came back but no engine stage ran (`ran: false`, `stagesRun: 0`, `levelsRun: 0`). A cascade with no loaded model returns only its seed. |
| `null_strict` | `null` because `determinism.mode` is `strict`, which disables inference. |
| `null_unavailable` | `null` in predictive mode: the model is undeclared, failed to load, or there was nothing to run. |
| `error` | The call threw. |

When a call returns `null` or does not run, the scenario's next value cannot have come from the
engine. It came from whatever fallback the scenario wrote. A summary dominated by `null_strict`
means that the run was strict. A summary dominated by `null_unavailable` usually means a model
file is missing. The `model missing` info record names it, and so does `models_missing` in the
summary.

## Let a scenario say when it uses its own law

The engine can see a `null` result. It cannot see what the scenario did next. Two hook
functions let a scenario report that itself. When the trace is off, both do nothing and change
nothing:

```js
onEventEnd(ctx) {
  const learned = ctx.predict("viscosity", { temperature_k: T });
  let viscosity;
  if (learned === null) {
    ctx.authored("arrhenius_viscosity", { reason: "no engine result", T });
    viscosity = A * Math.exp(B / T);           // residual authored law
  } else {
    viscosity = learned.viscosity_pa_s;
  }
  ctx.log("viscosity chosen", { viscosity });
  ctx.emit("viscosity", { viscosity });
}
```

- `ctx.authored(law, detail?)` counts one use of a named authored law. The summary lists the
  count for each law. A `debug` record (`{uses, detail?}`) is written at uses 1, 2, 4, 8, and so
  on, so a law called inside a loop cannot fill the category.
- `ctx.log(message, data?)` writes an `info` record in the `scenario` category.
- `TRECH_LOG(message, data?)` does the same while the scenario is being evaluated, before any
  hook runs.

### Validation and reference code: roles

The project principles let a scenario name or force a method only to **validate** it, and such
code must be labelled and stay off the decision path. The trace keeps that code apart, so a
validation companion that grades engine methods does not make the scenario look engine-backed,
and a reference solver it runs does not look like the scenario's own law.

- Functions of a `<name>.validation.js` companion (`TRECH_CHECKS["<name>"]`) run under the
  `validation` role. While tracing, the host wraps each of them after loading the companion. You
  do not need to change the companion.
- Any other code can declare its role with `TRECH_TRACE.role(role, fn)`. The role is one of
  `validation`, `reference`, `teacher` or `forced`; any other name throws a `TypeError`, with
  the trace on or off. With the trace off, `role` only calls `fn`.

```js
// A forced reference run, labelled as such:
const column = TRECH_TRACE.role("reference", () => solveReferenceColumn(state));
```

Under a role, records carry `"role": "<role>"`. The role's `ctx.*` calls and authored laws are
counted under `roles` in the summary, not in `calls`, `authored` or the scenario totals. A role's
engine call never makes a hook's emits count as engine-backed. The verdict ends with what ran off
the decision path, for example on the lava lamp:

```text
1 of 1 ctx inference calls returned an engine result. 5 of 8 emits came from hook calls with no
engine-backed inference. Off the decision path (validation/reference roles, not counted above):
3 ctx calls and 0 authored-law uses; see `roles`.
```

Here the lamp's validation companion ran `ctx.evolveField` three times to grade the engine's
field methods. Before roles existed, those calls were counted as the lamp's own engine calls.

These reports come from the scenario's own declaration. The [scenario purity report](../validation/TRECH_current_scenarios_purity.md)
remains the static audit of authored laws in the source. The trace adds what actually ran.

## Log from any JavaScript: `TRECH_TRACE` and `console`

Scenarios, companions, domain libraries and model definitions log through one global API. The
API is the same under QuickJS, under V8, in the Node model-definition loader (`trech-ml
inspect`, Studio's Models panel) and in plain Node:

```js
const log = TRECH_TRACE.channel("glass_model");   // records in category "glass_model"
log.info("library loaded", { version: 2 });       // info level
log.debug("plan", { layers: 3 });                 // debug level
log.trace("per-element detail", { i, v });        // trace level
log.warn("viscosity clamped", { at: T });         // info level, severity "warn"
log.error("no fit", { reason });                  // info level, severity "error"
if (log.enabled("trace")) log.trace("expensive", build());   // skip building costly payloads
log.count("solves");                              // summed in the run summary as glass_model.solves
const v = log.span("solve", () => solve(x));      // debug record with its wall-clock duration
TRECH_TRACE.info("…");                            // the default channel, category "script"
TRECH_TRACE.authored("arrhenius_viscosity");      // same as ctx.authored
TRECH_TRACE.role("reference", () => solve(x));    // counted under roles.reference, off the decision path
TRECH_TRACE.level();                              // "off", "summary", "info", "debug" or "trace"
console.log("plain", 2, { a: 1 });                // category "console", formatted like Node
```

| Function | Level, category | Note |
| --- | --- | --- |
| `info`/`log`, `debug`, `trace` | as named; the channel's category | `data` is digested (about 2 KB). |
| `warn`, `error` | info; `severity` set | If the level or category is not recorded, the message goes to stderr instead (`TRECH js warn: …`). It is never lost. |
| `enabled(level?)` | — | Whether a record at that level and category would be written. |
| `count(name, amount = 1)` | summary `counters` | Named per channel: `<category>.<name>`. |
| `span(name, fn, data?)` | debug | Returns `fn()`. The duration is written only to the trace and never returned to the script. |
| `channel(category)` | — | A logger with its own category, which you can filter with `--trace debug:<category>`. |
| `role(role, fn)` | — | Returns `fn()`, run as `validation`, `reference`, `teacher` or `forced` code. See [roles](#validation-and-reference-code-roles). |
| `console.log/info/debug/trace/warn/error` | info/info/debug/trace/info+warn/info+error, `console` | Replaces QuickJS's missing console and V8's silent one, so both engines behave the same. |

**Determinism.** None of these functions returns engine state or wall time to the script, apart
from `level()` and `enabled()`. Use those two only to decide whether to log, never to change
physics. Results, RNG and emits are the same with the trace on or off.
QuickJS and V8 write the same records. `trech_engine_trace` checks this, ignoring only the
span durations.

**Hosts.**

- In `trech` (QuickJS or V8), the engine installs `TRECH_TRACE` and `console`, and
  `TRECH_TRACE.host` is `"trech"`.
- In the Node model loader ([`tools/ml/lib/load.js`](../../tools/ml/lib/load.js)), records go
  into the inspection result. `logs` holds one text line per record and `records` holds the
  objects. The level comes from `$TRECH_TRACE` and defaults to `info`.
- In plain Node, `require("js/trech_trace.js")` installs the same API. Records go to
  `TRECH_TRACE_FILE` as JSONL, or to stderr.
- [`js/trech_trace.js`](../../js/trech_trace.js) is host-neutral. Inside `trech`,
  `TRECH_INCLUDE("trech_trace.js")` returns the engine's object, so a library can include it
  without checking which host it runs in.

## What the shared libraries log

The libraries in [`js/`](../../js) log on their own channels. So a trace of any scenario also
shows what its libraries decided, without any change to the scenario. Each library gets its
channel through one accessor line. In `trech` and in the model loader this is `TRECH_TRACE`.
In plain Node it is `js/trech_trace.js`. In any other host it is a silent no-op. No library
writes `warn` or `error`, so a library never prints on stderr when tracing is off.

| Channel | Records (level) | Counters (`<channel>.<name>`) |
| --- | --- | --- |
| `process_operators` | Contract bound (debug). Process advanced by the engine operator, with inferences and selection (debug). **Process not advanced**, with the reason code: `operator_blocked`, `artifact_mismatch`, `unit_mismatch`, `missing_context` and the others (info; `strict_disabled` is debug). | `<contract>.advanced`, `<contract>.<code>`, `<contract>.no_op` |
| `process_runtime` | Stage advanced (info). Step blocked or rejected, with the reason (info). Every other step (debug). | one per step status: `advanced`, `blocked`, `rejected`, `strict_disabled`, `complete` |
| `solution_processes` | Recipe compiled (debug). | |
| `molecular_particle` | Atom and molecular responses inferred, or none because inference is disabled in strict mode (debug). | |
| `material_facts` | Geant4-derived optics read (trace). PubChem reference structure read (debug). | |
| `domain_learning`, `domain_tracking` | Learned rates applied to fields (debug). Domain lineage (debug). | `rates_applied`, `rates_untouched` |
| `chemistry`, `chemistry_scene` | Reaction plan and scene declared (debug). | |
| `ml` | Model or search defined (debug). **Model resolved from the registry** (checkpoint, version) or the registry **fallback path used** (info). | |
| `geometry` | Geometry audit (debug; info when it finds a problem). | |
| `atomic_stability`, `atomic_composition` | Independent quantum reference solve (debug). | `solves`, `analyses` |
| `foam_solver`, `water_md`, `water_mw`, `euler_reference`, `euler3d_reference`, `crystallization_reference` | **Authored solver created (physics for comparison)** (info). | Each public step calls `TRECH_TRACE.authored("<library>.<step>")`, so the summary's `authored` lists every reference law that ran, for example `water_md.step: 4000`. |

`trech_math.js`, `trech_random.js` and the deterministic-math kernels are not instrumented. They
are hot numeric primitives with no decisions to report. `trech_helpers.js` is not instrumented
yet.

## Geant4: what was simulated and how

The base of truth is traced as well, so a trace shows when Geant4 ran, with which physics, and
what it did. Nothing here changes the simulation: the records only read Geant4's state.

| Level | Category | Records |
| --- | --- | --- |
| info | `geant4` | **kernel initialized**: Geant4 version, physics list (with its TRECH extensions, for example `QBBC+Optical`), threads, number of placed volumes, the materials (density, elements, state). **run start (beamOn)**: run id, events, seed, determinism and every primary source (particle, energy, direction, origin, spot, divergence, spread). **run end**: events and the particles seen. |
| debug | `geant4` | Every placed volume (solid, material, mother, translation), the production-cut couples, the physics processes of the primaries and of common particles, and at run end of every particle seen. One **event simulated** record per event (deposit, steps, tracks, worker thread). |
| trace | `geant4` | **event start** with the event's primaries (particle, energy, position). |
| trace | `geant4_track` | **track start** (id, parent, particle, energy, creator process or `primary`, volume, position) and **track end** (process that ended it, steps, length, final energy). |
| trace | `geant4_step` | One record per step; the message is the process that limited the step (`compt`, `eIoni`, `Transportation`...), with particle, volume, deposit, length and the energy before and after. |

At every level the summary has `tallies` counted from all threads: `geant4.events`,
`geant4.steps_by_process`, `geant4.edep_mev_by_process`, `geant4.tracks_by_particle`,
`geant4.tracks_by_creator` and `geant4.steps_by_volume`. The verdict ends with one sentence on
the base, for example:

```text
Geant4 simulated 3 events: 10 tracks, 21 steps (most steps: NoProcess 7, eIoni 7, compt 4).
```

Track and step records are capped at 20000 per category like any other, so filter them, for
example `--trace trace:geant4_track`; the tallies are always complete. With QBBC, gamma's process
list shows `GammaGeneralProc`, the wrapper that samples Compton, photoelectric and conversion;
steps still name the sub-process that ran. While tracing, the engine also registers its tracking
action (without track hooks) so that tracks are counted.

## Torch: what was inferred and trained

Category `torch` records the engine's learned models and its own training:

- **model loaded / model load failed** (info): component (`generic_surrogate`,
  `optics_surrogate`, `event_stratifier`), path, backend (`torchscript`, or the JSON law the
  file holds: `dense`, `ridge_json`, `logistic_json`...), and for TorchScript the module's type,
  parameter count, submodules and methods plus the LibTorch runtime (version, intra- and
  inter-op threads, MKL, OpenMP, MPS).
- **forward** (trace): one record per forward pass with the model and input and output digests.
  `torch.forwards_by_model` counts every pass and `torch.forward_failures_by_model` the rejected
  ones (non-finite input or output, wrong width).
- **training burst** (debug): each time `ctx.learnDomains` trains a domain's residual network
  with LibTorch Adam: domain, rows, features, targets, hidden width, parameters, steps, learning
  rate and the loss before and after. `torch.train_steps_by_learner` sums the steps.
- `trech arch` adds **classic reference trained** (category `arch`, debug) for each structure
  of its native C++ reference family.

The verdict adds, for example, `Torch ran 2 forward passes over 2 models and 48 training steps.`

## Python tools: torch and numpy

The training tools in [`tools/torch`](../../tools/torch) log through
[`trech_torch.trace`](../../tools/torch/trech_torch/trace.py), which writes the same records
(`schema` `trech_trace_v1`, plus `host: "python"`) and reads the same environment:

```sh
TRECH_TRACE=debug TRECH_TRACE_FILE=build/train_trace.jsonl \
  build/render-venv/bin/python -m trech_torch.train_surrogate ...
```

| Category | Records |
| --- | --- |
| `torch` | **runtime** once per process (Python, numpy, torch, threads, CUDA/MPS, deterministic algorithms, default dtype). **training start** (learner, epochs, rows, seed, the model's layers and parameters, the optimizer and its settings), **epoch** (loss, learning rate; epochs 1, 2, 4, 8... and the last at debug, every epoch at trace, with the gradient norm), **training end** (steps, first/last/best loss). **model exported** (path, format, bytes, SHA-256). |
| `numpy` | **array** (debug): shape, dtype, bytes, non-finite count, min/max/mean/std and constant columns of the data a fit saw. **fit** (debug): least-squares/ridge fits with design and target shapes, regularisation and the condition number. The event stratifier's numpy gradient descent is traced like a training loop. |
| `arch` | Architecture search start and end, and **candidate trained** for every architecture Evolvo trains (architecture, parameters, epochs, loss, stop reason). |

Traced learners: `train_surrogate` (MLP and ridge), `set_networks`, `train_optics_surrogate`,
`train_event_stratifier`, `domain_learner` (publishing), and the Evolvo architecture search.
A process writes a **python summary** when it exits: its tallies, counters and authored laws.
Training gives the same weights with the trace on or off; the trace never draws random numbers.

When `trech arch` runs with `--trace`, it starts its Python worker with the same level and
categories and its own file (`<job>.worker.log.trace.jsonl`). When the worker ends, the engine
copies the worker's records into `trech_trace.jsonl` with `origin: "python"` between **worker
start** and **worker end** records (category `python`), and adds the worker's tallies to its
summary:

```text
TRECH trace summary: No ctx inference call ran and nothing was emitted. Torch ran 160 forward passes over 2 models and 360 training steps.
  torch.train_steps_by_learner: arch.classic_native=180 evolvo.candidate=180
```

## Watch it live in Studio

The **Engine trace** tab in Studio's bottom dock asks the engine for the level and categories
you choose, and shows records as they are written. Records written with the functions above
appear there under their categories. When the run ends, the panel shows the attribution
verdict. See [the Studio guide](../../studio/README.md#engine-trace-panel). The engine flushes
every record so that a live reader sees it right away.

## Batches and provenance

Every Geant4 run ends with a **batch attribution summary** record: the same counts as the run
summary, but only for that batch. A `trech run` has one batch; a `trech lab` session has one
per `simulate`. The first batch also counts what happened before it (configuration and
`onInit`), and each later batch counts what happened since the previous one. The last line of
the file is still the run summary for the whole session.

The same batch is referenced from the `run_end` record of `trech_provenance.jsonl` as `trace`:

```json
"trace": {"schema": "trech_trace_ref_v1", "level": "summary", "categories": [],
          "path": "build/out_lab/trech_trace.jsonl", "batch": 2, "seq": 2,
          "summary_hash": "cb816bd11bd30996",
          "totals": {"calls": 1, "engine_backed": 1, "emits": 10, "emits_without_inference": 6, ...},
          "verdict": "1 of 1 ctx inference calls returned an engine result. ..."}
```

`summary_hash` is the FNV-1a 64 hash of the batch summary JSON, so you can check that a trace file
belongs to a provenance record. Two identical batches have the same hash. The reference is
written only when the trace is on, and it never enters `config_json` or `config_hash`.

To check a run, recompute the hashes:

```sh
PYTHONPATH=tools/validation python3 -m trech_validation.trace_ref build/out_lab
# build/out_lab: ok; 2 reference(s), 2 batch record(s), run summary present
```

The checker hashes the exact bytes of each batch record's `data` object, so it does not depend on
how a JSON library spells numbers. It also compares `seq`, `totals` and `verdict`, and exits 1 on
any mismatch. A traced `trech run` that fails before Geant4 runs (for example, a scenario that
throws while it is evaluated) closes one batch and writes a
[`run_failed` provenance record](output_schema.md#run_failed-records) with the same reference; the
checker verifies it like a `run_end` one and names the stage
(`out: ok; 1 reference(s), 1 batch record(s), run summary present; run_failed at evaluate`).
A run with neither record (a `trech lab` session that failed before its first batch) is reported
as `unreferenced`, not as a mismatch. A hook that throws during the run still writes `run_end`
with a matching reference. The validation suite runs this check in the
`trace_reference_matches_file` case.

```sh
# Per-batch verdicts of a lab session
jq -c 'select(.msg=="batch attribution summary") | {batch: .data.batch, emits: .data.totals.emits}' \
  build/out_lab/trech_trace.jsonl
```

## Example: read a trace

```sh
# Which hook invocations emitted without any engine result?
jq -c 'select(.cat=="hook" and .data.emits>0 and .data.engine_backed_calls==0) | {hook, event, tags: .data.emit_tags}' \
  build/out_br/trech_trace.jsonl

# The run summary only
tail -n 1 build/out_br/trech_trace.jsonl | jq .data
```

The record format is in the [output schema](output_schema.md#trech_tracejsonl).

## Limits

- The trace attributes each emit to its hook invocation. It does not attribute individual
  emitted values. An invocation that made one engine call and also used an authored law counts
  as engine-backed unless the scenario reports the law with `ctx.authored`.
- A Geant4 tally read from `ctx.event` is ground truth, but the trace does not record those
  reads. Emits built only from tallies appear in `emits_without_inference`.
- The inner stages of `ctx.evolve` and `ctx.cascade` are not traced separately. Their
  per-stage metadata appears in the result digest at `trace` level.
- Geant4's internal model choices within a process (which hadronic model or cross-section data
  set sampled an interaction) are not recorded; steps name the process only.
- In the Python tools, Evolvo's per-epoch training inside a candidate is not traced (only each
  candidate's result), and the scripts in `tools/torch/*.py` outside the `trech_torch` package
  log only through the trainers they call.

Open work is tracked in the [core roadmap](../../AGENTS/engine/core/ROADMAP.md#priority-queue).
