#!/usr/bin/env python3
"""A scenario hook that throws ends the run with its message instead of hanging.

The JS runtime turns a hook exception into a C++ exception. Raised inside a Geant4 user
action on a worker task, it used to end the task while the master waited for it forever:
`trech run` sat at 0% CPU with no message. The dispatch site now latches the first failure,
soft-aborts the event loop, dispatches no further hooks, and the run exits 1 with
"TRECH error: hook <name> threw: <message>".

Cases: a throw in onEventStart on event 3, serial and with two workers, and a throw in
onRunStart. Each must exit 1 well inside the timeout, name the hook and carry the message, and
never dispatch a later hook (onRunEnd's emit is absent).

Usage: test_hook_failure_exit.py <path to trech>
"""

from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path

SCENARIO = """
globalThis.TRECH_CONFIG = {{
  beam: {{ particle: "geantino", energyMeV: 1.0, direction: [0, 0, 1] }},
  run: {{ nEvents: 40, seed: 11, threads: {threads} }}
}};
let started = 0;
globalThis.TRECH_HOOKS = {{
  onRunStart(ctx) {{
    if ({throw_on_run_start}) throw new Error("planted run-start failure");
  }},
  onEventStart(ctx) {{
    started += 1;
    if (ctx.event && ctx.event.id === 3) throw new Error("planted event failure at 3");
  }},
  onRunEnd(ctx) {{
    ctx.emit("run_end_reached", {{ started }});
  }}
}};
"""


def fail(message: str) -> None:
    print(message, file=sys.stderr)
    raise SystemExit(1)


def run_case(trech: str, work: Path, name: str, threads: int, throw_on_run_start: bool,
             expect_hook: str, expect_message: str) -> None:
    script = work / f"{name}.js"
    script.write_text(SCENARIO.format(threads=threads,
                                      throw_on_run_start="true" if throw_on_run_start else "false"),
                      encoding="utf-8")
    out = work / f"out_{name}"
    try:
        proc = subprocess.run([trech, "run", str(script), "--output", str(out)],
                              capture_output=True, text=True, timeout=120,
                              stdin=subprocess.DEVNULL)
    except subprocess.TimeoutExpired:
        fail(f"{name}: trech run hung after a hook threw (timed out)")
    if proc.returncode != 1:
        fail(f"{name}: expected exit 1, got {proc.returncode}\n{proc.stderr[-2000:]}")
    wanted = f"TRECH error: hook {expect_hook} threw: "
    if wanted not in proc.stderr or expect_message not in proc.stderr:
        fail(f"{name}: stderr lacks {wanted!r} / {expect_message!r}\n{proc.stderr[-2000:]}")
    emits = out / "trech_hook_emits.jsonl"
    if emits.exists() and "run_end_reached" in emits.read_text(encoding="utf-8"):
        fail(f"{name}: a hook ran after the failure (onRunEnd emitted)")
    print(f"ok {name}: exit 1, {wanted}{expect_message}")


def main() -> int:
    if len(sys.argv) != 2:
        fail(__doc__)
    trech = sys.argv[1]
    with tempfile.TemporaryDirectory(prefix="trech_hook_failure_") as tmp:
        work = Path(tmp)
        run_case(trech, work, "event_serial", 1, False, "onEventStart", "planted event failure at 3")
        run_case(trech, work, "event_two_workers", 2, False, "onEventStart",
                 "planted event failure at 3")
        run_case(trech, work, "run_start", 1, True, "onRunStart", "planted run-start failure")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
