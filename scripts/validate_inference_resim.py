#!/usr/bin/env python3
"""Exercise inference resim policies in real serial Geant4 runs, using synthetic models.

Every case runs on JSON networks and, with ``--backend torchscript`` or ``both`` (the default),
on TorchScript modules loaded by LibTorch with the same trust metadata in their ``.pt.io.json``
sidecar. ``both`` also requires the two backends to write identical score, event-score and queue
bytes. Checks routing/accounting/replay, never model accuracy or automatic resimulation.
"""
from __future__ import annotations

import argparse
import hashlib
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


# Trust metadata a TorchScript sidecar carries; weights and activations live in the module.
SIDECAR_KEYS = ("input_features", "output_features", "input_mean", "input_std",
                "input_domain", "trained_scale_bands")
# Artifacts that must not depend on the backend. Provenance and the score row's
# ``model_artifacts`` block describe which files were loaded (path, hash, load note), so the
# block is masked in scores and provenance is not compared. Emits must match byte for byte:
# the synthetic affine maps are exact in float32.
BACKEND_NEUTRAL = ("trech_scores.jsonl", "trech_event_scores.jsonl", "trech_hook_emits.jsonl",
                   "trech_resim_queue.jsonl")


def backend_neutral(files: dict[str, bytes]) -> dict[str, object]:
    neutral: dict[str, object] = {key: files[key] for key in BACKEND_NEUTRAL}
    scores = rows(files["trech_scores.jsonl"])
    for row in scores:
        assert "model_artifacts" in row or not row.get("hook_predict_count"), "model artifacts missing"
        row.pop("model_artifacts", None)
    neutral["trech_scores.jsonl"] = scores
    return neutral


