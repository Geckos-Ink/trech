#!/usr/bin/env python3
"""Validate TRECH optical-photon transport against classical optics.

Companion to examples/experiments/validation_glass_of_water.js.

TRECH derives n / absorption / scatter from Geant4 atomic cross
sections (no hard-coded refractive index) and then lets Geant4's optical
photon process sample refraction / Fresnel reflection / absorption on
those derived tables.  Classical optics, by contrast, *requires* a
constant per material -- n_air, n_glass, n_water (for Snell / Fresnel),
or alpha (for Beer-Lambert).

This script runs the comparison in inverse form: from the *statistical*
behavior recorded by TRECH it solves Snell / Fresnel / Beer-Lambert
backwards to recover the material constants that the simulation
implicitly used, then prints those next to the dogmatic handbook
values.  A small delta means "the simulation reproduces the textbook
behavior"; a large delta is a regression signal.

Three inverse comparisons:

  1. Inverse Snell.  For every interface crossing recorded in the viz
     trajectories, measure (theta_i, theta_r) from the photon's
     direction vectors immediately before and after the crossing, then
     solve  n_2 = n_1 * sin(theta_i) / sin(theta_r)  given the
     handbook n_1 of the incident medium.  Aggregate over all crossings
     into a given target material.

  2. Inverse Fresnel.  At each interface, count how many photons
     refracted through versus Fresnel-reflected back; convert the
     measured transmittance T into an inferred n_2 via the unpolarized
     Fresnel formula at the known incidence angle.

  3. Inverse Beer-Lambert.  For photons that entered water, count the
     fraction that survived to exit versus were absorbed in-flight, and
     measure their path length inside water; solve
     alpha = -ln(survival) / mean_path  for the absorption coefficient.
     Compared against the handbook absorption coefficient at the beam
     wavelength (water is highly transparent in the visible, so this
     mostly produces an upper bound on alpha).

Run:
    python3 scripts/validate_glass_of_water.py --run build/dev/out_validation_gow

Outputs:
    docs/validation_glass_of_water.md         (markdown summary)
    docs/validation_glass_of_water.json       (machine-readable sidecar)

The output paths are overridable with --report / --json.  Pass --no-write
to print the markdown to stdout without touching the docs/ tree.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple


# ---------------------------------------------------------------------------
# Handbook references.  Air/water at 589 nm and Schott BK7 at 589 nm; the
# beam in the companion scenario is 2.25 eV (~ 550 nm) so these references
# are within the same dispersion window.
# ---------------------------------------------------------------------------

HANDBOOK_N: Dict[str, float] = {
    "air":   1.000293,
    "water": 1.333,
    "glass": 1.46,
}

# Visible-band absorption coefficients (1/mm).  Water is famously
# transparent; the value here is the handbook absorption coefficient
# at ~ 550 nm.  Glass and air are effectively non-absorbing on
# centimeter scales so we only score water.
HANDBOOK_ALPHA_PER_MM: Dict[str, float] = {
    "water": 5.0e-5,   # ~ alpha at 550 nm; absorption length ~ 20 m
}


# ---------------------------------------------------------------------------
# Geometry helpers.  All volumes in the scenario are axis-aligned boxes,
# so the surface normal at every face is exactly +/- x, y or z.
# ---------------------------------------------------------------------------

@dataclass
class BoxVolume:
    name: str
    material: str
    center: Tuple[float, float, float]
    half_size: Tuple[float, float, float]

    def face_distances(self, x: float, y: float, z: float) -> Tuple[float, float, float]:
        """Signed distances to the |x|, |y|, |z| faces.  Smallest |d|
        wins -- that face is the one we're crossing."""
        return (
            self.half_size[0] - abs(x - self.center[0]),
            self.half_size[1] - abs(y - self.center[1]),
            self.half_size[2] - abs(z - self.center[2]),
        )

    def contains(self, x: float, y: float, z: float, tol_mm: float = 1.0e-6) -> bool:
        dx, dy, dz = self.face_distances(x, y, z)
        return dx >= -tol_mm and dy >= -tol_mm and dz >= -tol_mm


