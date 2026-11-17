#!/usr/bin/env python3
"""Regenerate the recursive group-lifting (GroupHierarchy / ctx.lift) parity fixtures.

Needs NumPy + torch (e.g. `build/render-venv/bin/python`). Synthetic systems: 60-140 charged
points (q = +-1) uniform in a 4 x 4 x 4 box, pair energy e_ij = q_i q_j exp(-d^2 / 2 sigma^2)
with sigma = 0.3, labels at three levels:

    cell   (lattice 1.0, nano)  : sum of e_ij over pairs inside the cell
    block  (lattice 2.0, micro) : sum of e_ij over pairs inside the 2x2x2-cell block
    system (all, meso)          : g x sum of all e_ij        (g = per-system context)

Cross-cell and cross-block pairs are NOT in any lower label, so each level must infer them from
its members' learned latent channels: the hierarchy has to lift *behaviour*, not add up labels.
The data are synthetic: these models test the recursive architecture and its C++/NumPy parity,
not physics.

    PYTHONPATH=tools/torch build/render-venv/bin/python tests/fixtures/ml_group_hierarchy/regenerate.py
    PYTHONPATH=tools/torch build/render-venv/bin/python tests/fixtures/ml_group_hierarchy/regenerate.py \
        --demo build/group_hierarchy_demo     # larger training run + report (not committed)

The fixture writes `cell.json`, `block.json`, `system.json` (compact), `plan.json` and
`expected.json`: three held-out systems with their base elements and the NumPy reference
output of every level. `tests/test_group_hierarchy.cpp` compares the C++ GroupHierarchy with it.
"""

from __future__ import annotations

import argparse
import json
import math
import random
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(ROOT / "tools" / "torch"))

SIDE = 4.0
SIGMA = 0.3

PLAN = {
    "schema": "trech_group_hierarchy_plan_v1",
    "base_features": ["q"],
    "levels": [
        {"name": "cell", "scale": "nano", "grouping": "cell", "cell_size": 1.0,
         "member_features": ["present", "rel_x", "rel_y", "rel_z", "q"],
         "outputs": ["cell_energy"], "latent": 4,
         "network": {"kind": "mpnn", "phi": [24], "rho": [24], "message": [24], "rounds": 1,
                     "relative_features": ["rel_x", "rel_y", "rel_z"], "aggregate": "sum",
                     "pool": "sum"}},
        {"name": "block", "scale": "micro", "grouping": "cell", "cell_size": 2.0,
         "member_features": ["present", "weight", "rel_x", "rel_y", "rel_z", "cell_energy",
                             "cell_h0", "cell_h1", "cell_h2", "cell_h3"],
         "outputs": ["block_energy"], "latent": 4,
         "network": {"kind": "mpnn", "phi": [32], "rho": [32], "message": [32], "rounds": 1,
                     "relative_features": ["rel_x", "rel_y", "rel_z"], "aggregate": "sum",
                     "pool": "sum"}},
        {"name": "system", "scale": "meso", "grouping": "all", "length": SIDE,
         "member_features": ["present", "weight", "rel_x", "rel_y", "rel_z", "block_energy",
                             "block_h0", "block_h1", "block_h2", "block_h3"],
         "context": ["g"], "outputs": ["energy"],
         "network": {"kind": "deepsets", "phi": [16, 16], "rho": [16], "pool": "sum"}},
    ],
}


def pair_energy(a, b, qa, qb):
    d2 = sum((a[i] - b[i]) ** 2 for i in range(3))
    return qa * qb * math.exp(-d2 / (2 * SIGMA * SIGMA))


def make_system(rng: random.Random, run: str) -> dict:
    n = rng.randint(60, 140)
    bias = rng.uniform(0.3, 0.7)
    g = rng.uniform(0.5, 1.5)
    pts = [(rng.uniform(0, SIDE), rng.uniform(0, SIDE), rng.uniform(0, SIDE)) for _ in range(n)]
    q = [1.0 if rng.random() < bias else -1.0 for _ in range(n)]
    cell = [tuple(int(math.floor(p[a] / 1.0)) for a in range(3)) for p in pts]
    block = [tuple(int(math.floor(p[a] / 2.0)) for a in range(3)) for p in pts]
    cell_e, block_e, total = {}, {}, 0.0
    for i in range(n):
        for j in range(i + 1, n):
            e = pair_energy(pts[i], pts[j], q[i], q[j])
            total += e
            if cell[i] == cell[j]:
                cell_e[cell[i]] = cell_e.get(cell[i], 0.0) + e
            if block[i] == block[j]:
                block_e[block[i]] = block_e.get(block[i], 0.0) + e
    key = lambda c: ",".join(str(v) for v in c)  # noqa: E731
    return {
        "schema": "trech_group_samples_v1", "run": run,
        "features": {"q": q},
        "positions": {"x": [p[0] for p in pts], "y": [p[1] for p in pts], "z": [p[2] for p in pts]},
        "context": {"g": g},
        "targets": {
            "cell": {key(c): {"cell_energy": cell_e.get(c, 0.0)} for c in set(cell)},
            "block": {key(c): {"block_energy": block_e.get(c, 0.0)} for c in set(block)},
            "system": {"all": {"energy": g * total}},
        },
    }


