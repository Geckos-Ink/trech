"""Permutation-invariant set networks (DeepSets / message passing) for generic_surrogate_v3.

A v3 model keeps the flat NAMED interface of every TRECH surrogate (`ctx.predict` feeds a
name->value map): its inputs are `elements` blocks of `element_features` values, element-major
(element e, feature f at index e*F + f), followed by `context_features` global inputs. The
network sees the elements as a SET, so permuting element blocks never changes the prediction.

    deepsets:  y = rho([pool_i phi(z_i), z_context])
    mpnn:      h_i = phi(z_i)
               repeat `rounds` times (weights shared across rounds):
                 m_i = agg_{j != i, present} message([h_i, h_j, z_j[rel] - z_i[rel]])
                 h_i = update([h_i, m_i])
               y = rho([pool_i h_i, z_context])

`z` are the standardised inputs (the model's own input_mean/std, shared by every element so
the scalers are permutation invariant too). With `mask_feature` = f, element i is PRESENT iff
its RAW feature f is > 0.5; absent elements take part in neither pooling nor messages, so one
model serves sets of varying size up to `elements`. `pool` is sum/mean/max over present
elements (zeros when none is present); `aggregate` is sum/mean over present neighbours.
Summation runs in ascending element order: the C++ evaluator (src/ml/GenericSurrogate.cpp)
uses the same order and the same dense-layer arithmetic.

This module owns three evaluators of the SAME exported arithmetic -- the torch module used
for training/TorchScript, a NumPy batch evaluator (trainer metrics, validator), and a
pure-Python one (validator parity) -- plus the JSON export.
"""

from __future__ import annotations

import math
from typing import Dict, List, Optional, Sequence

# NumPy is imported inside the functions that need it: the validator's static gates use the
# pure-Python parts of this module under interpreters without NumPy.

KINDS = ("deepsets", "mpnn")
POOLS = ("sum", "mean", "max")
AGGREGATES = ("sum", "mean")


# ---------------------------------------------------------------------------- spec

def make_spec(kind: str, n_inputs: int, *, elements: int, context: int = 0, pool: str = "sum",
              mask_feature: Optional[int] = None, phi: Sequence[int], rho: Sequence[int] = (),
              activation: str = "silu", message: Sequence[int] = (), rounds: int = 1,
              relative: Sequence[int] = (), aggregate: str = "mean") -> dict:
    """Validated set-network description (hidden widths only; weights come from training)."""
    if kind not in KINDS:
        raise ValueError(f"network kind must be one of {KINDS}")
    if elements < 1 or context < 0:
        raise ValueError("elements must be >= 1 and context >= 0")
    element_inputs = n_inputs - context
    if element_inputs < elements or element_inputs % elements:
        raise ValueError(f"{n_inputs} inputs minus {context} context inputs do not split into "
                         f"{elements} equal element blocks")
    features = element_inputs // elements
    if mask_feature is not None and not 0 <= mask_feature < features:
        raise ValueError(f"mask feature {mask_feature} is not one of the {features} element features")
    if pool not in POOLS or aggregate not in AGGREGATES:
        raise ValueError(f"pool must be {POOLS}, aggregate {AGGREGATES}")
    if not phi or any(int(w) < 1 for w in phi) or any(int(w) < 1 for w in list(rho) + list(message)):
        raise ValueError("phi needs at least one positive width; rho/message widths must be positive")
    rel = sorted({int(i) for i in relative})
    if any(not 0 <= i < features for i in rel):
        raise ValueError(f"relative feature indices must be in [0, {features})")
    if kind == "mpnn" and not 1 <= rounds <= 16:
        raise ValueError("rounds must be in [1, 16]")
    spec = {"kind": kind, "elements": int(elements), "element_features": int(features),
            "context_features": int(context), "pool": pool, "mask_feature": mask_feature,
            "phi": [int(w) for w in phi], "rho": [int(w) for w in rho], "activation": activation}
    if kind == "mpnn":
        spec.update({"message": [int(w) for w in message], "rounds": int(rounds),
                     "relative_features": rel, "aggregate": aggregate})
    return spec


