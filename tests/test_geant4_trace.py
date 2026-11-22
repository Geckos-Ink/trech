"""Engine trace, Geant4 side: a real kernel reports when and how it simulated.

    python3 tests/test_geant4_trace.py <trech>

Runs one small scenario untraced and traced at `trace` level, serial and with two worker threads,
and checks that the trace is observation-only (identical scores and emits; with two workers the
emit order is compared as a set, see the runtime roadmap's strict-MT replay item) and complete:
kernel/run/event records, one track record per tallied track, one step record per tallied step,
per-process tallies that sum to the event step counts, and the `run_end` provenance reference.
"""

from __future__ import annotations

import collections
import json
import subprocess
import sys
import tempfile
from pathlib import Path

SCENARIO = """
globalThis.TRECH_CONFIG = {
  environment: { worldSizeMm: 100.0, worldMaterial: "G4_WATER" },
  beam: { particle: "gamma", energyMeV: 0.5 },
  run: { nEvents: 4, seed: 4242, threads: THREADS },
  determinism: { mode: "strict" },
  hooks: { registered: ["onEventEnd"] },
};
globalThis.TRECH_HOOKS = {
  onEventEnd(ctx) { ctx.emit("edep", { id: ctx.event.id, edep: ctx.event.edepMeV }); },
};
"""


def run(trech: str, script: Path, out: Path, *extra: str) -> str:
    result = subprocess.run([trech, "run", str(script), "--output", str(out), *extra],
                            capture_output=True, text=True, timeout=240)
    if result.returncode != 0:
        raise SystemExit(f"trech run failed ({result.returncode}):\n{result.stderr[-3000:]}")
    return result.stderr


def lines(path: Path):
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def check(trech: str, root: Path, threads: int) -> None:
    script = root / f"g4trace_{threads}.js"
    script.write_text(SCENARIO.replace("THREADS", str(threads)))
    off, on = root / f"off_{threads}", root / f"on_{threads}"
    run(trech, script, off)
    stderr = run(trech, script, on, "--trace", "trace")
    for name in ("trech_scores.jsonl", "trech_hook_emits.jsonl", "trech_event_scores.jsonl"):
        a, b = off / name, on / name
        if not (a.exists() or b.exists()):
            continue
        if name == "trech_hook_emits.jsonl" and threads > 1:
            # With several workers the emit order still follows worker scheduling (on V8 even
            # between two untraced runs): the open strict-MT replay item in the runtime roadmap.
            # Every emitted value must still be identical.
            assert sorted(a.read_text().splitlines()) == sorted(b.read_text().splitlines()), \
                f"{name} content differs traced vs untraced ({threads} threads)"
            continue
        assert a.read_bytes() == b.read_bytes(), f"{name} differs traced vs untraced ({threads} threads)"

    records = lines(on / "trech_trace.jsonl")
    by = collections.Counter((r["cat"], r["msg"]) for r in records if r["cat"].startswith("geant4"))
    summary = records[-1]["data"]
    tallies = summary["tallies"]
    assert by[("geant4", "kernel initialized")] == 1, by
    kernel = next(r["data"] for r in records if r["msg"] == "kernel initialized")
    assert kernel["physics_list"].startswith("QBBC") and kernel["placed_volumes"] >= 1, kernel
    start = next(r["data"] for r in records if r["msg"] == "run start (beamOn)")
    assert start["events"] == 4 and start["sources"][0]["particle"] == "gamma", start
    assert by[("geant4", "event simulated")] == 4 and tallies["geant4.events"]["simulated"] == 4

    tracks = sum(tallies["geant4.tracks_by_particle"].values())
    steps = sum(tallies["geant4.steps_by_process"].values())
    assert tallies["geant4.tracks_by_particle"].get("gamma", 0) >= 4, tallies
    assert by[("geant4_track", "track start")] == tracks == by[("geant4_track", "track end")], (by, tracks)
    step_records = sum(1 for r in records if r["cat"] == "geant4_step")
    assert step_records == steps, (step_records, steps)
    event_steps = sum(r["data"]["steps"] for r in records if r["msg"] == "event simulated")
    assert event_steps == steps, (event_steps, steps)
    assert sum(tallies["geant4.steps_by_volume"].values()) == steps
    assert "Geant4 simulated 4 events" in summary["verdict"], summary["verdict"]
    assert "geant4.steps_by_process:" in stderr

    seen = next(r["data"] for r in records if r["msg"] == "run end")["particles_seen"]
    assert "gamma" in seen, seen
    processes = [r["data"] for r in records if r["msg"] == "physics processes" and r["data"]["particle"] == "gamma"]
    # QBBC wraps the gamma EM processes in GammaGeneralProc; steps still name compt/phot.
    names = {p["name"] for p in processes[0]["processes"]} if processes else set()
    assert "Transportation" in names and len(names) >= 2, processes

    provenance = lines(on / "trech_provenance.jsonl")
    ref = [r for r in provenance if r["phase"] == "run_end"][-1]["trace"]
    assert ref["schema"] == "trech_trace_ref_v1" and ref["totals"]["emits"] == 4, ref
    assert all("trace" not in r for r in lines(off / "trech_provenance.jsonl"))
    print(f"geant4 trace ({threads} thread(s)): {tracks:.0f} tracks, {steps:.0f} steps, ok")


def main() -> int:
    if len(sys.argv) != 2:
        print(__doc__)
        return 2
    with tempfile.TemporaryDirectory(prefix="trech_geant4_trace_") as tmp:
        for threads in (1, 2):
            check(sys.argv[1], Path(tmp), threads)
    return 0


if __name__ == "__main__":
    sys.exit(main())
