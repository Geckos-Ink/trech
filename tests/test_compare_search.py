#!/usr/bin/env python3
"""Search-strategy comparison harness (trech_torch.compare_search), torch required.

Every strategy trains through one shared TorchTask with the same budget of distinct trained
candidates; proposals the space refuses are counted, not trained; the knowledge-reuse strategy
only ever loads an earlier seed's knowledge; loaders refuse overlapping splits; repeated runs
are identical. Synthetic data: tests the harness, not physics.
"""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "thirds" / "evolvo" / "src"))
sys.path.insert(0, str(REPO / "tools" / "torch"))

FAILURES = 0


def check(cond, message):
    global FAILURES
    if not cond:
        FAILURES += 1
        print(f"FAIL: {message}")


def table(path: Path, overlap: bool = False) -> None:
    import numpy as np
    rng = np.random.default_rng(5)
    rows = []
    for split, n in (("train", 60), ("development", 20), ("test", 20)):
        for i in range(n):
            x = rng.uniform(-1, 1, 3)
            rows.append({"id": f"{split}_{i}" if not (overlap and split == "test" and i == 0) else "train_0",
                         "split": split, "inputs": x.tolist(),
                         "labels": {"u": float(np.sin(2 * x[0]) * x[1]), "v": float(x[2] ** 2 - x[0])}})
    path.write_text(json.dumps({"schema": "synthetic_rows_v1", "input_features": ["a", "b", "c"],
                                "output_features": ["u", "v"], "rows": rows}))


def main() -> int:
    from trech_torch import compare_search as cs

    check(len(cs.GRID) == 24 and len(set(cs.GRID)) == 24, "the grid has 24 distinct points")
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        table(tmp / "rows.json")
        table(tmp / "overlap.json", overlap=True)
        try:
            cs.load_rows_table(tmp / "overlap.json", "train", "development", "test")
            check(False, "overlapping splits are refused")
        except ValueError as error:
            check("disjoint" in str(error), "overlapping splits are refused with a reason")
        inputs, outputs, (x, y), (xv, yv), (xt, yt), schema = cs.load_rows_table(tmp / "rows.json", "train", "development", "test")
        check(inputs == ["a", "b", "c"] and outputs == ["u", "v"] and len(x) == 60 and len(xt) == 20, "table loads by split")
        run = lambda: cs.compare(x, y, xv, yv, xt, yt, outputs, seeds=(0, 1), budget=3, max_params=400,  # noqa: E731
                                 hard_max_epochs=60, knowledge=tmp / "k.json", log=lambda *_: None)
        out = run()
        results = out["results"]
        by = {(r["strategy"], r["seed"]): r for r in results}
        reuse0, reuse1 = by[("gfsl_reuse", 0)], by[("gfsl_reuse", 1)]
        check("skipped" in reuse0, "knowledge reuse is skipped at the first seed (nothing earlier to load)")
        check("skipped" not in reuse1, "knowledge reuse runs from the previous seed's knowledge")
        check((tmp / "k.seed0.json").exists() and (tmp / "k.seed1.json").exists(), "fresh searches save per-seed knowledge")
        for r in results:
            if "skipped" in r:
                continue
            name = f"{r['strategy']} seed {r['seed']}"
            check(r["evaluations"] == 3, f"{name}: exactly the budget of distinct trained candidates")
            check(len({t["signature"] for t in r["trials"]}) == len(r["trials"]), f"{name}: no candidate trained twice")
            check(all(t["params"] <= 400 for t in r["trials"]), f"{name}: no trained candidate exceeds max_params")
            check(r["best"]["loss"] == min(t["loss"] for t in r["trials"]), f"{name}: the winner has the lowest selection loss")
            check(r["loss_curve"][-1] == r["best"]["loss"] and r["loss_curve"] == sorted(r["loss_curve"], reverse=True),
                  f"{name}: best-so-far curve is non-increasing and ends at the winner")
            check(r["test"]["mse_standardized"] >= 0 and all(v is not None for v in r["test"]["r2"].values()),
                  f"{name}: held-out metrics are finite")
        # 45 x 3 deep grid points exceed 400 parameters: refused, never trained.
        check(by[("grid", 0)]["refused_proposals"] == 0 and by[("grid", 0)]["trials"][0]["describe"] != [],
              "the first grid points fit the budget")
        check(set(out["summary"]) == set(cs.STRATEGIES), "every strategy is summarized")
        check(out["ridge"]["test"]["mse_standardized"] > 0, "a ridge reference is reported")
        again = run()
        check([r.get("best", {}).get("loss") for r in again["results"]] == [r.get("best", {}).get("loss") for r in results],
              "a repeated comparison selects the same candidates with the same losses")
    print("compare_search: " + ("ok" if not FAILURES else f"{FAILURES} failure(s)"))
    return 1 if FAILURES else 0


if __name__ == "__main__":
    raise SystemExit(main())
