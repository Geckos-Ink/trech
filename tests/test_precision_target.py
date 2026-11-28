#!/usr/bin/env python3
"""`run.precisionTarget` stops a Geant4 run once its event-deposit mean is precise enough.

The engine adds each event's total deposited energy and ends the run (softly, after that event)
once the standard error of the mean is at most `relativeStderr` of the mean, after at least
`minEvents` events; `nEvents` stays the upper limit. The run uses a serial kernel, so the stop is
a function of seed and config and strict runs replay byte for byte.

Checks, on real serial Geant4 runs:
- a strict 5% target stops early with stop_reason "precision_target", its achieved relative
  standard error is at most 5% and equals the run's own system_event_edep_stderr_mev / mean, and
  a second run is byte-identical (scores; provenance apart from its paths);
- `--precision-target 0.05` on a config without a target gives the same run;
- an unreachable target runs every event (stop_reason "event_limit", reached false);
- events that deposit nothing never reach it (achieved null);
- run.threads > 1 with a target is refused (exit 1);
- a run without a target keeps its score shape (no precision_target, stop_reason, requested_events).

Usage: test_precision_target.py <path to trech>
"""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path


def config(target=None, particle="gamma", events=4000, threads=None) -> dict:
    run = {"nEvents": events, "seed": 11}
    if target is not None:
        run["precisionTarget"] = {"relativeStderr": target, "minEvents": 30}
    if threads is not None:
        run["threads"] = threads
    return {"environment": {"worldSizeMm": 200, "worldMaterial": "G4_WATER"},
            "beam": {"particle": particle, "energyMeV": 1.0, "direction": [0, 0, 1]},
            "run": run, "determinism": {"mode": "strict"}}


def run(trech: str, work: Path, name: str, cfg: dict, *flags: str):
    script = work / f"{name}.js"
    script.write_text("globalThis.TRECH_CONFIG = " + json.dumps(cfg) + ";\n")
    out = work / name
    proc = subprocess.run([trech, "run", str(script), "--output", str(out), *flags],
                          capture_output=True, text=True, timeout=600)
    scores = [json.loads(l) for l in (out / "trech_scores.jsonl").read_text().splitlines()] \
        if (out / "trech_scores.jsonl").exists() else []
    return proc, out, (scores[-1] if scores else {})


def main() -> int:
    if len(sys.argv) != 2:
        print(__doc__, file=sys.stderr)
        return 2
    trech = sys.argv[1]
    problems, checks = [], []

    def expect(ok: bool, message: str) -> None:
        checks.append(message)
        print(("PASS " if ok else "FAIL ") + message)
        if not ok:
            problems.append(message)

    with tempfile.TemporaryDirectory(prefix="trech_precision_") as tmp:
        work = Path(tmp)
        proc, out, s = run(trech, work, "target", config(0.05))
        target = s.get("precision_target") or {}
        expect(proc.returncode == 0 and s.get("stop_reason") == "precision_target"
               and 30 <= s.get("n_events", 0) < 4000 and s.get("requested_events") == 4000,
               f"5% target stops early ({s.get('n_events')} of 4000 events, {s.get('stop_reason')})")
        achieved = target.get("achieved_relative_stderr")
        own = s.get("system_event_edep_stderr_mev", 0) / s.get("system_event_edep_mean_mev", 1)
        expect(target.get("reached") is True and achieved is not None and achieved <= 0.05
               and abs(achieved - own) <= 1e-12 * own and target.get("events") == s.get("n_events"),
               f"achieved {achieved} <= 0.05 and equals the run's own stderr/mean {own}")
        _, again, _ = run(trech, work, "target_replay", config(0.05))
        same = (out / "trech_scores.jsonl").read_bytes() == (again / "trech_scores.jsonl").read_bytes()
        prov = [json.loads(l) for l in (out / "trech_provenance.jsonl").read_text().splitlines()]
        prov2 = [json.loads(l) for l in (again / "trech_provenance.jsonl").read_text().splitlines()]
        for record in prov + prov2:
            record.pop("cli_args", None)
            record.pop("output_dir", None)
        expect(same and prov == prov2, "strict replay is identical (score bytes, provenance)")
        end = prov[-1]
        expect(end.get("stop_reason") == "precision_target" and end.get("precision_target", {}).get("reached")
               and prov[0].get("precision_target") == {"relative_stderr": 0.05, "min_events": 30},
               "provenance records the target and why the run stopped")

        _, _, flagged = run(trech, work, "flag", config(None), "--precision-target", "0.05")
        expect(flagged.get("n_events") == s.get("n_events")
               and flagged.get("precision_target") == s.get("precision_target"),
               "--precision-target gives the same run as the config block")

        _, _, never = run(trech, work, "unreachable", config(0.001, events=60))
        expect(never.get("n_events") == 60 and never.get("stop_reason") == "event_limit"
               and (never.get("precision_target") or {}).get("reached") is False,
               "an unreachable target runs every event (event_limit)")

        _, _, empty = run(trech, work, "geantino", config(0.05, particle="geantino", events=40))
        et = empty.get("precision_target") or {}
        expect(empty.get("n_events") == 40 and et.get("reached") is False
               and et.get("achieved_relative_stderr") is None,
               "events that deposit nothing never reach the target (achieved null)")

        proc, _, _ = run(trech, work, "threads", config(0.05, threads=2))
        expect(proc.returncode == 1 and "run.threads must be 0 or 1" in proc.stderr,
               "a multi-threaded precision target is refused")

        _, _, plain = run(trech, work, "plain", config(None, events=20))
        expect(plain.get("n_events") == 20 and not ({"precision_target", "stop_reason", "requested_events"} & set(plain)),
               "a run without a target keeps its score shape")
    print(f"{len(checks) - len(problems)}/{len(checks)} precision-target checks passed")
    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main())
