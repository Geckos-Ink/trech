"""Fit a pooled response and conditional specialists for statistically separated populations.

Fit, selection and final evaluation use independent runs. The exported CPU TorchScript
module includes the training coordinates, support checks and selected component weights.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import tempfile

import numpy as np
import torch
from torch import nn

from .dataset import harvest_table
from .domain_partition import numpy_domains
from .torchscript_io import write_torchscript_io
from .train_surrogate import fit_mlp, input_domain, joint_reference, evaluate, holdout_block


class Response(nn.Module):
    def __init__(self, net, scalers):
        super().__init__()
        self.net = net.double().eval()
        for name, value in zip(("xm", "xs", "ym", "ys"), scalers):
            self.register_buffer(name, torch.tensor(value, dtype=torch.float64))

    def forward(self, x):
        return self.net((x - self.xm) / self.xs) * self.ys + self.ym


class Specialist(nn.Module):
    def __init__(self, model, x, center_count, columns, rules):
        super().__init__()
        self.model = model
        self.register_buffer("lo", torch.from_numpy(x.min(0)))
        self.register_buffer("hi", torch.from_numpy(x.max(0)))
        scale = x.std(0)
        scale[scale < 1e-12] = 1.0
        self.register_buffer("scale", torch.from_numpy(scale))
        ref = joint_reference((x - x.min(0)) / scale, center_count, 1.0)
        self.register_buffer("centers", torch.tensor(ref["centers"], dtype=torch.float64))
        self.radius = float(ref["radius"])
        self.register_buffer("columns", torch.tensor(columns, dtype=torch.long))
        self.register_buffer("normals", torch.from_numpy(np.stack([r[0] for r in rules])))
        self.register_buffer("origins", torch.from_numpy(np.stack([r[1] for r in rules])))
        self.register_buffer("thresholds", torch.tensor([r[2] for r in rules], dtype=torch.float64))
        self.register_buffer("sides", torch.tensor([r[3] for r in rules], dtype=torch.bool))
        self.enabled = False

    def covers(self, q):
        # The runtime passes float32 tensors. Compare the fitted extrema at
        # that precision, then compute standardized distances in double.
        bounded = ((q >= self.lo.float().double()) & (q <= self.hi.float().double())).all(1)
        z = (q - self.lo) / self.scale
        distance = torch.cdist(z, self.centers, compute_mode="donot_use_mm_for_euclid_dist").amin(1)
        centered = q[:, self.columns].unsqueeze(1) - self.origins
        right = (centered * self.normals).sum(-1) > self.thresholds
        return (right == self.sides).all(1) & bounded & (distance <= self.radius + 1e-6)


class DomainResponse(nn.Module):
    def __init__(self, pooled, experts):
        super().__init__()
        self.pooled = pooled
        self.experts = nn.ModuleList(experts)

    @torch.jit.export
    def route(self, x):
        x = x.double()
        selected = torch.full((x.size(0),), -1, dtype=torch.long, device=x.device)
        count = torch.zeros_like(selected)
        for i, expert in enumerate(self.experts):
            covered = expert.covers(x)
            count += covered.long()
            if expert.enabled:
                selected = torch.where(covered, i, selected)
        return torch.where(count == 1, selected, -1)

    def forward(self, x):
        x = x.double()
        selected = self.route(x)
        # Dispatch only the rows assigned to each network.
        result = x.new_empty((x.size(0), self.pooled.ym.numel()))
        parent = selected < 0
        if bool(parent.any()):
            result[parent] = self.pooled(x[parent])
        for i, expert in enumerate(self.experts):
            mask = selected == i
            if bool(mask.any()):
                result[mask] = expert.model(x[mask])
        return result.float()


def train_model(x, y, width, epochs, seed):
    net, scalers = fit_mlp(x, y, hidden=width, epochs=epochs, lr=.01, seed=seed,
                           depth=1, lr_final_factor=.1, quiet=True)
    return Response(net, scalers), scalers


def train(fitting, selection, columns, width, epochs, seed, min_elements):
    x, y, runs = fitting
    sx, sy, sruns = selection
    # Gather groups in a fixed feature order for parity with ctx.detectDomains.
    rules = []
    groups, labels = numpy_domains(x[:, columns], [""] * len(x), minimum=min_elements, leaf_rules=rules)
    parent, scalers = train_model(x, y, width, epochs, seed)
    xm, xs, ym, ys = scalers
    # Fit the simple baseline in the same coordinates, including collinear inputs.
    coeff = np.linalg.lstsq((x - xm) / xs, (y - ym) / ys, rcond=None)[0]
    affine = nn.Linear(x.shape[1], y.shape[1], bias=False).double()
    with torch.no_grad():
        affine.weight.copy_(torch.from_numpy(coeff.T))
    linear = Response(affine, scalers)
    with torch.no_grad():
        query = torch.from_numpy(sx).float().double()
        target = torch.from_numpy(sy)
        if all(bool(((linear(query[mask]) - target[mask]).square().mean(0) <=
                     (parent(query[mask]) - target[mask]).square().mean(0)).all())
               for mask in (sruns == run for run in np.unique(sruns))):
            parent = linear
    experts, details = [], []
    for i, group in enumerate(groups):
        mask = labels == i
        support = len(np.unique(runs[mask]))
        if len(groups) == 1 or support < 2:
            details.append({"path": group["path"], "fit_runs": support, "fit_rows": int(mask.sum()),
                            "decision": "single_population" if len(groups) == 1 else "single_run"})
            continue
        model, _ = train_model(x[mask], y[mask], max(2, width // len(groups)), epochs, seed)
        experts.append(Specialist(model, x[mask], 24, columns, rules[i]))
        details.append({"path": group["path"], "fit_runs": support, "fit_rows": int(mask.sum()),
                        "expert_index": len(experts) - 1})
    module = DomainResponse(parent, experts)
    with torch.no_grad():
        query = torch.from_numpy(sx).float().double()
        truth = torch.from_numpy(sy)
        base = parent(query)
        simple = linear(query)
        covers = [expert.covers(query) for expert in experts]
        eligible = torch.stack(covers).sum(0) == 1 if covers else None
        for detail in details:
            if "expert_index" not in detail:
                continue
            i = detail["expert_index"]
            mask = covers[i] & eligible
            expert = experts[i]
            selected_runs = np.unique(sruns[mask.numpy()])
            losses = []
            for run in selected_runs:
                rows = mask & torch.from_numpy(sruns == run)
                candidate = (expert.model(query[rows]) - truth[rows]).square().mean(0)
                pooled = (base[rows] - truth[rows]).square().mean(0)
                affine_loss = (simple[rows] - truth[rows]).square().mean(0)
                losses.append(bool((candidate <= torch.minimum(pooled, affine_loss)).all()
                                   and (candidate < pooled).any() and (candidate < affine_loss).any()))
            expert.enabled = len(selected_runs) >= 2 and all(losses)
            detail.update(selection_runs=len(selected_runs), selection_rows=int(mask.sum()),
                          decision="specialist" if expert.enabled else "pooled")
    return module.eval(), scalers, details


def read_runs(paths, inputs, outputs, source, tag, expand, seen):
    data, ids = [], []
    for i, run in enumerate(paths):
        rows, metas = harvest_table([str(run)], source=source, tag=tag, expand=expand)
        if len(metas) != 1 or not rows:
            raise ValueError(f"{run}: expected one nonempty run for {source}/{tag}")
        matrix = np.array([[row[key] for key in inputs + outputs] for row in rows], dtype=np.float64)
        if not np.isfinite(matrix).all() or (abs(matrix[:, :len(inputs)]) > np.finfo(np.float32).max).any():
            raise ValueError(f"{run}: non-finite data or inputs outside the TorchScript float32 range")
        # Hook-only controls can change the sampled data while leaving the
        # engine config hash unchanged. Check the effective rows for copies.
        ordered = matrix[np.lexsort(matrix.T[::-1])]
        identity = hashlib.sha256(ordered.astype("<f8").tobytes()).hexdigest()
        if identity in seen:
            raise ValueError(f"{run}: repeated harvested rows from {seen[identity]}; independent runs required")
        seen[identity] = str(run)
        data.append(matrix)
        ids.extend([i] * len(matrix))
    matrix = np.concatenate(data)
    return matrix[:, :len(inputs)], matrix[:, len(inputs):], np.asarray(ids)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("fit", "selection", "test"):
        parser.add_argument("--" + name, type=Path, nargs="+", required=True)
    parser.add_argument("--inputs", required=True)
    parser.add_argument("--outputs", required=True)
    parser.add_argument("--routing-features", required=True, help="comma-separated subset of inputs")
    parser.add_argument("--source", choices=["scores", "event_features", "hook_emits"], default="hook_emits")
    parser.add_argument("--tag")
    parser.add_argument("--expand")
    parser.add_argument("--scale", required=True, choices=["atomic", "nano", "micro", "meso", "macro"])
    parser.add_argument("--width", default="32",
                        help="hidden width, or 'auto' to size it from the engine's compute budget")
    parser.add_argument("--epochs", default="600",
                        help="training epochs, or 'auto' to size them from the engine's compute budget")
    parser.add_argument("--binary", type=Path, default=Path("build/dev/trech"),
                        help="engine binary probed by 'auto' (trech budget)")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--min-elements", type=int, default=16)
    parser.add_argument("--out", type=Path, required=True, help="new checkpoint directory")
    args = parser.parse_args(argv)
    # Model capacity follows the computational context of this host unless pinned.
    budget = None
    if "auto" in (args.width, args.epochs):
        from trech_torch.domain_learner import engine_budget
        budget = engine_budget(args.binary, len(args.inputs.split(",")), len(args.outputs.split(",")))
    try:
        args.width = budget["capacity"]["specialist_width"] if args.width == "auto" else int(args.width)
        args.epochs = budget["capacity"]["specialist_epochs"] if args.epochs == "auto" else int(args.epochs)
    except ValueError:
        parser.error("width and epochs must be integers or 'auto'")
    paths = args.fit + args.selection + args.test
    if len({p.resolve() for p in paths}) != len(paths):
        parser.error("use independent, non-repeated run directories for each split")
    if args.width < 2 or args.epochs < 1 or args.min_elements < 2:
        parser.error("width and min-elements must be at least two and epochs must be positive")
    inputs, outputs, routing = ([k.strip() for k in s.split(",")] for s in
                               (args.inputs, args.outputs, args.routing_features))
    if any(not all(keys) or len(keys) != len(set(keys)) for keys in (inputs, outputs, routing)):
        parser.error("feature names must be non-empty and unique within each list")
    if not set(routing) <= set(inputs) or set(inputs) & set(outputs):
        parser.error("routing features must be inputs and prediction targets must be separate")
    if args.out.exists():
        parser.error("choose a new checkpoint directory")
    seen = {}

    def load(paths):
        return read_runs(paths, inputs, outputs, args.source, args.tag, args.expand, seen)

    torch.set_num_threads(1)
    fitting = load(args.fit)
    model, scalers, details = train(fitting, load(args.selection), [inputs.index(k) for k in sorted(routing)],
                                    args.width, args.epochs, args.seed, args.min_elements)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    # Publish module, hash-bound metadata and measurements together.
    with tempfile.TemporaryDirectory(dir=args.out.parent) as tmp:
        checkpoint = Path(tmp) / "checkpoint"
        checkpoint.mkdir()
        pt = checkpoint / "response.pt"
        compiled = torch.jit.script(model)
        compiled.save(str(pt))
        test_x, test_y, test_run = load(args.test)
        per_run, predictions = [], []
        with torch.no_grad():
            for i, path in enumerate(args.test):
                mask = test_run == i
                chunks, routed_chunks = [], []
                for q in torch.from_numpy(test_x[mask]).float().split(1024):
                    chunks.append(compiled(q).numpy())
                    routed_chunks.append(compiled.route(q).numpy())
                predicted, routed = np.concatenate(chunks), np.concatenate(routed_chunks)
                predictions.append(predicted)
                truth = test_y[mask]
                pooled = model.pooled(torch.from_numpy(test_x[mask]).float().double()).float().numpy()
                scores = {}
                for index in np.unique(routed):
                    selected = routed == index
                    scores[str(index)] = {"rows": int(selected.sum()),
                                          "routed_rmse": dict(zip(outputs, np.sqrt(
                                              np.mean((truth[selected] - predicted[selected])**2, axis=0)))),
                                          "pooled_rmse": dict(zip(outputs, np.sqrt(
                                              np.mean((truth[selected] - pooled[selected])**2, axis=0))))}
                per_run.append({"run": str(path), "routing_counts": {k: v["rows"] for k, v in scores.items()},
                                "routing_metrics": scores,
                                "test_metrics": evaluate(truth, predicted, outputs),
                                "pooled_metrics": evaluate(truth, pooled, outputs)})
        metrics = evaluate(test_y, np.concatenate(predictions), outputs)
        meta = {"schema": "trech_domain_specialists_v1", "input_features": inputs, "output_features": outputs,
                "trained_scale_bands": [args.scale], "routing_features": sorted(routing), "domains": details,
                "input_mean": scalers[0].tolist(), "input_std": scalers[1].tolist(),
                "input_domain": input_domain(fitting[0], scalers), "holdout": holdout_block(metrics, len(test_y)),
                "fit_runs": list(map(str, args.fit)), "selection_runs": list(map(str, args.selection)),
                "pooled_model": "linear" if isinstance(model.pooled.net, nn.Linear) else "mlp",
                "source": args.source, "tag": args.tag, "expand": args.expand,
                "harvest_sha256": {run: digest for digest, run in seen.items()},
                "training": {"width": args.width, "epochs": args.epochs, "seed": args.seed,
                             "compute_budget": budget["budget"] if budget else None,
                             "min_elements": args.min_elements}, "tests": per_run,
                "frozen_model_sha256": hashlib.sha256(pt.read_bytes()).hexdigest()}
        manifest = checkpoint / "manifest.json"
        manifest.write_text(json.dumps(meta, indent=2, allow_nan=False) + "\n")
        write_torchscript_io(pt, manifest)
        checkpoint.rename(args.out)
    print(args.out / "manifest.json")


if __name__ == "__main__":
    main()