def write_model(spec: dict, path: Path, backend: str) -> Path:
    """Write ``spec`` as a JSON network, or as an equivalent TorchScript module plus sidecar."""
    if backend == "json":
        path = path.with_suffix(".json")
        path.write_text(json.dumps(spec))
        return path
    import torch  # only the TorchScript backend needs Python torch

    (layer,) = spec["layers"]
    assert layer["activation"] == "none", "synthetic models are affine"
    weights = torch.tensor(layer["weights"], dtype=torch.float32)
    linear = torch.nn.Linear(weights.shape[1], weights.shape[0])
    with torch.no_grad():
        linear.weight.copy_(weights)
        linear.bias.copy_(torch.tensor(layer["bias"], dtype=torch.float32))
    path = path.with_suffix(".pt")
    torch.jit.script(linear.eval()).save(str(path))
    sidecar = {"schema": "trech_torchscript_io_v1",
               "model_sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
    sidecar.update({key: spec[key] for key in SIDECAR_KEYS if key in spec})
    Path(str(path) + ".io.json").write_text(json.dumps(sidecar))
    return path


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
    parser.add_argument("--backend", choices=("json", "torchscript", "both"), default="both",
                        help="Model format; torchscript needs Python torch (default: both)")
    parser.add_argument("--cases", nargs="+", metavar="NAME", help="Run only these cases")
    args = parser.parse_args()
    backends = ("json", "torchscript") if args.backend == "both" else (args.backend,)
    args.output.mkdir(parents=True, exist_ok=True)
    work = Path(tempfile.mkdtemp(prefix="validation_", dir=args.output.resolve()))
    report = []
    neutral: dict[str, dict[str, object]] = {}
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
    if args.cases:
        unknown = sorted(set(args.cases) - {case[0] for case in cases})
        if unknown:
            parser.error(f"unknown case(s): {', '.join(unknown)}")
        cases = [case for case in cases if case[0] in args.cases]
    for (name, policies, condition, switches), backend in (
            (case, backend) for case in cases for backend in backends):
        label_name = name if len(backends) == 1 else f"{name}[{backend}]"
        directory = work / name / backend
        directory.mkdir(parents=True)
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
        paths = {label: write_model(spec, directory / label, backend)
                 for label, spec in (("lower", lower), ("upper", upper))}
        config = {
            "environment": {"worldSizeMm": 30, "worldMaterial": "G4_WATER"},
            "beam": {"particle": "gamma", "energyMeV": .1, "direction": [0, 0, 1]},
            "run": {"nEvents": 3, "seed": 424242, "threads": 1},
            "determinism": {"mode": "strict" if switches.get("strict") else "predictive"},
            "hooks": {"registered": ["onEventEnd"]},
            "stratify": {"enable": switches.get("enable", True),
                         "dumpResimQueue": switches.get("queue", True), **policies},
            "models": [{"name": "upper", "path": str(paths["upper"]), "scale": "meso"},
                       {"name": "lower", "path": str(paths["lower"]), "scale": "nano"}],
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
        assert files == replay, f"{label_name}: replay bytes differ"
        score = rows(files["trech_scores.jsonl"])[-1]
        inferred = condition != "missing" and not switches.get("strict")
        event_inferred = inferred and not switches.get("start_only")
        event_count = 1 if switches.get("first_only") else 3
        evaluations = 1 if switches.get("point") else 2
        assert score["hook_predict_count"] == (evaluations * event_count if inferred else 0), label_name
        ood = condition == "ood" and event_inferred
        assert score["hook_predict_out_of_domain_count"] == (evaluations * event_count if ood else 0), label_name
        reasons = []
        if ood and policies.get("resimOnLowConfidence"):
            reasons.append("inference_out_of_domain")
        if event_inferred and condition in ("sparse", "joint", "ood") and policies.get("resimOnStarvation"):
            reasons.append("inference_starved")
        if event_inferred and condition != "clean" and policies.get("resimOnScaleMismatch"):
            reasons.append("inference_scale_mismatch")
        enabled = switches.get("enable", True)
        expected_candidates = event_count if enabled and reasons else 0
        assert score["stratify_low_confidence_count"] == expected_candidates, label_name
        queue = rows(files["trech_resim_queue.jsonl"])
        expected_queued = (event_count if switches.get("feature") else expected_candidates)
        if not switches.get("queue", True):
            expected_queued = 0
        assert len(queue) == expected_queued, label_name
        events = rows(files["trech_event_scores.jsonl"])
        assert len(events) == (3 if enabled else 0), label_name
        extended = policies.get("resimOnStarvation") or policies.get("resimOnScaleMismatch")
        for event in events:
            trust = event["stratification"]
            active = not switches.get("first_only") or event["event_id"] == 0
            assert trust["low_confidence_inference"] == bool(reasons and active), label_name
            assert trust["inference_out_of_domain_count"] == (evaluations if ood and active else 0), label_name
            if extended:
                assert trust["inference_resim_reasons"] == (reasons if active else []), label_name
                assert trust["inference_starved_count"] == (
                    evaluations if event_inferred and active and condition in ("sparse", "joint", "ood") else 0), label_name
                assert trust["inference_scale_mismatch_count"] == (
                    evaluations if event_inferred and active and condition != "clean" else 0), label_name
            else:
                assert "inference_resim_reasons" not in trust, label_name
        for candidate in queue:
            if switches.get("feature"):
                assert candidate["reason"] == "track_length_mm_threshold", label_name
                assert candidate["source"] == "thresholds", label_name
            else:
                assert candidate["reason"] == reasons[0], label_name
                assert candidate["source"] == "cascade_coverage", label_name
        if args.baseline_binary and name.startswith("legacy"):
            baseline = run(args.baseline_binary.resolve(), script, directory / "baseline",
                           directory / "baseline.log")
            for artifact in ARTIFACTS:
                if artifact != "trech_provenance.jsonl":
                    assert baseline[artifact] == files[artifact], f"{label_name}: changed legacy {artifact}"
            before = rows(baseline["trech_provenance.jsonl"])[-1]
            after = rows(files["trech_provenance.jsonl"])[-1]
            assert before["config_hash"] == after["config_hash"], label_name
            assert before["config_json"] == after["config_json"], label_name
        if len(backends) > 1:
            current = backend_neutral(files)
            first = neutral.setdefault(name, current)
            for artifact in BACKEND_NEUTRAL:
                assert first[artifact] == current[artifact], f"{label_name}: {artifact} depends on the backend"
            if backend == "torchscript":
                loaded = rows(files["trech_scores.jsonl"])[-1].get("model_artifacts", {}).get("models", [])
                assert loaded and all(m.get("io_sidecar_sha256") for m in loaded), \
                    f"{label_name}: TorchScript models not loaded through their sidecars"
        report.append({"case": name, "backend": backend, "inferences": score["hook_predict_count"],
                       "low_confidence_events": expected_candidates, "queued": len(queue),
                       "reasons": reasons, "byte_identical_replay": True,
                       "backend_identical": len(backends) > 1})
        print(f"PASS {label_name}", flush=True)
    (work / "report.json").write_text(json.dumps(report, indent=2) + "\n")
    print(f"{len(report)} policy cases passed; synthetic diagnostics only. Artifacts: {work}")


if __name__ == "__main__":
    main()
