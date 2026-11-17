"""Evolvo architecture worker for the TRECH engine (``trech_arch_request_v1`` -> ``_result_v1``).

The C++ ``ArchitectureGenerator`` (``trech arch``) launches this module as a subprocess:

    python -m trech_torch.arch_worker --request <name>.worker_request.json --result <name>.worker_result.json

The request carries the train/selection/test tables, budgets, the classic reference family as
seed genomes and the classic reference's selection score. The worker runs the Evolvo GFSL-NN
search (``trech_torch.evolve_architecture``), exports the best architecture (native JSON for
dense chains, TorchScript + sidecar otherwise) and writes a result bound to the request's
SHA-256. The engine, not the worker, decides whether the evolved model replaces the classic
reference: it reloads and re-scores the export itself.

Exit codes: 0 with ``status: ok``; 3 with ``status: unavailable`` when torch or Evolvo cannot
be imported; 1 with ``status: error`` for any other failure (when a result can still be written).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import sys
import time
import traceback
from pathlib import Path

REQUEST_SCHEMA = "trech_arch_request_v1"
RESULT_SCHEMA = "trech_arch_result_v1"


def _write(path: Path, payload: dict) -> None:
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2, default=float) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def run(request: dict, request_sha: str) -> dict:
    import numpy as np

    from .evolve_architecture import export, predict, search_architecture
    from .train_surrogate import evaluate, holdout_block

    if request.get("schema") != REQUEST_SCHEMA:
        raise ValueError(f"request schema must be {REQUEST_SCHEMA}")
    arr = lambda t, k: np.asarray(request[t][k], dtype=float)  # noqa: E731
    x, y = arr("train", "x"), arr("train", "y")
    x_val, y_val = arr("selection", "x"), arr("selection", "y")
    has_test = len(request["test"]["y"]) > 0
    budget = request["budget"]
    knowledge = request.get("knowledge") or None
    started = time.monotonic()
    found = search_architecture(
        x, y, x_val, y_val, max_rows=budget["max_rows"], max_params=budget["max_params"],
        generations=budget["generations"], population=budget["population"], patience=budget["patience"],
        max_evaluations=budget.get("max_evaluations") or None, seconds=budget.get("time_budget_s", 0.0),
        seed=int(request["seed"]) % (2 ** 31), size_cost=request["size_cost"], lr=request["lr"],
        hard_max_epochs=budget["max_epochs"], ops=request.get("ops") or None,
        knowledge_path=Path(knowledge) if knowledge else None, quiet=False,
        seeds=request.get("seeds", []), native_only=bool(request.get("engine_native_only")))
    report = found["report"]
    inputs, outputs = request["inputs"], request["outputs"]
    holdout = None
    if has_test:
        x_test, y_test = arr("test", "x"), arr("test", "y")
        holdout = holdout_block(evaluate(y_test, predict(found["module"], x_test, found["scalers"]), outputs),
                                len(y_test))
    meta = {"generator": "evolvo_gfsl_nn", "request_sha256": request_sha,
            "classic_reference": request.get("classic_reference"),
            "selection_loss": found["selected"]["loss"], "parameter_count": found["selected"]["params"],
            "selection_objective": "mean_squared_error_in_training_standardized_outputs",
            "train": request["train"].get("source"), "selection": request["selection"].get("source"),
            "test": request["test"].get("source"), "seed": request["seed"]}
    out_prefix = Path(request["out_prefix"])
    exports = export(out_prefix, found, inputs, outputs, x, meta=meta, holdout=holdout)
    report_path = out_prefix.with_suffix(".search.json")
    report_path.write_text(json.dumps(report, indent=2, default=float) + "\n", encoding="utf-8")
    best = found["selected"]
    seeds = [{"signature": h["signature"], "loss": h["loss"], "params": h["params"], "score": h["score"]}
             for h in report["history"] if h["origin"] == "seed"]
    overall = report["best"]
    return {
        "status": "ok",
        "best": {"genome": best["genome"], "describe": best["describe"], "signature": best["signature"],
                 "selection_loss": best["loss"], "params": best["params"], "exports": exports,
                 "engine_native": best["engine_native"], "holdout": holdout},
        "overall_best": {"signature": overall["signature"], "selection_loss": overall["loss"],
                         "params": overall["params"], "score": overall["score"],
                         "describe": overall["describe"]},
        "search": {"stop_reason": report["stop_reason"], "evaluations": report["evaluations"],
                   "unique_architectures": report["unique_architectures"], "report": str(report_path),
                   "seconds": time.monotonic() - started, "seed_evaluations": seeds,
                   "efficient_params": report["efficiency"]["efficient_params"]},
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--request", required=True)
    parser.add_argument("--result", required=True)
    args = parser.parse_args(argv)
    result_path = Path(args.result)
    raw = Path(args.request).read_bytes()
    sha = hashlib.sha256(raw).hexdigest()
    base = {"schema": RESULT_SCHEMA, "request_sha256": sha, "python": sys.version.split()[0]}
    try:
        import numpy  # noqa: F401
        import torch  # noqa: F401

        from .evolve_architecture import evolvo_arch

        evolvo_arch()
        base["torch"] = torch.__version__
    except (ImportError, RuntimeError) as exc:
        _write(result_path, {**base, "status": "unavailable", "error": f"{type(exc).__name__}: {exc}"})
        print(f"arch_worker: unavailable: {exc}", file=sys.stderr)
        return 3
    try:
        payload = run(json.loads(raw), sha)
    except Exception as exc:  # report every failure to the engine, then fail
        traceback.print_exc()
        _write(result_path, {**base, "status": "error", "error": f"{type(exc).__name__}: {exc}"})
        return 1
    if not math.isfinite(payload["best"]["selection_loss"]):
        _write(result_path, {**base, "status": "error", "error": "non-finite selection loss"})
        return 1
    _write(result_path, {**base, **payload})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
