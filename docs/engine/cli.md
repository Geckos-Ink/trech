# CLI and live lab

[Documentation home](../README.md) · [Engine index](README.md) · [Build](../build.md) · [First run](../first_run.md)

Run `./build/dev/trech --help` for the options supported by the local executable.
Use paths relative to the repository root in the examples below.

| Command | Purpose |
| --- | --- |
| `trech inspect experiment.js` | Evaluate JS authoring and report its config, typed parameters and sources. |
| `trech run experiment.js --output dir` | Run an experiment and write its records. |
| `trech lab --config config.json` | Keep a session open and issue JSON Lines commands. |
| `trech budget` | Report host compute budget and model capacity. |
| `trech arch job.json` | Run the [architecture search workflow](../inference/evolvo_architectures.md). |

Use `--param name=<json>` repeatedly for declared values in `run` or `inspect`.
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
[Lab output and planner fields](output_schema.md#trech-lab-stdout) ·
[Runtime roadmap](../../AGENTS/engine/runtime/ROADMAP.md#priority-queue)
