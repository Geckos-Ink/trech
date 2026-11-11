"""Independently validate a portable generic_surrogate model (trech_ml_validation_v1).

The trainer measures its own held-out error. This validator re-derives what can be
re-derived and checks what the trainer cannot check about itself, as a list of named
gates, each `pass`, `warn`, `fail` or `skip` (with the reason):

Static gates (pure Python; no NumPy/torch, so they run in every CTest environment):

- `structure`        the layer chain, scalers, activations and output links are loadable
                     by the C++ GenericSurrogate (same rules, re-implemented here);
- `finite_on_domain` a float64 forward pass is finite at the training mean, at each
                     feature's trained edge and at the joint covering centres;
- `trust_profile`    the model carries what the engine needs to grade a prediction:
                     measured hull, occupancy, joint reference, held-out R2 and per-output
                     RMSE (a missing block is a `warn`: the engine falls back to heuristics);

Run-based gates (need NumPy and `--test-runs`):

- `evaluator_parity`     the pure-Python forward pass and the trainer's NumPy path agree;
- `run_leakage`          training and test runs are different directories AND different
                         configurations (identical provenance `config_hash` = replayed events);
- `test_accuracy`        per-output test R2 >= `--min-r2` (default 0: beats predicting the
                         test mean);
- `holdout_reproduces`   when the carried holdout was measured on these same runs, the
                         recomputed metrics equal the carried ones (reproducibility);
- `beats_linear_baseline` a ridge map fitted on the same training runs does not beat the
                         model on the test runs (a structure that loses to linear is a warn);
- `sigma_calibration`    the carried 1-sigma RMSE (and any prediction interval) covers the
                         test residuals at roughly the claimed rate;
- `test_domain_coverage` how much of the test set lies inside the trained hull/occupied
                         bins/joint reference, with accuracy split in- and out-of-domain;

Optional: `torchscript_parity` (needs torch and a `.pt` twin) compares the TorchScript twin
with the JSON model on the static probe set.

A validation verdict never upgrades a model's trust label: a passing distilled operator is
still `measured:false`, and a passing learned model is still a comparison model, not Geant4.

`--scan DIR...` audits every committed generic_surrogate JSON with the static gates and writes
a deterministic JSON + Markdown audit (`--audit-json/--audit-md`); `--check` compares instead
of writing (the CTest staleness guard).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

SCHEMA = "trech_ml_validation_v1"
AUDIT_SCHEMA = "trech_ml_model_audit_v1"
MODEL_KINDS = ("generic_surrogate_v1", "generic_surrogate_v2")
# Names GenericSurrogate::parseActivation maps. The engine maps ANY other name to identity
# without complaint, so the validator fails an unknown name instead of letting a "gelu" layer
# silently run as a linear one.
ACTIVATIONS = ("none", "linear", "identity", "relu", "silu", "swish", "tanh", "sigmoid", "logistic")
LINKS = ("identity", "exp", "sigmoid")
DEFAULT_RADIUS = 3.0  # the engine's kDefaultStandardizedDomainRadius


# ---------------------------------------------------------------------------- model access

def load_model(path: Path) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def is_generic_surrogate(obj) -> bool:
    # Training manifests also name the model kind; only a model carries named features.
    return isinstance(obj, dict) and obj.get("model") in MODEL_KINDS and "input_features" in obj


def scalers(model: dict) -> Tuple[List[float], List[float], List[float], List[float]]:
    """Scalers with the engine's defaults: absent mean 0 / std 1, |input std| < 1e-12 -> 1."""
    n_in = len(model.get("input_features") or [])
    n_out = len(model.get("output_features") or [])
    xm = [float(v) for v in model.get("input_mean", [0.0] * n_in)]
    xs = [1.0 if abs(float(v)) < 1e-12 else float(v) for v in model.get("input_std", [1.0] * n_in)]
    ym = [float(v) for v in model.get("output_mean", [0.0] * n_out)]
    ys = [float(v) for v in model.get("output_std", [1.0] * n_out)]
    return xm, xs, ym, ys


def model_layers(model: dict) -> list:
    if model.get("model") == "generic_surrogate_v2":
        return (model.get("network") or {}).get("layers") or []
    return model.get("layers") or []


def output_links(model: dict) -> List[str]:
    outputs = model.get("output_features") or []
    if model.get("model") == "generic_surrogate_v2" and isinstance(model.get("output_transforms"), list):
        return list(model["output_transforms"])
    return ["identity"] * len(outputs)


def layer_plan(model: dict) -> List[Tuple[int, int, str]]:
    plan = []
    for layer in model_layers(model):
        weights = layer.get("weights") or []
        n_out = len(weights)
        n_in = len(weights[0]) if n_out and isinstance(weights[0], list) else 0
        plan.append((n_in, n_out, str(layer.get("activation", "none"))))
    return plan


def structure_label(plan: Sequence[Tuple[int, int, str]]) -> str:
    if not plan:
        return "empty"
    if len(plan) == 1 and plan[0][2] == "none":
        return "linear"
    hidden = plan[:-1]
    widths = [h[1] for h in hidden]
    acts = [h[2] for h in hidden]
    if len(set(widths)) == 1 and len(set(acts)) == 1:
        return f"mlp({widths[0]}x{len(widths)},{acts[0]})"
    if len(set(acts)) == 1:
        return "mlp(" + "-".join(str(w) for w in widths) + f",{acts[0]})"
    return "mlp(" + "-".join(f"{w}:{a}" for w, a in zip(widths, acts)) + ")"


