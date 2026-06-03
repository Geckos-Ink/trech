#!/usr/bin/env python3
"""Quantify how degenerate a TRECH run is — the anti-degeneration regression
signals the ROADMAP standing objective says to watch.

Two failure modes are measured (see ROADMAP "Anti-degeneration"):

1. Simulation-sampling degeneration — are the primaries all identical? We
   report, over the sampled trajectories:
     - distinct primary exit points        (1  => fully degenerate)
     - first-segment incidence-angle stddev (0  => collimated/identical)
     - emission wavelength stddev (nm)      (0  => monochromatic/identical)
     - points-per-trajectory histogram      (how many interfaces were crossed)

2. Learned/derived-physics degeneration — did the optical constants collapse?
   When a scene manifest with `derived_optics` is present we report, per
   material, the fraction of handbook refraction recovered
   (n_derived - 1) / (n_handbook - 1); ~0 means near-straight, colourless
   transport (the visible-band n≈1 problem).

Usage:
    scripts/degeneration_metrics.py RUN_DIR [RUN_DIR ...]
    scripts/degeneration_metrics.py --baseline BASE_DIR RUN_DIR

A RUN_DIR is a trech `--output` directory holding
`trech_viz_trajectories.jsonl` (required) and `trech_viz_scene.json`
(optional, enables the optics-recovery section). Exits non-zero only on
usage/IO errors — it is a report, not a gate.
"""

from __future__ import annotations

import argparse
import json
import math
import statistics
import sys
from collections import Counter
from pathlib import Path
from typing import Dict, List, Optional, Tuple


# Handbook visible-band refractive indices used to score optics recovery. Same
# anchors the glass-of-water comparison demo and validator use.
HANDBOOK_N = {"air": 1.000293, "glass": 1.46, "water": 1.333}


def _trajectory_path(run_dir: Path) -> Path:
    if run_dir.is_file():
        return run_dir
    return run_dir / "trech_viz_trajectories.jsonl"


def _scene_path(run_dir: Path) -> Optional[Path]:
    if run_dir.is_file():
        cand = run_dir.parent / "trech_viz_scene.json"
    else:
        cand = run_dir / "trech_viz_scene.json"
    return cand if cand.exists() else None


def _angle_from_z(dx: float, dy: float, dz: float) -> Optional[float]:
    mag = math.sqrt(dx * dx + dy * dy + dz * dz)
    if mag <= 0:
        return None
    return math.degrees(math.acos(min(1.0, abs(dz) / mag)))


def sampling_metrics(traj_path: Path) -> Dict:
    n = 0
    points_hist: Counter = Counter()
    exits: Counter = Counter()
    incidence: List[float] = []
    wavelengths: List[float] = []
    with open(traj_path, "r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            rec = json.loads(line)
            pts = rec.get("points") or []
            if len(pts) < 2:
                continue
            n += 1
            points_hist[len(pts)] += 1
            last = pts[-1]
            exits[(round(last.get("x_mm", 0.0), 1),
                   round(last.get("y_mm", 0.0), 1),
                   round(last.get("z_mm", 0.0), 1))] += 1
            ang = _angle_from_z(
                pts[1].get("x_mm", 0.0) - pts[0].get("x_mm", 0.0),
                pts[1].get("y_mm", 0.0) - pts[0].get("y_mm", 0.0),
                pts[1].get("z_mm", 0.0) - pts[0].get("z_mm", 0.0),
            )
            if ang is not None:
                incidence.append(ang)
            e0 = pts[0].get("energy_ev", 0.0) or 0.0
            if e0 > 0:
                wavelengths.append(1239.841984 / e0)

    def stddev(xs: List[float]) -> float:
        return statistics.pstdev(xs) if len(xs) > 1 else 0.0

    return {
        "trajectories": n,
        "distinct_exit_points": len(exits),
        "points_per_traj": dict(sorted(points_hist.items())),
        "incidence_deg_mean": statistics.fmean(incidence) if incidence else 0.0,
        "incidence_deg_stddev": stddev(incidence),
        "wavelength_nm_mean": statistics.fmean(wavelengths) if wavelengths else 0.0,
        "wavelength_nm_stddev": stddev(wavelengths),
    }


def optics_recovery(scene_path: Path) -> List[Tuple[str, float, float, float]]:
    """Return [(material, n_handbook, n_derived, recovered_fraction)]."""
    scene = json.load(open(scene_path, "r", encoding="utf-8"))
    out: List[Tuple[str, float, float, float]] = []
    derived = {}
    for d in scene.get("derived_optics") or []:
        for key in (d.get("config_material_key"), d.get("material_name")):
            if key:
                derived[key.lower()] = float(d.get("mean_refractive_index") or 1.0)
    for mat in ("water", "glass"):
        if mat in derived:
            n_hand = HANDBOOK_N[mat]
            n_der = derived[mat]
            denom = n_hand - 1.0
            rec = (n_der - 1.0) / denom if abs(denom) > 1e-12 else 0.0
            out.append((mat, n_hand, n_der, rec))
    return out


def report(run_dir: Path) -> Dict:
    traj_path = _trajectory_path(run_dir)
    if not traj_path.exists():
        raise FileNotFoundError(f"no trajectories file: {traj_path}")
    metrics = sampling_metrics(traj_path)
    scene_path = _scene_path(run_dir)
    metrics["optics_recovery"] = (
        optics_recovery(scene_path) if scene_path else []
    )
    return metrics


def print_report(label: str, m: Dict) -> None:
    print(f"\n=== {label} ===")
    print(f"  trajectories            : {m['trajectories']}")
    print(f"  distinct exit points    : {m['distinct_exit_points']}"
          f"   (1 = fully degenerate)")
    print(f"  points/traj histogram   : {m['points_per_traj']}")
    print(f"  incidence angle (deg)   : mean {m['incidence_deg_mean']:.2f}"
          f"   stddev {m['incidence_deg_stddev']:.3f}")
    print(f"  emission wavelength (nm): mean {m['wavelength_nm_mean']:.1f}"
          f"   stddev {m['wavelength_nm_stddev']:.2f}")
    if m["optics_recovery"]:
        print("  optics recovery (fraction of handbook refraction):")
        for mat, n_hand, n_der, rec in m["optics_recovery"]:
            print(f"    {mat:6s}  n_handbook={n_hand:.3f}  n_derived={n_der:.4f}"
                  f"  recovered={rec * 100:5.1f}%")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("run_dirs", nargs="+", type=Path,
                    help="trech --output dir(s) (or a trajectories.jsonl file)")
    ap.add_argument("--baseline", type=Path, default=None,
                    help="reference run to print first and diff against")
    args = ap.parse_args()

    try:
        if args.baseline is not None:
            print_report(f"baseline: {args.baseline}", report(args.baseline))
        for rd in args.run_dirs:
            print_report(str(rd), report(rd))
    except (FileNotFoundError, json.JSONDecodeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
