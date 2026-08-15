"""Plan the next Geant4 experiments needed to improve TRECH's trained models.

This is the active-learning half of the scale-up loop in CHARTS.md: instead of
guessing which simulations to run, analyse the training data Geant4 has already
produced, find where the learned predictors are starved (coverage gaps,
extrapolation zones, degenerate labels), and emit a ranked machine-readable
plan of concrete simulation requests.  Each recommendation names the scenario
(or config levers) that would generate the missing training signal, so a human
or an orchestrator can execute the plan with `trech run`.

Diagnostics implemented (all deterministic):

Optics surrogate (material scale — needs an `optics.derive` panel run):
- element coverage: composition-vector slots exercised by <2 materials mean
  the per-element weight rests on a single sample;
- density extrapolation: >10x gaps in the sorted density ladder are OOD zones
  (the known air failure: 0.0012 g/cm3 vs a 0.9-4 g/cm3 panel);
- leave-one-out hotspots: materials the held-out ridge predicts worst are the
  neighbourhoods where more compositions are needed;
- unanchored materials: panel entries without a handbook anchor contribute no
  residual-learning signal.

Event stratifier (event scale — needs stratify.dumpFeatures runs):
- label balance: near-single-class teacher labels make classification
  unlearnable (fix thresholds, or vary beam.spread / beam.spectrum);
- degenerate features: zero-variance feature slots (e.g. optical_* with optics
  off) silently shrink the usable schema;
- dataset size and beam-energy variety;
- dimension-scale coverage: which bands (atomic/nano/micro/meso/macro) have
  produced labeled events at all, with a suggested bundled scenario per
  uncovered band.

Trained models (`--models`, any generic_surrogate_v1 JSON):
- per-feature starved bins: ranges inside the trained hull the training set
  never populated;
- JOINT starved regions: the gaps between the regions training actually
  covered -- the holes a point can fall into while passing every per-feature
  check. Each is reported as a concrete operating point in the model's own raw
  input units, i.e. a run to actually perform;
- models carrying no joint reference at all (retrain to export one).

Usage:

    python -m trech_torch.plan_experiments \
        --optics-run build/dev/out_optics_panel \
        --anchors data/optics_handbook_anchors.json \
        --runs build/dev/out_stratify_* \
        --out build/dev/geant4_experiment_plan.json

    python -m trech_torch.plan_experiments \
        --models data/discrete_operators/*.json \
        --out build/dev/model_gaps.json
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path
from typing import Dict, List, Optional, Sequence

import numpy as np

from .dataset import (
    COMPOSITION_ELEMENTS,
    FEATURE_NAMES,
    OpticsSample,
    RunMetadata,
    find_scene_manifests,
    harvest_event_dataset,
    harvest_optics_samples,
    load_anchors,
)

PLAN_SCHEMA = "trech_geant4_experiment_plan_v1"

# A bundled scenario per dimension-scale band, so scale-coverage
# recommendations point at something runnable out of the box.
SCALE_BAND_SCENARIOS = {
    "atomic": "examples/experiments/h2o_molecule_stability.js",
    "nano": "examples/experiments/config_cnt_stub.js",
    "micro": "examples/experiments/testscenario_efflux.js",
    "meso": "examples/experiments/glass_of_water_varied.js",
}


def _rec(severity: float, kind: str, reason: str, action: str,
         scenario: Optional[str] = None, details: Optional[dict] = None) -> dict:
    return {
        "severity": round(float(severity), 3),
        "kind": kind,
        "reason": reason,
        "geant4_experiment": {
            "scenario": scenario,
            "action": action,
        },
        "details": details or {},
    }


# ---------------------------------------------------------------------------
# Optics-panel diagnostics
# ---------------------------------------------------------------------------


def _ridge_loo_errors(samples: List[OpticsSample], lam: float) -> List[dict]:
    """Held-out |n error| per material (standardised ridge, numpy)."""
    feats = np.array([s.composition_vector for s in samples], dtype=float)
    targets = np.array([s.targets[0] for s in samples], dtype=float)
    rows: List[dict] = []
    for i in range(len(samples)):
        idx = [j for j in range(len(samples)) if j != i]
        x, y = feats[idx], targets[idx]
        mean = x.mean(axis=0)
        std = x.std(axis=0)
        std[std < 1e-9] = 1.0
        xs = (x - mean) / std
        a = xs.T @ xs + lam * np.eye(xs.shape[1])
        b = xs.T @ (y - y.mean())
        w = np.linalg.solve(a, b)
        pred = float(((feats[i] - mean) / std) @ w + y.mean())
        rows.append({
            "material": samples[i].material_name,
            "target_n": float(targets[i]),
            "loo_n": pred,
            "abs_err": abs(pred - float(targets[i])),
        })
    return rows


def analyze_optics(samples: List[OpticsSample], anchors: Dict[str, float],
                   ridge_lambda: float) -> tuple[dict, List[dict]]:
    recs: List[dict] = []
    report: dict = {"n_materials": len(samples)}
    if len(samples) < 4:
        recs.append(_rec(
            1.0, "optics_panel_too_small",
            f"only {len(samples)} materials in the optics panel; nothing to "
            "generalise from",
            "extend examples/experiments/optics_training_panel.js with more "
            "materials (composition + density) and rerun with "
            "optics.derive.enable",
            scenario="examples/experiments/optics_training_panel.js"))
        return report, recs

    # Element coverage: slots carried by fewer than 2 materials.
    feats = np.array([s.composition_vector for s in samples], dtype=float)
    thin_elements = []
    for i, element in enumerate(COMPOSITION_ELEMENTS):
        carriers = int((feats[:, i] > 0.01).sum())
        if 0 < carriers < 2:
            thin_elements.append({"element": element, "materials": carriers})
    report["thin_elements"] = thin_elements
    for entry in thin_elements:
        recs.append(_rec(
            0.7, "optics_element_coverage",
            f"element {entry['element']} appears in only "
            f"{entry['materials']} panel material(s); its learned weight "
            "rests on a single Geant4-derived composition",
            f"add 1-2 more materials containing {entry['element']} to the "
            "optics panel and rerun the derivation",
            scenario="examples/experiments/optics_training_panel.js",
            details=entry))

    # Density ladder: >10x gaps flag extrapolation zones.
    densities = sorted(float(s.composition_vector[-1]) for s in samples)
    report["density_range_gcm3"] = [densities[0], densities[-1]]
    gaps = []
    for lo, hi in zip(densities, densities[1:]):
        if lo > 0 and hi / lo > 10.0:
            gaps.append({"from_gcm3": lo, "to_gcm3": hi, "ratio": hi / lo})
    report["density_gaps"] = gaps
    for gap in gaps:
        mid = math.sqrt(gap["from_gcm3"] * gap["to_gcm3"])
        recs.append(_rec(
            0.8, "optics_density_extrapolation",
            f"no panel material between {gap['from_gcm3']:.4g} and "
            f"{gap['to_gcm3']:.4g} g/cm3 ({gap['ratio']:.0f}x gap); "
            "predictions in this band extrapolate (the known air-OOD "
            "failure mode)",
            f"add materials near ~{mid:.3g} g/cm3 (e.g. aerogels, foams, "
            "low-pressure gases) to the optics panel",
            scenario="examples/experiments/optics_training_panel.js",
            details=gap))

    # LOO hotspots: worst held-out materials need compositional neighbours.
    loo = _ridge_loo_errors(samples, ridge_lambda)
    loo_sorted = sorted(loo, key=lambda r: (-r["abs_err"], r["material"]))
    report["loo_errors"] = loo_sorted
    for row in loo_sorted[:3]:
        if row["abs_err"] < 0.02:
            continue
        recs.append(_rec(
            min(0.75, 0.4 + row["abs_err"]), "optics_loo_hotspot",
            f"held-out ridge misses {row['material']} by |dn|="
            f"{row['abs_err']:.3f}; its composition neighbourhood is "
            "under-sampled",
            f"simulate 2-3 materials compositionally similar to "
            f"{row['material']} (same dominant elements, varied density) in "
            "the optics panel",
            scenario="examples/experiments/optics_training_panel.js",
            details=row))

    # Unanchored materials contribute no residual-learning target.
    unanchored = sorted(s.material_name for s in samples if not s.anchored)
    report["unanchored_materials"] = unanchored
    if anchors and unanchored:
        recs.append(_rec(
            0.5, "optics_missing_anchor",
            f"{len(unanchored)} panel material(s) lack a handbook n anchor "
            "(training falls back to the extractor's own output for them)",
            "add measured n@589nm entries to data/optics_handbook_anchors.json "
            f"for: {', '.join(unanchored[:6])}"
            + (" ..." if len(unanchored) > 6 else ""),
            details={"materials": unanchored}))
    return report, recs


# ---------------------------------------------------------------------------
# Event/stratify diagnostics
# ---------------------------------------------------------------------------


def analyze_events(paths: Sequence[str]) -> tuple[dict, List[dict]]:
    samples, metas = harvest_event_dataset(paths)
    recs: List[dict] = []
    report: dict = {
        "n_runs_scanned": len(metas),
        "n_events": len(samples),
    }
    if not samples:
        recs.append(_rec(
            1.0, "stratify_no_training_data",
            "no labeled event features found in the given runs",
            "rerun scenarios with stratify.enable + stratify.dumpFeatures so "
            "trech_event_features.jsonl is produced",
            scenario="examples/experiments/config_stratify_ml.js"))
        return report, recs

    y = np.array([1.0 if s.exceptional else 0.0 for s in samples])
    x = np.array([s.features for s in samples], dtype=float)
    pos = int(y.sum())
    frac = pos / len(y)
    report["exceptional_fraction"] = frac
    if frac < 0.05 or frac > 0.95:
        recs.append(_rec(
            1.0 if frac in (0.0, 1.0) else 0.9, "stratify_label_balance",
            f"teacher labels are {frac:.1%} exceptional over {len(y)} events "
            "— (near-)single-class data cannot train a classifier",
            "recalibrate stratify.*Threshold near the observed feature "
            "distribution (see event_feature_stats in trech_scores.jsonl) "
            "and add sampling variety (beam.spread presets, beam.spectrum) "
            "so runs draw a real distribution",
            details={"n_exceptional": pos, "n_events": len(y)}))

    # Degenerate feature slots: zero variance across the whole dataset.
    stds = x.std(axis=0)
    dead = [FEATURE_NAMES[i] for i in range(len(FEATURE_NAMES))
            if stds[i] < 1e-12]
    report["zero_variance_features"] = dead
    if dead:
        optical_dead = [d for d in dead if d.startswith("optical_")]
        action = ("include optics.enable runs (optical photons populate the "
                  "optical_* features)" if optical_dead else
                  "add scenarios that vary these features")
        recs.append(_rec(
            0.85, "stratify_feature_degenerate",
            f"{len(dead)} of {len(FEATURE_NAMES)} feature slots have zero "
            f"variance in the training data: {', '.join(dead)}",
            action,
            scenario=("examples/experiments/glass_of_water_varied.js"
                      if optical_dead else None),
            details={"features": dead}))

    if len(samples) < 1000:
        recs.append(_rec(
            0.6, "stratify_dataset_size",
            f"only {len(samples)} labeled events; per-class statistics are "
            "Poisson-noisy",
            "rerun the stratify scenarios with --events >= 1000 (features are "
            "dumped per event, so cost scales linearly)",
            details={"n_events": len(samples)}))

    energies = sorted({m.beam_energy_mev for m in metas
                       if m.beam_energy_mev > 0})
    report["beam_energies_mev"] = energies
    if len(energies) <= 1:
        recs.append(_rec(
            0.65, "stratify_energy_coverage",
            f"all training runs share {len(energies)} beam energy value(s); "
            "the classifier cannot generalise over energy",
            "sweep beam.energyMeV (or use beam.spectrum weighted lines + "
            "beam.spread.energySpreadFractional) across the regime the model "
            "must cover",
            details={"energies_mev": energies}))

    covered = sorted({m.dimension_scale for m in metas
                      if m.dimension_scale != "unknown"})
    report["dimension_scales_covered"] = covered
    missing = [band for band in SCALE_BAND_SCENARIOS if band not in covered]
    report["dimension_scales_missing"] = missing
    for band in missing:
        recs.append(_rec(
            0.4, "scale_coverage",
            f"no labeled events from the '{band}' dimension-scale band; "
            "inference at that scale would extrapolate",
            f"run a {band}-scale scenario with stratify.enable + "
            "stratify.dumpFeatures",
            scenario=SCALE_BAND_SCENARIOS[band],
            details={"band": band}))
    return report, recs


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Trained-model domain diagnostics (the starved regions the engine flags)
# ---------------------------------------------------------------------------


def _portable_path(path: Path) -> str:
    """Prefer a cwd-relative provenance path without hiding external inputs."""
    resolved = Path(path).expanduser().resolve()
    try:
        return str(resolved.relative_to(Path.cwd().resolve()))
    except ValueError:
        return str(resolved)


def _load_model(path: Path) -> Optional[dict]:
    try:
        model = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"warning: cannot read model {path}: {exc}", file=sys.stderr)
        return None
    if not isinstance(model, dict) or "input_features" not in model:
        return None
    return model


def analyze_models(paths: Sequence[str], max_holes: int = 5,
                   ) -> tuple[dict, List[dict]]:
    """Where is a TRAINED model starved — and at what operating point?

    The engine flags starvation at prediction time, which tells you a run was
    low-confidence *after* paying for it. The same exported evidence says where
    to simulate NEXT, which is the active-learning half of the loop:

    * per-feature `occupancy` holes — a range the training set never populated,
      reported as the concrete value range to cover;
    * **joint** holes — the multivariate gap no per-feature histogram can see.
      Candidates are the midpoints between pairs of carried training-region
      centers: a midpoint far from every center is, by construction, inside the
      convex span of the training data yet in a region it never sampled (train
      on (cold, slow) and (hot, fast), and the (cold, fast) corner shows up
      here). Each is reported in the model's own raw input units, so it names an
      operating point a scenario can actually be run at.

    Deterministic: pair enumeration is index-ordered and ties break by distance
    then by coordinates.
    """
    report: dict = {"models": []}
    recommendations: List[dict] = []
    for raw in paths:
        path = Path(raw).expanduser()
        model = _load_model(path)
        if model is None:
            continue
        names = [str(n) for n in model.get("input_features", [])]
        n_feat = len(names)
        mean = np.array(model.get("input_mean", [0.0] * n_feat), dtype=float)
        std = np.array(model.get("input_std", [1.0] * n_feat), dtype=float)
        domain = model.get("input_domain") or {}
        entry: dict = {
            "path": _portable_path(path),
            "inputs": names,
            "n_train_rows": domain.get("n_train_rows"),
            "has_joint_reference": bool(domain.get("joint")),
        }

        # --- per-feature holes: a range training never populated ---------------
        occupancy = domain.get("occupancy") or {}
        counts = occupancy.get("counts") or []
        bins = int(occupancy.get("bins", 0))
        lo = domain.get("input_min") or []
        hi = domain.get("input_max") or []
        empty_ranges: List[dict] = []
        if bins > 0 and len(counts) == n_feat and len(lo) == n_feat:
            for i, row in enumerate(counts):
                width = (float(hi[i]) - float(lo[i])) / bins if bins else 0.0
                for b, count in enumerate(row):
                    if count == 0 and width > 0.0:
                        empty_ranges.append({
                            "input": names[i],
                            "from": float(lo[i]) + b * width,
                            "to": float(lo[i]) + (b + 1) * width,
                        })
        entry["empty_feature_bins"] = len(empty_ranges)
        if empty_ranges:
            recommendations.append(_rec(
                severity=min(1.0, 0.3 + 0.05 * len(empty_ranges)),
                kind="model_feature_starved",
                reason=(f"{path.name}: {len(empty_ranges)} training-range bin(s) "
                        f"the training set never populated — predictions there "
                        f"are interpolated through a hole"),
                action=("run this model's scenario at input values inside the "
                        "listed ranges and retrain, so the hull is populated "
                        "rather than merely spanned"),
                details={"empty_ranges": empty_ranges[:12]},
            ))

        # --- joint holes: the gap no per-feature histogram can see --------------
        joint = domain.get("joint") or {}
        centers = np.array(joint.get("centers") or [], dtype=float)
        radius = float(joint.get("radius", 0.0))
        if centers.ndim == 2 and len(centers) >= 2 and radius > 0.0:
            holes: List[tuple] = []
            for a in range(len(centers)):
                for b in range(a + 1, len(centers)):
                    mid = 0.5 * (centers[a] + centers[b])
                    d = float(np.sqrt(((centers - mid) ** 2).sum(axis=1)).min())
                    if d > radius:
                        holes.append((d, a, b, mid))
            # Worst first; ties break on the pair indices, so the plan is stable.
            holes.sort(key=lambda h: (-h[0], h[1], h[2]))
            entry["joint_holes"] = len(holes)
            entry["joint_radius"] = radius
            if holes:
                listed = []
                for d, a, b, mid in holes[:max_holes]:
                    raw_point = mid * std + mean
                    listed.append({
                        "distance": round(d, 4),
                        "distance_over_radius": round(d / radius, 3),
                        "between_centers": [int(a), int(b)],
                        # Raw input units: an operating point to actually run at.
                        "operating_point": {
                            names[i]: float(raw_point[i]) for i in range(n_feat)
                        },
                    })
                worst = holes[0][0] / radius
                recommendations.append(_rec(
                    severity=min(1.0, 0.4 + 0.1 * math.log10(max(worst, 1.0) * 10)),
                    kind="model_joint_starved",
                    reason=(f"{path.name}: {len(holes)} region(s) inside the "
                            f"trained per-feature ranges but far from every "
                            f"training point (worst {worst:.1f}x the covering "
                            f"radius) — a prediction there is an interpolation "
                            f"across untrained space no per-feature check sees"),
                    action=("run this model's scenario at the listed operating "
                            "points and retrain; they are the joint gaps "
                            "between the regions training actually covered"),
                    details={"holes": listed},
                ))
        elif not joint:
            entry["joint_holes"] = None
            recommendations.append(_rec(
                severity=0.25,
                kind="model_joint_unmeasured",
                reason=(f"{path.name}: carries no joint training reference, so "
                        f"the engine cannot tell an in-range-but-untrained "
                        f"point from a covered one"),
                action=("retrain with the current trech-train-surrogate; it "
                        "exports input_domain.joint from the training split"),
            ))
        report["models"].append(entry)
    return report, recommendations


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--optics-run", nargs="*", default=[],
                        help="optics panel run dir(s) / scene manifests "
                             "(trech_viz_scene.json with derived_optics)")
    parser.add_argument("--anchors", default=None,
                        help="handbook anchors JSON "
                             "(data/optics_handbook_anchors.json)")
    parser.add_argument("--runs", nargs="*", default=[],
                        help="stratify run dirs (or parents) with "
                             "trech_event_features.jsonl")
    parser.add_argument("--models", nargs="*", default=[],
                        help="trained generic_surrogate_v1 model JSON(s); "
                             "reports where each is starved and at which "
                             "operating point to simulate next")
    parser.add_argument("--ridge-lambda", type=float, default=1.0)
    parser.add_argument("--out", default="geant4_experiment_plan.json")
    args = parser.parse_args(argv)

    if not args.optics_run and not args.runs and not args.models:
        print("error: give --optics-run, --runs and/or --models",
              file=sys.stderr)
        return 2

    plan: dict = {"schema": PLAN_SCHEMA, "inputs": {
        "optics_runs": list(args.optics_run),
        "anchors": args.anchors,
        "event_runs": list(args.runs),
        "models": list(args.models),
    }}
    recommendations: List[dict] = []

    if args.optics_run:
        anchors = load_anchors(Path(args.anchors)) if args.anchors else {}
        scenes = find_scene_manifests(args.optics_run)
        samples = harvest_optics_samples(scenes, anchors=anchors)
        print(f"optics: {len(samples)} panel materials from "
              f"{len(scenes)} scene manifest(s)")
        report, recs = analyze_optics(samples, anchors, args.ridge_lambda)
        plan["optics_coverage"] = report
        recommendations.extend(recs)

    if args.runs:
        report, recs = analyze_events(args.runs)
        print(f"events: {report.get('n_events', 0)} labeled events from "
              f"{report.get('n_runs_scanned', 0)} run(s)")
        plan["event_coverage"] = report
        recommendations.extend(recs)

    if args.models:
        report, recs = analyze_models(args.models)
        print(f"models: {len(report.get('models', []))} trained model(s) "
              f"inspected for starved regions")
        plan["model_coverage"] = report
        recommendations.extend(recs)

    # Deterministic ranking: severity desc, then kind/reason for stability.
    recommendations.sort(key=lambda r: (-r["severity"], r["kind"],
                                        r["reason"]))
    for rank, rec in enumerate(recommendations, start=1):
        rec["priority"] = rank
    plan["recommendations"] = recommendations

    out_path = Path(args.out).expanduser().resolve()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(plan, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {out_path}")

    if recommendations:
        print(f"\n{len(recommendations)} recommendation(s):")
        for rec in recommendations:
            scenario = rec["geant4_experiment"]["scenario"]
            suffix = f"  [{scenario}]" if scenario else ""
            print(f"  {rec['priority']}. ({rec['severity']:.2f}) "
                  f"{rec['kind']}: {rec['reason']}{suffix}")
    else:
        print("\nno gaps found — current Geant4 coverage supports the "
              "trained models")
    return 0


if __name__ == "__main__":
    sys.exit(main())