def parameter_count(plan: Sequence[Tuple[int, int, str]]) -> int:
    return sum(i * o + o for i, o, _ in plan)


def _finite_list(values) -> bool:
    return isinstance(values, list) and all(isinstance(v, (int, float)) and math.isfinite(v) for v in values)


def _activate(name: str, v: float) -> float:
    if name == "relu":
        return v if v > 0 else 0.0
    if name in ("silu", "swish"):
        return v / (1.0 + math.exp(-v)) if v > -700 else 0.0
    if name == "tanh":
        return math.tanh(v)
    if name in ("sigmoid", "logistic"):
        return 1.0 / (1.0 + math.exp(-v)) if v > -700 else 0.0
    return v


def forward(model: dict, row: Sequence[float]) -> List[float]:
    """Float64 forward pass in plain Python, an evaluator independent of the NumPy path.

    Mirrors the engine: standardise, dense layers with per-layer activation, destandardise,
    then the v2 inverse link. Returns NaN/inf rather than raising so callers can grade it.
    """
    xm, xs, ym, ys = scalers(model)
    a = [(float(v) - m) / s for v, m, s in zip(row, xm, xs)]
    for layer in model_layers(model):
        act = str(layer.get("activation", "none"))
        nxt = []
        for weights, bias in zip(layer["weights"], layer["bias"]):
            total = float(bias)
            for w, v in zip(weights, a):
                total += float(w) * v
            try:
                nxt.append(_activate(act, total))
            except OverflowError:
                nxt.append(float("inf"))
        a = nxt
    out = []
    for i, (v, m, s) in enumerate(zip(a, ym, ys)):
        raw = v * s + m
        link = output_links(model)[i]
        if not math.isfinite(raw):
            out.append(raw)
        elif link == "exp":
            try:
                out.append(math.exp(raw))
            except OverflowError:
                out.append(float("inf"))
        elif link == "sigmoid":
            decay = math.exp(-abs(raw))
            out.append(1.0 / (1.0 + decay) if raw >= 0 else decay / (1.0 + decay))
        else:
            out.append(raw)
    return out


def probe_rows(model: dict) -> List[List[float]]:
    """Deterministic probe inputs inside the trained domain (raw units).

    The training mean, each feature moved to its trained minimum and maximum (others at the
    mean), and the joint covering centres. Without a measured hull, mean +/- 3 sigma.
    """
    xm, xs, _ym, _ys = scalers(model)
    domain = model.get("input_domain") or {}
    lo = domain.get("input_min") if _finite_list(domain.get("input_min")) and len(domain["input_min"]) == len(xm) else \
        [m - DEFAULT_RADIUS * s for m, s in zip(xm, xs)]
    hi = domain.get("input_max") if _finite_list(domain.get("input_max")) and len(domain["input_max"]) == len(xm) else \
        [m + DEFAULT_RADIUS * s for m, s in zip(xm, xs)]
    rows = [list(xm)]
    for i in range(len(xm)):
        for edge in (lo[i], hi[i]):
            row = list(xm)
            row[i] = float(edge)
            rows.append(row)
    joint = domain.get("joint") or {}
    for centre in joint.get("centers") or []:
        if _finite_list(centre) and len(centre) == len(xm):
            rows.append([m + z * s for m, z, s in zip(xm, centre, xs)])
    return rows


# ---------------------------------------------------------------------------- gate helpers

def gate(name: str, status: str, detail: str, **values) -> dict:
    record = {"name": name, "status": status, "detail": detail}
    record.update({k: v for k, v in values.items() if v is not None})
    return record


def overall(gates: Iterable[dict]) -> str:
    states = [g["status"] for g in gates]
    if "fail" in states:
        return "fail"
    if "warn" in states:
        return "warn"
    return "pass"


def _round(value, digits=6):
    if isinstance(value, float):
        if not math.isfinite(value):
            return None
        return float(f"{value:.{digits}g}")
    if isinstance(value, dict):
        return {k: _round(v, digits) for k, v in value.items()}
    if isinstance(value, list):
        return [_round(v, digits) for v in value]
    return value


# ---------------------------------------------------------------------------- static gates

