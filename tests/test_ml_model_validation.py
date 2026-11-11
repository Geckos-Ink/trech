#!/usr/bin/env python3
"""ML model validation: committed-model audit staleness, static gates, run-based gates.

1. docs/ml_model_audit.{json,md} must equal a fresh static audit of data/ + projects/
   (pure Python: runs in every CTest environment).
2. Static gates catch what the engine would silently accept or mis-run: unknown activations
   (the C++ loader maps them to identity), broken layer chains, v1 models carrying links,
   non-finite outputs inside the trained domain, a negative carried holdout R2.
3. With NumPy: run-based gates on synthetic runs (holdout reproduction, run leakage by
   directory and by replayed configuration, test accuracy threshold, coverage split).
4. With torch: a per-layer tanh/relu MLP trains, exports a TorchScript twin that matches the
   JSON model, and is compared with a linear baseline.
"""
from __future__ import annotations

import json
import math
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools/torch"))

from trech_torch import validate_model as vm  # noqa: E402


def check_audit_fresh() -> None:
    code = vm.main(["--scan", "data", "projects", "--root", str(ROOT), "--audit-json", "docs/ml_model_audit.json",
                    "--audit-md", "docs/ml_model_audit.md", "--check"])
    assert code == 0, "docs/ml_model_audit.* is stale or a committed model fails a static gate"


def base_model(**extra) -> dict:
    model = {"model": "generic_surrogate_v1", "input_features": ["a", "b"], "output_features": ["y"],
             "input_mean": [0.0, 0.0], "input_std": [1.0, 1.0], "output_mean": [0.0], "output_std": [1.0],
             "layers": [{"weights": [[0.5, -0.5], [0.25, 0.25]], "bias": [0.0, 0.1], "activation": "tanh"},
                        {"weights": [[1.0, 2.0]], "bias": [0.0], "activation": "none"}]}
    model.update(extra)
    return model


def statuses(model: dict) -> dict:
    gates, _ = vm.static_gates(model)
    return {g["name"]: g["status"] for g in gates}


def check_static_gates() -> None:
    ok = statuses(base_model())
    assert ok["structure"] == "pass" and ok["finite_on_domain"] == "pass", ok
    assert ok["trust_profile"] == "warn" and ok["carried_accuracy"] == "skip", ok
    # Hand-authored maps may omit scalers: the engine defaults them, so must the validator.
    bare = base_model()
    for key in ("input_mean", "input_std", "output_mean", "output_std"):
        bare.pop(key)
    assert statuses(bare)["structure"] == "pass"
    gelu = base_model()
    gelu["layers"][0]["activation"] = "gelu"
    assert statuses(gelu)["structure"] == "fail", "an unknown activation would silently run as identity"
    broken = base_model()
    broken["layers"][1]["weights"] = [[1.0, 2.0, 3.0]]
    assert statuses(broken)["structure"] == "fail"
    v1_links = base_model(output_transforms=["exp"])
    assert statuses(v1_links)["structure"] == "fail", "a v1 reader ignores output links"
    v2 = base_model(model="generic_surrogate_v2", output_transforms=["exp"])
    v2["network"] = {"layers": v2.pop("layers")}
    assert statuses(v2)["structure"] == "pass"
    # exp link overflowing inside the trained domain is a real failure.
    hot = json.loads(json.dumps(v2))
    hot["output_std"] = [1e4]
    hot["input_domain"] = {"input_min": [-10.0, -10.0], "input_max": [10.0, 10.0], "standardized_radius": [10.0, 10.0]}
    assert statuses(hot)["finite_on_domain"] == "fail"
    negative = base_model(holdout={"r2_min": -0.3, "n": 10, "r2": {"y": -0.3}, "rmse": {"y": 1.0}})
    assert statuses(negative)["carried_accuracy"] == "warn"
    # The pure-Python evaluator follows the engine's arithmetic and links.
    out = vm.forward(v2, [1.0, 0.0])
    h = [math.tanh(0.5), math.tanh(0.35)]
    assert abs(out[0] - math.exp(h[0] + 2 * h[1])) < 1e-12
    assert not vm.is_generic_surrogate({"model": "generic_surrogate_v1", "inputs": ["a"]}), "manifests are not models"


