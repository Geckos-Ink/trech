"""Offline companion of the engine's online domain learner (ctx.learnDomains).

The engine (``src/ml/DomainLearner.cpp``) grows response domains, fits their
laws and decides every split, merge and predictor choice. This module never
re-decides any of that. It

* ``budget``     -- reads the engine's computational context (``trech budget``),
                    so offline models are sized to the machine that trains them;
* ``extract``    -- copies the learner state from a run's final ``full`` emit into
                    a standalone ``trech_domain_learner_v1`` artifact with provenance;
* ``replay``     -- a NumPy twin of frozen routing and prediction, used to check the
                    engine's emitted predictions (parity);
* ``specialize`` -- trains per-domain residual networks in PyTorch on the rows the
                    learner buffered, with the engine's exact input transform, keeps a
                    network only where a temporal holdout shows it beats the domain's
                    ridge law, and writes it into the state so LibTorch evaluates it.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import subprocess
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np

SCHEMA = "trech_domain_learner_v1"


# ---------------------------------------------------------------- budget

def engine_budget(binary: Path, features: int, targets: int) -> dict:
    out = subprocess.run([str(binary), "budget", "--features", str(features), "--targets", str(targets)],
                         check=True, capture_output=True, text=True).stdout
    return json.loads(out)


# ---------------------------------------------------------------- extract

def iter_emits(run: Path, tag: str):
    with open(run / "trech_hook_emits.jsonl") as handle:
        for line in handle:
            row = json.loads(line)
            if row.get("tag") == tag:
                yield row["payload"]


def final_state(run: Path, learner: str, tag: str = "domain_learning") -> dict:
    state = None
    for payload in iter_emits(run, tag):
        if payload.get("learner") == learner and "state" in payload:
            state = payload["state"]
    if state is None:
        raise SystemExit(f"{run}: no full '{learner}' state in '{tag}' emits")
    if state.get("schema") != SCHEMA:
        raise SystemExit(f"{run}: unexpected learner schema {state.get('schema')}")
    return state


def strip_rows(state: dict) -> dict:
    out = json.loads(json.dumps(state))
    for leaf in out["leaves"]:
        leaf.pop("rows", None)
    out["pooled"].pop("rows", None)
    return out


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def extract(runs: List[Path], learner: str, out: Path, keep_rows: bool) -> dict:
    state = final_state(runs[-1], learner)
    if not keep_rows:
        state = strip_rows(state)
    state["provenance"] = {
        "tool": "trech_torch.domain_learner extract",
        "learner": learner,
        "runs": [str(r) for r in runs],
        "final_run_emits_sha256": sha256(runs[-1] / "trech_hook_emits.jsonl"),
        "rows_kept": keep_rows,
    }
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(state, indent=None, separators=(",", ":")) + "\n")
    return state


# ---------------------------------------------------------------- NumPy twin

def basis(z: np.ndarray, degree: int) -> np.ndarray:
    n, d = z.shape
    cols = [np.ones(n)] + [z[:, i] for i in range(d)]
    if degree >= 2:
        for i in range(d):
            for j in range(i, d):
                cols.append(z[:, i] * z[:, j])
    return np.stack(cols, axis=1)


class Learner:
    """Frozen routing and prediction exactly as DomainLearner::update does."""

    def __init__(self, state: dict):
        if state.get("schema") != SCHEMA:
            raise ValueError("not a trech_domain_learner_v1 state")
        self.state = state
        self.features = state["features"]
        self.targets = state["targets"]
        self.degree = int(state["capacity"]["basis_degree"])
        self.nodes = state["nodes"]
        self.leaves = {leaf["id"]: leaf for leaf in state["leaves"]}
        self.pooled = state["pooled"]

    def route(self, x: np.ndarray) -> np.ndarray:
        ids = np.empty(len(x), dtype=np.int64)
        for i, row in enumerate(x):
            n = 0
            while "leaf" not in self.nodes[n]:
                node = self.nodes[n]
                s = float(np.dot(node["direction"], row))
                n = node["left"] if s <= node["threshold"] else node["right"]
            ids[i] = self.nodes[n]["leaf"]
        return ids

    def prediction_basis(self, leaf: dict, x: np.ndarray) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
        z = (x - np.asarray(leaf["x_mean"])) / np.asarray(leaf["x_scale"])
        lo, hi = np.asarray(leaf["z_lo"]), np.asarray(leaf["z_hi"])
        span = hi - lo
        tol = np.maximum(0.05 * span, 1e-9)
        outside = np.any((z < lo - tol) | (z > hi + tol), axis=1) | (self.joint_ratio(leaf, x) > 1.5)
        clamped = np.clip(z, lo - 0.5 * span, hi + 0.5 * span)
        flat = ~(hi > lo)
        z = np.where(flat[None, :], clamped, np.clip(z, lo - 2.0 * span, hi + 2.0 * span))
        phi = basis(clamped, self.degree)
        phi[:, 1:1 + z.shape[1]] = z
        return phi, clamped, outside

    def joint_ratio(self, leaf: dict, x: np.ndarray) -> np.ndarray:
        """Distance to the nearest support centre in support radii (0 without a support set)."""
        if "support_centers" not in leaf:
            return np.zeros(len(x))
        z = (x - np.asarray(leaf["x_mean"])) / np.asarray(leaf["x_scale"])
        centers = np.asarray(leaf["support_centers"]).reshape(-1, z.shape[1])
        d2 = ((z[:, None, :] - centers[None, :, :]) ** 2).sum(axis=2)
        return np.sqrt(d2.min(axis=1)) / leaf["support_radius"]

    def remoteness(self, leaf: dict, x: np.ndarray) -> np.ndarray:
        return np.maximum(self.excess(leaf, x) / 0.5, self.joint_ratio(leaf, x) / 3.0)

    def excess(self, leaf: dict, x: np.ndarray) -> np.ndarray:
        """Largest excess over a law's raw envelope, in max(span, pooled scale) units."""
        mean, scale = np.asarray(leaf["x_mean"]), np.asarray(leaf["x_scale"])
        lo = np.asarray(leaf["z_lo"]) * scale + mean
        hi = np.asarray(leaf["z_hi"]) * scale + mean
        pooled_scale = np.asarray(self.pooled["x_scale"]) if "x_scale" in self.pooled else scale
        unit = np.maximum(hi - lo, pooled_scale)
        excess = np.maximum(lo - x, x - hi) / np.where(unit > 0, unit, np.inf)
        return np.maximum(excess.max(axis=1), 0.0)

    def law(self, leaf: dict, x: np.ndarray) -> Tuple[np.ndarray, Optional[np.ndarray], np.ndarray]:
        t = len(self.targets)
        phi, clamped, outside = self.prediction_basis(leaf, x)
        beta = np.asarray(leaf["beta"]).reshape(-1, t)
        s = phi @ beta
        y_mean, y_scale = np.asarray(leaf["y_mean"]), np.asarray(leaf["y_scale"])
        n = None
        if "residual_network" in leaf:
            bound = 3.0 * np.asarray(leaf["residual_std"]) / y_scale
            n = s + np.clip(mlp_forward(leaf["residual_network"], clamped), -bound, bound)
        if "y_lo" in leaf:
            y_lo, y_hi = np.asarray(leaf["y_lo"]), np.asarray(leaf["y_hi"])
            span = y_hi - y_lo
            s = np.clip(s, y_lo - span, y_hi + span)
            if n is not None:
                n = np.clip(n, y_lo - span, y_hi + span)
        ridge = s * y_scale + y_mean
        network = n * y_scale + y_mean if n is not None else None
        return ridge, network, outside

    def predict(self, x: np.ndarray) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
        x = np.asarray(x, dtype=np.float64)
        t = len(self.targets)
        out = np.full((len(x), t), np.nan)
        domains = self.route(x)
        outside_all = np.zeros(len(x), dtype=bool)
        pooled = None
        pooled_outside = np.ones(len(x), dtype=bool)
        if self.pooled.get("fitted"):
            pooled, _, pooled_outside = self.law(self.pooled, x)
        for leaf_id in np.unique(domains):
            rows = np.flatnonzero(domains == leaf_id)
            leaf = self.leaves[int(leaf_id)]
            if not leaf.get("fitted"):
                outside_all[rows] = True
                if pooled is not None:
                    out[rows] = pooled[rows]
                continue
            ridge, network, outside = self.law(leaf, x[rows])
            outside_all[rows] = outside
            choice = leaf.get("choice", [0, 2])
            # Far outside the envelope the pooled law takes over when it is less far out.
            own = self.remoteness(leaf, x[rows])
            far = outside & (own > 1.0) & (self.remoteness(self.pooled, x[rows]) < own) if pooled is not None \
                else np.zeros(len(rows), dtype=bool)
            for local, row in enumerate(rows):
                c = choice[1 if outside[local] else 0]
                if far[local]:
                    c = 2
                if c == 1 and network is not None:
                    out[row] = network[local]
                elif c == 2 and pooled is not None:
                    out[row] = pooled[row]
                else:
                    out[row] = ridge[local]
        return out, domains, outside_all


