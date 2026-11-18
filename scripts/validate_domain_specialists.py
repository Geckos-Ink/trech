#!/usr/bin/env python3
"""Test a frozen, data-discovered glass thermal split on whole held-out runs."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import torch

from trech_torch.dataset import harvest_table
from trech_torch.train_surrogate import (
    _linear_layers_json, _mlp_layers_json, fit_linear, fit_mlp, predict_np,
)
from validate_domain_discovery import numpy_domains

FEATURES = ["glass_silica_fraction", "melt_fraction", "temperature_k"]
INPUTS = ["temperature_k", "contact_temperature_k", "melt_onset_k"]
OUTPUT = "d_temperature_k_dt"


def load(run: Path):
    rows, _ = harvest_table([str(run)], source="hook_emits", tag="thermal_sample_glass",
                            expand="samples")
    values = np.asarray([[row[name] for name in FEATURES + INPUTS + [OUTPUT]] for row in rows])
    if not len(values) or not np.isfinite(values).all():
        raise ValueError(f"{run}: expected finite formed-glass teacher samples")
    return values[:, :3], values[:, 3:6], values[:, 6:]


def fit(x, y, width):
    net, scalers = fit_mlp(x, y, hidden=width, depth=1, epochs=600, lr=0.01,
                           lr_final_factor=0.1, seed=42, quiet=True)
    return _mlp_layers_json(net), scalers


def rms(residual):
    return float(np.sqrt(np.mean(residual ** 2)))


def evaluate(fit_runs: list[Path], holdouts: list[Path]):
    training = {run.name: load(run) for run in fit_runs}
    features, x, y = (np.concatenate(columns) for columns in zip(*training.values()))
    groups, assignment = numpy_domains(features, ["glass"] * len(features))
    # This case grades a single temperature split within the formed-glass routing parent.
    # Learn the gap from fit runs alone, then freeze its thresholds before reading holdouts.
    temperature = features[:, 2]
    if len(groups) != 2:
        raise ValueError(f"expected two candidate thermal domains, found {len(groups)}")
    lo = temperature[assignment == 0].max()
    hi = temperature[assignment == 1].min()
    cut = (lo + hi) * 0.5
    if lo >= hi or not np.array_equal(temperature > cut, assignment == 1):
        raise ValueError("the discovered split does not correspond to a temperature gap")

    torch.set_num_threads(1)
    pooled = fit(x, y, width=32)
    specialists = [fit(x[assignment == j], y[assignment == j], width=16) for j in range(2)]
    w, b, scalers = fit_linear(x, y, l2=0.0)
    linear = _linear_layers_json(w, b), scalers
    support = {
        name: np.bincount((facts[:, 2] > cut).astype(int), minlength=2).tolist()
        for name, (facts, _, _) in training.items()
    }

    comparisons = {}
    for run in holdouts:
        facts, held_x, held_y = load(run)
        upper = facts[:, 2] > cut
        pooled_prediction = predict_np(held_x, *pooled)
        routed = np.where(upper[:, None], predict_np(held_x, *specialists[1]),
                          predict_np(held_x, *specialists[0]))
        comparisons[run.name] = {
            "rows": len(held_x), "assigned_to_hotter_model": int(upper.sum()),
            "rows_in_training_gap": int(((facts[:, 2] > lo) & (facts[:, 2] < hi)).sum()),
            "rmse_k_per_s": {
                "pooled_nn": rms(pooled_prediction - held_y),
                "two_specialists": rms(routed - held_y),
                "pooled_least_squares": rms(predict_np(held_x, *linear) - held_y),
            },
        }
    return {
        "source": "formed-glass reference teacher rates from Geant4-clocked runs",
        "frozen_boundary_k": float(cut), "fit_gap_k": [float(lo), float(hi)],
        "fit_rows_by_run_and_domain": support,
        "fit_runs_per_domain": [sum(counts[domain] > 0 for counts in support.values())
                                for domain in range(2)],
        "nn_parameter_counts": {"pooled": 161, "two_specialists": 162},
        "holdout": comparisons,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fit", type=Path, nargs="+", required=True)
    parser.add_argument("--holdout", type=Path, nargs="+", required=True)
    args = parser.parse_args()
    all_runs = args.fit + args.holdout
    if (len({run.resolve() for run in all_runs}) != len(all_runs)
            or len({run.name for run in all_runs}) != len(all_runs)):
        parser.error("fit and holdout must contain distinct runs with distinct directory names")
    print(json.dumps(evaluate(args.fit, args.holdout), indent=2))


if __name__ == "__main__":
    main()
