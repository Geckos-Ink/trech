#!/usr/bin/env python3
"""Run scenarios on QuickJS and on V8 and compare every output byte for byte.

TRECH's V8 backend runs the same host source as QuickJS (src/js/JsRuntimeV8.cpp) with the
same deterministic Math, so `trech run` must write the same files on both engines. This tool
runs each scenario twice with one `trech` binary built with -DTRECH_ENABLE_V8=ON
(`--js-engine quickjs`, then `--js-engine v8`) and compares the output directories:

  - every file must exist on both sides with identical bytes, except
  - JSON Lines files, where each record is compared after dropping the fields that name the
    run rather than its physics: `cli_args`, `output_dir`, `macro_path`, `js_engine` and
    wall-clock fields (`*_wall_seconds`, `*_ms`, `timestamp*`).

A second QuickJS run is the control. When QuickJS does not replay itself (multi-threaded
emit order, for example), a difference is not the engine's: the scenario is reported as
`reference_not_replayable` and is not a failure. Both engines get the same pinned
TRECH_COMPUTE_BUDGET (unless one is set), because learner capacities derive from a measured
host budget otherwise.

Usage:
  scripts/js_engine_run_parity.py --trech build/v8/trech [--events N] [--json report.json]
                                  [--timing] [--no-control] [scenario.js ...]
Default scenarios: the hook-driven repository scenarios listed in DEFAULT_SCENARIOS.
Exit status 1 when any scenario differs or fails on one engine only.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import tempfile
import os
import time
from pathlib import Path
from typing import Dict, List, Optional

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_SCENARIOS = [
    "examples/scenarios/hello_world/hello_world.js",
    "examples/scenarios/config_hook_dispatch/config_hook_dispatch.js",
    "examples/scenarios/hooks_track_ledger/hooks_track_ledger.js",
    "examples/scenarios/cascade_multiscale_demo/cascade_multiscale_demo.js",
    "examples/scenarios/surrogate_generic_demo/surrogate_generic_demo.js",
    "examples/scenarios/h2o_bulk_water/h2o_bulk_water.js",
    "examples/scenarios/briggs_rauscher_oscillator/briggs_rauscher_oscillator.js",
    "examples/scenarios/lava_lamp/lava_lamp.js",
]
PINNED_BUDGET = ('{"hardware_threads":8,"torch_threads":1,"memory_bytes":8000000000,'
                 '"gflops":20,"source":"js_engine_run_parity"}')
VOLATILE = re.compile(r"^(cli_args|output_dir|macro_path|js_engine)$|_wall_seconds$|_ms$|^timestamp")


def normalize(record):
    if isinstance(record, dict):
        return {k: normalize(v) for k, v in record.items() if not VOLATILE.search(k)}
    if isinstance(record, list):
        return [normalize(v) for v in record]
    return record


def compare_dirs(left: Path, right: Path) -> List[str]:
    problems: List[str] = []
    names = sorted({p.relative_to(left).as_posix() for p in left.rglob("*") if p.is_file()} |
                   {p.relative_to(right).as_posix() for p in right.rglob("*") if p.is_file()})
    for name in names:
        a, b = left / name, right / name
        if not a.exists() or not b.exists():
            problems.append(f"{name}: only on {'v8' if not a.exists() else 'quickjs'}")
            continue
        da, db = a.read_bytes(), b.read_bytes()
        if da == db:
            continue
        if name.endswith(".jsonl"):
            la = [normalize(json.loads(x)) for x in da.decode().splitlines() if x.strip()]
            lb = [normalize(json.loads(x)) for x in db.decode().splitlines() if x.strip()]
            if la == lb:
                continue
            if len(la) != len(lb):
                problems.append(f"{name}: {len(la)} vs {len(lb)} records")
                continue
            for i, (ra, rb) in enumerate(zip(la, lb)):
                if ra != rb:
                    keys = sorted(k for k in set(ra) | set(rb) if ra.get(k) != rb.get(k)) if isinstance(ra, dict) else []
                    problems.append(f"{name}: record {i} differs in {keys[:8]}")
                    break
            continue
        problems.append(f"{name}: bytes differ ({len(da)} vs {len(db)})")
    return problems


def run(trech: str, scenario: str, engine: str, out: Path, events: Optional[int]) -> Dict:
    command = [trech, "run", scenario, "--js-engine", engine, "--output", str(out)]
    if events is not None:
        command += ["--events", str(events)]
    env = dict(os.environ)
    env.setdefault("TRECH_COMPUTE_BUDGET", PINNED_BUDGET)
    env.pop("TRECH_JS_ENGINE", None)
    start = time.perf_counter()
    done = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, env=env)
    return {"exit": done.returncode, "seconds": time.perf_counter() - start,
            "stderr": done.stderr[-2000:]}


def main(argv: List[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--trech", required=True, help="trech binary built with TRECH_ENABLE_V8")
    parser.add_argument("--events", type=int, default=None, help="override every scenario's event count")
    parser.add_argument("--json", type=Path, default=None, help="write a JSON report here")
    parser.add_argument("--timing", action="store_true", help="print wall time per engine")
    parser.add_argument("--no-control", action="store_true",
                        help="skip the second QuickJS run that checks QuickJS replays itself")
    parser.add_argument("scenarios", nargs="*")
    args = parser.parse_args(argv)
    scenarios = args.scenarios or DEFAULT_SCENARIOS
    report = []
    failed = 0
    with tempfile.TemporaryDirectory(prefix="trech_engine_parity_") as scratch:
        for index, scenario in enumerate(scenarios):
            base = Path(scratch) / f"{index:02d}"
            q = run(args.trech, scenario, "quickjs", base / "quickjs", args.events)
            v = run(args.trech, scenario, "v8", base / "v8", args.events)
            entry = {"scenario": scenario, "quickjs": q, "v8": v}
            if q["exit"] != 0 or v["exit"] != 0:
                same_failure = q["exit"] == v["exit"]
                entry["status"] = "both_failed" if same_failure else "engine_failure"
                if not same_failure:
                    failed += 1
            else:
                problems = compare_dirs(base / "quickjs", base / "v8")
                entry["problems"] = problems
                entry["status"] = "identical" if not problems else "differs"
                if problems and not args.no_control:
                    c = run(args.trech, scenario, "quickjs", base / "control", args.events)
                    control = compare_dirs(base / "quickjs", base / "control") if c["exit"] == 0 else ["control failed"]
                    entry["control_problems"] = control
                    if control:
                        entry["status"] = "reference_not_replayable"
                failed += entry["status"] == "differs"
            report.append(entry)
            line = f"{entry['status']:>14}  {scenario}"
            if args.timing:
                line += f"  quickjs {q['seconds']:.2f}s  v8 {v['seconds']:.2f}s"
            print(line)
            for problem in entry.get("problems", []):
                print(f"                {problem}")
            if entry["status"] in ("engine_failure", "both_failed"):
                for engine in ("quickjs", "v8"):
                    if entry[engine]["exit"]:
                        print(f"                {engine} exit {entry[engine]['exit']}: "
                              f"{entry[engine]['stderr'].strip().splitlines()[-1:]}")
    if args.json:
        args.json.write_text(json.dumps(report, indent=2) + "\n")
    unreplayable = sum(e["status"] == "reference_not_replayable" for e in report)
    print(f"{len(report) - failed - unreplayable}/{len(report)} scenarios identical across engines; "
          f"{unreplayable} not replayable on QuickJS itself; {failed} engine difference(s)")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