def check_structure(model: dict) -> dict:
    problems = []
    inputs = model.get("input_features")
    outputs = model.get("output_features")
    if not isinstance(inputs, list) or not inputs or not isinstance(outputs, list) or not outputs:
        problems.append("missing input_features/output_features")
        return gate("structure", "fail", "; ".join(problems))
    n_in, n_out = len(inputs), len(outputs)
    # Absent scalers are legal (the engine uses mean 0 / std 1, e.g. hand-authored maps).
    for key, n in (("input_mean", n_in), ("input_std", n_in), ("output_mean", n_out), ("output_std", n_out)):
        if key not in model:
            continue
        values = model.get(key)
        if not _finite_list(values) or len(values) != n:
            problems.append(f"{key} must hold {n} finite numbers")
    encoded = model.get("model") == "generic_surrogate_v2"
    if encoded and not isinstance(model.get("network"), dict):
        problems.append("v2 model requires a nested network")
    if encoded and "output_transforms" not in model:
        problems.append("v2 model requires output_transforms")
    if not encoded and "output_transforms" in model:
        problems.append("output_transforms requires generic_surrogate_v2 (a v1 reader ignores them)")
    layers = model_layers(model)
    if encoded and "layers" in model:
        problems.append("v2 model also carries top-level layers (older readers would ignore its links)")
    if not layers:
        problems.append("no dense layers")
    previous = n_in
    for index, layer in enumerate(layers):
        weights, bias = layer.get("weights"), layer.get("bias")
        act = str(layer.get("activation", "none"))
        if act not in ACTIVATIONS:
            problems.append(f"layer {index} has unknown activation {act!r}")
        if not isinstance(weights, list) or not weights or not all(_finite_list(r) for r in weights):
            problems.append(f"layer {index} weights are missing or non-finite")
            break
        if any(len(r) != previous for r in weights):
            problems.append(f"layer {index} input width does not chain ({previous} expected)")
        if not _finite_list(bias) or len(bias) != len(weights):
            problems.append(f"layer {index} bias must match its {len(weights)} outputs")
        previous = len(weights)
    if layers and previous != n_out:
        problems.append(f"last layer emits {previous} values for {n_out} outputs")
    links = output_links(model)
    if len(links) != n_out or any(l not in LINKS for l in links):
        problems.append("output_transforms must give identity/exp/sigmoid per output")
    if problems:
        return gate("structure", "fail", "; ".join(problems))
    plan = layer_plan(model)
    return gate("structure", "pass", f"{structure_label(plan)}, {parameter_count(plan)} parameters, "
                f"{n_in} -> {n_out}", layer_plan=[list(p) for p in plan])


def check_finite(model: dict) -> Tuple[dict, List[List[float]]]:
    rows = probe_rows(model)
    bad = []
    for index, row in enumerate(rows):
        out = forward(model, row)
        if not all(math.isfinite(v) for v in out):
            bad.append(index)
    if bad:
        return gate("finite_on_domain", "fail", f"{len(bad)} of {len(rows)} in-domain probes give a "
                    "non-finite output", probes=len(rows), non_finite_probes=len(bad)), rows
    return gate("finite_on_domain", "pass", f"{len(rows)} in-domain probes (mean, per-feature edges, "
                "joint centres) are finite", probes=len(rows)), rows


def trust_profile(model: dict) -> dict:
    """Which trust blocks the engine can read from this model (see GenericSurrogate::coverage)."""
    n_in = len(model.get("input_features") or [])
    outputs = model.get("output_features") or []
    domain = model.get("input_domain") or {}
    radius = domain.get("standardized_radius")
    occupancy = domain.get("occupancy") or {}
    joint = domain.get("joint") or {}
    holdout = model.get("holdout") or {}
    rmse = holdout.get("rmse") or {}
    interval = model.get("prediction_interval") or {}
    note = model.get("note") if isinstance(model.get("note"), dict) else {}
    profile = {
        "measured_hull": _finite_list(radius) and len(radius) == n_in and n_in > 0,
        "occupancy": isinstance(occupancy.get("counts"), list) and len(occupancy["counts"]) == n_in and n_in > 0,
        "joint_reference": bool(joint.get("centers")) and isinstance(joint.get("radius"), (int, float)),
        "holdout_r2": isinstance(holdout.get("r2_min"), (int, float)),
        "per_output_rmse": isinstance(rmse, dict) and bool(outputs) and all(
            isinstance(rmse.get(o), (int, float)) for o in outputs),
        "scale_bands": bool(model.get("trained_scale_bands")),
        "prediction_interval": isinstance(interval.get("half_width"), dict) and
        isinstance(interval.get("nominal_coverage"), (int, float)),
        "measured_flag": note.get("measured") if isinstance(note.get("measured"), bool) else None,
    }
    return profile


ESSENTIAL_TRUST = ("measured_hull", "occupancy", "joint_reference", "holdout_r2", "per_output_rmse")


def trust_grade(profile: dict) -> str:
    present = sum(1 for key in ESSENTIAL_TRUST if profile[key])
    if present == len(ESSENTIAL_TRUST):
        return "complete"
    return "partial" if present else "none"


def check_trust(model: dict) -> dict:
    profile = trust_profile(model)
    missing = [key for key in ESSENTIAL_TRUST if not profile[key]]
    grade = trust_grade(profile)
    detail = ("engine can grade coverage, density, joint starvation and measured sigma"
              if not missing else "missing " + ", ".join(missing) +
              " (engine falls back to heuristic coverage / absent accuracy)")
    return gate("trust_profile", "pass" if not missing else "warn", detail, grade=grade, profile=profile)


def check_carried_accuracy(model: dict) -> dict:
    """What the model's OWN holdout says, read back without re-measuring anything."""
    holdout = model.get("holdout") or {}
    r2_min = holdout.get("r2_min")
    if not isinstance(r2_min, (int, float)):
        return gate("carried_accuracy", "skip", "the model carries no held-out R2")
    r2 = holdout.get("r2") if isinstance(holdout.get("r2"), dict) else {}
    worse = sorted(o for o, v in r2.items() if isinstance(v, (int, float)) and v < 0)
    if r2_min < 0:
        return gate("carried_accuracy", "warn",
                    f"its own holdout R2min is {r2_min:.4g}: " + (f"{len(worse)} output(s) " if worse else "an output ") +
                    "predict worse than the holdout mean", r2_min=_round(r2_min, 4),
                    outputs_below_zero=len(worse) or None)
    return gate("carried_accuracy", "pass", f"carried holdout R2min {r2_min:.4g} on "
                f"{holdout.get('n', '?')} rows", r2_min=_round(r2_min, 4))


