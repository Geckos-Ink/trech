#!/usr/bin/env python3
"""A `trech run` that stops before Geant4 runs writes one `run_failed` provenance record.

Before, a scenario that failed to evaluate, a config that did not parse, an onInit hook that
threw or a setup Geant4 refused left no provenance at all, so the output directory did not say
which script failed or why, and a traced run's trace file had nothing pointing at it. Now each
of these exits 1 and appends one `run_failed` record (`failure`: schema `trech_run_failure_v1`,
stage, error, entry-script hashes). Its seed and determinism fields appear only once the config
parsed. When traced, the record carries a `trech_trace_ref_v1` reference to the batch summary the
failure closed, and `trech_validation.trace_ref` checks it like a `run_end` one.

Runs that already write provenance keep their records and get no `run_failed`: a clean run, a
geometry refusal (`geometry_refused`) and a hook that throws mid-run (`run_start`/`run_end`).

Usage: test_run_failure_provenance.py <path to trech>
"""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools" / "validation"))
from trech_validation.trace_ref import fnv1a64, verify_run  # noqa: E402

BASE = {
    "environment": {"worldSizeMm": 30, "worldMaterial": "G4_WATER"},
    "beam": {"particle": "gamma", "energyMeV": 0.1, "direction": [0, 0, 1]},
    "run": {"nEvents": 2, "seed": 7, "threads": 1},
}


def scenario(config=None, hooks=None, prefix="") -> str:
    text = prefix
    if config is not None:
        text += "globalThis.TRECH_CONFIG = " + json.dumps(config) + ";\n"
    if hooks:
        text += "globalThis.TRECH_HOOKS = {" + ",".join(
            f"{name}: function(ctx) {{ {body} }}" for name, body in hooks.items()) + "};\n"
    return text


def with_(**changes) -> dict:
    config = json.loads(json.dumps(BASE))
    for key, value in changes.items():
        config[key] = {**config.get(key, {}), **value} if isinstance(value, dict) else value
    return config


REFUSED_GEOMETRY = {
    "refuseOn": "any",
    "volumes": [{"name": "shield", "material": "G4_UNOBTAINIUM",
                 "shape": {"type": "box", "sizeMm": [10.0, 10.0, 2.0]},
                 "placement": {"parent": "world", "positionMm": [0, 0, 0]}}],
}

# name -> (script, expected stage or None for "no run_failed", expected phases, traced)
CASES = {
    "evaluate": (scenario(prefix='throw new Error("boom at evaluate");\n'), "evaluate", ["run_failed"], True),
    "evaluate_untraced": (scenario(prefix='throw new Error("boom at evaluate");\n'), "evaluate", ["run_failed"], False),
    "config": (scenario(with_(run={"nEvents": 2.5})), "config", ["run_failed"], True),
    "on_init": (scenario(with_(hooks={"registered": ["onInit"]}), {"onInit": 'throw new Error("init failed");'}),
                "on_init", ["run_failed"], True),
    "geant4": (scenario(with_(beam={"particle": "no_such_particle"})), "geant4", ["run_failed"], True),
    "geant4_mt": (scenario(with_(beam={"particle": "no_such_particle"}, run={"threads": 2})),
                  "geant4", ["run_failed"], False),
    "clean": (scenario(BASE), None, ["run_start", "run_end"], True),
    "geometry_refused": (scenario(with_(geometry=REFUSED_GEOMETRY)), None, ["geometry_refused"], False),
    "hook_throws": (scenario(with_(hooks={"registered": ["onEventEnd"]}), {"onEventEnd": 'throw new Error("late");'}),
                    None, ["run_start", "run_end"], True),
}


def read(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()] if path.exists() else []


