#!/usr/bin/env python3
"""Regenerate the generic_surrogate_v3 (DeepSets / MPNN) parity fixtures.

Needs NumPy + torch (e.g. `build/render-venv/bin/python`). Writes synthetic set runs to a
temporary directory -- up to four 2-D points with a presence mask and one global gain, target
= gain x sum of pairwise Gaussian proximities (a pair interaction a per-element sum cannot
represent exactly) -- trains two tiny set networks with `trech_torch.train_surrogate`, and
records NumPy-evaluated reference outputs in `expected.json`. The C++ test
(`tests/test_generic_surrogate.cpp`) and `tests/test_ml_model_validation.py` compare their own
evaluators with these references. The data are synthetic: these models test arithmetic, not
physics.

    PYTHONPATH=tools/torch build/render-venv/bin/python tests/fixtures/ml_set_networks/regenerate.py
"""

from __future__ import annotations

import json
import math
import random
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(ROOT / "tools" / "torch"))

ELEMENTS = 4
INPUTS = [f"p{e}_{f}" for e in range(ELEMENTS) for f in ("x", "y", "m")] + ["g"]


def sample(rng: random.Random) -> dict:
    row, points = {}, []
    present_count = rng.randint(2, ELEMENTS)
    for e in range(ELEMENTS):
        present = e < present_count
        x, y = (rng.uniform(-1, 1), rng.uniform(-1, 1)) if present else (0.0, 0.0)
        row[f"p{e}_x"], row[f"p{e}_y"], row[f"p{e}_m"] = x, y, 1.0 if present else 0.0
        if present:
            points.append((x, y))
    row["g"] = rng.uniform(0.5, 1.5)
    row["energy"] = row["g"] * sum(
        math.exp(-((a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2) / 0.3)
        for i, a in enumerate(points) for b in points[i + 1:])
    return row


def write_run(path: Path, seed: int, n: int) -> None:
    rng = random.Random(seed)
    rows = [sample(rng) for _ in range(n)]
    path.mkdir(parents=True, exist_ok=True)
    (path / "trech_provenance.jsonl").write_text(json.dumps(
        {"seed": seed, "config_json": json.dumps({"run": {"seed": seed}})}) + "\n")
    (path / "trech_scores.jsonl").write_text(json.dumps({"phase": "run_summary", "n_events": n}) + "\n")
    with (path / "trech_hook_emits.jsonl").open("w") as stream:
        for begin in range(0, n, 256):
            stream.write(json.dumps({"phase": "hook_emit", "event_id": begin, "hook": "fixture",
                                     "tag": "set_fixture", "payload": {"samples": rows[begin:begin + 256]}}) + "\n")


def scrub(path: Path, work: Path) -> None:
    """Replace the temporary run directories recorded in the model with stable placeholders."""
    text = path.read_text().replace(str(work.resolve()), "<synthetic>").replace(str(work), "<synthetic>")
    path.write_text(text)


def main() -> int:
    import numpy as np

    from trech_torch.train_surrogate import main as train, predict_np

    with tempfile.TemporaryDirectory() as tmp:
        work = Path(tmp)
        for name, seed, n in (("train", 11, 1500), ("test", 12, 300), ("cal", 13, 300)):
            write_run(work / name, seed, n)
        common = ["--runs", str(work / "train"), "--validation-runs", str(work / "test"),
                  "--calibration-runs", str(work / "cal"), "--source", "hook_emits",
                  "--tag", "set_fixture", "--expand", "samples", "--inputs", ",".join(INPUTS),
                  "--outputs", "energy", "--set-elements", str(ELEMENTS), "--set-context", "1",
                  "--mask-feature", "2", "--epochs", "250", "--seed", "7"]
        variants = {
            "deepsets": ["--network", "deepsets", "--pool", "max", "--phi-widths", "6,5",
                         "--rho-widths", "4"],
            "mpnn": ["--network", "mpnn", "--pool", "mean", "--aggregate", "sum", "--rounds", "2",
                     "--phi-widths", "5", "--message-widths", "4", "--rho-widths", "4",
                     "--relative-features", "0,1", "--activation", "tanh"],
        }
        for name, extra in variants.items():
            if train(common + extra + ["--out-json", str(HERE / f"{name}.json"),
                                       "--manifest", str(work / f"{name}.manifest.json")]) != 0:
                return 1
            scrub(HERE / f"{name}.json", work)

    rng = random.Random(99)
    rows = [[sample(rng)[c] for c in INPUTS] for _ in range(6)]
    # Permuted copies (set invariance), an all-absent set and a single present element.
    permuted = []
    for row in rows[:3]:
        blocks = [row[e * 3:(e + 1) * 3] for e in range(ELEMENTS)]
        blocks = blocks[::-1]
        permuted.append([v for b in blocks for v in b] + row[ELEMENTS * 3:])
    empty = [0.0] * (ELEMENTS * 3) + [1.0]
    single = [0.3, -0.2, 1.0] + [0.0] * ((ELEMENTS - 1) * 3) + [0.8]
    inputs = rows + permuted + [empty, single]
    expected = {"schema": "trech_set_network_fixture_v1", "inputs": INPUTS, "rows": inputs,
                "permutation_pairs": [[i, len(rows) + i] for i in range(3)], "outputs": {}}
    for name in ("deepsets", "mpnn"):
        model = json.loads((HERE / f"{name}.json").read_text())
        scalers = tuple(np.asarray(model[k], dtype=float)
                        for k in ("input_mean", "input_std", "output_mean", "output_std"))
        pred = predict_np(np.asarray(inputs, dtype=float), model["network"], scalers,
                          model["output_transforms"])
        expected["outputs"][name] = [float(v) for v in pred[:, 0]]
    (HERE / "expected.json").write_text(json.dumps(expected, indent=1) + "\n")
    print("wrote", HERE)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