def check_torchscript(model: dict, pt_path: Optional[Path], rows: List[List[float]]) -> dict:
    if not pt_path:
        return gate("torchscript_parity", "skip", "no TorchScript twin")
    try:
        import torch
    except ImportError:
        return gate("torchscript_parity", "skip", "torch is not installed")
    try:
        module = torch.jit.load(str(pt_path), map_location="cpu")
        module.eval()
        with torch.no_grad():
            out = module(torch.tensor(rows, dtype=torch.float32)).double().tolist()
    except Exception as exc:  # TorchScript load/eval failure is a real failure of the twin
        return gate("torchscript_parity", "fail", f"TorchScript twin failed: {exc}")
    worst = 0.0
    scales = [max(1.0, abs(float(s))) for s in scalers(model)[3]]
    for row, twin in zip(rows, out):
        ref = forward(model, row)
        for o, (a, b) in enumerate(zip(ref, twin)):
            rel = abs(a - b) / max(scales[o], abs(a))
            worst = max(worst, rel)
    status = "pass" if worst <= 1e-4 else "fail"
    return gate("torchscript_parity", status, f"max relative difference {worst:.3g} over {len(rows)} probes "
                "(float32 twin vs float64 JSON; tolerance 1e-4)", max_relative_difference=_round(worst))


def static_gates(model: dict, pt_path: Optional[Path] = None) -> Tuple[List[dict], List[List[float]]]:
    structure = check_structure(model)
    if structure["status"] == "fail":
        return [structure], []
    finite, rows = check_finite(model)
    gates = [structure, finite, check_trust(model), check_carried_accuracy(model)]
    return gates, rows


# ---------------------------------------------------------------------------- run-based gates

