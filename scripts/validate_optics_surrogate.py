#!/usr/bin/env python3
"""Held-out validation of the optics surrogate / training track.

The MolecularOptics extractor derives the visible refractive index from Geant4
atomic cross sections plus an f-sum-rule valence oscillator (see
``docs/viz_refraction.md``). One *global* oscillator energy gets the
electron-density scale right but leaves a material-specific residual: it nails
water / silica but, e.g., under-predicts polystyrene and over-predicts PTFE.

The ROADMAP anti-degeneration "training / inference" workstream says to learn
that residual from data and to *promote a surrogate only when it recovers
materially more refraction than the extractor, without overfitting*. This script
is that gate. From the curated panel run
(``examples/experiments/optics_training_panel.js``) it:

  1. tabulates, per material, the extractor's derived n vs a handbook anchor;
  2. runs a **leave-one-out** experiment: train a small ridge model on the
     Geant4-derived element composition + density -> handbook n using every
     material *except one*, predict the held-out material, and repeat. This
     measures how well a data-driven model GENERALISES to a composition it never
     saw, with no possibility of memorising it.
  3. compares mean |n - handbook| for the physics extractor vs the held-out
     surrogate, and reports whether training recovers materially more refraction.

The handbook indices live ONLY here (a validation target); they never feed the
engine's photon transport, which always uses the derived n. Run:

    python3 scripts/validate_optics_surrogate.py --run build/dev/out_optics_panel

Outputs docs/validation_optics_surrogate.md + a diff-friendly benchmark txt.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np

# Handbook visible-band (~589 nm) refractive indices for the panel materials.
# Loaded from the shared anchors file (single source of truth, also used by the
# trainer). These are validation/training targets only and never feed transport.
_ANCHORS_PATH = Path(__file__).resolve().parent.parent / "data" / "optics_handbook_anchors.json"


def _load_handbook() -> Dict[str, float]:
    try:
        doc = json.loads(_ANCHORS_PATH.read_text())
        return {k.lower(): float(v)
                for k, v in (doc.get("refractive_index_589nm") or {}).items()}
    except (OSError, json.JSONDecodeError) as exc:
        print(f"error: cannot load anchors {_ANCHORS_PATH}: {exc}", file=sys.stderr)
        return {}


HANDBOOK_N: Dict[str, float] = _load_handbook()

# Element feature order (matches OpticsSurrogate::kCompositionElements minus the
# trailing "other"; unknown elements fold into "other").
ELEMENTS = ["H", "C", "N", "O", "F", "Na", "Mg", "Al", "Si", "P", "S", "Cl", "I"]


def load_panel(run_dir: Path) -> List[dict]:
    """Return one record per panel material with derived n, composition, density."""
    scene = json.loads((run_dir / "trech_viz_scene.json").read_text())
    out: List[dict] = []
    seen = set()
    for d in scene.get("derived_optics") or []:
        key = (d.get("config_material_key") or "").lower()
        if key not in HANDBOOK_N or key in seen:
            continue
        if not d.get("available", True):
            continue
        seen.add(key)
        out.append({
            "name": key,
            "n_derived": float(d.get("mean_refractive_index") or 1.0),
            "density": float(d.get("density_gcm3") or 0.0),
            "fractions": d.get("element_mass_fractions") or {},
            "handbook": HANDBOOK_N[key],
        })
    return out


def feature_vector(rec: dict) -> np.ndarray:
    vec = np.zeros(len(ELEMENTS) + 2, dtype=float)  # elements + "other" + density
    for sym, frac in rec["fractions"].items():
        if sym in ELEMENTS:
            vec[ELEMENTS.index(sym)] += float(frac)
        else:
            vec[len(ELEMENTS)] += float(frac)
    vec[-1] = rec["density"]
    return vec


def ridge_fit(x: np.ndarray, y: np.ndarray, lam: float) -> Tuple[np.ndarray, float, np.ndarray, np.ndarray]:
    """Standardised ridge regression. Returns (weights, bias, mean, std)."""
    mean = x.mean(axis=0)
    std = x.std(axis=0)
    std[std < 1e-9] = 1.0
    xs = (x - mean) / std
    n_feat = xs.shape[1]
    a = xs.T @ xs + lam * np.eye(n_feat)
    b = xs.T @ (y - y.mean())
    w = np.linalg.solve(a, b)
    return w, float(y.mean()), mean, std


def ridge_predict(rec_x: np.ndarray, w: np.ndarray, bias: float,
                  mean: np.ndarray, std: np.ndarray) -> float:
    xs = (rec_x - mean) / std
    return float(xs @ w + bias)


def leave_one_out(records: List[dict], lam: float) -> List[dict]:
    """Per material: predict its handbook n from a ridge model trained on all
    the *other* materials' (composition, density) -> handbook n."""
    rows: List[dict] = []
    feats = np.array([feature_vector(r) for r in records])
    targets = np.array([r["handbook"] for r in records])
    for i, rec in enumerate(records):
        train_idx = [j for j in range(len(records)) if j != i]
        w, bias, mean, std = ridge_fit(feats[train_idx], targets[train_idx], lam)
        pred = ridge_predict(feats[i], w, bias, mean, std)
        rows.append({
            "name": rec["name"],
            "handbook": rec["handbook"],
            "n_extractor": rec["n_derived"],
            "n_surrogate_loo": pred,
            "err_extractor": rec["n_derived"] - rec["handbook"],
            "err_surrogate": pred - rec["handbook"],
        })
    return rows