def shared_scalers(x: np.ndarray, spec: dict):
    """Input scalers shared by every element block (permutation invariant).

    Element-feature statistics pool all element blocks -- only PRESENT elements when a mask
    feature is declared, so zero padding does not drag the scale -- and the mask feature itself
    pools all blocks. Context features keep their own statistics.
    """
    import numpy as np

    e, f, c = spec["elements"], spec["element_features"], spec["context_features"]
    blocks = x[:, :e * f].reshape(len(x), e, f)
    flat = blocks.reshape(-1, f)
    mask = spec.get("mask_feature")
    present = flat[:, mask] > 0.5 if mask is not None else np.ones(len(flat), dtype=bool)
    if not present.any():
        present = np.ones(len(flat), dtype=bool)
    mean = flat[present].mean(axis=0)
    std = flat[present].std(axis=0)
    if mask is not None:
        mean[mask] = flat[:, mask].mean()
        std[mask] = flat[:, mask].std()
    std[std < 1e-9] = 1.0
    xmean = np.concatenate([np.tile(mean, e), x[:, e * f:].mean(axis=0) if c else np.zeros(0)])
    cstd = x[:, e * f:].std(axis=0) if c else np.zeros(0)
    cstd[cstd < 1e-9] = 1.0
    xstd = np.concatenate([np.tile(std, e), cstd])
    return xmean, xstd


# ---------------------------------------------------------------------------- torch

def build_torch(spec: dict, n_out: int, mask_threshold_z: float = 0.0):
    """A scriptable torch module mapping STANDARDISED flat inputs [B, n_in] -> [B, n_out]."""
    import torch
    from torch import nn

    from .train_surrogate import _torch_activation

    def dense(first: int, widths: Sequence[int], act: str, last: Optional[int] = None,
              last_act: Optional[str] = None) -> nn.Sequential:
        layers: List[nn.Module] = []
        previous = first
        for w in widths:
            layers.extend([nn.Linear(previous, w), _torch_activation(act)])
            previous = w
        if last is not None:
            layers.append(nn.Linear(previous, last))
            if last_act is not None:
                layers.append(_torch_activation(last_act))
        return nn.Sequential(*layers)

    act = spec["activation"]
    hidden = spec["phi"][-1]
    rel = spec.get("relative_features") or []

    class SetNet(nn.Module):
        def __init__(self):
            super().__init__()
            self.elements = int(spec["elements"])
            self.features = int(spec["element_features"])
            self.context = int(spec["context_features"])
            self.pool = str(spec["pool"])
            self.has_mask = spec.get("mask_feature") is not None
            self.mask_index = int(spec["mask_feature"]) if self.has_mask else 0
            self.mask_threshold = float(mask_threshold_z)
            self.mpnn = spec["kind"] == "mpnn"
            self.rounds = int(spec.get("rounds", 0))
            self.mean_aggregate = spec.get("aggregate", "mean") == "mean"
            self.has_rel = len(rel) > 0
            self.register_buffer("rel", torch.tensor(rel if rel else [0], dtype=torch.long))
            self.phi = dense(self.features, spec["phi"][:-1], act, spec["phi"][-1], act)
            self.message = dense(2 * hidden + len(rel), spec.get("message", []), act, hidden, act)
            self.update = dense(2 * hidden, [], act, hidden, act)
            self.rho = dense(hidden + self.context, spec["rho"], act, n_out, None)

        def forward(self, x):
            batch = x.shape[0]
            elems = x[:, :self.elements * self.features].reshape(batch, self.elements, self.features)
            ctx = x[:, self.elements * self.features:]
            if self.has_mask:
                mask = (elems[:, :, self.mask_index] > self.mask_threshold).to(x.dtype)
            else:
                mask = torch.ones(batch, self.elements, dtype=x.dtype, device=x.device)
            h = self.phi(elems)
            if self.mpnn:
                eye = torch.eye(self.elements, dtype=x.dtype, device=x.device)
                pair = mask.unsqueeze(2) * mask.unsqueeze(1) * (1.0 - eye).unsqueeze(0)
                count = pair.sum(2).clamp(min=1.0).unsqueeze(2)
                for _ in range(self.rounds):
                    hi = h.unsqueeze(2).expand(batch, self.elements, self.elements, h.shape[2])
                    hj = h.unsqueeze(1).expand(batch, self.elements, self.elements, h.shape[2])
                    if self.has_rel:
                        sel = elems.index_select(2, self.rel)
                        d = sel.unsqueeze(1) - sel.unsqueeze(2)  # [b, i, j] = z_j - z_i
                        m = self.message(torch.cat([hi, hj, d], dim=3))
                    else:
                        m = self.message(torch.cat([hi, hj], dim=3))
                    agg = (m * pair.unsqueeze(3)).sum(2)
                    if self.mean_aggregate:
                        agg = agg / count
                    h = self.update(torch.cat([h, agg], dim=2))
            present = mask.sum(1, keepdim=True)
            if self.pool == "max":
                masked = torch.where(mask.unsqueeze(2) > 0, h, torch.full_like(h, -1e30))
                pooled = masked.max(dim=1).values
                pooled = torch.where(present > 0, pooled, torch.zeros_like(pooled))
            else:
                pooled = (h * mask.unsqueeze(2)).sum(1)
                if self.pool == "mean":
                    pooled = pooled / present.clamp(min=1.0)
            return self.rho(torch.cat([pooled, ctx], dim=1))

    return SetNet()


