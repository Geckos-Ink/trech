#!/usr/bin/env python3
"""Fit an experimental constitutive candidate; full-run promotion gates are separate.

Targets reproduce the retained reduced-law comparison teacher, not measured or
Geant4-derived foam mechanics. Held-out row accuracy alone cannot promote it.
"""
from __future__ import annotations

import argparse
import random
import json
from pathlib import Path

from distill_discrete_scenario_operators import _make_run
from trech_torch.train_surrogate import (fit_mlp, _mlp_layers_json, predict_np, evaluate,
                                         input_domain, holdout_block, write_generic_json)

INPUTS = ["gel", "rigidity", "inverse_relative_viscosity", "stress_relaxation_per_s",
          "structural_damping_per_s", "solid_conversion"]
OUTPUTS = ["set_relax_rate_per_s", "set_drag_per_s", "set_strength_scale"]
TEACHER = "referenceApplyMechanicsCoupling in polyurethane_foam.js (reduced constitutive law)"


def reference_rows(seed: int, count: int):
    """Independent condition/state samples; constants below belong ONLY to the audit teacher."""
    rng = random.Random(seed)
    rows = []
    for i in range(count):
        gel = 0.0 if i % 19 == 0 else 1.0 if i % 19 == 1 else rng.random()
        rigidity = 0.0 if i % 13 == 0 else rng.random() ** (3 if i % 3 == 0 else 1)
        inverse = 0.0 if i % 17 == 0 else rng.random()
        relaxation = rng.uniform(2.0, 4.0)
        damping = rng.uniform(2200.0, 3800.0)
        solid = rng.uniform(0.85, 0.95)
        rows.append(dict(zip(INPUTS + OUTPUTS, [
            gel, rigidity, inverse, relaxation, damping, solid,
            relaxation * max(inverse, 1e-12),
            min(damping * (1.0 + 2000.0 * rigidity * rigidity), 4e6),
            max(0.0, min(1.0, gel / solid)),
        ])))
    # Explicit range boundaries are sampled teacher data, not an expanded runtime hull.
    for value in [0.0, 1.0]:
        for column in range(3):
            row = rows[column].copy()
            row[INPUTS[column]] = value
            row[OUTPUTS[0]] = row[INPUTS[3]] * max(row[INPUTS[2]], 1e-12)
            row[OUTPUTS[1]] = min(row[INPUTS[4]] * (1 + 2000 * row[INPUTS[1]] ** 2), 4e6)
            row[OUTPUTS[2]] = max(0.0, min(1.0, row[INPUTS[0]] / row[INPUTS[5]]))
            rows.append(row)
    return rows


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--work-root", default="build/rel/foam_mechanics_teacher")
    parser.add_argument("--model-root", default="data/polyurethane_cascade")
    parser.add_argument("--epochs", type=int, default=4200)
    args = parser.parse_args()
    import torch
    torch.set_num_threads(2)
    root = Path(args.work_root)
    _make_run(root / "train", reference_rows(20261019, 18000), "mechanics_sample", 50.0, 20261019)
    _make_run(root / "holdout", reference_rows(20271022, 6000), "mechanics_sample", 50.0, 20271022)
    target = Path(args.model_root)
    import numpy as np
    train = reference_rows(20261019, 18000)
    hold = reference_rows(20271022, 6000)
    x = np.asarray([[r[k] for k in INPUTS] for r in train])
    y = np.asarray([[r[k] for k in OUTPUTS] for r in train])
    xh = np.asarray([[r[k] for k in INPUTS] for r in hold])
    yh = np.asarray([[r[k] for k in OUTPUTS] for r in hold])
    encoded = y.copy(); encoded[:, 1] = np.log(encoded[:, 1])
    # Independent constitutive heads avoid spurious coupling between unrelated
    # material descriptors. They are fused into ONE ordinary dense named-IO
    # network at export; no branch or material knowledge enters the runtime.
    dependencies = [[2, 3], [1, 4], [0, 5]]
    widths = [16, 32, 16]
    heads, output_mean, output_std = [], [], []
    for o, (columns, width) in enumerate(zip(dependencies, widths)):
        print("Fitting", OUTPUTS[o], flush=True)
        net, scalers = fit_mlp(x[:, columns], encoded[:, o:o+1], width, args.epochs,
                              0.003, 20261019 + o, lr_final_factor=0.04)
        heads.append(_mlp_layers_json(net))
        output_mean.append(float(scalers[2][0])); output_std.append(float(scalers[3][0]))
    width = sum(widths)
    weights = [np.zeros((width, len(INPUTS))), np.zeros((width, width)), np.zeros((len(OUTPUTS), width))]
    biases = [np.zeros(width), np.zeros(width), np.zeros(len(OUTPUTS))]
    offset = 0
    for o, (head, columns, size) in enumerate(zip(heads, dependencies, widths)):
        block = slice(offset, offset + size)
        weights[0][np.ix_(range(offset, offset + size), columns)] = head[0]["weights"]
        weights[1][block, block] = head[1]["weights"]
        weights[2][o, block] = head[2]["weights"][0]
        biases[0][block] = head[0]["bias"]; biases[1][block] = head[1]["bias"]
        biases[2][o] = head[2]["bias"][0]
        offset += size
    layers = [{"weights": w.tolist(), "bias": b.tolist(), "activation": "silu" if i < 2 else "none"}
              for i, (w,b) in enumerate(zip(weights,biases))]
    scalers = (x.mean(axis=0), x.std(axis=0), np.array(output_mean), np.array(output_std))
    transforms = ["identity", "exp", "identity"]
    metrics = evaluate(yh, predict_np(xh, layers, scalers, transforms), OUTPUTS)
    print("Independent holdout:", metrics, flush=True)
    domain = input_domain(x, scalers)
    note = {"teacher": TEACHER, "measured": False,
            "promotion_status": "experimental; requires scripts/validate_foam_mechanics.sh",
            "description": "Distilled local creep/drag/strength, not Geant4 or measured foam mechanics. "
                           "Growth is kinematic bookkeeping; bond/contact laws remain comparison physics."}
    metadata = {"runs": [str(root / "train")], "validation_runs": [str(root / "holdout")],
                "seed": 20261019, "source": "validation_only_teacher",
                "architecture": "constitutive heads fused into one named-IO operator"}
    target.mkdir(parents=True, exist_ok=True)
    path = target / "meso_mechanics_operator.json"
    write_generic_json(path, INPUTS, OUTPUTS, scalers, layers, metadata, domain=domain,
                       scale_bands=["meso"], holdout=holdout_block(metrics, len(hold)),
                       note=note, output_transforms=transforms)
    manifest = {"schema": "trech_generic_surrogate_manifest_v1", "model": "generic_surrogate_v2",
                "model_json": str(path), "inputs": INPUTS, "outputs": OUTPUTS,
                "output_transforms": transforms, "metrics_units": "decoded physical output units",
                "n_rows": len(train), "holdout_rows": len(hold), "metrics_holdout": metrics,
                "input_domain": domain, "note": note, "training": dict(metadata, epochs=args.epochs,
                    lr=0.003, lr_final_factor=0.04, head_inputs=[[INPUTS[c] for c in d] for d in dependencies]),
                "model_size": {"parameter_count": sum(w.size + b.size for w,b in zip(weights,biases)),
                               "model_file_bytes": path.stat().st_size}}
    (target / "meso_mechanics_operator.manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    return 0



if __name__ == "__main__":
    raise SystemExit(main())