def _resolve_box_world_position(volumes_by_name: Dict[str, dict], name: str) -> Tuple[float, float, float]:
    """Walk the parent chain to convert local positions to world coords."""
    cx = cy = cz = 0.0
    cursor = name
    visited = set()
    while cursor and cursor != "world" and cursor not in visited:
        visited.add(cursor)
        entry = volumes_by_name.get(cursor)
        if entry is None:
            break
        pos = entry.get("position_mm") or [0.0, 0.0, 0.0]
        cx += float(pos[0])
        cy += float(pos[1])
        cz += float(pos[2])
        cursor = entry.get("parent") or ""
    return (cx, cy, cz)


def load_boxes(scene: dict) -> Dict[str, BoxVolume]:
    """Index every box volume in the scene by name, in world coordinates."""
    volumes_by_name: Dict[str, dict] = {}
    for v in scene.get("volumes") or []:
        volumes_by_name[v.get("name")] = v
    boxes: Dict[str, BoxVolume] = {}
    for name, entry in volumes_by_name.items():
        shape = entry.get("shape") or {}
        if shape.get("type") != "box":
            continue
        size = shape.get("size_mm") or [0.0, 0.0, 0.0]
        center = _resolve_box_world_position(volumes_by_name, name)
        half = (0.5 * float(size[0]), 0.5 * float(size[1]), 0.5 * float(size[2]))
        boxes[name] = BoxVolume(
            name=name,
            material=str(entry.get("material") or ""),
            center=center,
            half_size=half,
        )
    return boxes


def crossing_normal_axis(p_before: dict, p_after: dict, box: BoxVolume) -> Optional[int]:
    """Return 0/1/2 for x/y/z (the box-face axis crossed between the two
    points), or None if we can't decide cleanly."""
    # Midpoint of the segment that straddles the face.
    mx = 0.5 * (float(p_before["x_mm"]) + float(p_after["x_mm"]))
    my = 0.5 * (float(p_before["y_mm"]) + float(p_after["y_mm"]))
    mz = 0.5 * (float(p_before["z_mm"]) + float(p_after["z_mm"]))
    dx, dy, dz = box.face_distances(mx, my, mz)
    distances = (abs(dx), abs(dy), abs(dz))
    axis = min(range(3), key=lambda i: distances[i])
    # Sanity gate: the smallest face-distance should be much smaller
    # than the second-smallest, otherwise we're probably looking at a
    # corner and our normal estimate is ambiguous.
    others = sorted(distances)
    if others[0] > 0.5 * others[1] and others[1] > 1.0e-6:
        return None
    return axis


# ---------------------------------------------------------------------------
# Inverse Snell on a single (incident, refracted) direction pair.
# ---------------------------------------------------------------------------

def _normal_axis_unit(axis: int) -> Tuple[float, float, float]:
    return ((1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0))[axis]


def angles_at_interface(d_in: Tuple[float, float, float],
                        d_out: Tuple[float, float, float],
                        axis: int) -> Tuple[float, float]:
    """Return (theta_incident, theta_refracted) measured from the face
    normal, both in radians and in [0, pi/2]."""
    n_hat = _normal_axis_unit(axis)
    # cos(theta) = |d . n_hat|.  We take |.| because the normal can
    # point either way -- the angle is unsigned.
    cos_i = abs(d_in[0] * n_hat[0] + d_in[1] * n_hat[1] + d_in[2] * n_hat[2])
    cos_r = abs(d_out[0] * n_hat[0] + d_out[1] * n_hat[1] + d_out[2] * n_hat[2])
    cos_i = max(0.0, min(1.0, cos_i))
    cos_r = max(0.0, min(1.0, cos_r))
    return math.acos(cos_i), math.acos(cos_r)


def inverse_snell_n2(theta_i: float, theta_r: float, n1: float) -> Optional[float]:
    """n_2 = n_1 * sin(theta_i) / sin(theta_r), guarding against the
    degenerate sin(theta_r) -> 0 case (i.e. ~ normal incidence, where
    the inverse problem has no information)."""
    si = math.sin(theta_i)
    sr = math.sin(theta_r)
    if sr < 1.0e-6:
        return None
    return n1 * si / sr