def mask_threshold_z(spec: dict, xmean, xstd) -> float:
    """Raw mask threshold 0.5 expressed in the standardised units the torch module sees."""
    m = spec.get("mask_feature")
    if m is None:
        return 0.0
    return float((0.5 - xmean[m]) / xstd[m])


def fit(x: np.ndarray, y: np.ndarray, spec: dict, *, epochs: int, lr: float, seed: int,
        lr_final_factor: float = 1.0, quiet: bool = False):
    import numpy as np

    import torch

    torch.manual_seed(seed)
    xmean, xstd = shared_scalers(x, spec)
    ymean, ystd = y.mean(axis=0), y.std(axis=0)
    ystd[ystd < 1e-9] = 1.0
    xs = torch.tensor((x - xmean) / xstd, dtype=torch.float32)
    ys = torch.tensor((y - ymean) / ystd, dtype=torch.float32)
    net = build_torch(spec, y.shape[1], mask_threshold_z(spec, xmean, xstd))
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


def _dense_json(seq) -> List[dict]:
    import torch

    names = {torch.nn.SiLU: "silu", torch.nn.Tanh: "tanh", torch.nn.ReLU: "relu",
             torch.nn.Sigmoid: "sigmoid"}
    modules = list(seq)
    out = []
    for position, module in enumerate(modules):
        if not isinstance(module, torch.nn.Linear):
            continue
        following = modules[position + 1] if position + 1 < len(modules) else None
        act = names.get(type(following), "none") if following is not None else "none"
        out.append({"weights": [[float(v) for v in row] for row in module.weight.detach().cpu().numpy()],
                    "bias": [float(v) for v in module.bias.detach().cpu().numpy()],
                    "activation": act})
    return out


def network_json(net, spec: dict) -> dict:
    """The generic_surrogate_v3 `network` block of a trained SetNet."""
    block = {"kind": spec["kind"], "elements": spec["elements"],
             "element_features": spec["element_features"],
             "context_features": spec["context_features"], "pool": spec["pool"],
             "phi": _dense_json(net.phi), "rho": _dense_json(net.rho)}
    if spec.get("mask_feature") is not None:
        block["mask_feature"] = int(spec["mask_feature"])
    if spec["kind"] == "mpnn":
        block.update({"rounds": spec["rounds"], "relative_features": list(spec["relative_features"]),
                      "aggregate": spec["aggregate"], "message": _dense_json(net.message),
                      "update": _dense_json(net.update)})
    return block


def parameter_count(network: dict) -> int:
    total = 0
    for key in ("phi", "rho", "message", "update"):
        for layer in network.get(key) or []:
            total += len(layer["weights"]) * len(layer["weights"][0]) + len(layer["bias"])
    return total


def describe(network: dict) -> str:
    phi = "-".join(str(len(l["weights"])) for l in network["phi"])
    rho = "-".join(str(len(l["weights"])) for l in network["rho"][:-1]) or "linear"
    acts = {l.get("activation", "none") for l in network["phi"]}
    act = acts.pop() if len(acts) == 1 else "mixed"
    head = f"{network['elements']}x{network['element_features']}"
    if network.get("context_features"):
        head += f"+{network['context_features']}"
    if network["kind"] == "mpnn":
        return (f"mpnn({head},phi={phi},rounds={network['rounds']},{network.get('aggregate', 'mean')},"
                f"{network['pool']},rho={rho},{act})")
    return f"deepsets({head},phi={phi},{network['pool']},rho={rho},{act})"


# ---------------------------------------------------------------------------- evaluators