def mlp_forward(params: list, z: np.ndarray) -> np.ndarray:
    tensors = [np.asarray(p["values"]).reshape(p["shape"]) for p in params]
    w1, b1, w2, b2, w3, b3 = tensors
    h = np.tanh(z @ w1.T + b1)
    h = np.tanh(h @ w2.T + b2)
    return h @ w3.T + b3


def replay(state: dict, samples: List[dict]) -> dict:
    """Compare emitted engine samples with the NumPy twin."""
    learner = Learner(state)
    worst = 0.0
    domain_mismatch = 0
    rows = 0
    for sample in samples:
        x = np.stack([np.asarray(sample["features"][f], dtype=np.float64) for f in learner.features], axis=1)
        predicted, domains, _ = learner.predict(x)
        engine = np.stack([np.asarray(sample["predictions"][t], dtype=np.float64) for t in learner.targets], axis=1)
        domain_mismatch += int(np.sum(domains != np.asarray(sample["domains"])))
        scale = np.maximum(np.abs(engine), 1.0)
        finite = np.isfinite(engine)
        if finite.any():
            worst = max(worst, float(np.max(np.abs(predicted - engine)[finite] / scale[finite])))
        rows += len(x)
    return {"rows": rows, "domain_mismatches": domain_mismatch, "max_relative_difference": worst}


