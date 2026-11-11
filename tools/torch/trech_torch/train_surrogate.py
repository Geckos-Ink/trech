"""Train a GENERIC TRECH surrogate: any named inputs -> any named outputs.

This is the scenario-agnostic trainer behind "Torch as a general capability in
every TRECH scenario".  Point it at Geant4 run outputs, name the input and
output columns, and it fits a small model and exports the portable
`generic_surrogate_v1`/`v2` JSON that the C++ `GenericSurrogate` loads and any hook
calls via `ctx.predict` — no engine changes per prediction.

Columns come from the shared tabular harvester (`trech_torch.dataset`), so the
same tool serves optics (`--source scores`), event/stratify data
(`--source event_features`), and arbitrary scenario observables emitted as hook
payloads (`--source hook_emits --tag <tag>`), present or future.

Model
-----

Input-standardised feed-forward net.  With torch available and `--hidden > 0`
it is an MLP (SiLU hidden layers by default; `--widths 32,16,8` gives per-layer
widths and `--activation`/`--activations` choose silu/tanh/relu/sigmoid, the
activations the C++ `GenericSurrogate` evaluates); otherwise (or `--linear`) a
numpy least-squares linear model.  Inputs and outputs are standardised and the
scalers are BAKED into the exported JSON (`input_mean/std`, `output_mean/std`),
so the engine feeds raw values and reads natural units.  Deterministic under
`--seed`. Optional `--log-outputs` fits positive targets in log space;
`--logit-outputs` fits fractions strictly inside (0,1) in logit space.
Both export v2 inverse links and evaluate held-out errors in natural units.

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

Set networks: `--network deepsets|mpnn` trains a permutation-invariant model over
`--set-elements` element blocks of the inputs (plus `--set-context` trailing global
inputs) and exports `generic_surrogate_v3` (see `set_networks.py`).

Error bars: `--calibration-runs` (disjoint from training and holdout runs) set the
carried `prediction_interval` -- a split-conformal |residual| quantile at
`--interval-coverage` plus the calibration RMSE -- so an error bar is never measured
on the runs that later test it.
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
from . import set_networks


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


# Hidden activations the portable JSON format and the C++ GenericSurrogate both evaluate.
ACTIVATIONS = ("silu", "tanh", "relu", "sigmoid")


def hidden_plan(hidden: int = 16, depth: int = 2, widths: Optional[List[int]] = None,
                activations: Optional[List[str]] = None) -> Tuple[List[int], List[str]]:
    """Resolve the hidden-layer plan: per-layer widths and per-layer activations.

    `widths` overrides the uniform `hidden` x `depth` shape. `activations` is
    either one name applied to every hidden layer or one name per layer. Only
    activations the exported JSON and the C++ loader both evaluate are allowed,
    so a trained structure is always one the engine can run.
    """
    plan = [int(w) for w in widths] if widths else [int(hidden)] * int(depth)
    if not plan or any(w < 1 for w in plan):
        raise ValueError("MLP depth and every hidden width must be positive")
    acts = list(activations) if activations else ["silu"]
    if len(acts) == 1:
        acts = acts * len(plan)
    if len(acts) != len(plan):
        raise ValueError("activations must name one activation or one per hidden layer")
    unknown = [a for a in acts if a not in ACTIVATIONS]
    if unknown:
        raise ValueError(f"unsupported activation(s) {unknown}; use {'/'.join(ACTIVATIONS)}")
    return plan, acts


def _torch_activation(name: str):
    import torch

    return {"silu": torch.nn.SiLU, "tanh": torch.nn.Tanh, "relu": torch.nn.ReLU,
            "sigmoid": torch.nn.Sigmoid}[name]()


def fit_mlp(x: np.ndarray, y: np.ndarray, hidden: int, epochs: int,
            lr: float, seed: int, lr_final_factor: float = 1.0,
            *, depth: int = 2, quiet: bool = False,
            widths: Optional[List[int]] = None,
            activations: Optional[List[str]] = None):
    import torch

    torch.manual_seed(seed)
    xmean, xstd = _standardize(x)
    ymean, ystd = _standardize(y)
    xs = torch.tensor((x - xmean) / xstd, dtype=torch.float32)
    ys = torch.tensor((y - ymean) / ystd, dtype=torch.float32)
    n_in, n_out = x.shape[1], y.shape[1]
    if depth < 1 and not widths:
        raise ValueError("MLP depth must be positive")
    plan, acts = hidden_plan(hidden, depth, widths, activations)
    layers = []
    previous = n_in
    for width, act in zip(plan, acts):
        layers.extend([torch.nn.Linear(previous, width), _torch_activation(act)])
        previous = width
    layers.append(torch.nn.Linear(previous, n_out))
    net = torch.nn.Sequential(*layers)
    optim = torch.optim.Adam(net.parameters(), lr=lr)
    loss_fn = torch.nn.MSELoss()
    for epoch in range(epochs):
        if lr_final_factor != 1.0:
            for group in optim.param_groups:
                group["lr"] = lr * lr_final_factor ** (epoch / max(1, epochs - 1))
        optim.zero_grad()
        loss = loss_fn(net(xs), ys)
        loss.backward()
        optim.step()
        if not quiet and (epoch + 1) % max(1, epochs // 10) == 0:
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

    names = {torch.nn.SiLU: "silu", torch.nn.Tanh: "tanh", torch.nn.ReLU: "relu",
             torch.nn.Sigmoid: "sigmoid"}
    modules = list(net)
    layers: List[dict] = []
    linear_mods = [(i, m) for i, m in enumerate(modules) if isinstance(m, torch.nn.Linear)]
    for idx, (position, lin) in enumerate(linear_mods):
        w = lin.weight.detach().cpu().numpy()   # [out, in]
        b = lin.bias.detach().cpu().numpy()
        following = modules[position + 1] if position + 1 < len(modules) else None
        activation = "none" if idx == len(linear_mods) - 1 else names.get(type(following), "silu")
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
                       note: Optional[dict] = None,
                       output_transforms: Optional[List[str]] = None,
                       interval: Optional[dict] = None) -> None:
    if output_transforms is not None and (
            len(output_transforms) != len(outputs) or
            any(t not in ("identity", "exp", "sigmoid") for t in output_transforms)):
        raise ValueError("output transforms must match outputs and use identity/exp/sigmoid")
    xmean, xstd, ymean, ystd = scalers
    if isinstance(layers, dict):
        # v3 always nests its network and states its links, so no v1/v2 reader can mistake it.
        model = {
            "model": "generic_surrogate_v3",
            "input_features": list(inputs),
            "output_features": list(outputs),
            "input_mean": [float(v) for v in xmean],
            "input_std": [float(v) for v in xstd],
            "output_mean": [float(v) for v in ymean],
            "output_std": [float(v) for v in ystd],
            "network": layers,
            "output_transforms": list(output_transforms or ["identity"] * len(outputs)),
            "trained_from": meta,
        }
        return _finish_generic_json(path, model, domain, scale_bands, holdout, note, interval)
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
    if output_transforms and any(t != "identity" for t in output_transforms):
        model["model"] = "generic_surrogate_v2"
        model["network"] = {"layers": model.pop("layers")}
        model["output_transforms"] = list(output_transforms)
    return _finish_generic_json(path, model, domain, scale_bands, holdout, note, interval)


def _finish_generic_json(path: Path, model: dict, domain, scale_bands, holdout, note, interval) -> None:
    if domain is not None:
        model["input_domain"] = domain
    if scale_bands:
        # Dimension-scale band(s) the training data came from, so the engine can
        # flag a stage applied off the band it learned (harvester band tags).
        model["trained_scale_bands"] = list(scale_bands)
    if holdout is not None:
        model["holdout"] = holdout
    if interval is not None:
        model["prediction_interval"] = interval
    if note:
        # Free-form audit metadata. The engine deliberately does not interpret
        # this block; it travels with the deployable artefact so a distilled
        # operator cannot be mistaken for a model trained from measurements.
        model["note"] = note
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(model, indent=2) + "\n", encoding="utf-8")


def export_torchscript(net, scalers, out_path: Path,
                       output_transforms: Optional[List[str]] = None) -> bool:
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
            self.register_buffer("exponential", torch.tensor(
                [t == "exp" for t in (output_transforms or ["identity"] * len(ymean))]))
            self.register_buffer("probability", torch.tensor(
                [t == "sigmoid" for t in (output_transforms or ["identity"] * len(ymean))]))

        def forward(self, x):
            xs = (x - self.xmean) / self.xstd
            raw = self.inner(xs) * self.ystd + self.ymean
            encoded = torch.where(self.exponential, raw, torch.zeros_like(raw))
            decoded = torch.where(self.exponential, torch.exp(encoded), raw)
            decoded = torch.where(self.probability, torch.sigmoid(raw), decoded)
            # Preserve a non-finite encoded failure for runtime rejection;
            # sigmoid must not conceal a network/scaler overflow as 0 or 1.
            return torch.where(torch.isfinite(raw), decoded, raw)

    wrapped = Wrapped(net)
    wrapped.eval()
    scripted = torch.jit.script(wrapped)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    scripted.save(str(out_path))
    return True


def predict_np(x: np.ndarray, layers, scalers,
               output_transforms: Optional[List[str]] = None) -> np.ndarray:
    """Evaluate the exported model in numpy (parity check with the C++ side).

    `layers` is a dense-layer list (v1/v2) or a v3 set-network block (dict)."""
    xmean, xstd, ymean, ystd = scalers
    a = (x - xmean) / xstd
    if isinstance(layers, dict):
        a = set_networks.predict_network_np(a, x, layers)
        layers = []
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
    result = a * ystd + ymean
    for i, transform in enumerate(output_transforms or []):
        if transform == "exp":
            result[:, i] = np.exp(result[:, i])
        elif transform == "sigmoid":
            raw = result[:, i]
            decay = np.exp(-np.abs(raw))
            decoded = np.where(raw >= 0, 1.0 / (1.0 + decay), decay / (1.0 + decay))
            result[:, i] = np.where(np.isfinite(raw), decoded, raw)
    return result


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


def _conformal_level(n: int, coverage: float) -> float:
    """Finite-sample split-conformal quantile level ceil((n+1)c)/n (capped at 1)."""
    return min(1.0, math.ceil((n + 1) * coverage) / n) if n else 1.0


def _conformal_quantile(values: np.ndarray, coverage: float) -> float:
    """The split-conformal score: the ceil((n+1)c)-th smallest value (the largest when that
    rank exceeds n). An explicit order statistic -- np.quantile indexes by (n-1)q, which is
    not this rank."""
    ordered = np.sort(np.asarray(values, dtype=float))
    rank = min(len(ordered), int(math.ceil((len(ordered) + 1) * coverage - 1e-12)))
    return float(ordered[max(rank, 1) - 1])


def calibration_interval(y_true: np.ndarray, y_pred: np.ndarray, outputs: List[str],
                         coverage: float, runs: List[str],
                         groups: Optional[np.ndarray] = None) -> dict:
    """Split-conformal error bar measured on CALIBRATION runs only.

    Rows from one run are correlated (same configuration, shared trajectory), so a row-level
    quantile treats far fewer independent draws as many and its coverage is only approximate.
    With `groups` (the calibration-run index of every row) the carried `half_width` is the
    RUN-LEVEL (grouped) conformal quantile instead: each run r scores
    q_r = the `coverage` quantile of its own |residuals| (the half-width that run needs), and the
    interval is the ceil((R+1)c)/R quantile of q_1..q_R over the R runs. Runs, not rows, are the
    exchangeable units, so for a new run exchangeable with the calibration runs
    P(the interval covers >= `coverage` of its rows) >= `coverage`. That guarantee needs
    R >= c/(1-c) runs (9 at c = 0.9); with fewer the level saturates, the interval is the worst
    run's q_r (conservative, but `run_level_guarantee` is false). The row-pooled quantile is kept
    as `pooled_half_width` for comparison. Without `groups` the pooled quantile is carried
    (method `split_conformal_abs_residual`, approximate). `rmse` is the pooled calibration 1-sigma.
    """
    n = len(y_true)
    residual = np.abs(y_pred - y_true)
    pooled_level = _conformal_level(n, coverage)
    pooled = {o: _conformal_quantile(residual[:, i], coverage) for i, o in enumerate(outputs)}
    rmse = {o: float(np.sqrt(np.mean((y_pred[:, i] - y_true[:, i]) ** 2))) for i, o in enumerate(outputs)}
    block = {"nominal_coverage": float(coverage), "rmse": rmse, "source": "calibration_runs",
             "runs": list(runs), "n": int(n)}
    ids = sorted(set(int(g) for g in groups)) if groups is not None else []
    if len(ids) < 1:
        block.update({"half_width": pooled, "method": "split_conformal_abs_residual",
                      "quantile_level": float(pooled_level),
                      "note": "row-level quantile: rows of one run are correlated, coverage is approximate"})
        return block
    r = len(ids)
    run_level = _conformal_level(r, coverage)
    per_run = {}
    half = {}
    for i, o in enumerate(outputs):
        scores = []
        for g in ids:
            res = residual[groups == g, i]
            scores.append(_conformal_quantile(res, coverage))
        per_run[o] = scores
        half[o] = _conformal_quantile(np.asarray(scores), coverage)
    needed = int(math.ceil(coverage / (1.0 - coverage) - 1e-12))
    block.update({
        "half_width": half, "method": "run_grouped_conformal_abs_residual",
        "quantile_level": float(run_level), "runs_scored": r,
        "rows_per_run": [int(np.sum(groups == g)) for g in ids],
        "per_run_half_width": per_run, "pooled_half_width": pooled,
        "pooled_quantile_level": float(pooled_level),
        "run_level_guarantee": bool(math.ceil((r + 1) * coverage) <= r),
        "runs_needed_for_guarantee": needed,
        "note": ("runs are the exchangeable units: the half-width covers >= nominal of a new run's rows "
                 "with probability >= nominal" if math.ceil((r + 1) * coverage) <= r else
                 f"only {r} calibration run(s) (< {needed} needed for the run-level guarantee): the half-width "
                 "is the worst run's own quantile -- conservative, not a guarantee"),
    })
    return block


def mlp_kind(widths: List[int], activations: List[str]) -> str:
    """Human label of an MLP plan; the uniform SiLU labels predate per-layer plans."""
    uniform = len(set(widths)) == 1 and len(set(activations)) == 1
    if uniform and activations[0] == "silu":
        return (f"mlp(hidden={widths[0]})" if len(widths) == 2 else
                f"mlp(hidden={widths[0]},depth={len(widths)})")
    if uniform:
        return f"mlp(hidden={widths[0]},depth={len(widths)},activation={activations[0]})"
    return ("mlp(widths=" + "-".join(str(w) for w in widths) + ",activations=" +
            "-".join(activations) + ")")


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
    ap.add_argument("--log-outputs", default="",
                    help="comma-separated strictly-positive targets fitted in log space; "
                         "exports v2 inverse links and physical-unit holdout errors")
    ap.add_argument("--logit-outputs", default="",
                    help="comma-separated targets strictly inside (0,1), fitted in logit space; "
                         "exports v2 sigmoid links; no implicit clipping or pseudocounts")
    ap.add_argument("--list-columns", action="store_true",
                    help="print the numeric columns available and exit")
    ap.add_argument("--out-json", default="surrogate.json")
    ap.add_argument("--out", default=None, help="optional TorchScript .pt")
    ap.add_argument("--manifest", default="surrogate.manifest.json")
    ap.add_argument("--hidden", type=int, default=16,
                    help="hidden width (0 or --linear -> linear model)")
    ap.add_argument("--depth", type=int, default=2,
                    help="positive number of hidden layers; no fixed three-level limit")
    ap.add_argument("--widths", default=None,
                    help="comma-separated per-layer hidden widths (e.g. 32,16,8); "
                         "overrides --hidden/--depth")
    ap.add_argument("--activation", default="silu", choices=list(ACTIVATIONS),
                    help="hidden-layer activation for every layer")
    ap.add_argument("--activations", default=None,
                    help="comma-separated per-layer activations (one per hidden layer); "
                         "overrides --activation")
    ap.add_argument("--network", default="mlp", choices=["mlp", *set_networks.KINDS],
                    help="mlp (default) or a permutation-invariant set network (generic_surrogate_v3)")
    ap.add_argument("--set-elements", type=int, default=0,
                    help="set networks: number of element blocks in the inputs (element-major)")
    ap.add_argument("--set-context", type=int, default=0,
                    help="set networks: trailing global (context) inputs after the element blocks")
    ap.add_argument("--pool", default="sum", choices=list(set_networks.POOLS))
    ap.add_argument("--mask-feature", type=int, default=None,
                    help="set networks: element feature index whose raw value > 0.5 marks a present element")
    ap.add_argument("--phi-widths", default="16,16", help="set networks: per-element encoder widths")
    ap.add_argument("--rho-widths", default="16", help="set networks: readout hidden widths (may be empty)")
    ap.add_argument("--message-widths", default="", help="mpnn: message hidden widths before the state width")
    ap.add_argument("--rounds", type=int, default=1, help="mpnn: message-passing rounds (shared weights)")
    ap.add_argument("--relative-features", default="",
                    help="mpnn: element feature indices whose differences x_j - x_i feed each message")
    ap.add_argument("--aggregate", default="mean", choices=list(set_networks.AGGREGATES))
    ap.add_argument("--calibration-runs", nargs="+", default=None,
                    help="runs used ONLY to set the carried prediction interval (disjoint from "
                         "--runs and --validation-runs)")
    ap.add_argument("--interval-coverage", type=float, default=0.9,
                    help="nominal coverage of the calibration prediction interval")
    ap.add_argument("--linear", action="store_true",
                    help="force a linear model (numpy, no torch needed)")
    ap.add_argument("--epochs", type=int, default=400)
    ap.add_argument("--lr", type=float, default=1e-2)
    ap.add_argument("--lr-final-factor", type=float, default=1.0,
                    help="optional exponential learning-rate decay; 1 preserves the existing trainer")
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
    if args.depth < 1:
        ap.error("--depth must be positive")
    try:
        widths = [int(w) for w in _split_cols(args.widths)] if args.widths else None
        hidden_widths, hidden_acts = hidden_plan(
            args.hidden if args.hidden > 0 else 1, args.depth, widths,
            _split_cols(args.activations) if args.activations else [args.activation])
    except ValueError as exc:
        ap.error(str(exc))
    if not 0.0 < args.lr_final_factor <= 1.0:
        ap.error("--lr-final-factor must be in (0,1]")
    if not 0.5 <= args.interval_coverage < 1.0:
        ap.error("--interval-coverage must be in [0.5, 1)")
    overlap = set(map(_portable_path, args.calibration_runs or [])) & set(
        map(_portable_path, list(args.runs) + list(args.validation_runs or [])))
    if overlap:
        ap.error("--calibration-runs must be disjoint from --runs/--validation-runs: " + ", ".join(sorted(overlap)))

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
    log_outputs = _split_cols(args.log_outputs)
    logit_outputs = _split_cols(args.logit_outputs)
    if any(name not in outputs for name in log_outputs):
        raise SystemExit("--log-outputs must name declared output columns")
    if any(name not in outputs for name in logit_outputs):
        raise SystemExit("--logit-outputs must name declared output columns")
    if set(log_outputs) & set(logit_outputs):
        raise SystemExit("an output cannot use both --log-outputs and --logit-outputs")
    transforms = ["exp" if name in log_outputs else
                  "sigmoid" if name in logit_outputs else "identity" for name in outputs]
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

    encoded_targets = y_train.copy()
    for i, transform in enumerate(transforms):
        if transform == "exp":
            if not (np.all(np.isfinite(y_train[:, i])) and np.all(y_train[:, i] > 0) and
                    np.all(np.isfinite(y_hold[:, i])) and np.all(y_hold[:, i] > 0)):
                raise SystemExit("log-output targets must be finite and strictly positive")
            encoded_targets[:, i] = np.log(y_train[:, i])
        elif transform == "sigmoid":
            if not (np.all(np.isfinite(y_train[:, i])) and
                    np.all((y_train[:, i] > 0) & (y_train[:, i] < 1)) and
                    np.all(np.isfinite(y_hold[:, i])) and
                    np.all((y_hold[:, i] > 0) & (y_hold[:, i] < 1))):
                raise SystemExit("logit-output targets must be finite and strictly inside (0,1)")
            encoded_targets[:, i] = np.log(y_train[:, i]) - np.log1p(-y_train[:, i])

    set_spec = None
    if args.network != "mlp":
        if args.linear:
            raise SystemExit("--linear and --network deepsets/mpnn are exclusive")
        try:
            set_spec = set_networks.make_spec(
                args.network, len(inputs), elements=args.set_elements, context=args.set_context,
                pool=args.pool, mask_feature=args.mask_feature,
                phi=[int(w) for w in _split_cols(args.phi_widths)],
                rho=[int(w) for w in _split_cols(args.rho_widths)], activation=args.activation,
                message=[int(w) for w in _split_cols(args.message_widths)], rounds=args.rounds,
                relative=[int(i) for i in _split_cols(args.relative_features)], aggregate=args.aggregate)
        except ValueError as exc:
            raise SystemExit(f"set network: {exc}")
        try:
            import torch  # noqa: F401
        except ImportError:
            # Never fall back to a different structure: the caller asked for a set network.
            raise SystemExit("--network deepsets/mpnn needs torch")

    use_mlp = (not args.linear) and set_spec is None and (args.hidden > 0 or bool(args.widths))
    if set_spec is not None:
        net, scalers = set_networks.fit(x_train, encoded_targets, set_spec, epochs=args.epochs,
                                        lr=args.lr, seed=args.seed,
                                        lr_final_factor=args.lr_final_factor)
        layers = set_networks.network_json(net, set_spec)
        param_count = set_networks.parameter_count(layers)
        model_kind = set_networks.describe(layers)
    if use_mlp:
        try:
            import torch  # noqa: F401
        except ImportError:
            print("torch not available; falling back to a linear model",
                  file=sys.stderr)
            use_mlp = False

    if use_mlp:
        net, scalers = fit_mlp(x_train, encoded_targets, hidden=args.hidden,
                               epochs=args.epochs, lr=args.lr, seed=args.seed,
                               lr_final_factor=args.lr_final_factor, depth=args.depth,
                               widths=hidden_widths, activations=hidden_acts)
        layers = _mlp_layers_json(net)
        param_count = int(sum(p.numel() for p in net.parameters()))
        model_kind = mlp_kind(hidden_widths, hidden_acts)
    elif set_spec is None:
        w, b, scalers = fit_linear(x_train, encoded_targets, l2=args.l2)
        layers = _linear_layers_json(w, b)
        net = None
        param_count = int(w.size + b.size)
        model_kind = "linear"

    # Held-out metrics evaluated through the EXPORTED numpy path (so they match
    # what the C++ GenericSurrogate will compute).
    y_hold_pred = predict_np(x_hold, layers, scalers, transforms)
    metrics = evaluate(y_hold, y_hold_pred, outputs)
    for name, m in metrics.items():
        print(f"  holdout {name}: MAE={m['mae']:.4g} RMSE={m['rmse']:.4g} "
              f"R2={m['r2']:.3f}")

    interval = None
    calibration_metas = []
    if args.calibration_runs:
        # Harvest each calibration run on its own so every row keeps its run: the interval is
        # a run-level (grouped) conformal quantile, runs being the independent units.
        xs, ys, gs = [], [], []
        for cal_run in args.calibration_runs:
            cal_rows, metas = harvest_table([cal_run], source=args.source, tag=args.tag, expand=args.expand)
            for meta in metas:
                calibration_metas.append(meta)
                if not cal_rows:
                    continue
                x_r, y_r, _dropped = build_xy(cal_rows, inputs, outputs)
                xs.append(x_r)
                ys.append(y_r)
                gs.append(np.full(len(x_r), len(gs)))
        x_cal = np.concatenate(xs) if xs else np.zeros((0, len(inputs)))
        y_cal = np.concatenate(ys) if ys else np.zeros((0, len(outputs)))
        if len(x_cal) < 2:
            print("error: fewer than two complete calibration rows", file=sys.stderr)
            return 2
        interval = calibration_interval(y_cal, predict_np(x_cal, layers, scalers, transforms), outputs,
                                        args.interval_coverage,
                                        [_portable_path(m.run_dir) for m in calibration_metas],
                                        groups=np.concatenate(gs))
        for name in outputs:
            print(f"  calibration {name}: RMSE={interval['rmse'][name]:.4g} "
                  f"{args.interval_coverage:g}-interval ±{interval['half_width'][name]:.4g} "
                  f"(n={interval['n']})")

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
    if calibration_metas:
        trained_from["calibration_runs"] = [_portable_path(m.run_dir) for m in calibration_metas]
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
                       note=note, output_transforms=transforms, interval=interval)
    print(f"wrote {json_path}")

    pt_written = False
    if args.out and net is not None:
        pt_written = export_torchscript(net, scalers, Path(args.out).expanduser(), transforms)
        if pt_written:
            print(f"wrote {Path(args.out).expanduser().resolve()}")

    manifest = {
        "schema": "trech_generic_surrogate_manifest_v1",
        "model": ("generic_surrogate_v3" if set_spec is not None else
                  "generic_surrogate_v2" if log_outputs or logit_outputs else "generic_surrogate_v1"),
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
        "structure": (dict(set_spec, family=set_spec["kind"]) if set_spec is not None else
                      {"family": "mlp", "widths": hidden_widths,
                       "activations": hidden_acts} if use_mlp else
                      {"family": "linear", "l2": args.l2}),
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
        "prediction_interval": interval,
        "input_domain": domain,
        "note": note,
    }
    if args.lr_final_factor != 1.0:
        manifest["training"]["lr_final_factor"] = args.lr_final_factor
    if log_outputs or logit_outputs:
        manifest["output_transforms"] = transforms
        manifest["metrics_units"] = "decoded physical output units"
    manifest_path = Path(args.manifest).expanduser().resolve()
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n",
                             encoding="utf-8")
    print(f"wrote {manifest_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