def _recovered(n_pred: float, n_hand: float) -> float:
    denom = n_hand - 1.0
    return (n_pred - 1.0) / denom if abs(denom) > 1e-9 else float("nan")


def export_ridge(records: List[dict], lam: float, out_path: Path) -> dict:
    """Fit the ridge on the FULL panel and write deployable coefficients.

    The C++ OpticsSurrogate ridge backend (no LibTorch) loads this JSON via
    optics.derive.surrogateModelPath and evaluates
    n = bias + sum_i w_i * (x_i - mean_i)/std_i with the same standardisation.
    The element order must match OpticsSurrogate::kCompositionElements; the 15th
    feature (density) is implicit after the 14 named element slots.
    """
    feats = np.array([feature_vector(r) for r in records])
    targets = np.array([r["handbook"] for r in records])
    w, bias, mean, std = ridge_fit(feats, targets, lam)
    model = {
        "model": "ridge_optics_n_v1",
        "elements": ELEMENTS + ["other"],  # 14 names; density is the implicit 15th feature
        "feature_count": int(len(w)),
        "weights": [float(x) for x in w],
        "mean": [float(x) for x in mean],
        "std": [float(x) for x in std],
        "bias": float(bias),
        "ridge_lambda": float(lam),
        "materials_trained": int(len(records)),
        "note": ("composition (+density) -> handbook n@589nm, standardised ridge, "
                 "trained on the full optics panel. Anchor-trained: leave-one-out "
                 "validated for generalisation; memorises in-panel materials. "
                 "Deploy via optics.derive.surrogateModelPath (opt-in)."),
    }
    out_path = Path(out_path).expanduser()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(model, indent=2) + "\n", encoding="utf-8")
    return model


def run(args: argparse.Namespace) -> int:
    run_dir = Path(args.run).expanduser().resolve()
    records = load_panel(run_dir)
    if len(records) < 4:
        print(f"error: only {len(records)} panel materials found in {run_dir}",
              file=sys.stderr)
        return 2

    if getattr(args, "export", None):
        model = export_ridge(records, args.ridge_lambda, Path(args.export))
        print(f"==> Exported ridge model ({model['materials_trained']} materials, "
              f"{model['feature_count']} features) to {args.export}")

    rows = leave_one_out(records, lam=args.ridge_lambda)

    # Aggregate: mean absolute index error and mean recovered-refraction fraction.
    mae_ext = float(np.mean([abs(r["err_extractor"]) for r in rows]))
    mae_sur = float(np.mean([abs(r["err_surrogate"]) for r in rows]))
    rec_ext = float(np.mean([abs(_recovered(r["n_extractor"], r["handbook"]) - 1.0) for r in rows]))
    rec_sur = float(np.mean([abs(_recovered(r["n_surrogate_loo"], r["handbook"]) - 1.0) for r in rows]))
    improved = mae_sur < mae_ext

    summary = {
        "run_dir": str(run_dir),
        "materials": len(rows),
        "ridge_lambda": args.ridge_lambda,
        "mae_extractor": mae_ext,
        "mae_surrogate_loo": mae_sur,
        "mean_abs_recovery_miss_extractor": rec_ext,
        "mean_abs_recovery_miss_surrogate": rec_sur,
        "surrogate_improves_over_extractor": improved,
        "rows": rows,
    }

    md = render_markdown(summary)
    txt = render_text(summary)
    if args.no_write:
        print(md)
    else:
        report = Path(args.report).expanduser()
        report.parent.mkdir(parents=True, exist_ok=True)
        report.write_text(md, encoding="utf-8")
        sidecar = Path(args.json).expanduser()
        sidecar.write_text(json.dumps(summary, indent=2), encoding="utf-8")
        txt_path = Path(args.txt).expanduser()
        txt_path.parent.mkdir(parents=True, exist_ok=True)
        txt_path.write_text(txt, encoding="utf-8")
        print(f"==> Report:    {report}")
        print(f"==> Sidecar:   {sidecar}")
        print(f"==> Reference: {txt_path}")
        print(f"extractor MAE={mae_ext:.4f}  surrogate(LOO) MAE={mae_sur:.4f}  "
              f"improved={improved}")
    return 0