# ---------------------------------------------------------------- specialists

def specialize(state: dict, width: int, epochs: int, seed: int, min_rows: int,
               holdout_fraction: float = 0.2, margin: float = 0.9,
               exact_law: float = 1e-6) -> Tuple[dict, List[dict]]:
    """Train residual networks offline on the learner's buffered rows."""
    import torch

    torch.manual_seed(seed)
    torch.set_default_dtype(torch.float64)
    learner = Learner(state)
    t = len(learner.targets)
    d = len(learner.features)
    out = json.loads(json.dumps(state))
    report = []
    for leaf in out["leaves"]:
        rows = leaf.get("rows")
        entry = {"domain": leaf["id"], "rows": 0, "accepted": False}
        if not leaf.get("fitted") or not rows or len(rows["call"]) < min_rows:
            entry["reason"] = "too_few_rows"
            report.append(entry)
            continue
        x = np.asarray(rows["x"], dtype=np.float64).reshape(-1, d)
        y = np.asarray(rows["y"], dtype=np.float64).reshape(-1, t)
        calls = np.asarray(rows["call"])
        cut = np.quantile(calls, 1.0 - holdout_fraction)
        train, test = calls < cut, calls >= cut
        entry["rows"] = int(len(x))
        if train.sum() < min_rows // 2 or test.sum() < max(8, min_rows // 8):
            entry["reason"] = "no_temporal_holdout"
            report.append(entry)
            continue
        phi, clamped, _ = learner.prediction_basis(leaf, x)
        beta = np.asarray(leaf["beta"]).reshape(-1, t)
        y_std = (y - np.asarray(leaf["y_mean"])) / np.asarray(leaf["y_scale"])
        residual = y_std - phi @ beta
        zt = torch.tensor(clamped)
        rt = torch.tensor(residual)
        net = torch.nn.Sequential(torch.nn.Linear(d, width), torch.nn.Tanh(), torch.nn.Linear(width, width),
                                  torch.nn.Tanh(), torch.nn.Linear(width, t))
        torch.nn.init.zeros_(net[4].weight)
        torch.nn.init.zeros_(net[4].bias)
        optimizer = torch.optim.Adam(net.parameters(), lr=3e-3)
        tr = torch.tensor(train)
        for _ in range(epochs):
            optimizer.zero_grad()
            loss = ((net(zt[tr]) - rt[tr]) ** 2).mean()
            loss.backward()
            optimizer.step()
        with torch.no_grad():
            te = torch.tensor(test)
            ridge_mse = float((rt[te] ** 2).mean())
            net_mse = float(((net(zt[te]) - rt[te]) ** 2).mean())
        entry.update({"train_rows": int(train.sum()), "holdout_rows": int(test.sum()),
                      "ridge_holdout_mse": ridge_mse, "network_holdout_mse": net_mse,
                      "width": width, "epochs": epochs})
        # Material gains only: a law already exact to 1e-6 of the target variance
        # (the engine's exact_law floor) has nothing a network can add.
        if ridge_mse <= exact_law:
            entry["reason"] = "law_exact"
            report.append(entry)
            continue
        if net_mse < margin * ridge_mse:
            params = [net[0].weight, net[0].bias, net[2].weight, net[2].bias, net[4].weight, net[4].bias]
            leaf["residual_network"] = [{"shape": list(p.shape), "values": p.detach().reshape(-1).tolist()}
                                        for p in params]
            choice = leaf.get("choice", [0, 2])
            leaf["choice"] = [1, choice[1]]
            leaf["model"] = "ridge+mlp (offline specialist)"
            leaf["offline_specialist"] = {k: entry[k] for k in ("train_rows", "holdout_rows", "ridge_holdout_mse",
                                                                 "network_holdout_mse", "width", "epochs")}
            entry["accepted"] = True
        else:
            entry["reason"] = "no_holdout_gain"
        report.append(entry)
    out["capacity"]["residual_hidden"] = max(int(out["capacity"].get("residual_hidden", 0)), width)
    return out, report


