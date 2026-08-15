#!/usr/bin/env python3
"""The exported JOINT training reference must be calibrated and deterministic.

`trech-train-surrogate` exports a covering set of standardized training rows plus
the distance that covers `quantile` of the training set, so the engine can flag a
prediction that is in range on every axis yet far from any training point. Two
properties have to hold or the flag is noise:

* **Calibration** — running the training set back through the check must flag
  roughly `1 - quantile` of it. Too many and every healthy run screams; too few
  and a genuine hole slips through.
* **Determinism** — the same training rows must export the same reference, or a
  rebuilt model stops being comparable to the one it replaced. Selection is
  farthest-point sampling from the row nearest the mean, with no RNG.

It also asserts the property the whole feature exists for: a point inside every
per-feature range but between the training clusters is far from all centers.

Runs under CTest; needs only numpy (the trainer's numpy-only path).
"""

from __future__ import annotations

import math
import random
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "tools" / "torch"))

try:
    import numpy as np
except ImportError:  # pragma: no cover - numpy is the trainer's only hard dep
    print("SKIP: numpy not available")
    raise SystemExit(0)

from trech_torch.train_surrogate import input_domain, joint_reference  # noqa: E402

FAILURES = 0


def expect(cond: bool, message: str) -> None:
    global FAILURES
    if not cond:
        print(f"FAIL: {message}")
        FAILURES += 1


def nearest_distance(z: np.ndarray, centers: np.ndarray) -> np.ndarray:
    """Distance from every row to its nearest center (the engine's check)."""
    d = ((z[:, None, :] - centers[None, :, :]) ** 2).sum(axis=2)
    return np.sqrt(d.min(axis=1))


