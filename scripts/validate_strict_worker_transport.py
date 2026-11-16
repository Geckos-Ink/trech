#!/usr/bin/env python3
"""Check strict Geant4 event and trajectory byte replay across workers.

Compare keyed physics, ordered bytes, and the sampled subset under tight viz caps.
Report run reduction and provenance differences separately.
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
ORDERED_FILES = (
    "trech_event_scores.jsonl", "trech_event_features.jsonl", "trech_resim_queue.jsonl",
    "trech_viz_trajectories.jsonl",
)
SCIENTIFIC_FILES = (*ORDERED_FILES, "trech_scores.jsonl", "trech_viz_scene.json")
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
    ordered_reference = None
    capped_reference = None
    for manager, workers in (("Tasking", 2), ("Tasking", 8), ("MT", 2), ("MT", 8)):
        case = work / f"{manager}_{workers}"
        case.mkdir()
        config = {
            "environment": {"worldSizeMm": 100, "worldMaterial": "G4_WATER"},
            "beam": {"particle": "e-", "energyMeV": 1},
            "run": {"nEvents": args.events, "seed": 12345, "threads": workers},
            "determinism": {"mode": "strict"},
            "stratify": {"enable": True, "dumpFeatures": True, "dumpResimQueue": True,
                         "totalTrackCountThreshold": 1},
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
            assert list(events) == sorted(events), "event scores are out of order"
            feature_ids = [row["event_id"] for row in rows(files["trech_event_features.jsonl"])]
            assert feature_ids == list(range(args.events)), "event features are missing or out of order"
            queued_ids = [row["event_id"] for row in rows(files["trech_resim_queue.jsonl"])]
            assert queued_ids and queued_ids == [
                key[0] for key, row in events.items() if row["stratification"]["exceptional"]
            ], "resim candidates are missing or out of order"
            assert list(trajectories) == sorted(trajectories), "trajectories are out of order"
            score = rows(files["trech_scores.jsonl"])[-1]
            assert score["n_events"] == args.events and score["hook_predict_count"] == 0
            assert score["event_feature_stats"]["total_edep_mev"]["count"] == args.events
            physics = (events, trajectories)
            if reference is None:
                reference = physics
            assert physics == reference, f"per-event/trajectory physics differs: {manager}/{workers}/{repeat}"
            ordered_files = {name: files[name] for name in ORDERED_FILES}
            if ordered_reference is None:
                ordered_reference = ordered_files
            assert ordered_files == ordered_reference, f"event/viz bytes differ: {manager}/{workers}/{repeat}"
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

        capped_config = {**config, "viz": {**config["viz"], "maxTrajectories": 5,
                                          "maxSegmentsPerTrajectory": 3}}
        capped_script = case / "capped.js"
        capped_script.write_text("globalThis.TRECH_CONFIG=" + json.dumps(capped_config) + ";\n")
        capped = run(args.binary.resolve(), capped_script, case / "capped", manager,
                     workers, case / "capped.log")
        data = capped["trech_viz_trajectories.jsonl"]
        if capped_reference is None:
            capped_reference = data
        assert data == capped_reference, f"capped trajectory bytes differ: {manager}/{workers}"
        uncapped = rows(first_files["trech_viz_trajectories.jsonl"])
        assert len(uncapped) > 5, "fixture must exercise the trajectory cap"
        expected = [
            {**row, "capped": len(row["points"]) > 3, "points": row["points"][:3]}
            for row in uncapped[:5]
        ]
        assert any(row["capped"] for row in expected), "fixture must exercise the point cap"
        assert rows(data) == expected, "trajectory cap kept the wrong data"
        score = rows(capped["trech_scores.jsonl"])[-1]
        assert score["viz_trajectories"] == 5
        assert score["viz_segments"] == sum(len(row["points"]) for row in expected)
        assert score["viz_capped"] == sum(row["capped"] for row in expected)
        assert score["viz_dropped"] == sum(len(row["points"]) for row in uncapped[5:])
        cases.append({"manager": manager, "workers": workers,
                      "events": args.events, "replay": replay, "capped_trajectories_match": True})

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
        "scope": "per_event_transport_and_ordered_artifacts",
        "exact_keyed_transport_across_workers_and_managers": True,
        "event_and_trajectory_bytes_equal_across_workers_and_managers": True,
        "full_strict_byte_replay_established": False,
        "observed_scientific_byte_replay": scientific_replay,
        "remaining_gap": "floating-point run reductions and multi-worker hook replay",
        "cases": cases, "single_worker_baseline_compatibility": compatibility,
    }
    target = work / "report.json"
    target.write_text(json.dumps(report, indent=2) + "\n")
    print(f"Exact event/viz replay passes {len(cases) * args.repeats} uncapped and "
          f"{len(cases)} capped runs; report: {target}")
    print(f"Observed raw scientific byte replay: {scientific_replay}; full strict replay remains open.")


if __name__ == "__main__":
    main()
