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
  Carries an `input_domain` block (the trained per-feature hull) so the engine
  flags out-of-domain / extrapolating predictions as low-confidence.
- `--out` (optional `.pt`): a TorchScript twin built from the same weights when
  torch is available.
- `--manifest`: columns, source, model size (parameters + bytes), and held-out
  metrics (per-output MAE / RMSE / R2 vs the mean-predictor baseline).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np

from .dataset import harvest_table


def _split_cols(spec: str) -> List[str]:
    return [c.strip() for c in spec.split(",") if c.strip()]


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


def input_domain(x_train: np.ndarray, scalers) -> dict:
    """The trained input hull, for the engine's coverage / extrapolation check.

    `standardized_radius[i]` is the largest |(x_i - mean_i)/std_i| the model saw
    in training: the per-feature edge of the trained region in standardized
    units.  The C++ `GenericSurrogate` flags an input out-of-domain when its
    standardized deviation exceeds this radius, so a prediction on inputs the
    model never saw is surfaced as low-confidence instead of a silent guess.
    Raw min/max are kept for humans.
    """
    xmean, xstd, _ymean, _ystd = scalers
    z = np.abs((x_train - xmean) / xstd)
    radius = z.max(axis=0) if len(x_train) else np.zeros(x_train.shape[1])
    return {
        "standardized_radius": [float(v) for v in radius],
        "input_min": [float(v) for v in x_train.min(axis=0)] if len(x_train) else [],
        "input_max": [float(v) for v in x_train.max(axis=0)] if len(x_train) else [],
        "n_train_rows": int(len(x_train)),
    }


def write_generic_json(path: Path, inputs: List[str], outputs: List[str],
                       scalers, layers: List[dict], meta: dict,
                       domain: Optional[dict] = None) -> None:
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
    ap.add_argument("--source", default="scores",
                    choices=["scores", "event_features", "hook_emits"])
    ap.add_argument("--tag", default=None,
                    help="hook-emit tag to select (source=hook_emits)")
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
    args = ap.parse_args(argv)

    rows, metas = harvest_table(args.runs, source=args.source, tag=args.tag)
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

    rng = np.random.default_rng(args.seed)
    order = rng.permutation(len(x))
    n_hold = int(len(x) * max(0.0, min(0.5, args.holdout)))
    hold_idx = order[:n_hold]
    train_idx = order[n_hold:] if n_hold > 0 else order
    if len(train_idx) < 2:
        train_idx = order
        hold_idx = order

    use_mlp = (not args.linear) and args.hidden > 0
    if use_mlp:
        try:
            import torch  # noqa: F401
        except ImportError:
            print("torch not available; falling back to a linear model",
                  file=sys.stderr)
            use_mlp = False

    if use_mlp:
        net, scalers = fit_mlp(x[train_idx], y[train_idx], hidden=args.hidden,
                               epochs=args.epochs, lr=args.lr, seed=args.seed)
        layers = _mlp_layers_json(net)
        param_count = int(sum(p.numel() for p in net.parameters()))
        model_kind = f"mlp(hidden={args.hidden})"
    else:
        w, b, scalers = fit_linear(x[train_idx], y[train_idx], l2=args.l2)
        layers = _linear_layers_json(w, b)
        net = None
        param_count = int(w.size + b.size)
        model_kind = "linear"

    # Held-out metrics evaluated through the EXPORTED numpy path (so they match
    # what the C++ GenericSurrogate will compute).
    y_hold_pred = predict_np(x[hold_idx], layers, scalers)
    metrics = evaluate(y[hold_idx], y_hold_pred, outputs)
    for name, m in metrics.items():
        print(f"  holdout {name}: MAE={m['mae']:.4g} RMSE={m['rmse']:.4g} "
              f"R2={m['r2']:.3f}")

    json_path = Path(args.out_json).expanduser().resolve()
    trained_from = {
        "runs": [m.run_dir for m in metas],
        "source": args.source,
        "tag": args.tag,
        "model_kind": model_kind,
        "seed": args.seed,
    }
    # The trained input hull, so the engine can flag out-of-domain predictions.
    domain = input_domain(x[train_idx], scalers)
    write_generic_json(json_path, inputs, outputs, scalers, layers, trained_from,
                       domain=domain)
    print(f"wrote {json_path}")

    pt_written = False
    if args.out and net is not None:
        pt_written = export_torchscript(net, scalers, Path(args.out).expanduser())
        if pt_written:
            print(f"wrote {Path(args.out).expanduser().resolve()}")

    manifest = {
        "schema": "trech_generic_surrogate_manifest_v1",
        "model": "generic_surrogate_v1",
        "model_json": str(json_path),
        "model_torchscript": (str(Path(args.out).expanduser().resolve())
                              if (args.out and pt_written) else None),
        "inputs": inputs,
        "outputs": outputs,
        "source": args.source,
        "tag": args.tag,
        "n_rows": int(len(x)),
        "model_size": {
            "parameter_count": param_count,
            "model_file_bytes": json_path.stat().st_size,
            "kind": model_kind,
        },
        "training": {"seed": args.seed, "holdout": args.holdout,
                     "epochs": args.epochs, "lr": args.lr, "l2": args.l2},
        "metrics_holdout": metrics,
        "input_domain": domain,
    }
    manifest_path = Path(args.manifest).expanduser().resolve()
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n",
                             encoding="utf-8")
    print(f"wrote {manifest_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
