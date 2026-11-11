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
5. generic_surrogate_v3 set networks: the committed DeepSets/MPNN fixtures pass the static gates
   and the pure-Python evaluator reproduces their recorded reference outputs (and NumPy too);
   malformed layouts fail `structure`. With torch: a trained MPNN's TorchScript twin matches.
6. Error bars: `--calibration-runs` carries a split-conformal interval set on runs disjoint from
   the test runs, and `sigma_calibration` reports that check as independent.
7. Fresh-run re-checks: docs/ml_model_recheck.json is current for data/ml_recheck_recipes.json
   (pure Python); recipes reusing a training seed are refused; with NumPy a python and an
   engine producer (a stand-in binary) produce fresh runs that grade a model end to end.
"""
from __future__ import annotations

import json
import math
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools/torch"))

from trech_torch import recheck_models as rc  # noqa: E402
from trech_torch import validate_model as vm  # noqa: E402

SET_FIXTURES = ROOT / "tests/fixtures/ml_set_networks"


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


def check_set_networks() -> None:
    expected = json.loads((SET_FIXTURES / "expected.json").read_text())
    for kind in ("deepsets", "mpnn"):
        model = json.loads((SET_FIXTURES / f"{kind}.json").read_text())
        got = statuses(model)
        assert got["structure"] == "pass" and got["finite_on_domain"] == "pass", (kind, got)
        for row, ref in zip(expected["rows"], expected["outputs"][kind]):
            out = vm.forward(model, row)[0]
            assert abs(out - ref) <= 1e-9 * max(1.0, abs(ref)), (kind, out, ref)
        for a, b in expected["permutation_pairs"]:
            assert abs(vm.forward(model, expected["rows"][a])[0] - vm.forward(model, expected["rows"][b])[0]) < 1e-12
        bad = json.loads(json.dumps(model))
        bad["network"]["elements"] = 3
        assert statuses(bad)["structure"] == "fail", "a set layout that does not match the inputs is caught"
        bad = json.loads(json.dumps(model))
        bad["network"]["phi"][0]["activation"] = "gelu"
        assert statuses(bad)["structure"] == "fail", "an unknown set-network activation is caught"
        bad = json.loads(json.dumps(model))
        bad["model"] = "generic_surrogate_v2"
        assert statuses(bad)["structure"] == "fail", "a set network under a v2 header is caught"
    try:
        import numpy as np
    except ImportError:
        print("SKIP set-network NumPy parity: numpy unavailable")
        return
    from trech_torch.train_surrogate import predict_np
    for kind in ("deepsets", "mpnn"):
        model = json.loads((SET_FIXTURES / f"{kind}.json").read_text())
        sc = tuple(np.asarray(model[k], dtype=float) for k in ("input_mean", "input_std", "output_mean", "output_std"))
        pred = predict_np(np.asarray(expected["rows"], dtype=float), model["network"], sc, model["output_transforms"])
        assert np.allclose(pred[:, 0], expected["outputs"][kind], rtol=1e-12, atol=1e-12), kind


def _set_rows(n, seed):
    import random
    rng = random.Random(seed)
    out = []
    for _ in range(n):
        row, pts = {}, []
        for e in range(3):
            present = e < rng.randint(2, 3) or e == 0
            x = rng.uniform(-1, 1) if present else 0.0
            row[f"p{e}_x"], row[f"p{e}_m"] = x, 1.0 if present else 0.0
            if present:
                pts.append(x)
        row["y"] = sum(math.exp(-(a - b) ** 2 / 0.2) for i, a in enumerate(pts) for b in pts[i + 1:])
        out.append(row)
    return out


def check_calibration_and_set_training() -> None:
    try:
        import numpy as np  # noqa: F401
    except ImportError:
        print("SKIP calibration-run error bars: numpy unavailable")
        return
    from distill_discrete_scenario_operators import _make_run
    from trech_torch.train_surrogate import main as train

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        for name, seed, n in (("train", 1, 600), ("test", 2, 200), ("cal", 3, 200)):
            _make_run(root / name, _set_rows(n, seed), "s", 10, seed)
        inputs = "p0_x,p0_m,p1_x,p1_m,p2_x,p2_m"
        common = ["--runs", str(root / "train"), "--validation-runs", str(root / "test"), "--source", "hook_emits",
                  "--tag", "s", "--expand", "samples", "--inputs", inputs, "--outputs", "y"]
        kw = dict(source="hook_emits", tag="s", expand="samples")
        # Calibration runs that overlap the training or holdout runs are refused.
        try:
            train(common + ["--linear", "--calibration-runs", str(root / "test"), "--out-json", str(root / "x.json"),
                            "--manifest", str(root / "x.manifest.json")])
        except SystemExit as exc:
            assert exc.code == 2
        else:
            raise AssertionError("overlapping calibration runs must be refused")
        assert train(common + ["--linear", "--calibration-runs", str(root / "cal"), "--interval-coverage", "0.8",
                               "--out-json", str(root / "lin.json"), "--manifest", str(root / "lin.manifest.json")]) == 0
        model = json.loads((root / "lin.json").read_text())
        interval = model["prediction_interval"]
        assert interval["nominal_coverage"] == 0.8 and interval["source"] == "calibration_runs" and interval["n"] == 200
        assert interval["runs"] and interval["runs"][0].endswith("cal") and interval["rmse"]["y"] > 0
        # One calibration run: the run-level interval cannot carry its guarantee and says so.
        assert interval["method"] == "run_grouped_conformal_abs_residual" and interval["runs_scored"] == 1, interval
        assert interval["run_level_guarantee"] is False and interval["runs_needed_for_guarantee"] == 4, interval
        assert interval["pooled_half_width"]["y"] > 0 and interval["rows_per_run"] == [200], interval
        check_grouped_interval()
        report = vm.validate(root / "lin.json", test_runs=[str(root / "test")], training_runs=[str(root / "train")], **kw)
        sigma = {g["name"]: g for g in report["gates"]}["sigma_calibration"]
        assert sigma["sigma_source"] == "calibration_runs" and sigma["independent"] is True, sigma
        assert sigma["interval_independent"] is True and "interval_coverage" in sigma["calibration"]["y"], sigma
        # Testing on the calibration runs themselves is reported as NOT independent.
        same = vm.validate(root / "lin.json", test_runs=[str(root / "cal")], training_runs=[str(root / "train")], **kw)
        sigma = {g["name"]: g for g in same["gates"]}["sigma_calibration"]
        assert sigma["independent"] is False and "NOT independent" in sigma["detail"], sigma

        try:
            import torch  # noqa: F401
        except ImportError:
            print("SKIP set-network training: torch unavailable")
            return
        assert train(common + ["--network", "mpnn", "--set-elements", "3", "--mask-feature", "1", "--phi-widths", "8",
                               "--rho-widths", "8", "--relative-features", "0", "--rounds", "2", "--epochs", "200",
                               "--out-json", str(root / "mpnn.json"), "--out", str(root / "mpnn.pt"),
                               "--manifest", str(root / "mpnn.manifest.json")]) == 0
        model = json.loads((root / "mpnn.json").read_text())
        assert model["model"] == "generic_surrogate_v3" and model["network"]["kind"] == "mpnn"
        assert json.loads((root / "mpnn.manifest.json").read_text())["structure"]["family"] == "mpnn"
        report = vm.validate(root / "mpnn.json", test_runs=[str(root / "test")], training_runs=[str(root / "train")], **kw)
        got = {g["name"]: g for g in report["gates"]}
        for name in ("structure", "torchscript_parity", "evaluator_parity", "holdout_reproduces"):
            assert got[name]["status"] == "pass", got[name]
        # A set network never silently becomes something else: a bad layout is an error.
        try:
            train(common + ["--network", "deepsets", "--set-elements", "4", "--out-json", str(root / "b.json"),
                            "--manifest", str(root / "b.manifest.json")])
        except SystemExit as exc:
            assert "equal element blocks" in str(exc.code)
        else:
            raise AssertionError("a set layout that does not divide the inputs must be refused")


def check_grouped_interval() -> None:
    """Run-level conformal: runs (not rows) are the units; the guarantee needs enough runs."""
    import numpy as np
    from trech_torch.train_surrogate import calibration_interval

    rng = np.random.default_rng(5)
    # 20 runs whose residual scale differs run to run (correlated rows within a run).
    scales = np.linspace(0.5, 2.0, 20)
    groups = np.repeat(np.arange(20), 50)
    resid = rng.normal(0.0, 1.0, len(groups)) * scales[groups]
    block = calibration_interval(np.zeros((len(groups), 1)), resid[:, None], ["y"], 0.9,
                                 [f"r{i}" for i in range(20)], groups=groups)
    per_run = sorted(block["per_run_half_width"]["y"])
    assert block["run_level_guarantee"] is True and block["runs_scored"] == 20, block
    assert abs(block["quantile_level"] - 19 / 20) < 1e-12, block
    assert block["half_width"]["y"] == per_run[18], "the ceil((R+1)c)-th smallest per-run quantile"
    assert block["half_width"]["y"] > block["pooled_half_width"]["y"], "heterogeneous runs widen the run-level bar"
    # Without run identities the row-pooled (approximate) quantile is carried and labelled.
    pooled = calibration_interval(np.zeros((len(groups), 1)), resid[:, None], ["y"], 0.9, ["all"])
    assert pooled["method"] == "split_conformal_abs_residual" and "approximate" in pooled["note"], pooled


FAKE_ENGINE = r"""#!/usr/bin/env python3
import json, random, sys
from pathlib import Path
args = sys.argv[1:]
seed = int(args[args.index("--seed") + 1]); out = Path(args[args.index("--output") + 1])
out.mkdir(parents=True, exist_ok=True)
rng = random.Random(seed)
params = {args[i + 1].split("=", 1)[0]: json.loads(args[i + 1].split("=", 1)[1])
          for i in range(len(args)) if args[i] == "--param"}