# ---------------------------------------------------------------------------
# Inverse Fresnel.  Given the measured transmittance T at a known
# incidence angle, solve the unpolarized Fresnel formula for n2.
# We do not have access to per-step Fresnel rolls, so T is estimated as
# (# photons that crossed into medium 2) / (# photons that arrived at
# the interface from medium 1).  We then bisect on n2.
# ---------------------------------------------------------------------------

def fresnel_unpolarized_T(theta_i: float, n1: float, n2: float) -> float:
    si = math.sin(theta_i)
    # sin(theta_t) via Snell.
    st_squared = (n1 / n2) ** 2 * si * si
    if st_squared >= 1.0:
        # Total internal reflection: T = 0.
        return 0.0
    ct_i = math.cos(theta_i)
    ct_t = math.sqrt(1.0 - st_squared)
    # Reflectance for s- and p-polarization.
    rs = (n1 * ct_i - n2 * ct_t) / (n1 * ct_i + n2 * ct_t)
    rp = (n1 * ct_t - n2 * ct_i) / (n1 * ct_t + n2 * ct_i)
    R = 0.5 * (rs * rs + rp * rp)
    return max(0.0, min(1.0, 1.0 - R))


def inverse_fresnel_n2(measured_T: float, theta_i: float, n1: float,
                       lo: float = 1.0, hi: float = 3.0) -> Optional[float]:
    """Bisect on n2 in [lo, hi] to match the measured transmittance.
    Fresnel T is monotonic in n2 for fixed n1 != n2; we pick the branch
    n2 >= n1 (the physically relevant one here -- glass denser than
    air, water denser than air, glass denser than water).  For n2 < n1
    crossings (water -> glass exits or glass -> air exits) caller flips
    the bracket."""
    if not (0.0 < measured_T <= 1.0):
        return None
    target = measured_T
    # Direction of monotonicity: T at n2 = n1 is 1.0; T decreases as
    # |n2 - n1| grows.  So the bracket [n1+eps, hi] gives a monotone
    # decreasing T from ~ 1 down to T(hi).
    f_lo = fresnel_unpolarized_T(theta_i, n1, max(lo, n1 + 1.0e-6)) - target
    f_hi = fresnel_unpolarized_T(theta_i, n1, hi) - target
    if f_lo * f_hi > 0:
        return None
    a, b = max(lo, n1 + 1.0e-6), hi
    for _ in range(60):
        m = 0.5 * (a + b)
        fm = fresnel_unpolarized_T(theta_i, n1, m) - target
        if fm == 0.0:
            return m
        if (fresnel_unpolarized_T(theta_i, n1, a) - target) * fm < 0:
            b = m
        else:
            a = m
    return 0.5 * (a + b)


# ---------------------------------------------------------------------------
# Inverse Beer-Lambert.  Aggregated over all photons that entered the
# water bulk, alpha = -ln(survival) / mean_path_in_water.
# ---------------------------------------------------------------------------

def inverse_beer_alpha(survived: int, entered: int, mean_path_mm: float) -> Optional[float]:
    if entered <= 0 or mean_path_mm <= 0.0:
        return None
    if survived <= 0:
        # All absorbed -> alpha can only be bounded from below.
        return float("inf")
    survival = survived / entered
    if survival >= 1.0:
        # Nothing absorbed in this run.  alpha is consistent with 0;
        # we report the upper bound implied by "could have absorbed at
        # most 1 photon out of `entered`" -- the usual Wilson-style
        # one-sided estimate would be tighter, but this is good enough
        # as a sanity bound.
        upper_survival = max((entered - 1.0) / entered, 1.0e-12)
        return -math.log(upper_survival) / mean_path_mm
    return -math.log(survival) / mean_path_mm


