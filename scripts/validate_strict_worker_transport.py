#!/usr/bin/env python3
"""Check strict per-event Geant4 transport across workers; report byte-replay gaps.

This manual gate verifies event/trajectory physics keyed by identity. It does not
claim full strict byte replay: worker reductions and JSONL append ordering can
still differ, and their raw bytes/differences remain visible in the report.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
SCIENTIFIC_FILES = (
    "trech_scores.jsonl", "trech_event_scores.jsonl", "trech_event_features.jsonl",
    "trech_viz_scene.json", "trech_viz_trajectories.jsonl",
)
FILES = (*SCIENTIFIC_FILES, "trech_provenance.jsonl")


def rows(data: bytes) -> list[dict]:
    return [json.loads(line) for line in data.splitlines() if line.strip()]


def keyed(data: bytes, keys: tuple[str, ...]) -> dict[tuple, dict]:
    result = {}
    for row in rows(data):
        key = tuple(row[name] for name in keys)
        if key in result:
            raise AssertionError(f"duplicate record identity {key}")
        result[key] = row
    return result


def differences(left: object, right: object, prefix: str = "") -> list[dict]:
    """Retain exact differing scalar values, including unrounded float totals."""
    if isinstance(left, dict) and isinstance(right, dict):
        output = []
        for key in sorted(left.keys() | right.keys()):
            output.extend(differences(left.get(key), right.get(key), f"{prefix}/{key}"))
        return output
    if left != right:
        return [{"path": prefix, "left": left, "right": right}]
    return []


def run(binary: Path, script: Path, directory: Path, manager: str,
        workers: int, log: Path) -> dict[str, bytes]:
    directory.mkdir(exist_ok=True)
    for name in FILES:
        (directory / name).unlink(missing_ok=True)
    environment = dict(os.environ)
    for key in ("G4RUN_MANAGER_TYPE", "G4FORCENUMBEROFTHREADS",
                "G4FORCE_EVENTS_PER_TASK", "G4FORCE_GRAINSIZE"):
        environment.pop(key, None)
    environment["G4FORCE_RUN_MANAGER_TYPE"] = manager
    result = subprocess.run(
        [str(binary), "run", str(script), "--output", str(directory)],
        cwd=ROOT, env=environment, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        timeout=120,
    )
    log.write_bytes(result.stdout)
    if result.returncode:
        raise RuntimeError(f"{manager}/{workers} failed ({result.returncode}); see {log}")
    if workers > 1:
        # The fixture's Geant4 accumulable startup diagnostics identify every
        # initialized worker. A silent switch to serial must not pass this gate.
        actual_workers = set(re.findall(rb"G4WT(\d+)\s*>", result.stdout))
        assert len(actual_workers) == workers, (
            f"expected {workers} initialized workers, observed {len(actual_workers)}; see {log}"
        )
    return {name: (directory / name).read_bytes() for name in FILES}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--binary", type=Path, default=ROOT / "build/rel/trech")
    parser.add_argument("--baseline-binary", type=Path,
                        help="Verify unchanged one-worker and true-serial scientific bytes")
    parser.add_argument("--output", type=Path, default=ROOT / "build/strict_worker_transport")
    parser.add_argument("--events", type=int, default=24)
    parser.add_argument("--repeats", type=int, default=3)
    args = parser.parse_args()
    if args.events < 10 or args.repeats < 2:
        parser.error("use at least 10 events and two repeats to exercise worker scheduling")
    args.output.mkdir(parents=True, exist_ok=True)
    work = Path(tempfile.mkdtemp(prefix="validation_", dir=args.output.resolve()))
    cases = []
    reference = None
    for manager, workers in (("Tasking", 2), ("Tasking", 8), ("MT", 2), ("MT", 8)):
        case = work / f"{manager}_{workers}"
        case.mkdir()
        config = {
            "detector": {"worldSizeMm": 100, "worldMaterial": "G4_WATER"},
            "beam": {"particle": "e-", "energyMeV": 1},
            "run": {"nEvents": args.events, "seed": 12345, "threads": workers},
            "determinism": {"mode": "strict"},
            "stratify": {"enable": True, "dumpFeatures": True},
            "viz": {"enable": True, "includeNonOptical": True,
                    "maxTrajectories": 10000, "maxSegmentsPerTrajectory": 10000},
        }
        script = case / "experiment.js"
        script.write_text("globalThis.TRECH_CONFIG=" + json.dumps(config) + ";\n")
        first_files = None
        replay = []
        for repeat in range(args.repeats):
            files = run(args.binary.resolve(), script, case / "run", manager, workers,
                        case / f"run_{repeat}.log")
            events = keyed(files["trech_event_scores.jsonl"], ("event_id",))
            trajectories = keyed(files["trech_viz_trajectories.jsonl"], ("event_id", "track_id"))
            assert set(events) == {(i,) for i in range(args.events)}, "lost/duplicate events"
            assert trajectories and all(not row["capped"] for row in trajectories.values())
            score = rows(files["trech_scores.jsonl"])[-1]
            assert score["n_events"] == args.events and score["hook_predict_count"] == 0
            assert score["event_feature_stats"]["total_edep_mev"]["count"] == args.events
            physics = (events, trajectories)
            if reference is None:
                reference = physics
            assert physics == reference, f"per-event/trajectory physics differs: {manager}/{workers}/{repeat}"
            if first_files is None:
                first_files = files
            replay.append({
                "repeat": repeat,
                "exact_keyed_transport": True,
                "raw_bytes_equal_first": {name: files[name] == first_files[name] for name in FILES},
                "score_differences_from_first": differences(
                    rows(first_files["trech_scores.jsonl"])[-1], score),
                "raw_sha256": {name: hashlib.sha256(data).hexdigest() for name, data in files.items()},
            })
        cases.append({"manager": manager, "workers": workers,
                      "events": args.events, "replay": replay})

    compatibility = []
    if args.baseline_binary:
        for manager in ("Serial", "Tasking"):
            case = work / f"compatibility_{manager}_1"
            case.mkdir()
            config["run"]["threads"] = 1
            script = case / "experiment.js"
            script.write_text("globalThis.TRECH_CONFIG=" + json.dumps(config) + ";\n")
            before = run(args.baseline_binary.resolve(), script, case / "run", manager, 1,
                         case / "baseline.log")
            after = run(args.binary.resolve(), script, case / "run", manager, 1,
                        case / "current.log")
            matches = {name: before[name] == after[name] for name in SCIENTIFIC_FILES}
            assert all(matches.values()), f"{manager}/1 changed prior scientific bytes: {matches}"
            before_hash = rows(before["trech_provenance.jsonl"])[-1]["config_hash"]
            after_hash = rows(after["trech_provenance.jsonl"])[-1]["config_hash"]
            assert before_hash == after_hash, "single-worker config hash changed"
            compatibility.append({"manager": manager, "workers": 1,
                                  "scientific_bytes_equal_baseline": matches,
                                  "config_hash_unchanged": True})
    scientific_replay = all(
        all(record["raw_bytes_equal_first"][name] for name in SCIENTIFIC_FILES)
        for case in cases for record in case["replay"]
    )
    report = {
        "scope": "per_event_transport_only",
        "exact_keyed_transport_across_workers_and_managers": True,
        "full_strict_byte_replay_established": False,
        "observed_scientific_byte_replay": scientific_replay,
        "remaining_gap": "floating-point run reduction and JSONL append ordering",
        "cases": cases, "single_worker_baseline_compatibility": compatibility,
    }
    target = work / "report.json"
    target.write_text(json.dumps(report, indent=2) + "\n")
    print(f"Exact per-event transport passes {len(cases) * args.repeats} runs; report: {target}")
    print(f"Observed raw scientific byte replay: {scientific_replay}; full strict replay remains open.")


if __name__ == "__main__":
    main()