def two_cluster_training_set(rows: int = 800) -> np.ndarray:
    """(cold, slow) and (hot, fast) only -- (cold, fast) is never trained."""
    rng = random.Random(20260815)
    out = []
    for t0, r0 in ((300.0, 0.10), (360.0, 0.90)):
        for _ in range(rows // 2):
            out.append([t0 + rng.gauss(0, 4.0), r0 + rng.gauss(0, 0.03)])
    return np.array(out, dtype=float)


def main() -> int:
    x = two_cluster_training_set()
    mean, std = x.mean(axis=0), x.std(axis=0)
    scalers = (mean, std, np.zeros(1), np.ones(1))
    domain = input_domain(x, scalers)

    expect("joint" in domain, "input_domain exports a joint reference")
    joint = domain["joint"]
    centers = np.array(joint["centers"], dtype=float)
    radius = float(joint["radius"])
    quantile = float(joint["quantile"])
    expect(centers.shape[1] == x.shape[1],
           "each center has one coordinate per input feature")
    expect(len(centers) <= 24, "the reference stays small (24 centers by default)")
    expect(radius > 0.0 and math.isfinite(radius), "a finite positive radius")

    # --- calibration: the training set itself must mostly pass ------------------
    z = (x - mean) / std
    d = nearest_distance(z, centers)
    flagged = float((d > radius).mean())
    expect(flagged <= (1.0 - quantile) + 0.02,
           f"training rows flagged starved ({flagged:.3%}) stays near the "
           f"exported quantile ({1 - quantile:.1%})")
    expect(flagged > 0.0,
           "the radius is a quantile, not the maximum (some tail is flagged)")

    # --- the hole the per-feature checks cannot see -----------------------------
    hole = np.array([[300.0, 0.90]])  # cold AND fast: in range on both axes
    z_hole = (hole - mean) / std
    per_feature_radius = np.array(domain["standardized_radius"])
    expect(bool((np.abs(z_hole[0]) <= per_feature_radius).all()),
           "the untrained corner passes every per-feature range check")
    hole_distance = float(nearest_distance(z_hole, centers)[0])
    expect(hole_distance > radius,
           f"the untrained corner is jointly starved "
           f"(d={hole_distance:.3f} > radius={radius:.3f})")
    expect(hole_distance > 4.0 * radius,
           "and it is not a marginal call -- it sits far outside every cluster")

    # --- determinism: same rows in, same reference out -------------------------
    again = input_domain(x, scalers)["joint"]
    expect(again == joint, "the same training rows export the same joint reference")
    # Row ORDER must not matter either: the seed is the row nearest the mean and
    # ties break by index, so a shuffled harvest cannot silently move the hull.
    order = np.array(sorted(range(len(x)), key=lambda i: (x[i][1], x[i][0])))
    shuffled = input_domain(x[order], scalers)["joint"]
    expect(math.isclose(shuffled["radius"], joint["radius"], rel_tol=1e-9),
           "the covering radius is independent of training-row order")

    # --- degenerate inputs must not export a bogus reference --------------------
    expect(joint_reference(np.zeros((1, 2)), 24, 0.99) is None,
           "a single training row exports no joint reference")
    expect(joint_reference(np.zeros((0, 2)), 24, 0.99) is None,
           "an empty training set exports no joint reference")
    identical = joint_reference(np.zeros((50, 3)), 24, 0.99)
    expect(identical is not None and len(identical["centers"]) == 1,
           "identical training rows collapse to a single center, not 24 copies")
    expect(identical is not None and identical["radius"] == 0.0,
           "identical rows give a zero covering radius (everything is that point)")

    # --- the planner turns the same evidence into where to simulate NEXT -------
    import json
    import tempfile

    from trech_torch.plan_experiments import analyze_models  # noqa: E402
    from trech_torch.train_surrogate import write_generic_json  # noqa: E402

    with tempfile.TemporaryDirectory() as tmp:
        model_path = Path(tmp) / "two_cluster.json"
        write_generic_json(
            model_path, ["temperature_k", "rate_per_s"], ["response"],
            (mean, std, np.zeros(1), np.ones(1)),
            [{"weights": [[1.0, 1.0]], "bias": [0.0], "activation": "none"}],
            {"source": "test"}, domain=domain,
        )
        report, recs = analyze_models([str(model_path)])
        kinds = {r["kind"] for r in recs}
        expect("model_joint_starved" in kinds,
               "the planner reports the joint gap between the two clusters")
        joint_rec = next(r for r in recs if r["kind"] == "model_joint_starved")
        holes = joint_rec["details"]["holes"]
        expect(bool(holes), "the planner names at least one starved region")
        point = holes[0]["operating_point"]
        expect(set(point) == {"temperature_k", "rate_per_s"},
               "the proposal is in the model's own raw input units")
        # The worst gap must sit BETWEEN the clusters, not outside the data.
        expect(300.0 < point["temperature_k"] < 360.0
               and 0.10 < point["rate_per_s"] < 0.90,
               f"the proposed operating point lies between the trained "
               f"clusters (got {point})")
        expect(holes[0]["distance_over_radius"] > 1.0,
               "and it is reported as a multiple of the covering radius")
        expect(report["models"][0]["has_joint_reference"] is True,
               "the planner records that the model carries a joint reference")

        # A model with no joint reference is reported as UNCHECKED, and the
        # planner says how to fix it rather than treating it as covered.
        bare = Path(tmp) / "bare.json"
        bare.write_text(json.dumps({
            "model": "generic_surrogate_v1",
            "input_features": ["a"], "output_features": ["b"],
            "layers": [{"weights": [[1.0]], "bias": [0.0], "activation": "none"}],
        }), encoding="utf-8")
        _bare_report, bare_recs = analyze_models([str(bare)])
        expect(any(r["kind"] == "model_joint_unmeasured" for r in bare_recs),
               "a model with no joint reference is flagged as unchecked")

    if FAILURES == 0:
        print("test_joint_domain: all checks passed")
        return 0
    print(f"test_joint_domain: {FAILURES} check(s) failed")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
