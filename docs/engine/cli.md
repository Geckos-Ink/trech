# CLI and live lab

[Documentation home](../README.md) · [Engine index](README.md) · [Build](../build.md) · [First run](../first_run.md)

Run `./build/dev/trech --help` for the options supported by the local executable.
Use paths relative to the repository root in the examples below.

| Command | Purpose |
| --- | --- |
| `trech inspect experiment.js` | Evaluate JS authoring and report its config, typed parameters and sources. |
| `trech run experiment.js --output dir` | Run an experiment and write its records. |
| `trech lab --config config.json` | Keep a session open and issue JSON Lines commands. |
| `trech lab experiment.js` | The same live session driven by a JavaScript scenario, whose hooks can be re-tuned between batches. |
| `trech budget` | Report host compute budget and model capacity. |
| `trech arch job.json` | Run the [architecture search workflow](../inference/evolvo_architectures.md). |

Use `--param name=<json>` repeatedly for declared values in `run`, `inspect` or a
scenario-backed `lab`.
Quote JSON strings for your shell, for example `--param 'material="urea"'`.
`--strict-config` refuses unknown keys. `--events` and `--seed` override the
requested event count and random seed in `run`. `--viz` captures optical trajectories
and `--viz-all` also captures non-optical trajectories. `run` also supports a Geant4
`--macro` or interactive `--ui` when the corresponding Geant4 support is available.
Use a separate `--output` directory per run to make comparisons easy.

## Strict and predictive runs

Set `determinism.mode` in the JavaScript configuration or the lab JSON. Some bundles
expose a typed `mode` parameter. Use `inspect` to see the controls for the chosen
bundle.

| Mode | Behaviour |
| --- | --- |
| `strict` (default) | Fixed-work replay with model inference disabled. Use one worker for callbacks that accumulate JavaScript state across events. |
| `predictive` | Enables configured model paths and logs the inference and artifact provenance. The batch CLI can use a soft `--time-budget` that stops at complete event boundaries. |

`--refinement` changes supported scenario precision axes. See
[work budgets and refinement](adaptive_precision.md), the
[hook API](scenario_hooks.md#determinism-modes) and
[recorded output fields](output_schema.md).

## Live lab

The lab reads one JSON object per line from stdin or `--commands`. Try the bundled
[initial config](../../examples/lab/realtime_lab_bootstrap.json) and
[command stream](../../examples/lab/realtime_lab_commands.jsonl).

```sh
./build/dev/trech lab --config examples/lab/realtime_lab_bootstrap.json \
  --commands examples/lab/realtime_lab_commands.jsonl --output build/dev/out_lab
```

| Action | Use |
| --- | --- |
| `{"action":"patch","patch":{...}}` | Merge and validate the patch. Null values remove fields and restore defaults. |
| `{"action":"simulate"}` | Run a batch with the timing planner's event count. |
| `{"action":"simulate","events":5,"seed":42}` | Override the event count or seed for this simulation command. |
| `{"action":"snapshot"}` | Print the canonical config and timing/precision state. |
| `{"action":"help"}` / `{"action":"quit"}` | List actions or close the session. |

The first batch initializes Geant4. Compatible batches reuse its kernel. Live
changes to event count, seed and planner settings are allowed. Changes to
kernel-bound geometry, beam, physics, scoring or output state require a new
session. Use `achieved_hz` when describing actual batch rate.

### Scenario-backed lab: re-tune hooks between batches

Start the lab with a scenario instead of `--config` and its JavaScript hooks run in every
batch. Two more actions then re-evaluate the scenario between batches, on the same
initialized Geant4 kernel:

| Action | Use |
| --- | --- |
| `{"action":"params","values":{"name":<json>}}` | Change declared [`TRECH_VALUE`](scenario_hooks.md#typed-authoring-values)s and re-evaluate the scenario. `null` restores a value's default. Values accumulate across commands. |
| `{"action":"reload"}` | Re-read the scenario and its includes from disk, for example after editing a hook. |

Add `--watch` and you don't need to send `reload` at all. Before each batch, the lab checks
the files the active script read: the entry, its `TRECH_INCLUDE`s and its `TRECH_READ_JSON`
data files. If any of them now has different bytes, or is gone, the lab re-evaluates the
scenario first, with the same all-or-nothing rules as `reload`. Saving a file without changing
it is no edit, so hook state survives. A refused watched edit prints
`lab error: watched edit refused, the previous script stays active: …` once for that on-disk
state. The batch, and later ones, still run on the previous script, even from a command file.
Edit the file again to try once more.

```sh
./build/dev/trech lab examples/lab/live_hook_tuning.js --watch --output build/dev/out_live_lab
```

For example, type `{"action":"simulate","events":20}`, change the threshold's `default: 0.5`
to `0.15` in the file, save, and simulate again: the second `deposit_tally` reports
`"threshold_mev":0.15` from script generation 2, with trigger `watch`. Studio's live lab
(**Run ▸ Start live lab**) runs this mode for you; see the
[Studio guide](../../studio/README.md#live-lab).

Try the bundled [live tuning scenario](../../examples/lab/live_hook_tuning.js) with its
[command stream](../../examples/lab/live_hook_tuning_commands.jsonl):

```sh
./build/dev/trech lab examples/lab/live_hook_tuning.js \
  --commands examples/lab/live_hook_tuning_commands.jsonl --output build/dev/out_live_lab
```

It runs three 200-event batches with the same seed. Geant4 therefore transports the same
events each time, and only the hook-layer threshold changes: the `deposit_tally` emits report
44, 58 and 44 events above 0.5, 0.1 and 0.5 MeV.

A re-evaluation is all or nothing. The lab evaluates the scenario in a separate JavaScript
runtime, runs its `onInit`, replays your accepted `patch` commands on the new config and keeps
the session's event count and seed. It swaps the new hooks in only if all of that succeeds and
the result still fits the initialized kernel. Otherwise it prints
`lab error: re-evaluation refused: …` and the previous hooks, their JavaScript state and the
config stay active. A command file stops with exit code 1 on a refusal; an interactive session
continues. The kernel refuses a re-evaluation that changes geometry, beam, physics, scoring,
output, models or the set of registered hook names. Changing a hook's body or a value only
the hooks read is always accepted. In the example, `beam_energy_mev` is refused and
`edep_threshold_mev` is accepted.

Hook state, such as module variables and `ctx.state`, persists from batch to batch and starts
afresh after each accepted re-evaluation. After every (re)load the lab prints
`Scenario re-evaluated (script generation N, <trigger>).` and one `{"phase":"lab_script",…}`
line with the script generation, why it was made (`trigger`: `start`, `params`, `reload` or
`watch`), the source digests, the overrides and the resolved declarations; `snapshot` repeats it as `lab.script`. Each batch's provenance
and scores record which script generation drove it as
[`lab_script`](output_schema.md#lab-script-identity), and `onInit` is counted once, in the
first batch after each load. Use `run.threads: 1` when hooks accumulate state, as for
`trech run`.

[Lab output and planner fields](output_schema.md#trech-lab-stdout) ·
[Runtime roadmap](../../AGENTS/engine/runtime/ROADMAP.md#priority-queue)
