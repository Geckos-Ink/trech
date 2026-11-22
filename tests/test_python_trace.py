#!/usr/bin/env python3
"""Python side of the engine trace (tools/torch/trech_torch/trace.py).

    TRECH_ML_PYTHON tests/test_python_trace.py

* The API matches the engine's: levels, categories, roles, authored-law thinning, tallies and a
  summary with a verdict; records use schema trech_trace_v1 with ``host: "python"``.
* numpy: array statistics (shape, dtype, non-finite count) and least-squares fit records.
* torch: training start/epoch/end records (epochs 1, 2, 4, ... and the last at debug), model
  structure, optimizer settings, export hash.
* Observation only: the weights trained by ``fit_mlp`` and ``fit_linear`` are byte-identical with
  the trace on and off.
"""

from __future__ import annotations

import hashlib
import io
import json
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "tools" / "torch"))

FAILURES = 0


def check(cond, message):
    global FAILURES
    if not cond:
        FAILURES += 1
        print(f"FAIL: {message}")


def fit_bytes(train_surrogate, x, y):
    import torch

    net, _ = train_surrogate.fit_mlp(x, y, hidden=8, epochs=20, lr=1e-2, seed=3, quiet=True)
    buffer = io.BytesIO()
    torch.save({k: v.detach().clone() for k, v in net.state_dict().items()}, buffer)
    w, _, _ = train_surrogate.fit_linear(x, y, l2=1e-3)
    return hashlib.sha256(buffer.getvalue()).hexdigest(), w.tobytes()


def main() -> int:
    import numpy as np

    from trech_torch import trace
    from trech_torch import train_surrogate

    # --- API ---------------------------------------------------------------------------
    records = []
    t = trace.Trace("debug", sink=records.append)
    log = t.channel("data")
    log.info("dataset", {"rows": 3})
    log.trace("hidden")
    check(not t.enabled("trace", "data") and t.enabled("debug", "data"), "levels")
    for _ in range(5):
        t.authored("fallback")
    with t.role("reference"):
        t.authored("reference_law")
    try:
        with t.role("decision"):
            pass
        check(False, "unknown role accepted")
    except TypeError:
        pass
    t.tally("torch.train_steps_by_learner", "demo", 7)
    summary = t.summary()
    check(summary["authored"] == {"fallback": 5} and summary["roles"]["reference"]["authored"] == {"reference_law": 1},
          f"authored and roles: {summary}")
    check("Torch trained 7 optimizer steps" in summary["verdict"], summary["verdict"])
    authored = [r["data"]["uses"] for r in records if r["cat"] == "authored" and r["msg"] == "fallback"]
    check(authored == [1, 2, 4], f"authored records thinned to 1, 2, 4: {authored}")
    check(all(r["schema"] == "trech_trace_v1" and r["host"] == "python" for r in records), "record schema")
    check(any(r.get("role") == "reference" for r in records), "role stamped")
    filtered = trace.Trace("trace", ["torch"], sink=records.append)
    before = len(records)
    filtered.channel("data").info("dropped")
    check(len(records) == before, "category filter")

    # --- numpy + torch through the module-level trace ------------------------------------
    rng = np.random.default_rng(0)
    x = rng.normal(size=(40, 3))
    y = np.stack([x[:, 0] * 2.0 + x[:, 1], np.sin(x[:, 2])], axis=1)
    stats = trace.array_stats(np.array([1.0, np.nan, 3.0]))
    check(stats["nonfinite"] == 1 and stats["min"] == 1.0 and stats["max"] == 3.0, f"array stats {stats}")

    trace.configure(trace.Trace("off"))
    untraced = fit_bytes(train_surrogate, x, y)
    captured = []
    trace.configure(trace.Trace("debug", sink=captured.append))
    traced = fit_bytes(train_surrogate, x, y)
    check(traced == untraced, "tracing changed trained weights")
    by = {}
    for r in captured:
        by.setdefault((r["cat"], r["msg"]), []).append(r)
    start = by.get(("torch", "training start"), [{}])[0].get("data", {})
    check(start.get("learner") == "train_surrogate.mlp" and start.get("model", {}).get("parameters", 0) > 0
          and start.get("optimizer", {}).get("type") == "Adam", f"training start: {start}")
    epochs = [r["data"]["epoch"] for r in by.get(("torch", "epoch"), [])]
    check(epochs == [1, 2, 4, 8, 16, 20], f"epoch records at debug: {epochs}")
    end = by.get(("torch", "training end"), [{}])[0].get("data", {})
    check(end.get("steps") == 20 and end.get("loss_last", 1e9) <= end.get("loss_first", 0), f"training end: {end}")
    check(("numpy", "array fit_mlp.x") in by and ("numpy", "fit ridge_normal_equations") in by,
          f"numpy records: {sorted(by)}")
    check("gram_condition" in by[("numpy", "fit ridge_normal_equations")][0]["data"], "fit conditioning")
    runtime = by.get(("torch", "runtime"), [{}])[0].get("data", {})
    check(runtime.get("torch") and runtime.get("numpy") and runtime.get("threads", 0) >= 1, f"runtime: {runtime}")
    summary = trace.summary()
    check(summary["tallies"]["torch.train_steps_by_learner"]["train_surrogate.mlp"] == 20.0 and
          summary["tallies"]["numpy.fits_by_kind"]["ridge_normal_equations"] == 1.0, f"tallies {summary['tallies']}")

    with tempfile.TemporaryDirectory() as tmp:
        net, scalers = train_surrogate.fit_mlp(x, y, hidden=4, epochs=2, lr=1e-2, seed=1, quiet=True)
        pt = Path(tmp) / "m.pt"
        check(train_surrogate.export_torchscript(net, scalers, pt), "export")
        exported = [r for r in captured if r["msg"] == "model exported"][-1]["data"]
        check(exported["sha256"] == hashlib.sha256(pt.read_bytes()).hexdigest() and exported["format"] == "torchscript",
              f"export record {exported}")

        # Environment configuration and the summary written at exit, as a worker does it.
        out = Path(tmp) / "child.jsonl"
        code = ("from trech_torch import trace; trace.channel('arch').info('hello', {'n': 1}); "
                "trace.tally('torch.train_steps_by_learner', 'x', 3)")
        env = {"PYTHONPATH": str(REPO / "tools" / "torch"), "TRECH_TRACE": "info", "TRECH_TRACE_FILE": str(out),
               "TRECH_TRACE_STDERR": "0", "PATH": "/usr/bin:/bin"}
        run = subprocess.run([sys.executable, "-c", code], env=env, capture_output=True, text=True)
        check(run.returncode == 0, run.stderr[-800:])
        lines = [json.loads(line) for line in out.read_text().splitlines()] if out.exists() else []
        check([r["msg"] for r in lines] == ["hello", "python summary"] and
              lines[-1]["data"]["tallies"]["torch.train_steps_by_learner"]["x"] == 3.0,
              f"environment-configured child trace: {lines}")
    trace.configure(trace.Trace("off"))

    if FAILURES:
        print(f"{FAILURES} python trace check(s) failed")
        return 1
    print("python trace: ok")
    return 0


if __name__ == "__main__":
    sys.exit(main())