# ---------------------------------------------------------------------------
# Trajectory walker.  Pulls every interface crossing out of a single
# trajectory and yields (incident_medium, refracted_medium, theta_i,
# theta_r, kind) where kind is 'refracted' or 'reflected'.
# ---------------------------------------------------------------------------

@dataclass
class Crossing:
    medium_in: str
    medium_out: str   # the medium the photon enters AFTER the crossing
    theta_i: float
    theta_r: float
    kind: str         # 'refracted' | 'reflected'
    axis: int


def _which_box(boxes: Dict[str, BoxVolume], point: dict) -> Optional[BoxVolume]:
    """Return the deepest box containing the point (so water_bulk wins
    over glass_cup at points where the photon is inside the water)."""
    x = float(point["x_mm"]); y = float(point["y_mm"]); z = float(point["z_mm"])
    # Smaller volumes first -> children are checked before parents.
    ordered = sorted(boxes.values(),
                     key=lambda b: b.half_size[0] * b.half_size[1] * b.half_size[2])
    for box in ordered:
        if box.contains(x, y, z):
            return box
    return None


def _classify_medium(box: Optional[BoxVolume]) -> str:
    if box is None:
        return "air"     # world material in our scenario
    mat = (box.material or "").lower()
    if "water" in mat or mat in ("g4_water",):
        return "water"
    if "silicon" in mat or "glass" in mat:
        return "glass"
    if "air" in mat:
        return "air"
    return mat or "air"


def walk_trajectory(traj: dict, boxes: Dict[str, BoxVolume]) -> Iterable[Crossing]:
    points = traj.get("points") or []
    if len(points) < 2:
        return
    # The "medium" of a point is decided by its containing box.
    media: List[str] = []
    containing: List[Optional[BoxVolume]] = []
    for p in points:
        box = _which_box(boxes, p)
        containing.append(box)
        # Prefer the explicit material string on the point if present
        # (Geant4 reports it after the step).  Fall back to geometric.
        explicit = (p.get("material") or "").lower()
        if "water" in explicit:
            media.append("water")
        elif "silicon" in explicit or "glass" in explicit:
            media.append("glass")
        elif "air" in explicit:
            media.append("air")
        else:
            media.append(_classify_medium(box))
    for i in range(1, len(points)):
        if media[i] == media[i - 1]:
            continue
        # The crossing is between points[i-1] and points[i].  We need
        # the face axis -- use whichever box owns the interface (the
        # smaller of the two, since the interior box's face IS the
        # interface).
        box_pick = containing[i] or containing[i - 1]
        if box_pick is None:
            continue
        axis = crossing_normal_axis(points[i - 1], points[i], box_pick)
        if axis is None:
            continue
        d_in = (float(points[i - 1]["dx"]), float(points[i - 1]["dy"]), float(points[i - 1]["dz"]))
        d_out = (float(points[i]["dx"]),     float(points[i]["dy"]),     float(points[i]["dz"]))
        theta_i, theta_r = angles_at_interface(d_in, d_out, axis)
        # Reflection vs refraction: did the normal component flip sign?
        n_hat = _normal_axis_unit(axis)
        sign_in = d_in[0] * n_hat[0] + d_in[1] * n_hat[1] + d_in[2] * n_hat[2]
        sign_out = d_out[0] * n_hat[0] + d_out[1] * n_hat[1] + d_out[2] * n_hat[2]
        kind = "refracted" if (sign_in * sign_out > 0) else "reflected"
        yield Crossing(
            medium_in=media[i - 1],
            medium_out=media[i],
            theta_i=theta_i,
            theta_r=theta_r,
            kind=kind,
            axis=axis,
        )


# ---------------------------------------------------------------------------
# Aggregation buckets.
# ---------------------------------------------------------------------------

@dataclass
class SnellBucket:
    """All Snell-style refraction samples for one (medium_in -> medium_out) interface."""
    medium_in: str
    medium_out: str
    n2_samples: List[float] = field(default_factory=list)
    theta_i: List[float] = field(default_factory=list)
    theta_r: List[float] = field(default_factory=list)


@dataclass
class FresnelBucket:
    medium_in: str
    medium_out: str
    refracted: int = 0
    reflected: int = 0
    theta_i_sum: float = 0.0