def check_run_gates() -> None:
    try:
        import numpy as np
    except ImportError:
        print("SKIP run-based gates: numpy unavailable")
        return
    from distill_discrete_scenario_operators import _make_run
    from trech_torch.train_surrogate import main as train

    def rows(n, seed):
        rng = np.random.default_rng(seed)
        out = []
        for a, b in rng.uniform(-1, 1, size=(n, 2)):
            out.append({"a": float(a), "b": float(b), "y": float(1.5 * a - 0.5 * b + 0.3 * math.sin(3 * a))})
        return out

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        _make_run(root / "train", rows(400, 1), "s", 10, 1)
        _make_run(root / "test", rows(200, 2), "s", 10, 2)
        _make_run(root / "replay", rows(400, 1), "s", 10, 1)  # identical configuration to train
        common = ["--runs", str(root / "train"), "--source", "hook_emits", "--tag", "s", "--expand", "samples",
                  "--inputs", "a,b", "--outputs", "y"]
        assert train(common + ["--validation-runs", str(root / "test"), "--linear",
                               "--out-json", str(root / "lin.json"), "--manifest", str(root / "lin.manifest.json")]) == 0
        kw = dict(source="hook_emits", tag="s", expand="samples")
        report = vm.validate(root / "lin.json", test_runs=[str(root / "test")], training_runs=[str(root / "train")], **kw)
        got = {g["name"]: g for g in report["gates"]}
        assert got["evaluator_parity"]["status"] == "pass", got["evaluator_parity"]
        assert got["holdout_reproduces"]["status"] == "pass", got["holdout_reproduces"]
        assert got["run_leakage"]["status"] == "pass", got["run_leakage"]
        assert got["test_accuracy"]["status"] == "pass"
        assert got["beats_linear_baseline"]["status"] == "skip"
        assert got["sigma_calibration"]["independent"] is False
        assert got["test_domain_coverage"]["fractions"]["in_hull"] > 0.9
        assert report["status"] in ("pass", "warn"), report["status"]
        strict = vm.validate(root / "lin.json", test_runs=[str(root / "test")], min_r2=0.999, **kw)
        assert {g["name"]: g["status"] for g in strict["gates"]}["test_accuracy"] == "fail"
        assert strict["status"] == "fail"
        same = vm.validate(root / "lin.json", test_runs=[str(root / "train")], training_runs=[str(root / "train")], **kw)
        assert {g["name"]: g["status"] for g in same["gates"]}["run_leakage"] == "fail"
        replay = vm.validate(root / "lin.json", test_runs=[str(root / "replay")], training_runs=[str(root / "train")], **kw)
        leak = {g["name"]: g for g in replay["gates"]}["run_leakage"]
        assert leak["status"] == "fail" and "same configuration" in leak["detail"], leak

        try:
            import torch  # noqa: F401
        except ImportError:
            print("SKIP torch structure/twin gates: torch unavailable")
            return
        assert train(common + ["--validation-runs", str(root / "test"), "--widths", "12,6",
                               "--activations", "tanh,relu", "--epochs", "300", "--seed", "3",
                               "--out-json", str(root / "mlp.json"), "--out", str(root / "mlp.pt"),
                               "--manifest", str(root / "mlp.manifest.json")]) == 0
        model = json.loads((root / "mlp.json").read_text())
        assert [l["activation"] for l in model["layers"]] == ["tanh", "relu", "none"]
        assert [len(l["weights"]) for l in model["layers"]] == [12, 6, 1]
        manifest = json.loads((root / "mlp.manifest.json").read_text())
        assert manifest["structure"] == {"family": "mlp", "widths": [12, 6], "activations": ["tanh", "relu"]}
        report = vm.validate(root / "mlp.json", test_runs=[str(root / "test")], training_runs=[str(root / "train")], **kw)
        got = {g["name"]: g for g in report["gates"]}
        assert got["torchscript_parity"]["status"] == "pass", got["torchscript_parity"]
        assert got["beats_linear_baseline"]["status"] in ("pass", "warn")
        assert "skill_vs_linear" in got["beats_linear_baseline"]
        assert got["holdout_reproduces"]["status"] == "pass"


def main() -> int:
    check_audit_fresh()
    check_static_gates()
    check_run_gates()
    print("ml model validation: ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
