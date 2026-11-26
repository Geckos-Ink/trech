#!/usr/bin/env python3
"""Python side of the recursive group-lifting contract (trech_torch.hierarchy).

* Plan validation fails closed: no `present` mask, member features the level below does not
  produce, rel_* without a length, an unsupervised top level.
* `partition` / `build_structure` reproduce the engine's grouping order (lattice cells by
  (ix, iy, iz), explicit ids ascending, members ascending) -- checked on the committed fixture
  keys, which the C++ test also checks against GroupHierarchy.
* NumPy (required): `lift_np` on the committed fixture models reproduces `expected.json`, so the
  reference the C++ parity test reads cannot drift from the evaluator that wrote it, and a
  capacity overflow blocks the group and everything above it.

Runs under CTest with TRECH_ML_PYTHON; a missing NumPy fails it.
"""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "tools" / "torch"))
FIXTURE = REPO / "tests" / "fixtures" / "ml_group_hierarchy"

from trech_torch import hierarchy  # noqa: E402

FAILURES = 0


def check(cond: bool, message: str) -> None:
    global FAILURES
    if not cond:
        FAILURES += 1
        print(f"FAIL: {message}")


def rejects(plan: dict, fragment: str, message: str) -> None:
    try:
        hierarchy.load_plan(plan)
    except ValueError as exc:
        check(fragment in str(exc), f"{message} (got: {exc})")
        return
    check(False, message)


def main() -> int:
    plan_json = json.loads((FIXTURE / "plan.json").read_text())
    plan = hierarchy.load_plan(plan_json)
    check([l["produced"] for l in plan["levels"]][0] == ["cell_energy", "cell_h0", "cell_h1", "cell_h2", "cell_h3"],
          "supervised outputs come first, then the named latent channels")
    check(plan["levels"][2]["length"] == 4.0 and plan["levels"][0]["length"] == 1.0,
          "rel_* length defaults to the lattice edge")

    bad = json.loads(json.dumps(plan_json))
    bad["levels"][0]["member_features"].remove("present")
    rejects(bad, "present", "a level without the presence mask is rejected")
    bad = json.loads(json.dumps(plan_json))
    bad["levels"][1]["member_features"].append("cell_h9")
    rejects(bad, "not produced", "a member feature the level below does not produce is rejected")
    bad = json.loads(json.dumps(plan_json))
    del bad["levels"][2]["length"]
    rejects(bad, "length", "rel_* without a length is rejected")
    bad = json.loads(json.dumps(plan_json))
    bad["levels"][2]["outputs"] = []
    bad["levels"][2]["latent"] = 2
    rejects(bad, "top level", "an unsupervised top level is rejected")

    # Engine grouping order on synthetic points (pure Python).
    level = {"name": "c", "grouping": "cell", "cell_size": 1.0}
    pts = [(1.5, 0.2, 0.2), (0.1, 0.1, 0.1), (-0.5, 3.0, 0.0), (0.9, 0.9, 0.9), (1.1, 0.0, 0.0)]
    groups = hierarchy.partition(len(pts), pts, level, (0.0, 0.0, 0.0))
    check([k for k, _ in groups] == ["-1,3,0", "0,0,0", "1,0,0"], "lattice cells are ordered by (ix, iy, iz)")
    check(groups[1][1] == [1, 3] and groups[2][1] == [0, 4], "members keep ascending order")
    explicit = hierarchy.partition(4, None, {"name": "e", "grouping": "explicit"}, (0, 0, 0), [7, -2, 7, 0])
    check(explicit == [("-2", [1]), ("0", [3]), ("7", [0, 2])], "explicit ids are ordered ascending")
    w, c = hierarchy.centroid([0, 2], [(0.0, 0.0, 0.0), (9, 9, 9), (3.0, 6.0, 0.0)], [1.0, 1.0, 2.0])
    check(w == 3.0 and c == (2.0, 4.0, 0.0), "the centroid is weight-averaged")

    expected = json.loads((FIXTURE / "expected.json").read_text())
    for bad_weight in (0.0, -1.0, float("nan")):
        case = json.loads(json.dumps(expected["cases"][0]))
        case["weight"] = [1.0] * len(case["features"]["q"])
        case["weight"][3] = bad_weight
        try:
            hierarchy.build_structure(case, plan)
            check(False, f"a weight of {bad_weight} is refused, as ctx.lift refuses it")
        except ValueError as exc:
            check("finite and positive" in str(exc), f"weight refusal names the rule (got: {exc})")
    for case in expected["cases"]:
        structure = hierarchy.build_structure(case, plan)
        for k, level_struct in enumerate(structure):
            check(level_struct["keys"] == case["levels"][k]["keys"],
                  f"level {k} keys reproduce the committed partition")
        check(sum(len(m) for m in structure[0]["members"]) == len(case["features"]["q"]),
              "every base element lands in exactly one cell")

    import numpy as np

    models = [json.loads((FIXTURE / f"{l['name']}.json").read_text()) for l in plan["levels"]]
    worst = 0.0
    for case in expected["cases"]:
        result = hierarchy.lift_np(case, plan, models)
        for k, level_result in enumerate(result):
            ref = case["levels"][k]
            check([bool(v) for v in level_result["valid"]] == ref["valid"], "validity is reproduced")
            for g, row in enumerate(ref["features"]):
                for o, value in enumerate(row):
                    if value is not None:
                        got = float(level_result["features"][g, o])
                        worst = max(worst, abs(got - value) / max(1.0, abs(value)))
    check(worst <= 1e-12, f"lift_np reproduces the committed reference (worst {worst:.3g})")

    lumped = json.loads(json.dumps(plan_json))
    lumped["levels"][0]["grouping"] = "explicit"
    lumped_plan = hierarchy.load_plan(lumped)
    case = dict(expected["cases"][0])
    case["groups"] = {"cell": [0] * len(case["features"]["q"])}
    result = hierarchy.lift_np(case, lumped_plan, models)
    check(not result[0]["valid"].any() and not result[2]["valid"].any() and
          math.isnan(float(result[2]["features"][0, 0])),
          "an over-capacity group blocks itself and every level above it")

    # A bounded lower response is decoded before the higher level consumes it.
    import torch

    torch.set_num_threads(1)
    bounded = hierarchy.load_plan({
        "base_features": ["q"],
        "levels": [
            {"name": "group", "grouping": "all", "member_features": ["present", "q"],
             "outputs": ["fraction"], "output_transforms": ["sigmoid"]},
            {"name": "observer", "grouping": "all", "member_features": ["present", "fraction"],
             "outputs": ["twice_fraction"]},
        ]
    })
    samples = [{"features": {"q": [i / 16]}, "targets": {
        "group": {"all": {"fraction": i / 16}},
        "observer": {"all": {"twice_fraction": i / 8}},
    }} for i in range(17)]
    fitted, _ = hierarchy.train(bounded, samples, epochs=300, quiet=True)
    held, _ = hierarchy.chained_metrics(bounded, fitted, samples)
    check(fitted[0]["output_transforms"] == ["sigmoid"] and
          0 < held[0]["pred"].min() < held[0]["pred"].max() < 1 and
          held[1]["metrics"]["twice_fraction"]["r2"] > .95,
          "upper level consumes bounded lower predictions on the exported path")

    if FAILURES:
        print(f"{FAILURES} failure(s)")
        return 1
    print("test_group_hierarchy.py: all checks passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
