# Engine trace: see what the engine decided

[Documentation home](../README.md) · [Engine index](README.md) · [CLI and live lab](cli.md) · [Hook API](scenario_hooks.md) · [Output schema](output_schema.md#trech_tracejsonl)

A rendered scenario shows you a result. It does not show you where that result came from.
A frame of the lava lamp may come from the engine's statistical layers, such as a learned
cascade, an operator or a method chosen by the arbiter. It may instead come from a law the
scenario wrote itself, often a fallback that runs when the engine returns nothing. The
**engine trace** is a verbose log that you can configure. It records these decisions while the
run happens. At the end it prints an *attribution summary*: how many inference calls the engine
answered, how many returned nothing, and how many emitted records had no engine result behind
them.

The trace only observes. It never changes physics, random-number streams, emitted payloads, the
config JSON or the config hash. It is off by default. You turn it on from the command line or
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
| `--trace <level>[:<cat>,...]` | Level and optional category filter, e.g. `trace:predict,evolve`. `run` and `lab` only. |
| `--trace-file <path>` | Write the JSONL somewhere other than `<output>/trech_trace.jsonl`. |
| `--trace-stderr` | Also print every record as one line on stderr (`[trech:debug] hook onEventEnd#3 …`). |
| `TRECH_TRACE`, `TRECH_TRACE_FILE`, `TRECH_TRACE_STDERR=1` | The same settings from the environment. CLI flags take precedence. Useful when Studio or a script launches `trech`. |

### Levels

Each level includes everything below it.

| Level | Records |
| --- | --- |
| `off` | Nothing (default). |
| `summary` | Only the run attribution summary (counters are kept, no per-call records). |
| `info` | Run start (mode, models declared and loaded), each model load **or miss**, method-arbiter leader changes, hook exceptions, `ctx.log`/`TRECH_LOG` notes. |
| `debug` | One record per hook invocation (engine calls, engine-backed calls, emits by tag, `ctx.authored` reports) and per method-arbiter step (policy, leader, methods selected, RMSE). |
| `trace` | One record per `ctx.*` inference call with digests of its arguments and result. This level is large: filter it by category. |

### Categories

`run`, `model`, `hook`, `scenario`, `authored`, `arbiter`, and one per inference entry point:
`predict`, `cascade`, `evolve`, `react`, `interact`, `lift`, `detectDomains`, `learnDomains`,
`evolveField`. The category filter limits the records written. It never limits the summary
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
  count for each law, and a `debug` record carries the detail.
- `ctx.log(message, data?)` writes an `info` record in the `scenario` category.
- `TRECH_LOG(message, data?)` does the same while the scenario is being evaluated, before any
  hook runs.

These reports come from the scenario's own declaration. The [scenario purity report](../validation/TRECH_current_scenarios_purity.md)
remains the static audit of authored laws in the source. The trace adds what actually ran.

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
- Geant4 transport itself (steps, processes) and the inner stages of `ctx.evolve` and
  `ctx.cascade` are not traced separately. Their per-stage metadata appears in the result digest
  at `trace` level.
- Studio does not show the trace yet. If you start Studio with `TRECH_TRACE` set, the `trech`
  processes it launches inherit the setting. Each run then writes `trech_trace.jsonl` in its
  output directory.
- In a `trech lab` session, one summary covers the whole session. The summary is not split per
  batch.

Open work is tracked in the [core roadmap](../../AGENTS/engine/core/ROADMAP.md#priority-queue).
