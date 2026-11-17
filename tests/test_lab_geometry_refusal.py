#!/usr/bin/env python3
"""Lab-mode geometry refusal through a real Geant4 kernel (``trech lab``).

A lab config with ``geometry.refuseOn: "any"`` and a volume naming a material
Geant4 does not know is refused on its first ``simulate``: one
``geometry_refused`` provenance record, no scores, and a ``lab error`` line.
An interactive session (stdin, as Studio drives it) stays up, and a second
``simulate`` on the same kernel is refused again without a second record. A
command file stops at the first refusal with exit 1. The config registers
``onInit``, but a lab session runs no JavaScript, so the refusal record must
not count an ``onInit`` call.

Usage: test_lab_geometry_refusal.py <path to trech>
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

CONFIG = {
    "beam": {"particle": "gamma", "energyMeV": 0.662, "direction": [0, 0, 1],
             "originMm": [0, 0, -120]},
    "run": {"nEvents": 4, "seed": 7},
    "hooks": {"registered": ["onInit"]},
    "geometry": {
        "refuseOn": "any",
        "volumes": [
            {"name": "target", "material": "G4_WATER",
             "shape": {"type": "box", "sizeMm": [60.0, 60.0, 60.0]},
             "placement": {"parent": "world", "positionMm": [0, 0, 0]}, "scoreEdep": True},
            {"name": "shield", "material": "G4_UNOBTAINIUM",
             "shape": {"type": "box", "sizeMm": [40.0, 40.0, 4.0]},
             "placement": {"parent": "world", "positionMm": [0, 0, -60.0]}},
        ],
    },
}
COMMANDS = ('{"action":"simulate","events":2}\n'
            '{"action":"simulate","events":2}\n'
            '{"action":"quit"}\n')


def fail(message: str) -> None:
    print(message, file=sys.stderr)
    raise SystemExit(1)


def lab(trech: str, work: Path, name: str, stdin: str = "", command_file: bool = False):
    out = work / name
    config = work / "config.json"
    args = [trech, "lab", "--config", str(config), "--output", str(out)]
    if command_file:
        commands = work / "commands.jsonl"
        commands.write_text(COMMANDS, encoding="utf-8")
        args += ["--commands", str(commands)]
    proc = subprocess.run(args, input=stdin, capture_output=True, text=True, timeout=240)
    provenance = out / "trech_provenance.jsonl"
    records = ([json.loads(line) for line in provenance.read_text(encoding="utf-8").splitlines()
                if line.strip()] if provenance.exists() else [])
    return proc, records, out


def main() -> int:
    if len(sys.argv) != 2:
        fail(__doc__)
    trech = sys.argv[1]
    with tempfile.TemporaryDirectory() as tmp:
        work = Path(tmp)
        (work / "config.json").write_text(json.dumps(CONFIG), encoding="utf-8")

        proc, records, out = lab(trech, work, "interactive", stdin=COMMANDS)
        errors = [line for line in proc.stderr.splitlines() if line.startswith("lab error:")]
        if proc.returncode != 0:
            fail(f"interactive lab exited {proc.returncode}:\n{proc.stderr[-2000:]}")
        if len(errors) != 2 or "geometry.refuseOn" not in errors[0]:
            fail(f"expected two refused batches, got:\n{proc.stderr[-2000:]}")
        if "Restart the lab session" not in proc.stderr:
            fail("the second batch must be refused by the remembered kernel refusal")
        if [r.get("phase") for r in records] != ["geometry_refused"]:
            fail(f"expected one geometry_refused record, got {[r.get('phase') for r in records]}")
        record = records[0]
        refusal = record.get("geometry_refusal") or {}
        if refusal.get("schema") != "trech_geometry_refusal_v1" or \
                refusal.get("refused_count", 0) < 1 or "material_fallback" not in refusal.get("refuse_on", []):
            fail(f"unexpected geometry_refusal block: {refusal}")
        kinds = [issue.get("kind") for issue in record.get("geometry_resolution", {}).get("issues", [])]
        if "material_fallback" not in kinds:
            fail(f"refusal record lacks the material_fallback issue: {kinds}")
        if record.get("hook_on_init_count") != 0 or record.get("n_events") != 0:
            fail("a lab refusal must count no onInit call and no events: "
                 f"hook_on_init_count={record.get('hook_on_init_count')} n_events={record.get('n_events')}")
        if (out / "trech_scores.jsonl").exists():
            fail("a refused lab batch must not write scores")

        proc, records, _ = lab(trech, work, "command_file", command_file=True)
        if proc.returncode != 1 or proc.stderr.count("lab error:") != 1:
            fail(f"a command file must stop at the first refusal (exit {proc.returncode}):\n"
                 f"{proc.stderr[-2000:]}")
        if [r.get("phase") for r in records] != ["geometry_refused"]:
            fail("the command-file refusal must write one geometry_refused record")
    print("lab geometry refusal: interactive session refuses twice with one record; "
          "command file stops at the first refusal")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