# ---------------------------------------------------------------- CLI

def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    b = sub.add_parser("budget")
    b.add_argument("--binary", type=Path, default=Path("build/dev/trech"))
    b.add_argument("--features", type=int, default=4)
    b.add_argument("--targets", type=int, default=2)
    e = sub.add_parser("extract")
    e.add_argument("--runs", type=Path, nargs="+", required=True, help="training runs in order; the last holds the state")
    e.add_argument("--learner", required=True)
    e.add_argument("--out", type=Path, required=True)
    e.add_argument("--keep-rows", action="store_true")
    r = sub.add_parser("replay")
    r.add_argument("--state", type=Path, required=True)
    r.add_argument("--run", type=Path, required=True)
    r.add_argument("--learner", required=True)
    s = sub.add_parser("specialize")
    s.add_argument("--state", type=Path, required=True, help="state with buffered rows (extract --keep-rows)")
    s.add_argument("--out", type=Path, required=True)
    s.add_argument("--binary", type=Path, default=Path("build/dev/trech"))
    s.add_argument("--width", default="auto")
    s.add_argument("--epochs", default="auto")
    s.add_argument("--seed", type=int, default=20261118)
    s.add_argument("--min-rows", type=int, default=128)
    args = parser.parse_args(argv)

    if args.command == "budget":
        print(json.dumps(engine_budget(args.binary, args.features, args.targets), indent=2))
    elif args.command == "extract":
        state = extract(args.runs, args.learner, args.out, args.keep_rows)
        print(json.dumps({"out": str(args.out), "domains": len(state["leaves"]), "calls": state["calls"]}))
    elif args.command == "replay":
        state = json.loads(args.state.read_text())
        samples = [p["samples"] for p in iter_emits(args.run, "domain_learning")
                   if p.get("learner") == args.learner and p.get("samples")]
        print(json.dumps(replay(state, samples), indent=2))
    else:
        state = json.loads(args.state.read_text())
        budget = engine_budget(args.binary, len(state["features"]), len(state["targets"]))
        width = budget["capacity"]["specialist_width"] if args.width == "auto" else int(args.width)
        epochs = budget["capacity"]["specialist_epochs"] if args.epochs == "auto" else int(args.epochs)
        out, report = specialize(state, width, epochs, args.seed, args.min_rows)
        out = strip_rows(out)
        out.setdefault("provenance", {})["specialists"] = {"budget": budget["budget"], "width": width,
                                                            "epochs": epochs, "seed": args.seed, "domains": report}
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(out, separators=(",", ":")) + "\n")
        print(json.dumps({"out": str(args.out), "accepted": sum(e["accepted"] for e in report),
                          "domains": report}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