def systems(seed: int, count: int, prefix: str, per_run: int = 1):
    rng = random.Random(seed)
    return [make_system(rng, f"{prefix}{i // per_run}") for i in range(count)]


def additive_baselines(samples, models, plan):
    """R^2 of g x sum(block energies), with predicted and with TRUE block labels: what adding
    up lower-level answers gives without learning the cross-block behaviour."""
    import numpy as np

    from trech_torch.hierarchy import lift_np

    truth, guess, oracle = [], [], []
    for s in samples:
        levels = lift_np(s, plan, models)
        block = levels[1]
        g = s["context"]["g"]
        truth.append(s["targets"]["system"]["all"]["energy"])
        guess.append(g * float(np.nansum(block["features"][:, 0])))
        oracle.append(g * sum(v["block_energy"] for v in s["targets"]["block"].values()))
    t = np.asarray(truth)
    r2 = lambda p: float(1 - np.mean((np.asarray(p) - t) ** 2) / np.var(t))  # noqa: E731
    return {"predicted_blocks": r2(guess), "true_blocks": r2(oracle)}


def main() -> int:
    import numpy as np

    from trech_torch import hierarchy

    parser = argparse.ArgumentParser()
    parser.add_argument("--demo", default="", help="write a larger demo run here instead of the fixture")
    args = parser.parse_args()
    plan = hierarchy.load_plan(PLAN)

    if args.demo:
        out = Path(args.demo)
        train = systems(101, 500, "train")
        selection = systems(404, 100, "select")
        holdout = systems(202, 200, "holdout")
        calibration = systems(303, 180, "cal", per_run=20)  # 9 runs of 20 systems
        models, report = hierarchy.train(plan, train, selection_samples=selection, epochs=1500,
                                         lr=3e-3, seed=0, weight_decay=1e-4)
        summary = hierarchy.finalize(plan, models, train, holdout, calibration,
                                     note={"description": "synthetic pair-energy hierarchy demo"},
                                     meta={"synthetic": True})
        hierarchy.write_models(models, out, plan)
        summary["additive_baseline_r2"] = additive_baselines(holdout, models, plan)
        summary["training"] = report
        for k, model in enumerate(models):
            summary.setdefault("intervals", []).append(model.get("prediction_interval"))
        (out / "report.json").write_text(json.dumps(summary, indent=2, default=float) + "\n")
        print(json.dumps({"holdout": summary["holdout"], "groups": summary["holdout_groups"],
                          "additive_baseline_r2": summary["additive_baseline_r2"],
                          "capacities": report["capacities"], "selected_epoch": report["selected_epoch"],
                          "selection_per_level": report["selection_per_level"]}, indent=1, default=float))
        return 0

    train = systems(11, 160, "train")
    holdout = systems(12, 40, "holdout")
    plan_small = json.loads(json.dumps(PLAN))
    for level in plan_small["levels"]:
        level["network"] = {"kind": "deepsets", "phi": [12, 12], "rho": [12], "pool": "sum"}
    plan_small["levels"][1]["network"] = {"kind": "mpnn", "phi": [12], "rho": [12], "message": [12],
                                          "rounds": 1, "relative_features": ["rel_x", "rel_y", "rel_z"],
                                          "pool": "mean"}
    plan = hierarchy.load_plan(plan_small)
    models, _ = hierarchy.train(plan, train, epochs=300, lr=5e-3, seed=3, quiet=True)
    hierarchy.finalize(plan, models, train, holdout,
                       note={"description": "synthetic parity fixture: tests arithmetic, not physics"},
                       meta={"synthetic": True})
    for level, model in zip(plan["levels"], models):
        (HERE / f"{level['name']}.json").write_text(json.dumps(model) + "\n")
    (HERE / "plan.json").write_text(json.dumps(plan_small, indent=2) + "\n")
    cases = []
    for sample in holdout[:3]:
        levels = hierarchy.lift_np(sample, plan, models)
        cases.append({
            "features": sample["features"], "positions": sample["positions"], "context": sample["context"],
            "levels": [{"keys": r["keys"], "valid": [bool(v) for v in r["valid"]],
                        "features": [[None if not math.isfinite(v) else float(v) for v in row]
                                     for row in np.asarray(r["features"]).tolist()]} for r in levels],
        })
    (HERE / "expected.json").write_text(json.dumps({"cases": cases}) + "\n")
    print("wrote", ", ".join(p.name for p in sorted(HERE.glob("*.json"))))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