def _np_act(name: str, a: np.ndarray) -> np.ndarray:
    import numpy as np

    if name in ("silu", "swish"):
        return a / (1.0 + np.exp(-a))
    if name == "relu":
        return np.maximum(a, 0.0)
    if name == "tanh":
        return np.tanh(a)
    if name in ("sigmoid", "logistic"):
        return 1.0 / (1.0 + np.exp(-a))
    return a


def _np_dense(layers: List[dict], a: np.ndarray) -> np.ndarray:
    import numpy as np

    for layer in layers:
        a = a @ np.asarray(layer["weights"], dtype=float).T + np.asarray(layer["bias"], dtype=float)
        a = _np_act(str(layer.get("activation", "none")), a)
    return a


def predict_network_np(z: np.ndarray, raw: np.ndarray, network: dict) -> np.ndarray:
    """NumPy batch evaluation on standardised inputs `z` (raw inputs only for the mask)."""
    import numpy as np

    e, f = int(network["elements"]), int(network["element_features"])
    c = int(network.get("context_features") or 0)
    batch = len(z)
    elems = z[:, :e * f].reshape(batch, e, f)
    ctx = z[:, e * f:e * f + c]
    m_idx = network.get("mask_feature")
    if m_idx is not None:
        mask = (raw[:, :e * f].reshape(batch, e, f)[:, :, int(m_idx)] > 0.5).astype(float)
    else:
        mask = np.ones((batch, e))
    h = _np_dense(network["phi"], elems)
    if network["kind"] == "mpnn":
        rel = [int(i) for i in network.get("relative_features") or []]
        pair = mask[:, :, None] * mask[:, None, :] * (1.0 - np.eye(e))[None]
        count = np.maximum(pair.sum(2), 1.0)[:, :, None]
        for _ in range(int(network["rounds"])):
            hi = np.broadcast_to(h[:, :, None, :], (batch, e, e, h.shape[2]))
            hj = np.broadcast_to(h[:, None, :, :], (batch, e, e, h.shape[2]))
            parts = [hi, hj]
            if rel:
                sel = elems[:, :, rel]
                parts.append(sel[:, None, :, :] - sel[:, :, None, :])
            msg = _np_dense(network["message"], np.concatenate(parts, axis=3))
            agg = (msg * pair[:, :, :, None]).sum(2)
            if network.get("aggregate", "mean") == "mean":
                agg = agg / count
            h = _np_dense(network["update"], np.concatenate([h, agg], axis=2))
    present = mask.sum(1, keepdims=True)
    if network["pool"] == "max":
        pooled = np.where(mask[:, :, None] > 0, h, -np.inf).max(axis=1)
        pooled = np.where(present > 0, pooled, 0.0)
    else:
        pooled = (h * mask[:, :, None]).sum(1)
        if network["pool"] == "mean":
            pooled = pooled / np.maximum(present, 1.0)
    return _np_dense(network["rho"], np.concatenate([pooled, ctx], axis=1))


def _py_act(name: str, v: float) -> float:
    if name == "relu":
        return v if v > 0 else 0.0
    if name in ("silu", "swish"):
        return v / (1.0 + math.exp(-v)) if v > -700 else 0.0
    if name == "tanh":
        return math.tanh(v)
    if name in ("sigmoid", "logistic"):
        return 1.0 / (1.0 + math.exp(-v)) if v > -700 else 0.0
    return v


def _py_dense(layers: List[dict], a: List[float]) -> List[float]:
    for layer in layers:
        act = str(layer.get("activation", "none"))
        nxt = []
        for weights, bias in zip(layer["weights"], layer["bias"]):
            total = float(bias)
            for w, v in zip(weights, a):
                total += float(w) * v
            try:
                nxt.append(_py_act(act, total))
            except OverflowError:
                nxt.append(float("inf"))
        a = nxt
    return a


