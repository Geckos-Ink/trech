"""Train a GENERIC TRECH surrogate: any named inputs -> any named outputs.

This is the scenario-agnostic trainer behind "Torch as a general capability in
every TRECH scenario".  Point it at Geant4 run outputs, name the input and
output columns, and it fits a small model and exports the portable
`generic_surrogate_v1` JSON that the C++ `GenericSurrogate` loads and any hook
calls via `ctx.predict` — no engine changes per prediction.

Columns come from the shared tabular harvester (`trech_torch.dataset`), so the
same tool serves optics (`--source scores`), event/stratify data
(`--source event_features`), and arbitrary scenario observables emitted as hook
payloads (`--source hook_emits --tag <tag>`), present or future.

Model
-----

Input-standardised feed-forward net.  With torch available and `--hidden > 0`
it is an MLP (SiLU hidden layers); otherwise (or `--linear`) a numpy
least-squares linear model.  Inputs and outputs are standardised and the
scalers are BAKED into the exported JSON (`input_mean/std`, `output_mean/std`),
so the engine feeds raw values and reads natural units.  Deterministic under
`--seed`.

Exports
-------

- `--out-json` (default `surrogate.json`): the portable `generic_surrogate_v1`
  model (LibTorch-free; the deployable artefact for `models[]` + `ctx.predict`).
  Carries a per-stage **trust profile** the engine surfaces: `input_domain` (the
  trained per-feature hull → out-of-domain / extrapolation flag, an `occupancy`
  histogram → in-hull starved-region flag, and a `joint` covering set → the
  multivariate starved-region flag no per-feature check can raise),
  `trained_scale_bands` (the harvester's dimension bands → off-band flag), and
  `holdout` (`r2_min`/`n` → grade-the-gap accuracy, plus the per-output `r2`/
  `mae`/`rmse` split, where `rmse` is a measured 1-sigma residual the engine
  hands back with the prediction).
- `--out` (optional `.pt`): a TorchScript twin built from the same weights when
  torch is available.
- `--manifest`: columns, source, model size (parameters + bytes), and held-out
  metrics (per-output MAE / RMSE / R2 vs the mean-predictor baseline).

For correlated per-element data, pass independent operating-point runs through
`--validation-runs`. They are excluded from fitting and replace the random row
split, so thousands of neighbouring parcels from one run cannot leak across
the train/holdout boundary and inflate the carried accuracy.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Union

import numpy as np

from .dataset import harvest_table


def _split_cols(spec: str) -> List[str]:
    return [c.strip() for c in spec.split(",") if c.strip()]


def _portable_path(path: Union[str, Path]) -> str:
    """Prefer a cwd-relative provenance path without hiding external inputs."""
    resolved = Path(path).expanduser().resolve()
    try:
        return str(resolved.relative_to(Path.cwd().resolve()))
    except ValueError:
        return str(resolved)


def build_xy(rows: List[Dict[str, float]], inputs: List[str],
             outputs: List[str]) -> Tuple[np.ndarray, np.ndarray, int]:
    """Rows -> (X, Y) keeping only rows that carry every named column."""
    xs: List[List[float]] = []
    ys: List[List[float]] = []
    dropped = 0
    for row in rows:
        if all(c in row for c in inputs) and all(c in row for c in outputs):
            xs.append([row[c] for c in inputs])
            ys.append([row[c] for c in outputs])
        else:
            dropped += 1
    if not xs:
        raise SystemExit(
            "no rows carry all requested columns.\n"
            f"  inputs:  {inputs}\n  outputs: {outputs}\n"
            "Check --source/--tag and the available columns "
            "(run with --list-columns).")
    return np.array(xs, dtype=float), np.array(ys, dtype=float), dropped


def _standardize(a: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
    mean = a.mean(axis=0)
    std = a.std(axis=0)
    std[std < 1e-9] = 1.0
    return mean, std


def fit_linear(x: np.ndarray, y: np.ndarray, l2: float,
               ) -> Tuple[np.ndarray, np.ndarray]:
    """Ridge least squares on standardised x -> standardised y.

    Returns (W, b) with W shape [n_out, n_in] and b shape [n_out] operating on
    STANDARDISED inputs and producing STANDARDISED outputs (the scalers are
    applied around this by the exported model).
    """
    xmean, xstd = _standardize(x)
    ymean, ystd = _standardize(y)
    xs = (x - xmean) / xstd
    ys = (y - ymean) / ystd
    n_in = xs.shape[1]
    a = xs.T @ xs + l2 * np.eye(n_in)
    w = np.linalg.solve(a, xs.T @ ys)  # [n_in, n_out]
    return w.T, np.zeros(y.shape[1]), (xmean, xstd, ymean, ystd)


def fit_mlp(x: np.ndarray, y: np.ndarray, hidden: int, epochs: int,
            lr: float, seed: int):
    import torch

    torch.manual_seed(seed)
    xmean, xstd = _standardize(x)
    ymean, ystd = _standardize(y)
    xs = torch.tensor((x - xmean) / xstd, dtype=torch.float32)
    ys = torch.tensor((y - ymean) / ystd, dtype=torch.float32)
    n_in, n_out = x.shape[1], y.shape[1]
    layers = [torch.nn.Linear(n_in, hidden), torch.nn.SiLU(),
              torch.nn.Linear(hidden, hidden), torch.nn.SiLU(),
              torch.nn.Linear(hidden, n_out)]
    net = torch.nn.Sequential(*layers)
    optim = torch.optim.Adam(net.parameters(), lr=lr)
    loss_fn = torch.nn.MSELoss()
    for epoch in range(epochs):
        optim.zero_grad()
        loss = loss_fn(net(xs), ys)
        loss.backward()
        optim.step()
        if (epoch + 1) % max(1, epochs // 10) == 0:
            print(f"  epoch {epoch + 1}/{epochs}  loss = {loss.item():.6f}")
    return net, (xmean, xstd, ymean, ystd)


def _linear_layers_json(w: np.ndarray, b: np.ndarray) -> List[dict]:
    return [{
        "weights": [[float(v) for v in row] for row in w],
        "bias": [float(v) for v in b],
        "activation": "none",
    }]


def _mlp_layers_json(net) -> List[dict]:
    import torch

    layers: List[dict] = []
    linear_mods = [m for m in net if isinstance(m, torch.nn.Linear)]
    for idx, lin in enumerate(linear_mods):
        w = lin.weight.detach().cpu().numpy()   # [out, in]
        b = lin.bias.detach().cpu().numpy()
        activation = "none" if idx == len(linear_mods) - 1 else "silu"
        layers.append({
            "weights": [[float(v) for v in row] for row in w],
            "bias": [float(v) for v in b],
            "activation": activation,
        })
    return layers


def joint_reference(z_train: np.ndarray, centers: int, quantile: float) -> Optional[dict]:
    """A compact JOINT picture of where the training points actually are.

    The per-feature hull + occupancy histogram answer "is each input in range,
    and is that range populated?".  They cannot answer the question that
    actually bites a multi-input surrogate: a point can sit inside every
    feature's range and still be nowhere near any training point.  Train on
    (cold, slow) and (hot, fast) and you are asked for (cold, fast) -- every
    per-feature check passes, and the model is interpolating across a hole it
    never saw.

    So the model also carries a small covering set of REAL training rows (in
    standardized units) plus the distance that covers `quantile` of the training
    set.  The engine flags a point farther than that from every center as
    jointly starved.

    Selection is deterministic farthest-point (k-center) sampling seeded from
    the row nearest the training mean: no RNG, no k-means restarts, so the same
    training split always exports the same reference and a rebuilt model stays
    byte-comparable.
    """
    n_rows, n_feat = z_train.shape if z_train.ndim == 2 else (0, 0)
    if n_rows < 2 or n_feat == 0 or centers < 1:
        return None
    k = int(min(centers, n_rows))

    # Seed: the row closest to the (standardized) mean -- ties broken by index.
    mean = z_train.mean(axis=0)
    first = int(np.argmin(((z_train - mean) ** 2).sum(axis=1)))
    chosen = [first]
    # Distance of every row to the nearest chosen center, updated incrementally.
    nearest = ((z_train - z_train[first]) ** 2).sum(axis=1)
    for _ in range(1, k):
        pick = int(np.argmax(nearest))
        if nearest[pick] <= 0.0:
            break  # every row is already a center (or a duplicate of one)
        chosen.append(pick)
        nearest = np.minimum(nearest, ((z_train - z_train[pick]) ** 2).sum(axis=1))

    radius = float(np.sqrt(np.quantile(nearest, min(max(quantile, 0.0), 1.0))))
    if not math.isfinite(radius):
        return None
    return {
        "metric": "euclidean_standardized",
        "centers": [[float(v) for v in z_train[i]] for i in chosen],
        # Distance covering `quantile` of the training rows; a point farther than
        # this from every center is in a region training never populated.
        "radius": radius,
        "quantile": float(quantile),
        "max_train_distance": float(np.sqrt(nearest.max())),
    }


def input_domain(x_train: np.ndarray, scalers, occupancy_bins: int = 8,
                 joint_centers: int = 24, joint_quantile: float = 0.99) -> dict:
    """The trained input hull + interior density, for the engine's coverage check.

    `standardized_radius[i]` is the largest |(x_i - mean_i)/std_i| the model saw
    in training: the per-feature edge of the trained region in standardized
    units.  The C++ `GenericSurrogate` flags an input out-of-domain when its
    standardized deviation exceeds this radius, so a prediction on inputs the
    model never saw is surfaced as low-confidence instead of a silent guess.

    `occupancy` is a per-feature histogram of the training values over
    [input_min, input_max] (default 8 bins): the engine flags an input that is
    in-range but lands in an empty bin as *starved* -- a hole the model
    interpolated through (density inside the hull, not just its edge, the
    planner's starved-region signal).  Raw min/max are kept for humans + the bin
    mapping.

    `joint` is the multivariate version of that density check (see
    joint_reference): both of the above are per-feature and cannot see a point
    that is in range on every axis yet far from any training point.
    """
    xmean, xstd, _ymean, _ystd = scalers
    n_feat = x_train.shape[1] if x_train.ndim == 2 else 0
    if not len(x_train):
        return {"standardized_radius": [], "input_min": [], "input_max": [],
                "n_train_rows": 0}
    z_signed = (x_train - xmean) / xstd
    z = np.abs(z_signed)
    radius = z.max(axis=0)
    xmin = x_train.min(axis=0)
    xmax = x_train.max(axis=0)
    counts = []
    for i in range(n_feat):
        lo, hi = float(xmin[i]), float(xmax[i])
        if hi > lo:
            hist, _ = np.histogram(x_train[:, i], bins=occupancy_bins,
                                   range=(lo, hi))
            counts.append([int(c) for c in hist])
        else:  # constant feature: all mass in one bin
            counts.append([int(len(x_train))] + [0] * (occupancy_bins - 1))
    domain = {
        "standardized_radius": [float(v) for v in radius],
        "input_min": [float(v) for v in xmin],
        "input_max": [float(v) for v in xmax],
        "n_train_rows": int(len(x_train)),
        "occupancy": {"bins": int(occupancy_bins), "counts": counts},
    }
    joint = joint_reference(z_signed, joint_centers, joint_quantile)
    if joint is not None:
        domain["joint"] = joint
    return domain


def holdout_block(metrics: dict, n_holdout: int) -> dict:
    """Held-out accuracy carried WITH the model (grade-the-gap).

    `r2_min` is the worst output's held-out R^2 -- the single honest "how much
    should I trust this stage" number the engine surfaces per cascade stage. The
    engine treats the whole block as absent unless `r2_min` is present, so a
    model with no holdout never reports a fake 0 == perfect.

    `rmse` is the per-output held-out root-mean-square residual, in that
    output's own units: a MEASURED 1-sigma uncertainty the engine hands back
    with the prediction (`__accuracy` / `outputAccuracy`), so a scenario reports
    the model's real error instead of typing a sigma of its own.
    """
    r2s = [m.get("r2", 0.0) for m in metrics.values()]
    return {
        "r2_min": float(min(r2s)) if r2s else 0.0,
        "n": int(n_holdout),
        "r2": {name: float(m.get("r2", 0.0)) for name, m in metrics.items()},
        "mae": {name: float(m.get("mae", 0.0)) for name, m in metrics.items()},
        "rmse": {name: float(m.get("rmse", 0.0)) for name, m in metrics.items()},
    }


def write_generic_json(path: Path, inputs: List[str], outputs: List[str],
                       scalers, layers: List[dict], meta: dict,
                       domain: Optional[dict] = None,
                       scale_bands: Optional[List[str]] = None,
                       holdout: Optional[dict] = None,
                       note: Optional[dict] = None) -> None:
    xmean, xstd, ymean, ystd = scalers
    model = {
        "model": "generic_surrogate_v1",
        "input_features": list(inputs),
        "output_features": list(outputs),
        "input_mean": [float(v) for v in xmean],
        "input_std": [float(v) for v in xstd],
        "output_mean": [float(v) for v in ymean],
        "output_std": [float(v) for v in ystd],
        "layers": layers,
        "trained_from": meta,
    }
    if domain is not None:
        model["input_domain"] = domain
    if scale_bands:
        # Dimension-scale band(s) the training data came from, so the engine can
        # flag a stage applied off the band it learned (harvester band tags).
        model["trained_scale_bands"] = list(scale_bands)
    if holdout is not None:
        model["holdout"] = holdout
    if note:
        # Free-form audit metadata. The engine deliberately does not interpret
        # this block; it travels with the deployable artefact so a distilled
        # operator cannot be mistaken for a model trained from measurements.
        model["note"] = note
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(model, indent=2) + "\n", encoding="utf-8")


def export_torchscript(net, scalers, out_path: Path) -> bool:
    try:
        import torch
    except ImportError:
        return False
    xmean, xstd, ymean, ystd = scalers

    class Wrapped(torch.nn.Module):
        def __init__(self, inner):
            super().__init__()
            self.inner = inner
            self.xmean = torch.nn.Parameter(
                torch.tensor(xmean, dtype=torch.float32), requires_grad=False)
            self.xstd = torch.nn.Parameter(
                torch.tensor(xstd, dtype=torch.float32), requires_grad=False)
            self.ymean = torch.nn.Parameter(
                torch.tensor(ymean, dtype=torch.float32), requires_grad=False)
            self.ystd = torch.nn.Parameter(
                torch.tensor(ystd, dtype=torch.float32), requires_grad=False)

        def forward(self, x):
            xs = (x - self.xmean) / self.xstd
            return self.inner(xs) * self.ystd + self.ymean

    wrapped = Wrapped(net)
    wrapped.eval()
    scripted = torch.jit.script(wrapped)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    scripted.save(str(out_path))
    return True


def predict_np(x: np.ndarray, layers: List[dict], scalers) -> np.ndarray:
    """Evaluate the exported model in numpy (parity check with the C++ side)."""
    xmean, xstd, ymean, ystd = scalers
    a = (x - xmean) / xstd
    for layer in layers:
        w = np.array(layer["weights"])
        b = np.array(layer["bias"])
        a = a @ w.T + b
        act = layer["activation"]
        if act == "silu":
            a = a / (1.0 + np.exp(-a))
        elif act == "relu":
            a = np.maximum(a, 0.0)
        elif act == "tanh":
            a = np.tanh(a)
        elif act == "sigmoid":
            a = 1.0 / (1.0 + np.exp(-a))
    return a * ystd + ymean


def evaluate(y_true: np.ndarray, y_pred: np.ndarray,
             outputs: List[str]) -> dict:
    metrics = {}
    for i, name in enumerate(outputs):
        t, p = y_true[:, i], y_pred[:, i]
        mae = float(np.mean(np.abs(p - t)))
        rmse = float(np.sqrt(np.mean((p - t) ** 2)))
        var = float(np.var(t))
        r2 = float(1.0 - np.mean((p - t) ** 2) / var) if var > 1e-12 else 0.0
        metrics[name] = {"mae": mae, "rmse": rmse, "r2": r2}
    return metrics


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--runs", nargs="+", required=True,
                    help="run dirs (or parents) holding the source JSONL")
    ap.add_argument("--validation-runs", nargs="+", default=None,
                    help="optional independent run dirs used only for held-out "
                         "metrics; when present, every --runs row trains and "
                         "the random --holdout split is disabled")
    ap.add_argument("--source", default="scores",
                    choices=["scores", "event_features", "hook_emits"])
    ap.add_argument("--tag", default=None,
                    help="hook-emit tag to select (source=hook_emits)")
    ap.add_argument("--expand", default=None,
                    help="payload key holding a LIST of per-element samples; "
                         "yields one training row per entry (source=hook_emits). "
                         "This is the per-element OPERATOR harvest: one bounded "
                         "emit per step carries many parcel/cell samples.")
    ap.add_argument("--inputs", default=None, help="comma-separated input columns")
    ap.add_argument("--outputs", default=None, help="comma-separated output columns")
    ap.add_argument("--list-columns", action="store_true",
                    help="print the numeric columns available and exit")
    ap.add_argument("--out-json", default="surrogate.json")
    ap.add_argument("--out", default=None, help="optional TorchScript .pt")
    ap.add_argument("--manifest", default="surrogate.manifest.json")
    ap.add_argument("--hidden", type=int, default=16,
                    help="hidden width (0 or --linear -> linear model)")
    ap.add_argument("--linear", action="store_true",
                    help="force a linear model (numpy, no torch needed)")
    ap.add_argument("--epochs", type=int, default=400)
    ap.add_argument("--lr", type=float, default=1e-2)
    ap.add_argument("--l2", type=float, default=1e-3)
    ap.add_argument("--seed", type=int, default=1234)
    ap.add_argument("--holdout", type=float, default=0.25)
    ap.add_argument("--note", default=None,
                    help="human-readable model-purpose/provenance note")
    ap.add_argument("--teacher", default=None,
                    help="teacher or measurement source distilled by this model")
    ap.add_argument("--measured", choices=["true", "false"], default=None,
                    help="whether the targets are direct measurements; carried "
                         "in the model note for inference honesty")
    args = ap.parse_args(argv)

    rows, metas = harvest_table(args.runs, source=args.source, tag=args.tag,
                                expand=args.expand)
    for m in metas:
        for note in m.notes:
            print(f"  note: {m.run_dir}: {note}", file=sys.stderr)
    if not rows:
        print("error: no rows harvested; check --runs/--source/--tag",
              file=sys.stderr)
        return 2

    available = sorted({k for r in rows for k in r})
    if args.list_columns or not args.inputs or not args.outputs:
        print(f"{len(rows)} rows from source={args.source}"
              + (f" tag={args.tag}" if args.tag else ""))
        print("available numeric columns:")
        for c in available:
            print(f"  {c}")
        if args.list_columns:
            return 0
        print("error: pass --inputs and --outputs (see columns above)",
              file=sys.stderr)
        return 2

    inputs = _split_cols(args.inputs)
    outputs = _split_cols(args.outputs)
    x, y, dropped = build_xy(rows, inputs, outputs)
    print(f"training rows {len(x)} (dropped {dropped} missing columns); "
          f"{len(inputs)} inputs -> {len(outputs)} outputs")
    if len(x) < 2:
        print("error: fewer than two complete training rows", file=sys.stderr)
        return 2

    validation_metas = []
    if args.validation_runs:
        validation_rows, validation_metas = harvest_table(
            args.validation_runs, source=args.source, tag=args.tag,
            expand=args.expand)
        for m in validation_metas:
            for note in m.notes:
                print(f"  validation note: {m.run_dir}: {note}",
                      file=sys.stderr)
        x_train, y_train = x, y
        x_hold, y_hold, validation_dropped = build_xy(
            validation_rows, inputs, outputs)
        print(f"independent holdout rows {len(x_hold)} "
              f"(dropped {validation_dropped} missing columns) from "
              f"{len(validation_metas)} run(s)")
        if len(x_hold) < 2:
            print("error: fewer than two complete independent holdout rows",
                  file=sys.stderr)
            return 2
    else:
        rng = np.random.default_rng(args.seed)
        order = rng.permutation(len(x))
        n_hold = int(len(x) * max(0.0, min(0.5, args.holdout)))
        hold_idx = order[:n_hold]
        train_idx = order[n_hold:] if n_hold > 0 else order
        if len(train_idx) < 2:
            train_idx = order
            hold_idx = order
        x_train, y_train = x[train_idx], y[train_idx]
        x_hold, y_hold = x[hold_idx], y[hold_idx]

    use_mlp = (not args.linear) and args.hidden > 0
    if use_mlp:
        try:
            import torch  # noqa: F401
        except ImportError:
            print("torch not available; falling back to a linear model",
                  file=sys.stderr)
            use_mlp = False

    if use_mlp:
        net, scalers = fit_mlp(x_train, y_train, hidden=args.hidden,
                               epochs=args.epochs, lr=args.lr, seed=args.seed)
        layers = _mlp_layers_json(net)
        param_count = int(sum(p.numel() for p in net.parameters()))
        model_kind = f"mlp(hidden={args.hidden})"
    else:
        w, b, scalers = fit_linear(x_train, y_train, l2=args.l2)
        layers = _linear_layers_json(w, b)
        net = None
        param_count = int(w.size + b.size)
        model_kind = "linear"

    # Held-out metrics evaluated through the EXPORTED numpy path (so they match
    # what the C++ GenericSurrogate will compute).
    y_hold_pred = predict_np(x_hold, layers, scalers)
    metrics = evaluate(y_hold, y_hold_pred, outputs)
    for name, m in metrics.items():
        print(f"  holdout {name}: MAE={m['mae']:.4g} RMSE={m['rmse']:.4g} "
              f"R2={m['r2']:.3f}")

    json_path = Path(args.out_json).expanduser().resolve()
    trained_from = {
        "runs": [_portable_path(m.run_dir) for m in metas],
        "validation_runs": [_portable_path(m.run_dir)
                            for m in validation_metas],
        "source": args.source,
        "tag": args.tag,
        "model_kind": model_kind,
        "seed": args.seed,
    }
    # The trained input hull, so the engine can flag out-of-domain predictions.
    domain = input_domain(x_train, scalers)
    # Dimension-scale band(s) the harvester tagged the training runs with, so the
    # engine can flag a stage applied off the band it learned.
    scale_bands = sorted({m.dimension_scale for m in metas
                          if m.dimension_scale not in ("", "unknown")})
    # Held-out accuracy travels with the model (grade-the-gap per cascade stage).
    holdout = holdout_block(metrics, len(x_hold))
    note = {}
    if args.note:
        note["description"] = args.note
    if args.teacher:
        note["teacher"] = args.teacher
    if args.measured is not None:
        note["measured"] = args.measured == "true"
    write_generic_json(json_path, inputs, outputs, scalers, layers, trained_from,
                       domain=domain, scale_bands=scale_bands, holdout=holdout,
                       note=note)
    print(f"wrote {json_path}")

    pt_written = False
    if args.out and net is not None:
        pt_written = export_torchscript(net, scalers, Path(args.out).expanduser())
        if pt_written:
            print(f"wrote {Path(args.out).expanduser().resolve()}")

    manifest = {
        "schema": "trech_generic_surrogate_manifest_v1",
        "model": "generic_surrogate_v1",
        "model_json": _portable_path(json_path),
        "model_torchscript": (_portable_path(args.out)
                              if (args.out and pt_written) else None),
        "inputs": inputs,
        "outputs": outputs,
        "source": args.source,
        "tag": args.tag,
        "expand": args.expand,
        "n_rows": int(len(x)),
        "model_size": {
            "parameter_count": param_count,
            "model_file_bytes": json_path.stat().st_size,
            "kind": model_kind,
        },
        "training": {"seed": args.seed,
                     "split": ("independent_runs"
                               if validation_metas else "random_rows"),
                     "holdout": (None if validation_metas else args.holdout),
                     "training_runs": [_portable_path(m.run_dir)
                                       for m in metas],
                     "validation_runs": [_portable_path(m.run_dir)
                                         for m in validation_metas],
                     "epochs": args.epochs, "lr": args.lr, "l2": args.l2},
        "metrics_holdout": metrics,
        "input_domain": domain,
        "note": note,
    }
    manifest_path = Path(args.manifest).expanduser().resolve()
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n",
                             encoding="utf-8")
    print(f"wrote {manifest_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
