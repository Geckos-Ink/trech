#!/usr/bin/env python3
"""``trech lab <experiment.js> --watch`` through a real Geant4 kernel.

A copy of ``examples/lab/live_hook_tuning.js`` runs in an interactive session (stdin, as
Studio drives it). Between batches the test edits the file on disk, without sending any
``reload`` command:

1. A hook-only edit (the threshold's default 0.5 -> 0.15) is picked up before the next batch:
   script generation 2, trigger ``watch``, and the batch's ``deposit_tally`` uses 0.15.
2. A kernel-bound edit (the beam energy's default) is refused before the next batch. The
   refusal is reported once, not before every batch, and the batches keep running on
   generation 2 on the same kernel.
3. Reverting the beam energy makes the file byte-identical to generation 2 again: no change,
   no reload.
4. A further threshold edit (0.15 -> 0.2) is accepted as generation 3.

Every batch's provenance ``lab_script`` names the generation that ran and its trigger, and
the config hash never changes (one kernel).

Usage: test_lab_watch.py <path to trech> <path to examples/lab/live_hook_tuning.js>
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROUND_PLAN = '"phase":"lab_round_plan"'


def fail(message: str) -> None:
    print(message, file=sys.stderr)
    raise SystemExit(1)


def batch(proc: subprocess.Popen, events: int = 20) -> None:
    """Send one simulate command and wait for its round-plan telemetry line."""
    assert proc.stdin is not None and proc.stdout is not None
    proc.stdin.write(json.dumps({"action": "simulate", "events": events}) + "\n")
    proc.stdin.flush()
    for line in proc.stdout:
        if ROUND_PLAN in line:
            return
    fail("lab exited before the batch finished")


def edit(path: Path, old: str, new: str) -> None:
    text = path.read_text(encoding="utf-8")
    if old not in text:
        fail(f"fixture text not found: {old}")
    path.write_text(text.replace(old, new, 1), encoding="utf-8")


def main() -> int:
    if len(sys.argv) != 3:
        fail(__doc__)
    trech, example = sys.argv[1], Path(sys.argv[2])
    with tempfile.TemporaryDirectory(prefix="trech_lab_watch_") as tmp:
        work = Path(tmp)
        scenario = work / "live_hook_tuning.js"
        shutil.copyfile(example, scenario)
        out = work / "out"
        stderr_path = work / "stderr.txt"
        with stderr_path.open("w", encoding="utf-8") as stderr:
            proc = subprocess.Popen(
                [trech, "lab", str(scenario), "--watch", "--output", str(out)],
                stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=stderr, text=True)
            try:
                batch(proc)                                  # generation 1 (start)
                edit(scenario, "default: 0.5, min: 0", "default: 0.15, min: 0")
                batch(proc)                                  # generation 2 (watch)
                edit(scenario, "default: 1.25, min: 0.1", "default: 2.5, min: 0.1")
                batch(proc)                                  # refused: still generation 2
                batch(proc)                                  # refused state is not re-reported
                edit(scenario, "default: 2.5, min: 0.1", "default: 1.25, min: 0.1")
                batch(proc)                                  # same bytes as generation 2
                edit(scenario, "default: 0.15, min: 0", "default: 0.2, min: 0")
                batch(proc)                                  # generation 3 (watch)
                assert proc.stdin is not None
                proc.stdin.write('{"action":"quit"}\n')
                proc.stdin.flush()
                proc.stdin.close()
                code = proc.wait(timeout=120)
            finally:
                if proc.poll() is None:
                    proc.kill()
        errors = stderr_path.read_text(encoding="utf-8")
        if code != 0:
            fail(f"lab exited {code}:\n{errors}")
        refusals = errors.count("watched edit refused")
        if refusals != 1:
            fail(f"expected one watched-edit refusal, got {refusals}:\n{errors}")
        if "restart the lab session" not in errors:
            fail(f"the refusal should explain the restart:\n{errors}")

        runs = [json.loads(line) for line in (out / "trech_provenance.jsonl").open(encoding="utf-8")]
        ends = [r for r in runs if r.get("phase") == "run_end"]
        scripts = [(r["lab_script"]["generation"], r["lab_script"]["trigger"]) for r in ends]
        expected = [(1, "start"), (2, "watch"), (2, "watch"), (2, "watch"), (2, "watch"),
                    (3, "watch")]
        if scripts != expected:
            fail(f"batch script generations {scripts}, expected {expected}")
        hashes = {r.get("config_hash") for r in ends}
        if len(hashes) != 1:
            fail(f"one kernel should keep one config hash, got {hashes}")

        emits = [json.loads(line) for line in (out / "trech_hook_emits.jsonl").open(encoding="utf-8")]
        thresholds = [e["payload"]["threshold_mev"] for e in emits if e.get("tag") == "deposit_tally"]
        if thresholds != [0.5, 0.15, 0.15, 0.15, 0.15, 0.2]:
            fail(f"deposit_tally thresholds {thresholds}")
    print("lab watch: hook edits reloaded before the batch, a kernel edit refused once")
    return 0


if __name__ == "__main__":
    sys.exit(main())