def check(trech: str, work: Path, name: str) -> list[str]:
    script_text, stage, phases, traced = CASES[name]
    script = work / f"{name}.js"
    script.write_text(script_text)
    out = work / f"out_{name}"
    command = [trech, "run", str(script), "--output", str(out)] + (["--trace", "summary"] if traced else [])
    proc = subprocess.run(command, capture_output=True, text=True, timeout=300)
    problems = []
    expected_exit = 0 if name == "clean" else 1
    if proc.returncode != expected_exit:
        problems.append(f"exit {proc.returncode}, expected {expected_exit}: {proc.stderr[-400:]}")
    records = read(out / "trech_provenance.jsonl")
    if [r.get("phase") for r in records] != phases:
        problems.append(f"phases {[r.get('phase') for r in records]}, expected {phases}")
        return problems
    if stage is None:
        return problems
    record = records[0]
    failure = record.get("failure") or {}
    if failure.get("schema") != "trech_run_failure_v1" or failure.get("stage") != stage:
        problems.append(f"failure block {failure}")
    if "TRECH error: " + failure.get("error", "\0") not in proc.stderr:
        problems.append("the recorded error is not the one printed")
    data = script.read_bytes()
    identity = failure.get("script") or {}
    if (identity.get("sha256"), identity.get("fnv1a64"), identity.get("size_bytes")) != (
            hashlib.sha256(data).hexdigest(), fnv1a64(data), len(data)):
        problems.append(f"script identity {identity}")
    parsed = stage not in ("evaluate", "config")
    if failure.get("config_parsed") != parsed or failure.get("config_evaluated") != (stage != "evaluate"):
        problems.append(f"config flags {failure}")
    if stage == "evaluate":
        if record.get("config_json") != "" or record.get("config_hash") != "":
            problems.append("an unevaluated script recorded a config")
    elif record.get("config_hash") != fnv1a64(record.get("config_json", "").encode()):
        problems.append("config_hash is not the hash of config_json")
    # Seed and mode only once the config parsed: an unparsed config claims neither.
    if parsed != ("seed" in record) or parsed != ("determinism_mode" in record):
        problems.append(f"seed/determinism present={('seed' in record)} for stage {stage}")
    if parsed and (record["seed"], record["requested_events"]) != (7, 2):
        problems.append(f"seed/requested_events {record['seed']}/{record['requested_events']}")
    if record.get("n_events") != 0 or not str(record.get("geant4_version", "")).startswith("Geant4 version"):
        problems.append(f"n_events {record.get('n_events')} / geant4_version {record.get('geant4_version')!r}")
    for absent in ("hook_on_step_count", "stratify_enabled", "system_event_count"):
        if absent in record:
            problems.append(f"run_failed carries the full-run counter {absent}")
    if traced != ("trace" in record):
        problems.append(f"trace reference present={'trace' in record}, traced={traced}")
    if traced:
        report = verify_run(out)
        if report["state"] != "ok" or report.get("failure_stages") != [stage]:
            problems.append(f"trace_ref {report['state']}: {report['problems']}")
    return problems


def main() -> int:
    if len(sys.argv) != 2:
        print(__doc__, file=sys.stderr)
        return 2
    trech = sys.argv[1]
    failed = 0
    with tempfile.TemporaryDirectory(prefix="trech_run_failure_") as tmp:
        work = Path(tmp)
        for name in CASES:
            problems = check(trech, work, name)
            print(("FAIL " if problems else "PASS ") + name)
            for problem in problems:
                print("  - " + problem)
            failed += bool(problems)
        # A failure appends to an output directory that already holds a run's records.
        (work / "out_clean" / "trech_provenance.jsonl").replace(work / "kept.jsonl")
        reused = work / "out_reused"
        reused.mkdir()
        (work / "kept.jsonl").replace(reused / "trech_provenance.jsonl")
        script = work / "reused.js"
        script.write_text(CASES["evaluate"][0])
        subprocess.run([trech, "run", str(script), "--output", str(reused)], capture_output=True, timeout=120)
        phases = [r.get("phase") for r in read(reused / "trech_provenance.jsonl")]
        ok = phases == ["run_start", "run_end", "run_failed"]
        print(("PASS" if ok else "FAIL") + f" reused directory {phases}")
        failed += not ok
    print(f"{len(CASES) + 1 - failed}/{len(CASES) + 1} run-failure provenance checks passed")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