import os
slope = float(params.get("slope", 2.0)); offset = float(os.environ.get("FAKE_OFFSET", "0.5"))
rows = [{"a": rng.uniform(-1, 1)} for _ in range(200)]
for r in rows: r["y"] = slope * r["a"] + offset
(out / "trech_provenance.jsonl").write_text(json.dumps({"config_hash": "h%d" % seed, "seed": seed}) + "\n")
(out / "trech_scores.jsonl").write_text(json.dumps({"phase": "run_summary"}) + "\n")
(out / "trech_hook_emits.jsonl").write_text(json.dumps({"phase": "hook_emit", "event_id": 0, "tag": "e",
    "payload": {"samples": rows}}) + "\n")
"""


def check_recheck() -> None:
    code = rc.main(["--recipes", "data/ml_recheck_recipes.json", "--root", str(ROOT), "--json",
                    "docs/ml_model_recheck.json", "--check"])
    assert code == 0, "docs/ml_model_recheck.* is stale: a re-checked model or its recipe changed"
    good = {"model": "m.json", "producer": {"kind": "python", "script": "p.py", "function": "f"},
            "harvest": {"source": "hook_emits"}, "used_seeds": [1, 2], "fresh_seeds": [3, 4]}
    assert rc.recipe_problems(good) == []
    reuse = dict(good, fresh_seeds=[2, 5])
    assert any("replay the same rows" in p for p in rc.recipe_problems(reuse)), "a training seed is never a fresh seed"
    assert rc.recipe_problems(dict(good, holdout={"seed": 9})), "holdout regeneration must use a recorded seed"
    assert rc.recipe_hash(good) != rc.recipe_hash(dict(good, fresh_seeds=[3, 5]))
    engine = dict(good, producer={"kind": "engine", "scenario": "x.js", "params": {"a": 1},
                                  "seed_params": {"3": {"t": 300.0}, "4": {"t": 310.0}}},
                  training={"seeds": [1]})
    assert rc.recipe_problems(engine) == [], rc.recipe_problems(engine)
    same_point = dict(engine, producer=dict(engine["producer"], seed_params={"3": {"t": 1}, "4": {"t": 1}}))
    assert any("share an operating point" in p for p in rc.recipe_problems(same_point))
    assert any("among used_seeds" in p for p in rc.recipe_problems(dict(engine, training={"seeds": [9]})))
    assert any("training.seeds" in p for p in rc.recipe_problems(dict(engine, training={"seed": 1})))
    cmd = rc.engine_command(Path("/r"), engine["producer"], Path("/o"), 4)
    assert cmd[cmd.index("--seed") + 1] == "4" and "a=1" in cmd and "t=310.0" in cmd, cmd
    try:
        import numpy as np  # noqa: F401
    except ImportError:
        print("SKIP fresh-run re-check execution: numpy unavailable")
        return
    from trech_torch.train_surrogate import main as train
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        engine = root / "fake_trech"
        engine.write_text(FAKE_ENGINE)
        engine.chmod(0o755)
        (root / "producer.py").write_text(
            "import json, random\nfrom pathlib import Path\n"
            "def make(out_dir, seed, rows, slope):\n"
            "    rng = random.Random(seed); out = Path(out_dir); out.mkdir(parents=True, exist_ok=True)\n"
            "    data = [{'a': rng.uniform(-1, 1)} for _ in range(rows)]\n"
            "    for r in data: r['y'] = slope * r['a'] + 0.5\n"
            "    (out / 'trech_provenance.jsonl').write_text(json.dumps({'config_hash': 'p%d' % seed}) + '\\n')\n"
            "    (out / 'trech_scores.jsonl').write_text(json.dumps({'phase': 'run_summary'}) + '\\n')\n"
            "    (out / 'trech_hook_emits.jsonl').write_text(json.dumps({'phase': 'hook_emit', 'event_id': 0, 'tag': 'e',"
            " 'payload': {'samples': data}}) + '\\n')\n")
        rc_mod = rc._python_producer(root, {"script": "producer.py", "function": "make"})
        rc_mod(str(root / "train"), 1, 300, slope=2.0)
        rc_mod(str(root / "hold"), 2, 100, slope=2.0)
        assert train(["--runs", str(root / "train"), "--validation-runs", str(root / "hold"), "--source", "hook_emits",
                      "--tag", "e", "--expand", "samples", "--inputs", "a", "--outputs", "y", "--linear",
                      "--out-json", str(root / "m.json"), "--manifest", str(root / "m.manifest.json")]) == 0
        base = {"model": "m.json", "harvest": {"source": "hook_emits", "tag": "e", "expand": "samples"},
                "used_seeds": [1, 2], "fresh_seeds": [7, 8]}
        python_recipe = dict(base, producer={"kind": "python", "script": "producer.py", "function": "make",
                                             "args": {"slope": 2.0}}, rows=150, training={"seed": 1, "rows": 300},
                             holdout={"seed": 2, "rows": 100})
        entry = rc.recheck(python_recipe, root=root, work=root / "work")
        assert entry["producer_reproduces_holdout"]["ok"], entry
        assert entry["gates"]["run_leakage"] == "pass" and entry["gates"]["test_accuracy"] == "pass", entry
        assert entry["fresh_rows"] == 300 and entry["training_regenerated"]
        # A drifted producer (slope changed) is caught by the regenerated holdout, not hidden.
        drift = dict(python_recipe, producer=dict(python_recipe["producer"], args={"slope": 2.5}))
        assert rc.recheck(drift, root=root, work=root / "work")["status"] == "fail"
        engine_recipe = dict(base, producer={"kind": "engine", "scenario": "x.js", "binary": "fake_trech", "events": 10})
        entry = rc.recheck(engine_recipe, root=root, work=root / "work")
        assert entry["gates"]["test_accuracy"] == "pass" and entry["fresh_rows"] == 400, entry
        # Per-seed operating points, an environment and regenerated engine training runs.
        points = dict(engine_recipe, producer=dict(engine_recipe["producer"], env={"FAKE_OFFSET": "0.5"},
                                                   seed_params={"7": {"slope": 2.0}, "8": {"slope": 2.0, "u": 1},
                                                                "1": {"slope": 2.0}}),
                      training={"seeds": [1]})
        entry = rc.recheck(points, root=root, work=root / "work")
        assert entry["training_regenerated"] and entry["gates"]["run_leakage"] == "pass", entry
        assert entry["fresh_conditions"]["8"] == {"slope": 2.0, "u": 1} and entry["status"] != "fail", entry
        # The env block reaches the engine: a shifted offset is a different (worse) data source.
        shifted = dict(points, producer=dict(points["producer"], env={"FAKE_OFFSET": "3.0"}))
        assert rc.recheck(shifted, root=root, work=root / "work")["gates"]["test_accuracy"] != "pass"


def main() -> int:
    check_audit_fresh()
    check_static_gates()
    check_run_gates()
    check_set_networks()
    check_calibration_and_set_training()
    check_recheck()
    print("ml model validation: ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
