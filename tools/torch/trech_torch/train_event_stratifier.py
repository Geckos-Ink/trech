"""Train the event stratifier from TRECH Geant4 stratify outputs.

Dataset
-------

Consumes run directories produced by `trech run` with `stratify.enable` +
`stratify.dumpFeatures` (see `docs/output_schema.md`): each line of
`trech_event_features.jsonl` carries the ordered `trech_event_features_v1`
feature vector plus a teacher label.  The bootstrap teacher is the engine's
deterministic thresholds (`stratify.*Threshold`); once a model is deployed
its own resim-confirmed labels can retrain it (the CHARTS.md prediction
loop).  Teacher sources are recorded per run in the manifest.

Model
-----

Standardised logistic regression:

    p(exceptional) = sigmoid(bias + sum_i w_i * (x_i - mean_i) / std_i)

Fit deterministically with full-batch gradient descent in numpy (class-weighted
for rare exceptional events), so training needs no GPU and reruns are
byte-stable under a fixed `--seed` (the seed only shuffles the holdout split).
Model size: 7 weights + bias (+ 7+7 scaler stats) — small enough to audit by
eye and to run per event with zero overhead at any run scale.

Exports
-------

- `--out-json` (default `stratify_logistic.json`): the LibTorch-free logistic
  model for the C++ `TorchScriptStub` json backend — works in a stock build
  via `stratify.modelPath` + `determinism.mode: "predictive"`.
- `--out` (optional `.pt`): TorchScript module returning a `[1, 2]` tensor
  `[p(predictable), p(exceptional)]` matching the engine's tensor contract;
  built from the SAME numpy weights (bit-parity) and only written when torch
  is importable.
- `--manifest`: dataset provenance, class balance, held-out metrics
  (accuracy / precision / recall vs the majority-class baseline), and model
  size.  The promotion gate is `beats_majority_baseline`.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path
from typing import List, Optional

import numpy as np

from .dataset import (
    FEATURE_NAMES,
    FEATURE_SCHEMA_ID,
    EventSample,
    RunMetadata,
    harvest_event_dataset,
)


def fit_logistic(x: np.ndarray, y: np.ndarray, epochs: int, lr: float,
                 l2: float) -> tuple[np.ndarray, float, np.ndarray, np.ndarray]:
    """Class-weighted logistic regression on standardised features.

    Returns (weights, bias, mean, std).  Deterministic: full-batch gradient
    descent from a zero init (no RNG involved).
    """
    mean = x.mean(axis=0)
    std = x.std(axis=0)
    std[std < 1e-9] = 1.0
    xs = (x - mean) / std
    n, d = xs.shape
    # Inverse-frequency class weights so rare exceptional events still pull.
    pos = float(y.sum())
    neg = float(n - pos)
    w_pos = n / (2.0 * pos) if pos > 0 else 1.0
    w_neg = n / (2.0 * neg) if neg > 0 else 1.0
    sample_w = np.where(y > 0.5, w_pos, w_neg)
    w = np.zeros(d)
    b = 0.0
    for _ in range(epochs):
        z = xs @ w + b
        p = 1.0 / (1.0 + np.exp(-np.clip(z, -30.0, 30.0)))
        grad_z = sample_w * (p - y) / n
        grad_w = xs.T @ grad_z + l2 * w
        grad_b = float(grad_z.sum())
        w -= lr * grad_w
        b -= lr * grad_b
    return w, b, mean, std


def predict_proba(x: np.ndarray, w: np.ndarray, b: float,
                  mean: np.ndarray, std: np.ndarray) -> np.ndarray:
    xs = (x - mean) / std
    z = xs @ w + b
    return 1.0 / (1.0 + np.exp(-np.clip(z, -30.0, 30.0)))


def evaluate(y_true: np.ndarray, p: np.ndarray, threshold: float) -> dict:
    pred = (p >= threshold).astype(float)
    tp = float(((pred == 1) & (y_true == 1)).sum())
    tn = float(((pred == 0) & (y_true == 0)).sum())
    fp = float(((pred == 1) & (y_true == 0)).sum())
    fn = float(((pred == 0) & (y_true == 1)).sum())
    n = max(1.0, float(len(y_true)))
    majority = max(float(y_true.sum()), float(len(y_true) - y_true.sum())) / n
    precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
    recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
    f1 = (2 * precision * recall / (precision + recall)
          if (precision + recall) > 0 else 0.0)
    accuracy = (tp + tn) / n
    return {
        "n": int(n),
        "accuracy": accuracy,
        "majority_baseline_accuracy": majority,
        "precision_exceptional": precision,
        "recall_exceptional": recall,
        "f1_exceptional": f1,
        "confusion": {"tp": int(tp), "tn": int(tn),
                      "fp": int(fp), "fn": int(fn)},
        "beats_majority_baseline": bool(accuracy > majority),
    }


def export_logistic_json(w: np.ndarray, b: float, mean: np.ndarray,
                         std: np.ndarray, threshold: float,
                         out_path: Path) -> None:
    """Write the LibTorch-free model for the C++ TorchScriptStub json backend."""
    model = {
        "model": "logistic_stratifier_v1",
        "feature_schema": FEATURE_SCHEMA_ID,
        "feature_names": list(FEATURE_NAMES),
        "weights": [float(v) for v in w],
        "mean": [float(v) for v in mean],
        "std": [float(v) for v in std],
        "bias": float(b),
        "threshold": float(threshold),
        "note": ("event stratifier: p(exceptional) = sigmoid(bias + sum w_i * "
                 "(x_i-mean_i)/std_i). Trained from Geant4 stratify outputs by "
                 "tools/torch/trech_torch/train_event_stratifier.py; deploy via "
                 "stratify.modelPath (predictive mode only)."),
    }
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(model, indent=2) + "\n", encoding="utf-8")


def export_torchscript(w: np.ndarray, b: float, mean: np.ndarray,
                       std: np.ndarray, out_path: Path) -> bool:
    """Optional TorchScript export built from the SAME numpy weights.

    Returns False (with a warning) when torch is not importable — the json
    export remains the deployable artefact in that case.
    """
    try:
        import torch
    except ImportError:
        print("warning: torch not importable; skipping TorchScript export "
              f"({out_path})", file=sys.stderr)
        return False

    class LogisticStratifier(torch.nn.Module):
        def __init__(self) -> None:
            super().__init__()
            self.w = torch.nn.Parameter(
                torch.tensor(w, dtype=torch.float32), requires_grad=False)
            self.b = torch.nn.Parameter(
                torch.tensor([b], dtype=torch.float32), requires_grad=False)
            self.mean = torch.nn.Parameter(
                torch.tensor(mean, dtype=torch.float32), requires_grad=False)
            self.std = torch.nn.Parameter(
                torch.tensor(std, dtype=torch.float32), requires_grad=False)

        def forward(self, x: torch.Tensor) -> torch.Tensor:
            xs = (x - self.mean) / self.std
            z = xs @ self.w + self.b
            p = torch.sigmoid(z)
            return torch.stack([1.0 - p, p], dim=1)

    module = LogisticStratifier()
    module.eval()
    scripted = torch.jit.script(module)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    scripted.save(str(out_path))
    return True


def _teacher_summary(samples: List[EventSample]) -> dict:
    by_source: dict = {}
    for s in samples:
        by_source[s.source] = by_source.get(s.source, 0) + 1
    return by_source


def _scale_summary(metas: List[RunMetadata]) -> dict:
    scales: dict = {}
    for m in metas:
        scales.setdefault(m.dimension_scale, []).append(
            Path(m.run_dir).name)
    return {k: sorted(v) for k, v in sorted(scales.items())}


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--runs", nargs="+", required=True,
                        help="run dirs (or parents) holding "
                             "trech_event_features.jsonl dumps")
    parser.add_argument("--out-json", default="stratify_logistic.json",
                        help="LibTorch-free logistic model for "
                             "stratify.modelPath (stock build)")
    parser.add_argument("--out", default=None,
                        help="optional TorchScript .pt export (same weights; "
                             "needs torch installed)")
    parser.add_argument("--manifest", default="stratify_model.manifest.json")
    parser.add_argument("--seed", type=int, default=1234,
                        help="seed for the holdout split shuffle")
    parser.add_argument("--holdout", type=float, default=0.25,
                        help="held-out fraction for the promotion metrics")
    parser.add_argument("--epochs", type=int, default=500)
    parser.add_argument("--lr", type=float, default=0.1)
    parser.add_argument("--l2", type=float, default=1e-3)
    parser.add_argument("--threshold", type=float, default=0.5,
                        help="decision threshold stored in the model")
    args = parser.parse_args(argv)

    samples, metas = harvest_event_dataset(args.runs)
    run_count = sum(1 for m in metas if not m.notes)
    print(f"collected {len(samples)} labeled events from {run_count} run(s) "
          f"({len(metas)} scanned)")
    for m in metas:
        for note in m.notes:
            print(f"  note: {m.run_dir}: {note}", file=sys.stderr)
    if not samples:
        print("error: no event samples found (enable stratify.enable + "
              "stratify.dumpFeatures in the Geant4 runs)", file=sys.stderr)
        return 2

    x = np.array([s.features for s in samples], dtype=float)
    y = np.array([1.0 if s.exceptional else 0.0 for s in samples])
    pos, neg = int(y.sum()), int(len(y) - y.sum())
    print(f"class balance: {pos} exceptional / {neg} predictable")
    if pos == 0 or neg == 0:
        print("error: single-class dataset — a classifier cannot learn from "
              "this. Run more varied Geant4 experiments (beam.spread / "
              "beam.spectrum / threshold sweeps); see "
              "trech-plan-geant4-experiments for concrete suggestions.",
              file=sys.stderr)
        return 2

    # Deterministic seeded holdout split.
    rng = np.random.default_rng(args.seed)
    order = rng.permutation(len(samples))
    n_hold = int(len(samples) * max(0.0, min(0.5, args.holdout)))
    hold_idx = order[:n_hold]
    train_idx = order[n_hold:]
    holdout_ok = (n_hold >= 4 and
                  len(set(y[hold_idx])) == 2 and len(set(y[train_idx])) == 2)
    if not holdout_ok:
        print("warning: holdout split too small/degenerate; metrics are "
              "computed on the training set", file=sys.stderr)
        train_idx = np.arange(len(samples))
        hold_idx = train_idx

    w, b, mean, std = fit_logistic(x[train_idx], y[train_idx],
                                   epochs=args.epochs, lr=args.lr, l2=args.l2)
    metrics = evaluate(y[hold_idx],
                       predict_proba(x[hold_idx], w, b, mean, std),
                       args.threshold)
    print(f"holdout accuracy {metrics['accuracy']:.3f} "
          f"(majority baseline {metrics['majority_baseline_accuracy']:.3f}) "
          f"recall(exceptional) {metrics['recall_exceptional']:.3f}")

    # Refit on ALL data for the deployed model (metrics stay held-out).
    w, b, mean, std = fit_logistic(x, y, epochs=args.epochs, lr=args.lr,
                                   l2=args.l2)

    json_path = Path(args.out_json).expanduser().resolve()
    export_logistic_json(w, b, mean, std, args.threshold, json_path)
    print(f"wrote {json_path}")

    pt_written = False
    if args.out:
        pt_path = Path(args.out).expanduser().resolve()
        pt_written = export_torchscript(w, b, mean, std, pt_path)
        if pt_written:
            print(f"wrote {pt_path}")

    manifest = {
        "schema": "trech_stratify_model_v1",
        "feature_schema": FEATURE_SCHEMA_ID,
        "feature_names": list(FEATURE_NAMES),
        "model": "logistic_stratifier_v1",
        "model_json": str(json_path),
        "model_torchscript": (str(Path(args.out).expanduser().resolve())
                              if (args.out and pt_written) else None),
        "model_size": {
            "parameter_count": int(len(w) + 1),
            "scaler_value_count": int(2 * len(mean)),
            "model_file_bytes": json_path.stat().st_size,
        },
        "dataset": {
            "n_events": len(samples),
            "n_exceptional": pos,
            "n_predictable": neg,
            "teacher_label_sources": _teacher_summary(samples),
            "runs": [m.run_dir for m in metas],
            "dimension_scales": _scale_summary(metas),
        },
        "training": {
            "seed": args.seed,
            "holdout_fraction": args.holdout,
            "holdout_valid": bool(holdout_ok),
            "epochs": args.epochs,
            "lr": args.lr,
            "l2": args.l2,
            "threshold": args.threshold,
            "class_weighting": "inverse frequency",
        },
        "metrics_holdout": metrics,
        "promotion_gate": {
            "beats_majority_baseline": metrics["beats_majority_baseline"],
            "note": ("deploy via stratify.modelPath only when the held-out "
                     "metrics beat the majority baseline; the engine also "
                     "requires determinism.mode=predictive."),
        },
    }
    manifest_path = Path(args.manifest).expanduser().resolve()
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n",
                             encoding="utf-8")
    print(f"wrote {manifest_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