def forward_network_py(z: List[float], raw: List[float], network: dict) -> List[float]:
    """Pure-Python single-row evaluation (independent of NumPy), ascending element order."""
    e, f = int(network["elements"]), int(network["element_features"])
    c = int(network.get("context_features") or 0)
    elems = [z[i * f:(i + 1) * f] for i in range(e)]
    ctx = z[e * f:e * f + c]
    m_idx = network.get("mask_feature")
    present = [m_idx is None or raw[i * f + int(m_idx)] > 0.5 for i in range(e)]
    h = [_py_dense(network["phi"], elems[i]) for i in range(e)]
    if network["kind"] == "mpnn":
        rel = [int(i) for i in network.get("relative_features") or []]
        mean = network.get("aggregate", "mean") == "mean"
        for _ in range(int(network["rounds"])):
            nxt = []
            for i in range(e):
                agg = [0.0] * len(h[i])
                count = 0
                for j in range(e):
                    if j == i or not (present[i] and present[j]):
                        continue
                    edge = h[i] + h[j] + [elems[j][k] - elems[i][k] for k in rel]
                    msg = _py_dense(network["message"], edge)
                    agg = [a + b for a, b in zip(agg, msg)]
                    count += 1
                if mean and count:
                    agg = [a / count for a in agg]
                nxt.append(_py_dense(network["update"], h[i] + agg))
            h = nxt
    width = len(h[0])
    chosen = [h[i] for i in range(e) if present[i]]
    if not chosen:
        pooled = [0.0] * width
    elif network["pool"] == "max":
        pooled = [max(v[k] for v in chosen) for k in range(width)]
    else:
        pooled = [sum(v[k] for v in chosen) for k in range(width)]
        if network["pool"] == "mean":
            pooled = [p / len(chosen) for p in pooled]
    return _py_dense(network["rho"], pooled + list(ctx))


def structure_problems(network: dict, n_in: int, n_out: int, activations: Sequence[str]) -> List[str]:
    """Loadability rules the C++ GenericSurrogate v3 reader enforces (validator mirror)."""
    problems: List[str] = []
    if network.get("kind") not in KINDS:
        return [f"network.kind must be one of {KINDS}"]
    e, f = network.get("elements"), network.get("element_features")
    c = network.get("context_features", 0)
    if not all(isinstance(v, int) and v >= 0 for v in (e, f, c)) or not e or not f:
        return ["elements/element_features must be positive integers, context_features >= 0"]
    if e * f + c != n_in:
        problems.append(f"set layout {e}x{f}+{c} does not match {n_in} inputs")
    if network.get("pool", "sum") not in POOLS:
        problems.append(f"pool must be one of {POOLS}")
    m = network.get("mask_feature")
    if m is not None and not (isinstance(m, int) and 0 <= m < f):
        problems.append("mask_feature must index an element feature")

    def chain(key: str, first: int, last: Optional[int]) -> Optional[int]:
        layers = network.get(key)
        if not isinstance(layers, list) or not layers:
            problems.append(f"{key} has no dense layers")
            return None
        previous = first
        for index, layer in enumerate(layers):
            w, b = layer.get("weights"), layer.get("bias")
            if str(layer.get("activation", "none")) not in activations:
                problems.append(f"{key} layer {index} has unknown activation {layer.get('activation')!r}")
            if not isinstance(w, list) or not w or not all(
                    isinstance(r, list) and all(isinstance(v, (int, float)) and math.isfinite(v) for v in r)
                    for r in w):
                problems.append(f"{key} layer {index} weights are missing or non-finite")
                return None
            if any(len(r) != previous for r in w):
                problems.append(f"{key} layer {index} input width does not chain ({previous} expected)")
            if not isinstance(b, list) or len(b) != len(w) or not all(
                    isinstance(v, (int, float)) and math.isfinite(v) for v in b):
                problems.append(f"{key} layer {index} bias must match its {len(w)} outputs")
            previous = len(w)
        if last is not None and previous != last:
            problems.append(f"{key} emits {previous} values, {last} expected")
        return previous

    hidden = chain("phi", f, None)
    if hidden is None:
        return problems
    chain("rho", hidden + c, n_out)
    if network["kind"] == "mpnn":
        rel = network.get("relative_features") or []
        if not all(isinstance(i, int) and 0 <= i < f for i in rel):
            problems.append("relative_features must index element features")
        rounds = network.get("rounds")
        if not isinstance(rounds, int) or not 1 <= rounds <= 16:
            problems.append("rounds must be an integer in [1, 16]")
        if network.get("aggregate", "mean") not in AGGREGATES:
            problems.append(f"aggregate must be one of {AGGREGATES}")
        chain("message", 2 * hidden + len(rel), hidden)
        update = network.get("update")
        if not isinstance(update, list) or len(update) != 1:
            problems.append("update must be exactly one dense layer")
        else:
            chain("update", 2 * hidden, hidden)
    return problems


def layer_plan(network: dict) -> Dict[str, list]:
    plan = {}
    for key in ("phi", "message", "update", "rho"):
        if network.get(key):
            plan[key] = [(len(l["weights"][0]), len(l["weights"]), str(l.get("activation", "none")))
                         for l in network[key]]
    return plan