def _fmt(x: float, d: int = 4, signed: bool = False) -> str:
    if x is None or (isinstance(x, float) and not math.isfinite(x)):
        return "n/a"
    return f"{x:+.{d}f}" if signed else f"{x:.{d}f}"


def render_markdown(s: dict) -> str:
    L: List[str] = []
    L.append("# Optics Surrogate — Held-Out Validation")
    L.append("")
    L.append(f"- Panel run: `{s['run_dir']}`")
    L.append(f"- Materials: {s['materials']}  ·  ridge λ = {s['ridge_lambda']}")
    L.append("")
    L.append("Leave-one-out: each material's handbook n is predicted by a ridge")
    L.append("model trained on the Geant4-derived composition (+density) of every")
    L.append("*other* material. This tests whether a data-driven optical model")
    L.append("generalises the material-specific dispersion the single global")
    L.append("valence-oscillator energy cannot. Handbook n is a validation target")
    L.append("only — the engine's photon transport always uses the derived n.")
    L.append("")
    L.append("| Material | handbook n | extractor n | Δ extractor | surrogate n (LOO) | Δ surrogate |")
    L.append("|---|---:|---:|---:|---:|---:|")
    for r in s["rows"]:
        L.append("| {m} | {h} | {e} | {de} | {sg} | {ds} |".format(
            m=r["name"], h=_fmt(r["handbook"], 3), e=_fmt(r["n_extractor"], 4),
            de=_fmt(r["err_extractor"], 4, True), sg=_fmt(r["n_surrogate_loo"], 4),
            ds=_fmt(r["err_surrogate"], 4, True)))
    L.append("")
    L.append("## Verdict")
    L.append("")
    L.append(f"- Mean |n − handbook|: **extractor {s['mae_extractor']:.4f}** vs "
             f"**held-out surrogate {s['mae_surrogate_loo']:.4f}**")
    if s["surrogate_improves_over_extractor"]:
        L.append("- The held-out surrogate recovers **materially more** refraction "
                 "than the physics extractor alone: learning the residual from the "
                 "Geant4-derived composition generalises to unseen materials. This "
                 "is the promotion signal the ROADMAP inference workstream asks for.")
    else:
        L.append("- The held-out surrogate does **not** beat the extractor on this "
                 "panel — either the panel is too small/narrow or the residual is "
                 "not composition-predictable at this resolution. Do not promote; "
                 "grow the panel or add a microscale visible-band sub-simulation.")
    L.append("")
    return "\n".join(L)


def render_text(s: dict) -> str:
    L: List[str] = []
    L.append("TRECH benchmark reference: Optics Surrogate Held-Out Validation")
    L.append("==============================================================")
    L.append("")
    L.append(f"Panel materials: {s['materials']}   ridge lambda: {s['ridge_lambda']}")
    L.append("Leave-one-out composition(+density) -> handbook n (ridge).")
    L.append("Handbook n is a validation target only; transport uses derived n.")
    L.append("")
    L.append(f"  {'material':<14}{'handbook':>10}{'extractor':>11}{'d_ext':>10}{'surrogate':>11}{'d_sur':>10}")
    for r in s["rows"]:
        L.append(f"  {r['name']:<14}{_fmt(r['handbook'],3):>10}{_fmt(r['n_extractor'],4):>11}"
                 f"{_fmt(r['err_extractor'],4,True):>10}{_fmt(r['n_surrogate_loo'],4):>11}"
                 f"{_fmt(r['err_surrogate'],4,True):>10}")
    L.append("")
    L.append(f"  mean |n-handbook|  extractor={s['mae_extractor']:.4f}  "
             f"surrogate(LOO)={s['mae_surrogate_loo']:.4f}")
    L.append(f"  surrogate improves over extractor: {s['surrogate_improves_over_extractor']}")
    L.append("")
    L.append("Regenerate:")
    L.append("  ./build/dev/trech run examples/experiments/optics_training_panel.js \\")
    L.append("      --events 1 --output build/dev/out_optics_panel")
    L.append("  python3 scripts/validate_optics_surrogate.py --run build/dev/out_optics_panel")
    L.append("")
    return "\n".join(L)


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--run", default="build/dev/out_optics_panel",
                    help="panel output dir (trech_viz_scene.json with derived_optics)")
    ap.add_argument("--ridge-lambda", type=float, default=1.0,
                    help="ridge regularisation strength (small panel -> keep firm)")
    ap.add_argument("--report", default="docs/validation_optics_surrogate.md")
    ap.add_argument("--json", default="docs/validation_optics_surrogate.json")
    ap.add_argument("--txt", default="docs/benchmarks/validation_optics_surrogate.txt")
    ap.add_argument("--no-write", action="store_true")
    ap.add_argument("--export", default=None,
                    help="fit the ridge on the full panel and write deployable "
                         "coefficients JSON to this path (for the C++ "
                         "OpticsSurrogate ridge backend, no LibTorch)")
    return run(ap.parse_args(argv))


if __name__ == "__main__":
    sys.exit(main())