def _provenance_hash(run_dir: Path) -> Optional[str]:
    path = Path(run_dir) / "trech_provenance.jsonl"
    if not path.is_file():
        return None
    try:
        with path.open(encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if line:
                    record = json.loads(line)
                    if record.get("config_hash"):
                        return str(record["config_hash"])
                    # Older/synthetic provenance: the configuration text identifies the run.
                    if isinstance(record.get("config_json"), str):
                        return "sha256:" + hashlib.sha256(record["config_json"].encode()).hexdigest()[:16]
                    return None
    except (OSError, ValueError):
        return None
    return None


def check_leakage(train_dirs: List[Path], test_dirs: List[Path]) -> dict:
    train = {str(Path(p).resolve()) for p in train_dirs}
    test = {str(Path(p).resolve()) for p in test_dirs}
    shared = sorted(train & test)
    if shared:
        return gate("run_leakage", "fail", "the same run directory is used for training and testing",
                    shared_runs=shared)
    train_hashes = {_provenance_hash(Path(p)): p for p in train}
    test_hashes = {_provenance_hash(Path(p)): p for p in test}
    if None in train_hashes or None in test_hashes:
        return gate("run_leakage", "warn", "disjoint directories, but some runs have no provenance "
                    "config_hash, so a replayed configuration cannot be ruled out")
    replay = sorted(set(train_hashes) & set(test_hashes))
    if replay:
        return gate("run_leakage", "fail", "a test run has the same configuration (incl. seed) as a "
                    "training run: deterministic runs replay the same events", config_hashes=replay)
    return gate("run_leakage", "pass", f"{len(train)} training and {len(test)} test runs are distinct "
                "directories with distinct provenance config hashes")


def _encode(y, links):
    import numpy as np

    enc = y.copy()
    for i, link in enumerate(links):
        if link == "exp":
            enc[:, i] = np.log(y[:, i])
        elif link == "sigmoid":
            enc[:, i] = np.log(y[:, i]) - np.log1p(-y[:, i])
    return enc


def run_gates(model: dict, test_paths: List[str], training_paths: List[str], *, source: str,
              tag: Optional[str], expand: Optional[str], min_r2: float) -> Tuple[List[dict], dict]:
    import numpy as np
    from .dataset import harvest_table
    from .train_surrogate import build_xy, evaluate, fit_linear, predict_np

    inputs = list(model["input_features"])
    outputs = list(model["output_features"])
    links = output_links(model)
    layers = model_layers(model)
    model_scalers = tuple(np.asarray(v, dtype=float) for v in scalers(model))
    gates: List[dict] = []
    rows, metas = harvest_table(test_paths, source=source, tag=tag, expand=expand)
    x, y, dropped = build_xy(rows, inputs, outputs)
    test_dirs = [Path(m.run_dir) for m in metas]
    info: dict = {"runs": [_portable(p) for p in test_dirs], "rows": int(len(x)), "dropped_rows": int(dropped),
                  "source": source, "tag": tag, "expand": expand}

    # Two independent evaluators of the exported arithmetic must agree.
    numpy_pred = predict_np(x, layers, model_scalers, links)
    sample = list(range(0, len(x), max(1, len(x) // 64)))[:64]
    worst = 0.0
    for i in sample:
        ref = forward(model, x[i].tolist())
        for o, value in enumerate(ref):
            worst = max(worst, abs(value - numpy_pred[i, o]) / max(1.0, abs(value)))
    gates.append(gate("evaluator_parity", "pass" if worst <= 1e-9 else "fail",
                      f"pure-Python vs NumPy forward pass on {len(sample)} test rows: max relative "
                      f"difference {worst:.2g} (tolerance 1e-9)", max_relative_difference=_round(worst)))

    train_dirs: List[Path] = []
    train_xy = None
    if training_paths:
        train_rows, train_metas = harvest_table(training_paths, source=source, tag=tag, expand=expand)
        train_dirs = [Path(m.run_dir) for m in train_metas]
        try:
            train_xy = build_xy(train_rows, inputs, outputs)[:2]
        except SystemExit:
            train_xy = None
        gates.append(check_leakage(train_dirs, test_dirs))
        info["training_runs"] = [_portable(p) for p in train_dirs]
    else:
        gates.append(gate("run_leakage", "skip", "training runs unknown (pass --training-runs)"))

    metrics = evaluate(y, numpy_pred, outputs)
    info["metrics"] = _round(metrics)
    low = [o for o in outputs if metrics[o]["r2"] < min_r2]
    gates.append(gate("test_accuracy", "fail" if low else "pass",
                      ("R2 below " + f"{min_r2:g} for " + ", ".join(low)) if low else
                      f"every output reaches test R2 >= {min_r2:g} (worst "
                      f"{min(m['r2'] for m in metrics.values()):.4g})",
                      r2_min=_round(min(m["r2"] for m in metrics.values())), threshold=min_r2))

    holdout = model.get("holdout") or {}
    carried_runs = {str(Path(p).resolve()) for p in
                    ((model.get("trained_from") or {}).get("validation_runs") or [])}
    if carried_runs and carried_runs == {str(p.resolve()) for p in test_dirs} and isinstance(holdout.get("rmse"), dict):
        mismatch = []
        for o in outputs:
            carried = holdout["rmse"].get(o)
            if not isinstance(carried, (int, float)):
                continue
            if abs(carried - metrics[o]["rmse"]) > 1e-6 * max(1e-12, abs(carried)) + 1e-12:
                mismatch.append(o)
        gates.append(gate("holdout_reproduces", "fail" if mismatch else "pass",
                          ("recomputed RMSE differs from the carried holdout for " + ", ".join(mismatch))
                          if mismatch else "recomputed test metrics equal the carried holdout (same runs)"))
    else:
        gates.append(gate("holdout_reproduces", "skip", "the carried holdout was not measured on exactly these runs"))

    plan = layer_plan(model)
    if len(plan) == 1:
        gates.append(gate("beats_linear_baseline", "skip", "the model is itself linear"))
    elif train_xy is None or len(train_xy[0]) < 2:
        gates.append(gate("beats_linear_baseline", "skip", "no training rows to fit a linear baseline"))
    else:
        tx, ty = train_xy
        try:
            enc = _encode(ty, links)
            w, b, base_scalers = fit_linear(tx, enc, l2=1e-3)
            base_pred = predict_np(x, [{"weights": w.tolist(), "bias": b.tolist(), "activation": "none"}],
                                   base_scalers, links)
            base = evaluate(y, base_pred, outputs)
        except (ValueError, FloatingPointError, np.linalg.LinAlgError) as exc:
            gates.append(gate("beats_linear_baseline", "skip", f"linear baseline could not be fitted: {exc}"))
        else:
            skill = {}
            for o in outputs:
                mse_m, mse_b = metrics[o]["rmse"] ** 2, base[o]["rmse"] ** 2
                skill[o] = 1.0 - mse_m / mse_b if mse_b > 0 else (0.0 if mse_m == 0 else -math.inf)
            losers = [o for o, s in skill.items() if s < 0]
            gates.append(gate("beats_linear_baseline", "warn" if losers else "pass",
                              ("a ridge map on the same training runs is more accurate for " + ", ".join(losers) +
                               " (the extra structure does not pay for itself here)") if losers else
                              "lower test MSE than a ridge map fitted on the same training runs for every output",
                              skill_vs_linear=_round(skill), linear_r2={o: _round(base[o]["r2"]) for o in outputs}))

    residual = numpy_pred - y
    rmse = holdout.get("rmse") if isinstance(holdout.get("rmse"), dict) else {}
    if rmse and all(isinstance(rmse.get(o), (int, float)) and rmse.get(o) > 0 for o in outputs):
        calibration = {}
        flagged = []
        for i, o in enumerate(outputs):
            ratio = metrics[o]["rmse"] / rmse[o]
            within = float(np.mean(np.abs(residual[:, i]) <= rmse[o]))
            calibration[o] = {"test_over_carried_rmse": _round(ratio), "within_1_sigma": _round(within)}
            if ratio > 1.5 or ratio < 1 / 1.5:
                flagged.append(o)
        interval = model.get("prediction_interval") or {}
        nominal = interval.get("nominal_coverage")
        if isinstance(nominal, (int, float)) and isinstance(interval.get("half_width"), dict):
            for i, o in enumerate(outputs):
                half = interval["half_width"].get(o)
                if isinstance(half, (int, float)) and half >= 0:
                    cover = float(np.mean(np.abs(residual[:, i]) <= half))
                    calibration[o]["interval_coverage"] = _round(cover)
                    calibration[o]["interval_nominal"] = nominal
                    if cover < nominal - 0.1:
                        flagged.append(o + " (interval)")
        independent = not (carried_runs and carried_runs == {str(p.resolve()) for p in test_dirs})
        gates.append(gate("sigma_calibration", "warn" if flagged else "pass",
                          ("carried uncertainty mis-states the test error for " + ", ".join(flagged)) if flagged else
                          ("carried sigma within a factor 1.5 of the test RMSE" +
                           ("" if independent else " (measured on these same runs: not an independent check)")),
                          independent=independent, calibration=calibration))
    else:
        gates.append(gate("sigma_calibration", "skip", "the model carries no per-output RMSE"))

    gates.append(_coverage_gate(model, x, y, numpy_pred, outputs))
    return gates, info


def _coverage_gate(model: dict, x, y, pred, outputs) -> dict:
    import numpy as np
    from .train_surrogate import evaluate

    domain = model.get("input_domain") or {}
    xm, xs = (np.asarray(v, dtype=float) for v in scalers(model)[:2])
    z = (x - xm) / xs
    radius = domain.get("standardized_radius")
    measured = _finite_list(radius) and len(radius) == x.shape[1]
    r = np.asarray(radius, dtype=float) if measured else np.full(x.shape[1], DEFAULT_RADIUS)
    in_hull = np.all(np.abs(z) <= r + 1e-12, axis=1)
    starved = np.zeros(len(x), dtype=bool)
    occupancy = domain.get("occupancy") or {}
    counts = occupancy.get("counts")
    lo, hi = domain.get("input_min"), domain.get("input_max")
    if isinstance(counts, list) and _finite_list(lo) and _finite_list(hi):
        for i, bins in enumerate(counts):
            n = len(bins)
            if n == 0 or hi[i] <= lo[i]:
                continue
            idx = np.clip(((x[:, i] - lo[i]) / (hi[i] - lo[i]) * n).astype(int), 0, n - 1)
            inside = (x[:, i] >= lo[i]) & (x[:, i] <= hi[i])
            starved |= inside & (np.asarray(bins)[idx] == 0)
    joint = domain.get("joint") or {}
    jointly = np.ones(len(x), dtype=bool)
    if joint.get("centers") and isinstance(joint.get("radius"), (int, float)):
        centres = np.asarray(joint["centers"], dtype=float)
        dist = np.sqrt(((z[:, None, :] - centres[None, :, :]) ** 2).sum(axis=2)).min(axis=1)
        jointly = dist <= float(joint["radius"]) + 1e-12
    covered = in_hull & ~starved & jointly
    fractions = {"in_hull": _round(float(in_hull.mean())), "not_starved": _round(float((~starved).mean())),
                 "jointly_covered": _round(float(jointly.mean())), "fully_covered": _round(float(covered.mean()))}
    split = {}
    for label, mask in (("covered", covered), ("uncovered", ~covered)):
        if mask.sum() >= 2:
            split[label] = {o: {"rmse": _round(m["rmse"]), "r2": _round(m["r2"])}
                            for o, m in evaluate(y[mask], pred[mask], outputs).items()}
            split[label]["rows"] = int(mask.sum())
    status = "pass" if fractions["in_hull"] >= 0.5 else "warn"
    detail = (f"{fractions['fully_covered'] * 100:.0f}% of test rows inside the trained hull, occupied bins and "
              "joint reference" + ("" if measured else " (hull radius heuristic: model carries none)"))
    if status == "warn":
        detail += "; the test mostly exercises extrapolation, so its accuracy says little about the trained domain"
    return gate("test_domain_coverage", status, detail, fractions=fractions, accuracy_split=split,
                hull_measured=measured)


def _portable(path) -> str:
    resolved = Path(path).expanduser().resolve()
    try:
        return str(resolved.relative_to(Path.cwd().resolve()))
    except ValueError:
        return str(resolved)


def _sha256(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def model_summary(model: dict, path: Path) -> dict:
    plan = layer_plan(model)
    trained = model.get("trained_from") if isinstance(model.get("trained_from"), dict) else {}
    note = model.get("note") if isinstance(model.get("note"), dict) else {}
    return {
        "path": _portable(path), "sha256": _sha256(path), "kind": model.get("model"),
        "inputs": model.get("input_features"), "outputs": model.get("output_features"),
        "links": output_links(model), "structure": structure_label(plan),
        "parameter_count": parameter_count(plan),
        "trained_from": {k: trained.get(k) for k in ("runs", "validation_runs", "source", "tag", "model_kind", "seed")
                         if k in trained},
        "measured": note.get("measured") if isinstance(note.get("measured"), bool) else None,
        "teacher": note.get("teacher"),
    }


def validate(model_path: Path, *, torchscript: Optional[Path] = None, test_runs: Sequence[str] = (),
             training_runs: Sequence[str] = (), source: str = "scores", tag: Optional[str] = None,
             expand: Optional[str] = None, min_r2: float = 0.0) -> dict:
    model = load_model(model_path)
    if not is_generic_surrogate(model):
        raise SystemExit(f"{model_path}: not a generic_surrogate_v1/v2 model")
    gates, rows = static_gates(model)
    report = {"schema": SCHEMA, "model": model_summary(model, model_path), "gates": gates}
    if rows:
        if torchscript is None:
            twin = Path(model_path).with_suffix(".pt")
            torchscript = twin if twin.is_file() else None
        gates.append(check_torchscript(model, torchscript, rows))
        if test_runs:
            training = list(training_runs) or [p for p in (model.get("trained_from") or {}).get("runs") or []
                                               if Path(p).exists()]
            run_based, info = run_gates(model, list(test_runs), training, source=source, tag=tag,
                                        expand=expand, min_r2=min_r2)
            gates.extend(run_based)
            report["test"] = info
        else:
            gates.append(gate("test_accuracy", "skip", "no --test-runs given: static checks only"))
    report["status"] = overall(gates)
    return report


# ---------------------------------------------------------------------------- committed audit

def find_models(dirs: Iterable[Path]) -> List[Path]:
    found = []
    for base in dirs:
        for path in sorted(Path(base).rglob("*.json")):
            try:
                head = path.read_text(encoding="utf-8")
            except OSError:
                continue
            if '"generic_surrogate_v' not in head:
                continue
            try:
                obj = json.loads(head)
            except ValueError:
                continue
            if is_generic_surrogate(obj):
                found.append(path)
    return sorted(set(found))


def audit(dirs: Sequence[Path], root: Path) -> dict:
    models = []
    for path in find_models(dirs):
        model = load_model(path)
        gates, _rows = static_gates(model)
        profile = trust_profile(model) if gates[0]["status"] == "pass" else None
        holdout = model.get("holdout") or {}
        plan = layer_plan(model)
        note = model.get("note") if isinstance(model.get("note"), dict) else {}
        models.append({
            "path": path.resolve().relative_to(root.resolve()).as_posix(),
            "sha256": _sha256(path),
            "kind": model.get("model"),
            "inputs": len(model.get("input_features") or []),
            "outputs": len(model.get("output_features") or []),
            "structure": structure_label(plan),
            "parameter_count": parameter_count(plan),
            "holdout_r2_min": _round(holdout.get("r2_min"), 4) if isinstance(holdout.get("r2_min"), (int, float)) else None,
            "holdout_n": holdout.get("n") if isinstance(holdout.get("n"), int) else None,
            "measured": note.get("measured") if isinstance(note.get("measured"), bool) else None,
            "trust": trust_grade(profile) if profile else "invalid",
            "profile": profile,
            "status": overall(gates),
            "gates": {g["name"]: g["status"] for g in gates},
            "problems": [f"{g['name']}: {g['detail']}" for g in gates if g["status"] == "fail"],
            "accuracy_warnings": [g["detail"] for g in gates if g["name"] == "carried_accuracy" and g["status"] == "warn"],
        })
    totals = {
        "models": len(models),
        "structure_ok": sum(1 for m in models if m["gates"].get("structure") == "pass"),
        "finite_on_domain": sum(1 for m in models if m["gates"].get("finite_on_domain") == "pass"),
        "trust_complete": sum(1 for m in models if m["trust"] == "complete"),
        "trust_partial": sum(1 for m in models if m["trust"] == "partial"),
        "trust_none": sum(1 for m in models if m["trust"] == "none"),
        "failing": sum(1 for m in models if m["status"] == "fail"),
        "distilled_measured_false": sum(1 for m in models if m["measured"] is False),
        "carried_r2_negative": sum(1 for m in models if m["gates"].get("carried_accuracy") == "warn"),
    }
    for key in ("measured_hull", "occupancy", "joint_reference", "holdout_r2", "per_output_rmse",
                "scale_bands", "prediction_interval"):
        totals["with_" + key] = sum(1 for m in models if m["profile"] and m["profile"][key])
    return {"schema": AUDIT_SCHEMA, "scanned": [Path(d).resolve().relative_to(root.resolve()).as_posix() for d in dirs],
            "totals": totals, "models": models}


def audit_markdown(data: dict, regenerate: str) -> str:
    t = data["totals"]
    yes = lambda v: "yes" if v else "—"  # noqa: E731
    lines = [
        "# Committed ML model audit",
        "",
        "<!-- Generated; do not edit. Regenerate with:",
        f"     {regenerate}",
        "     CTest `trech_ml_model_audit` fails when this file is stale. -->",
        "",
        "Static validation of every committed `generic_surrogate` model under "
        + ", ".join(f"`{d}/`" for d in data["scanned"]) + " by "
        "[`validate_model.py`](../tools/torch/trech_torch/validate_model.py) "
        "([contract](ml_models.md#validating-a-model)). It checks that each model loads under the engine's rules, "
        "stays finite across its own trained domain, and carries the trust blocks the engine grades predictions "
        "with. It does **not** re-measure accuracy: that needs the model's independent test runs "
        "(`trech-ml validate`). A complete trust profile is not a validity claim; `measured:false` models are "
        "distilled from an authored teacher.",
        "",
        "## Totals",
        "",
        "| Measure | Count |",
        "| --- | ---: |",
        f"| Models scanned | {t['models']} |",
        f"| Load under engine rules (`structure`) | {t['structure_ok']} |",
        f"| Finite on their trained domain | {t['finite_on_domain']} |",
        f"| Failing a static gate | {t['failing']} |",
        f"| Trust profile complete / partial / none | {t['trust_complete']} / {t['trust_partial']} / {t['trust_none']} |",
        f"| Measured hull | {t['with_measured_hull']} |",
        f"| Occupancy histogram | {t['with_occupancy']} |",
        f"| Joint reference | {t['with_joint_reference']} |",
        f"| Held-out R² | {t['with_holdout_r2']} |",
        f"| Per-output measured σ (RMSE) | {t['with_per_output_rmse']} |",
        f"| Trained scale bands | {t['with_scale_bands']} |",
        f"| Calibrated prediction interval | {t['with_prediction_interval']} |",
        f"| Own holdout R²min below 0 (worse than the mean on some output) | {t['carried_r2_negative']} |",
        f"| Labelled `measured:false` (distilled) | {t['distilled_measured_false']} |",
        "",
        "## Models",
        "",
        "| Model | Structure | Params | Hull | Occ. | Joint | R²min (n) | σ | Bands | measured | Trust | Status |",
        "| --- | --- | ---: | --- | --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for m in data["models"]:
        p = m["profile"] or {}
        r2 = "—" if m["holdout_r2_min"] is None else f"{m['holdout_r2_min']:.4f}" + (
            f" ({m['holdout_n']})" if m["holdout_n"] is not None else "")
        measured = "—" if m["measured"] is None else str(m["measured"]).lower()
        lines.append(
            f"| `{m['path']}` | {m['structure']} {m['inputs']}→{m['outputs']} | {m['parameter_count']} | "
            f"{yes(p.get('measured_hull'))} | {yes(p.get('occupancy'))} | {yes(p.get('joint_reference'))} | {r2} | "
            f"{yes(p.get('per_output_rmse'))} | {yes(p.get('scale_bands'))} | {measured} | {m['trust']} | {m['status']} |")
    problems = [(m["path"], p) for m in data["models"] for p in m["problems"]]
    lines += ["", "## Problems", ""]
    lines += [f"- `{path}` — {p}" for path, p in problems] if problems else ["None: every scanned model passes the static gates."]
    warnings = [(m["path"], w) for m in data["models"] for w in m["accuracy_warnings"]]
    lines += ["", "## Accuracy warnings (from the models' own carried holdout)", ""]
    lines += [f"- `{path}` — {w}" for path, w in warnings] if warnings else ["None."]
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------- CLI

def _print_gates(report: dict) -> None:
    print(f"{report['model']['path']}: {report['model']['structure']} -> {report['status'].upper()}")
    for g in report["gates"]:
        print(f"  {g['status']:>4}  {g['name']}: {g['detail']}")


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--model", help="generic_surrogate JSON to validate")
    ap.add_argument("--torchscript", default=None, help="TorchScript twin (default: sibling .pt if present)")
    ap.add_argument("--test-runs", nargs="+", default=[], help="independent test run dirs")
    ap.add_argument("--training-runs", nargs="+", default=[],
                    help="training run dirs (default: the model's trained_from.runs when they exist)")
    ap.add_argument("--source", default=None, choices=["scores", "event_features", "hook_emits"],
                    help="harvest source (default: the model's trained_from.source)")
    ap.add_argument("--tag", default=None)
    ap.add_argument("--expand", default=None)
    ap.add_argument("--min-r2", type=float, default=0.0, help="test R2 every output must reach (default 0)")
    ap.add_argument("--out", default=None, help="write the JSON report here")
    ap.add_argument("--scan", nargs="+", default=None, help="audit every generic_surrogate JSON under these dirs")
    ap.add_argument("--root", default=".", help="repository root for audit paths")
    ap.add_argument("--audit-json", default=None)
    ap.add_argument("--audit-md", default=None)
    ap.add_argument("--check", action="store_true", help="compare the audit with the committed files")
    args = ap.parse_args(argv)

    if args.scan:
        root = Path(args.root)
        data = audit([root / d for d in args.scan], root)
        regenerate = ("python3 -m trech_torch.validate_model --scan " + " ".join(args.scan) +
                      " --audit-json docs/ml_model_audit.json --audit-md docs/ml_model_audit.md"
                      " (with PYTHONPATH=tools/torch)")
        rendered = {args.audit_json: json.dumps(data, indent=2, sort_keys=True) + "\n" if args.audit_json else None,
                    args.audit_md: audit_markdown(data, regenerate) if args.audit_md else None}
        stale = []
        for target, text in rendered.items():
            if not target or text is None:
                continue
            path = root / target
            if args.check:
                if not path.is_file() or path.read_text(encoding="utf-8") != text:
                    stale.append(target)
            else:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(text, encoding="utf-8")
        t = data["totals"]
        print(f"{t['models']} models: {t['failing']} failing, trust complete/partial/none "
              f"{t['trust_complete']}/{t['trust_partial']}/{t['trust_none']}")
        if stale:
            print("stale: " + ", ".join(stale) + "\nregenerate: " + regenerate, file=sys.stderr)
            return 1
        return 1 if t["failing"] else 0

    if not args.model:
        ap.error("--model or --scan is required")
    model = load_model(Path(args.model))
    trained = (model.get("trained_from") or {}) if isinstance(model, dict) else {}
    report = validate(Path(args.model), torchscript=Path(args.torchscript) if args.torchscript else None,
                      test_runs=args.test_runs, training_runs=args.training_runs,
                      source=args.source or trained.get("source") or "scores",
                      tag=args.tag if args.tag is not None else trained.get("tag"),
                      expand=args.expand, min_r2=args.min_r2)
    _print_gates(report)
    if args.out:
        out = Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return 1 if report["status"] == "fail" else 0


if __name__ == "__main__":
    sys.exit(main())
