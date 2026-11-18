#!/usr/bin/env python3
"""NumPy twin of the engine's frozen domain learner (trech_torch.domain_learner).

The C++ test exports a learned state (quadratic laws, residual networks, pooled law) and the
engine's predictions for rows inside and beyond the learned envelopes. The NumPy replay must
route every row to the same domain and reproduce every prediction to rounding.

Usage (CTest): test_domain_learner.py <path to test_domain_learner executable>
"""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "tools" / "torch"))

from trech_torch.domain_learner import Learner, strip_rows  # noqa: E402


def main() -> int:
    binary = Path(sys.argv[1])
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "parity.json"
        subprocess.run([str(binary), "--export", str(path)], check=True, capture_output=True)
        data = json.loads(path.read_text())
    state = data["state"]
    learner = Learner(strip_rows(state))
    d = len(state["features"])
    x = np.asarray(data["features"], dtype=np.float64).reshape(-1, d)
    predicted, domains, outside = learner.predict(x)
    engine = np.asarray([np.nan if v is None else v for v in data["predictions"]], dtype=np.float64)
    engine = engine.reshape(predicted.shape)
    failures = []
    if not np.array_equal(domains, np.asarray(data["domains"])):
        failures.append("domain routing differs")
    if not np.array_equal(np.isfinite(predicted), np.isfinite(engine)):
        failures.append("prediction availability differs")
    finite = np.isfinite(engine)
    diff = np.abs(predicted - engine)[finite] / np.maximum(1.0, np.abs(engine[finite]))
    if diff.size and diff.max() > 1e-9:
        failures.append(f"max relative prediction difference {diff.max():.3g}")
    networks = sum("residual_network" in leaf for leaf in state["leaves"])
    if not networks:
        failures.append("the exported state carries no residual network")
    if not outside.any():
        failures.append("no extrapolated row exercised the bounded paths")
    print(f"rows={len(x)} domains={len(learner.leaves)} networks={networks} extrapolated={int(outside.sum())} "
          f"max_rel={diff.max() if diff.size else 0:.3g}")
    for failure in failures:
        print("FAIL:", failure)
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