@dataclass
class WaterAbsorptionBucket:
    entered: int = 0
    survived: int = 0
    path_mm_sum: float = 0.0


def _stats(values: Iterable[float]) -> Tuple[float, float, int]:
    values = [v for v in values if math.isfinite(v)]
    n = len(values)
    if n == 0:
        return (float("nan"), float("nan"), 0)
    mean = sum(values) / n
    if n == 1:
        return (mean, 0.0, n)
    var = sum((v - mean) ** 2 for v in values) / (n - 1)
    return (mean, math.sqrt(max(var, 0.0)), n)


# ---------------------------------------------------------------------------
# Main driver.
# ---------------------------------------------------------------------------

def load_run(run_dir: Path) -> Tuple[dict, List[dict]]:
    scene_path = run_dir / "trech_viz_scene.json"
    traj_path = run_dir / "trech_viz_trajectories.jsonl"
    if not scene_path.exists():
        raise FileNotFoundError(f"missing scene manifest: {scene_path}")
    if not traj_path.exists():
        raise FileNotFoundError(f"missing trajectories file: {traj_path}")
    scene = json.loads(scene_path.read_text())
    trajectories: List[dict] = []
    with open(traj_path, "r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                trajectories.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return scene, trajectories


def derived_n_by_material(scene: dict) -> Dict[str, float]:
    out: Dict[str, float] = {}
    for entry in scene.get("derived_optics") or []:
        n = entry.get("mean_refractive_index")
        if n is None:
            continue
        for key in (entry.get("material_name"), entry.get("config_material_key")):
            if key:
                out[str(key).lower()] = float(n)
    return out


def water_path_length(traj: dict) -> float:
    """Cumulative distance the photon spent inside a 'water'-material
    point.  Used as L for the inverse Beer-Lambert."""
    points = traj.get("points") or []
    total = 0.0
    for i in range(1, len(points)):
        mat = (points[i].get("material") or "").lower()
        prev_mat = (points[i - 1].get("material") or "").lower()
        # Count the segment if either endpoint reports water -- a
        # segment that crosses an interface counts the water side only
        # via the explicit material flag.
        if "water" in mat or "water" in prev_mat:
            dx = float(points[i]["x_mm"]) - float(points[i - 1]["x_mm"])
            dy = float(points[i]["y_mm"]) - float(points[i - 1]["y_mm"])
            dz = float(points[i]["z_mm"]) - float(points[i - 1]["z_mm"])
            total += math.sqrt(dx * dx + dy * dy + dz * dz)
    return total


def run(args: argparse.Namespace) -> int:
    run_dir = Path(args.run).expanduser().resolve()
    scene, trajectories = load_run(run_dir)
    boxes = load_boxes(scene)

    snell: Dict[Tuple[str, str], SnellBucket] = {}
    fresnel: Dict[Tuple[str, str], FresnelBucket] = {}
    water_abs = WaterAbsorptionBucket()

    for traj in trajectories:
        crossings = list(walk_trajectory(traj, boxes))

        # --- Snell + Fresnel buckets ---------------------------------
        for c in crossings:
            key = (c.medium_in, c.medium_out)
            if c.kind == "refracted":
                bucket = snell.setdefault(key, SnellBucket(c.medium_in, c.medium_out))
                n1 = HANDBOOK_N.get(c.medium_in)
                if n1 is None:
                    continue
                n2 = inverse_snell_n2(c.theta_i, c.theta_r, n1)
                if n2 is not None and math.isfinite(n2) and n2 > 0:
                    bucket.n2_samples.append(n2)
                    bucket.theta_i.append(c.theta_i)
                    bucket.theta_r.append(c.theta_r)
            f = fresnel.setdefault(key, FresnelBucket(c.medium_in, c.medium_out))
            f.theta_i_sum += c.theta_i
            if c.kind == "refracted":
                f.refracted += 1
            else:
                f.reflected += 1

        # --- Water absorption accounting -----------------------------
        # A photon counts as "present in water" if any of its recorded
        # points reports a water material (covers both photons born
        # in the water bulk and photons that entered through a glass
        # interface).  It "survived" if it ever left -- the easiest
        # test is that the trajectory's last point reports a non-water
        # material, or the trajectory recorded a 'water -> *' crossing.
        points = traj.get("points") or []
        any_in_water = any("water" in (p.get("material") or "").lower() for p in points)
        if any_in_water:
            water_abs.entered += 1
            last_mat = (points[-1].get("material") or "").lower() if points else ""
            left_water = ("water" not in last_mat) or any(c.medium_in == "water" for c in crossings)
            if left_water:
                water_abs.survived += 1
            water_abs.path_mm_sum += water_path_length(traj)

    # ----------------------------------------------------------------
    # Build the comparison rows.
    # ----------------------------------------------------------------
    rows_snell = []
    for (m_in, m_out), bucket in sorted(snell.items()):
        mean, std, n = _stats(bucket.n2_samples)
        ref = HANDBOOK_N.get(m_out, float("nan"))
        rows_snell.append({
            "interface": f"{m_in} -> {m_out}",
            "samples": n,
            "n2_inferred_mean": mean,
            "n2_inferred_std": std,
            "n2_reference": ref,
            "delta": (mean - ref) if math.isfinite(mean) and math.isfinite(ref) else float("nan"),
            "rel_error": (abs(mean - ref) / ref) if (math.isfinite(mean) and math.isfinite(ref) and ref > 0) else float("nan"),
            "theta_i_mean_deg": math.degrees(sum(bucket.theta_i) / n) if n else float("nan"),
            "theta_r_mean_deg": math.degrees(sum(bucket.theta_r) / n) if n else float("nan"),
        })

    rows_fresnel = []
    for (m_in, m_out), bucket in sorted(fresnel.items()):
        total = bucket.refracted + bucket.reflected
        if total == 0:
            continue
        T_meas = bucket.refracted / total
        theta_i_mean = bucket.theta_i_sum / total
        n1 = HANDBOOK_N.get(m_in)
        ref_n2 = HANDBOOK_N.get(m_out, float("nan"))
        n2_inv: Optional[float] = None
        if n1 is not None and math.isfinite(ref_n2):
            # Bracket: pick the side that brackets the reference.
            if ref_n2 >= n1:
                n2_inv = inverse_fresnel_n2(T_meas, theta_i_mean, n1, lo=n1, hi=max(3.0, ref_n2 * 2.0))
            else:
                # Below-n1 branch: invert by solving 1/n2 instead.
                inv_n2 = inverse_fresnel_n2(T_meas, theta_i_mean, 1.0 / n1, lo=1.0 / 3.0, hi=1.0 / max(1.0e-3, n1))
                n2_inv = (1.0 / inv_n2) if inv_n2 else None
        rows_fresnel.append({
            "interface": f"{m_in} -> {m_out}",
            "refracted": bucket.refracted,
            "reflected": bucket.reflected,
            "T_measured": T_meas,
            "theta_i_mean_deg": math.degrees(theta_i_mean),
            "n2_inferred": n2_inv if n2_inv is not None else float("nan"),
            "n2_reference": ref_n2,
            "delta": (n2_inv - ref_n2) if (n2_inv is not None and math.isfinite(ref_n2)) else float("nan"),
        })

    # Water absorption.
    mean_path_mm = (water_abs.path_mm_sum / water_abs.entered) if water_abs.entered else 0.0
    alpha_inv = inverse_beer_alpha(water_abs.survived, water_abs.entered, mean_path_mm)
    alpha_ref = HANDBOOK_ALPHA_PER_MM.get("water", float("nan"))
    row_beer = {
        "photons_entered_water": water_abs.entered,
        "photons_survived_water": water_abs.survived,
        "mean_path_mm": mean_path_mm,
        "alpha_inferred_per_mm": alpha_inv if alpha_inv is not None else float("nan"),
        "alpha_reference_per_mm": alpha_ref,
        "absorption_length_inferred_mm": (1.0 / alpha_inv) if (alpha_inv and math.isfinite(alpha_inv) and alpha_inv > 0) else float("nan"),
        "absorption_length_reference_mm": (1.0 / alpha_ref) if alpha_ref > 0 else float("nan"),
    }

    # Direct derived-n cross-check (the engine also exposes its derived n).
    derived = derived_n_by_material(scene)
    rows_direct = []
    for material, ref in HANDBOOK_N.items():
        n = derived.get(material)
        rows_direct.append({
            "material": material,
            "n_derived_by_engine": n if n is not None else float("nan"),
            "n_reference": ref,
            "delta": (n - ref) if n is not None else float("nan"),
        })

    summary = {
        "run_dir": str(run_dir),
        "beam_energy_ev": (scene.get("beams") or [{}])[0].get("energy_ev"),
        "n_trajectories": len(trajectories),
        "snell": rows_snell,
        "fresnel": rows_fresnel,
        "beer_lambert_water": row_beer,
        "derived_optics_direct": rows_direct,
        "handbook_references": {
            "n": HANDBOOK_N,
            "alpha_per_mm": HANDBOOK_ALPHA_PER_MM,
        },
    }

    md = render_markdown(summary)
    if args.no_write:
        print(md)
    else:
        report = Path(args.report).expanduser()
        report.parent.mkdir(parents=True, exist_ok=True)
        report.write_text(md, encoding="utf-8")
        sidecar = Path(args.json).expanduser()
        sidecar.parent.mkdir(parents=True, exist_ok=True)
        sidecar.write_text(json.dumps(summary, indent=2, default=_json_default), encoding="utf-8")
        print(f"==> Report:  {report}")
        print(f"==> Sidecar: {sidecar}")
    return 0


def _json_default(o):
    if isinstance(o, float) and not math.isfinite(o):
        return None
    raise TypeError(f"not JSON serializable: {type(o).__name__}")


# ---------------------------------------------------------------------------
# Markdown rendering.
# ---------------------------------------------------------------------------

def _fmt(x, digits=6, signed=False):
    if x is None:
        return "-"
    if isinstance(x, float):
        if not math.isfinite(x):
            return "n/a"
        if signed:
            return f"{x:+.{digits}f}"
        return f"{x:.{digits}f}"
    return str(x)


def render_markdown(summary: dict) -> str:
    lines: List[str] = []
    lines.append("# Glass-of-Water Optical Validation")
    lines.append("")
    lines.append(f"- Run directory: `{summary['run_dir']}`")
    e_ev = summary.get("beam_energy_ev")
    if e_ev:
        lines.append(f"- Beam energy: {e_ev:.4f} eV (~ {1239.84 / e_ev:.0f} nm)")
    lines.append(f"- Trajectories analyzed: {summary['n_trajectories']}")
    lines.append("")
    lines.append("Comparison is inverse: from the photon trajectories produced by")
    lines.append("TRECH (Geant4 optical photon transport on top of n / abs / scat")
    lines.append("tables derived from atomic cross sections), the classical")
    lines.append("formulas are solved backwards for n_2 and alpha and the result")
    lines.append("is compared against handbook references.")
    lines.append("")

    # Snell.
    lines.append("## Inverse Snell's Law")
    lines.append("")
    lines.append("`n_2_inferred = n_1_ref * sin(theta_i) / sin(theta_r)`")
    lines.append("aggregated over every refraction at each material interface.")
    lines.append("")
    lines.append("| Interface | Samples | theta_i mean | theta_r mean | n_2 inferred | n_2 reference | delta | rel err |")
    lines.append("|---|---:|---:|---:|---:|---:|---:|---:|")
    for r in summary["snell"]:
        lines.append("| {iface} | {n} | {ti}° | {tr}° | {ninf} ± {nstd} | {nref} | {d} | {re} |".format(
            iface=r["interface"],
            n=r["samples"],
            ti=_fmt(r["theta_i_mean_deg"], 3),
            tr=_fmt(r["theta_r_mean_deg"], 3),
            ninf=_fmt(r["n2_inferred_mean"], 5),
            nstd=_fmt(r["n2_inferred_std"], 5),
            nref=_fmt(r["n2_reference"], 5),
            d=_fmt(r["delta"], 5, signed=True),
            re=_fmt(r["rel_error"], 4),
        ))
    lines.append("")

    # Fresnel.
    lines.append("## Inverse Fresnel (unpolarized)")
    lines.append("")
    lines.append("Transmittance T = refracted / (refracted + reflected) at each")
    lines.append("interface; bisection solves the unpolarized Fresnel formula")
    lines.append("for n_2 given the handbook n_1 and the mean incidence angle.")
    lines.append("")
    lines.append("| Interface | Refracted | Reflected | T measured | theta_i mean | n_2 inferred | n_2 reference | delta |")
    lines.append("|---|---:|---:|---:|---:|---:|---:|---:|")
    for r in summary["fresnel"]:
        lines.append("| {iface} | {rf} | {rl} | {T} | {ti}° | {ninf} | {nref} | {d} |".format(
            iface=r["interface"],
            rf=r["refracted"],
            rl=r["reflected"],
            T=_fmt(r["T_measured"], 4),
            ti=_fmt(r["theta_i_mean_deg"], 3),
            ninf=_fmt(r["n2_inferred"], 5),
            nref=_fmt(r["n2_reference"], 5),
            d=_fmt(r["delta"], 5, signed=True),
        ))
    lines.append("")

    # Beer-Lambert.
    b = summary["beer_lambert_water"]
    lines.append("## Inverse Beer-Lambert (water)")
    lines.append("")
    lines.append("`alpha = -ln(N_survived / N_entered) / mean_path_mm`")
    lines.append("(water is highly transparent in the visible, so this is")
    lines.append("usually an upper-bound estimate of alpha).")
    lines.append("")
    lines.append("| Entered | Survived | Mean path (mm) | alpha inferred (1/mm) | alpha ref (1/mm) | L_abs inferred (mm) | L_abs ref (mm) |")
    lines.append("|---:|---:|---:|---:|---:|---:|---:|")
    lines.append("| {e} | {s} | {mp} | {ai} | {ar} | {li} | {lr} |".format(
        e=b["photons_entered_water"],
        s=b["photons_survived_water"],
        mp=_fmt(b["mean_path_mm"], 3),
        ai=_fmt(b["alpha_inferred_per_mm"], 6),
        ar=_fmt(b["alpha_reference_per_mm"], 6),
        li=_fmt(b["absorption_length_inferred_mm"], 2),
        lr=_fmt(b["absorption_length_reference_mm"], 2),
    ))
    lines.append("")

    # Direct cross-check.
    lines.append("## Direct cross-check: engine-derived n vs handbook")
    lines.append("")
    lines.append("The MolecularOptics extractor writes its mean refractive index")
    lines.append("per material into the scene manifest.  These values feed the")
    lines.append("Geant4 transport that produced the trajectories above, so")
    lines.append("they should be self-consistent with the inverse-Snell column.")
    lines.append("")
    lines.append("| Material | n derived | n reference | delta |")
    lines.append("|---|---:|---:|---:|")
    for r in summary["derived_optics_direct"]:
        lines.append("| {m} | {nd} | {nr} | {d} |".format(
            m=r["material"],
            nd=_fmt(r["n_derived_by_engine"], 6),
            nr=_fmt(r["n_reference"], 6),
            d=_fmt(r["delta"], 6, signed=True),
        ))
    lines.append("")

    return "\n".join(lines)


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--run", required=True, help="Path to a TRECH output directory.")
    parser.add_argument("--report", default="docs/validation_glass_of_water.md",
                        help="Where to write the markdown report.")
    parser.add_argument("--json", default="docs/validation_glass_of_water.json",
                        help="Where to write the JSON sidecar.")
    parser.add_argument("--no-write", action="store_true",
                        help="Print the markdown to stdout instead of writing files.")
    args = parser.parse_args(argv)
    return run(args)


if __name__ == "__main__":
    sys.exit(main())
