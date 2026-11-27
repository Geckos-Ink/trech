#!/usr/bin/env python3
"""An unknown beam particle fails the run instead of silently becoming an electron.

TrechPrimaryGeneratorAction used to replace a particle name missing from the Geant4 particle
table with e-, so a misspelled beam ran electrons while the scores still reported the requested
name. The run now exits 1 with "beam.particle '<name>' ...", serial and with two workers, and a
known particle in the same configuration still runs.

Usage: test_beam_particle_refusal.py <path to trech>
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

SCENARIO = """
globalThis.TRECH_CONFIG = {{
  environment: {{ worldSizeMm: 20, worldMaterial: "G4_WATER" }},
  beam: {{ particle: "{particle}", energyMeV: 0.1, direction: [0, 0, 1] }},
  run: {{ nEvents: 3, seed: 1, threads: {threads} }},
  determinism: {{ mode: "strict" }}
}};
"""


def run(trech: str, work: Path, particle: str, threads: int):
    script = work / f"{particle}_{threads}.js"
    script.write_text(SCENARIO.format(particle=particle, threads=threads))
    out = work / f"out_{particle}_{threads}"
    proc = subprocess.run([trech, "run", str(script), "--output", str(out)], capture_output=True, text=True, timeout=180)
    return proc, out


def main() -> int:
    if len(sys.argv) != 2:
        print(__doc__, file=sys.stderr)
        return 2
    failures = []
    with tempfile.TemporaryDirectory() as tmp:
        work = Path(tmp)
        for threads in (1, 2):
            proc, _ = run(sys.argv[1], work, "no_such_particle", threads)
            text = proc.stdout + proc.stderr
            if proc.returncode != 1 or "beam.particle 'no_such_particle'" not in text:
                failures.append(f"threads {threads}: exit {proc.returncode}, message missing: {text[-400:]}")
        proc, out = run(sys.argv[1], work, "gamma", 1)
        scores = out / "trech_scores.jsonl"
        if proc.returncode != 0 or not scores.exists():
            failures.append(f"known particle failed: exit {proc.returncode}")
        else:
            last = json.loads(scores.read_text().splitlines()[-1])
            if last.get("primaries_emitted") != 3:
                failures.append(f"known particle emitted {last.get('primaries_emitted')} primaries")
    for f in failures:
        print("FAIL: " + f)
    print("beam particle refusal: " + ("ok" if not failures else f"{len(failures)} failure(s)"))
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
