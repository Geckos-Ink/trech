#!/usr/bin/env python3
"""Exercise inference resim policies in real serial Geant4 runs, using synthetic models.

Checks routing/accounting/replay, never model accuracy or automatic resimulation.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
ARTIFACTS = (
    "trech_scores.jsonl", "trech_provenance.jsonl", "trech_event_scores.jsonl",
    "trech_hook_emits.jsonl", "trech_resim_queue.jsonl",
)


def rows(data: bytes) -> list[dict]:
    return [json.loads(line) for line in data.splitlines() if line.strip()]


def model(input_name: str, output_name: str) -> dict:
    return {
        "model": "generic_surrogate_v1",
        "input_features": [input_name], "output_features": [output_name],
        "input_mean": [0], "input_std": [1],
        "input_domain": {"standardized_radius": [4]},
        "layers": [{"weights": [[0]], "bias": [1], "activation": "none"}],
    }


def run(binary: Path, script: Path, output: Path, log: Path) -> dict[str, bytes]:
    output.mkdir(exist_ok=True)
    for name in ARTIFACTS:
        (output / name).unlink(missing_ok=True)
    result = subprocess.run(
        [str(binary), "run", str(script), "--output", str(output)],
        cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=120,
    )
    log.write_bytes(result.stdout)
    if result.returncode:
        raise RuntimeError(f"Geant4 run failed ({result.returncode}); see {log}")
    return {name: (output / name).read_bytes() if (output / name).exists() else b""
            for name in ARTIFACTS}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--binary", type=Path, default=ROOT / "build/dev/trech")
    parser.add_argument("--baseline-binary", type=Path,
                        help="Also check legacy score/event/queue bytes and config hashes")
    parser.add_argument("--output", type=Path, default=ROOT / "build/inference_resim_checks")
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    work = Path(tempfile.mkdtemp(prefix="validation_", dir=args.output.resolve()))
    report = []
    # Each tuple: name, enabled policies, input condition, other switches.
    cases = [
        ("legacy", {}, "sparse", {}),
        ("legacy_ood", {"resimOnLowConfidence": True}, "ood", {}),
        ("legacy_point", {}, "sparse", {"point": True}),
        ("point_starved", {"resimOnStarvation": True}, "sparse", {"point": True}),
        ("point_off_band", {"resimOnScaleMismatch": True}, "sparse", {"point": True}),
        ("starved", {"resimOnStarvation": True}, "sparse", {}),
        ("off_band", {"resimOnScaleMismatch": True}, "sparse", {}),
        ("both", {"resimOnStarvation": True, "resimOnScaleMismatch": True}, "sparse", {}),
        ("joint", {"resimOnStarvation": True}, "joint", {}),
        ("all_causes", {"resimOnLowConfidence": True, "resimOnStarvation": True,
                        "resimOnScaleMismatch": True}, "ood", {}),
        ("clean", {"resimOnStarvation": True, "resimOnScaleMismatch": True}, "clean", {}),
        ("missing", {"resimOnStarvation": True, "resimOnScaleMismatch": True}, "missing", {}),
        ("strict", {"resimOnStarvation": True, "resimOnScaleMismatch": True}, "sparse", {"strict": True}),
        ("feature", {"resimOnStarvation": True, "resimOnScaleMismatch": True}, "sparse", {"feature": True}),
        ("no_queue", {"resimOnStarvation": True}, "sparse", {"queue": False}),
        ("disabled", {"resimOnStarvation": True}, "sparse", {"enable": False}),
        ("event_reset", {"resimOnStarvation": True}, "sparse", {"first_only": True}),
        ("callback_reset", {"resimOnStarvation": True}, "sparse", {"start_only": True}),
    ]
    for name, policies, condition, switches in cases:
        directory = work / name
        directory.mkdir()
        lower = model("x", "signal")
        lower["trained_scale_bands"] = ["nano" if condition == "clean" else "macro"]
        if condition in ("sparse", "ood"):
            lower["input_domain"].update({"input_min": [0], "input_max": [8]})
            lower["input_domain"]["occupancy"] = {"bins": 4, "counts": [[5, 0, 0, 3]]}
        if condition == "ood":
            lower["input_domain"]["joint"] = {"centers": [[0]], "radius": .25}
        if condition == "joint":
            lower["input_domain"]["joint"] = {"centers": [[-1], [1]], "radius": .25}
        upper = model("signal", "observer")
        for label, spec in (("lower", lower), ("upper", upper)):
            (directory / f"{label}.json").write_text(json.dumps(spec))
        config = {
            "detector": {"worldSizeMm": 30, "worldMaterial": "G4_WATER"},
            "beam": {"particle": "gamma", "energyMeV": .1, "direction": [0, 0, 1]},
            "run": {"nEvents": 3, "seed": 424242, "threads": 1},
            "determinism": {"mode": "strict" if switches.get("strict") else "predictive"},
            "hooks": {"registered": ["onEventEnd"]},
            "stratify": {"enable": switches.get("enable", True),
                         "dumpResimQueue": switches.get("queue", True), **policies},
            "models": [{"name": "upper", "path": str(directory / "upper.json"), "scale": "meso"},
                       {"name": "lower", "path": str(directory / "lower.json"), "scale": "nano"}],
        }
        if switches.get("feature"):
            config["stratify"]["totalTrackLengthMmThreshold"] = 1e-12
        seed = "{}" if condition == "missing" else json.dumps({"x": {
            "ood": 8, "joint": 0, "clean": 1,
        }.get(condition, 3)})
        call = f'ctx.predict("lower", {seed})' if switches.get("point") else f"ctx.cascade({seed})"
        callback = f'ctx.emit("trust", {call});'
        if switches.get("first_only"):
            callback = f"if (ctx.event.id === 0) {{ {callback} }}"
        hooks = {"onEventEnd": callback}
        if switches.get("start_only"):
            config["hooks"]["registered"].append("onEventStart")
            hooks = {"onEventStart": callback, "onEventEnd": ""}
        script = directory / "experiment.js"
        script.write_text("globalThis.TRECH_CONFIG = " + json.dumps(config) + ";\n"
                          "globalThis.TRECH_HOOKS = {" + ",".join(
                              f"{key}: function(ctx) {{ {body} }}" for key, body in hooks.items()) + "};\n")
        files = run(args.binary.resolve(), script, directory / "run", directory / "run_0.log")
        replay = run(args.binary.resolve(), script, directory / "run", directory / "run_1.log")
        assert files == replay, f"{name}: replay bytes differ"
        score = rows(files["trech_scores.jsonl"])[-1]
        inferred = condition != "missing" and not switches.get("strict")
        event_inferred = inferred and not switches.get("start_only")
        event_count = 1 if switches.get("first_only") else 3
        evaluations = 1 if switches.get("point") else 2
        assert score["hook_predict_count"] == (evaluations * event_count if inferred else 0), name
        ood = condition == "ood" and event_inferred
        assert score["hook_predict_out_of_domain_count"] == (evaluations * event_count if ood else 0), name
        reasons = []
        if ood and policies.get("resimOnLowConfidence"):
            reasons.append("inference_out_of_domain")
        if event_inferred and condition in ("sparse", "joint", "ood") and policies.get("resimOnStarvation"):
            reasons.append("inference_starved")
        if event_inferred and condition != "clean" and policies.get("resimOnScaleMismatch"):
            reasons.append("inference_scale_mismatch")
        enabled = switches.get("enable", True)
        expected_candidates = event_count if enabled and reasons else 0
        assert score["stratify_low_confidence_count"] == expected_candidates, name
        queue = rows(files["trech_resim_queue.jsonl"])
        expected_queued = (event_count if switches.get("feature") else expected_candidates)
        if not switches.get("queue", True):
            expected_queued = 0
        assert len(queue) == expected_queued, name
        events = rows(files["trech_event_scores.jsonl"])
        assert len(events) == (3 if enabled else 0), name
        extended = policies.get("resimOnStarvation") or policies.get("resimOnScaleMismatch")
        for event in events:
            trust = event["stratification"]
            active = not switches.get("first_only") or event["event_id"] == 0
            assert trust["low_confidence_inference"] == bool(reasons and active), name
            assert trust["inference_out_of_domain_count"] == (evaluations if ood and active else 0), name
            if extended:
                assert trust["inference_resim_reasons"] == (reasons if active else []), name
                assert trust["inference_starved_count"] == (
                    evaluations if event_inferred and active and condition in ("sparse", "joint", "ood") else 0), name
                assert trust["inference_scale_mismatch_count"] == (
                    evaluations if event_inferred and active and condition != "clean" else 0), name
            else:
                assert "inference_resim_reasons" not in trust, name
        for candidate in queue:
            if switches.get("feature"):
                assert candidate["reason"] == "track_length_mm_threshold", name
                assert candidate["source"] == "thresholds", name
            else:
                assert candidate["reason"] == reasons[0], name
                assert candidate["source"] == "cascade_coverage", name
        if args.baseline_binary and name.startswith("legacy"):
            baseline = run(args.baseline_binary.resolve(), script, directory / "baseline",
                           directory / "baseline.log")
            for artifact in ARTIFACTS:
                if artifact != "trech_provenance.jsonl":
                    assert baseline[artifact] == files[artifact], f"{name}: changed legacy {artifact}"
            before = rows(baseline["trech_provenance.jsonl"])[-1]
            after = rows(files["trech_provenance.jsonl"])[-1]
            assert before["config_hash"] == after["config_hash"], name
            assert before["config_json"] == after["config_json"], name
        report.append({"case": name, "inferences": score["hook_predict_count"],
                       "low_confidence_events": expected_candidates, "queued": len(queue),
                       "reasons": reasons, "byte_identical_replay": True})
        print(f"PASS {name}", flush=True)
    (work / "report.json").write_text(json.dumps(report, indent=2) + "\n")
    print(f"{len(report)} policy cases passed; synthetic diagnostics only. Artifacts: {work}")


if __name__ == "__main__":
    main()
