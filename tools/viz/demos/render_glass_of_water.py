"""Render a short video of a photon crossing a glass of water — two ways.

This demo deliberately shows **both** stories side by side so the gap
between them is honest and obvious:

* **physics target** — where a 2.25 eV (green) photon *should* go, computed
  from classical Snell refraction using the handbook indices the scenario
  records under ``optics.derive.validate.references``
  (``n_air = 1.000``, ``n_glass = 1.46``, ``n_water = 1.333``). This is the
  well-known-physical-law reference, not a TRECH output.

* **TRECH simulated** — where the photon *actually* went in the engine run,
  replayed verbatim from ``trech_viz_trajectories.jsonl``. TRECH derives
  each material's refractive index from Geant4 nanoscale cross sections
  (photoelectric + Compton + Rayleigh → Kramers-Kronig dispersion) plus an
  f-sum-rule valence oscillator (the valence-electron strength the atomic
  tables miss below ~100 eV), with no hard-coded optics. That derivation now
  recovers ``n_glass ≈ 1.47`` and ``n_water ≈ 1.33`` — about **100 %** of the
  real refractive response — so the simulated photon refracts at every
  interface and the two rays essentially coincide.

The point of the comparison is the ROADMAP goal: a *realistic* and
*TRECH-based* glass-of-water beam. The two rays now overlap to well under a
millimetre at the world boundary: TRECH reproduces the textbook Snell angles
(air 30° → glass 19.9° → water 22.1° → glass → air 30°) from physics-derived
indices. The small residual (glass over-recovers by ~3 %, water under by
~1 %) is the material-specific dispersion the single global oscillator energy
can't resolve — the surrogate training track is meant to close it. This video
is the regression artefact that tracks that residual.

Modes (``--mode``):

* ``compare`` (default) — overlay both rays + an HUD quantifying the gap.
* ``physics``           — only the Snell target (the old illustrative clip).
* ``trech``             — only the faithful replay of the engine trajectories.

Geometry, beam direction, world size and the derived optical constants are
all read from ``trech_viz_scene.json`` so any scenario tweak propagates here.

Run::

    cd tools/viz
    source .venv/bin/activate            # see tools/viz/README.md
    python demos/render_glass_of_water.py            # compare (default)
    python demos/render_glass_of_water.py --mode physics
    python demos/render_glass_of_water.py --mode trech

Output: ``tools/viz/demos/glass_of_water_beam.mp4`` (override with ``--out``).
"""

from __future__ import annotations

import argparse
import math
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np
import pyvista as pv

from trech_viz.scene import Scene, Volume, load_scene
from trech_viz.trajectories import (
    Trajectory,
    load_trajectories,
    visible_rgb_for_wavelength,
    wavelength_nm_for_energy_ev,
)


REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_RUN_DIR = REPO_ROOT / "build" / "dev" / "out_validation_gow"
DEFAULT_OUT = Path(__file__).resolve().parent / "glass_of_water_beam.mp4"

C_MM_PER_NS = 299.792458  # speed of light in vacuum, mm/ns

# Handbook indices from validate.references in the scenario JS. These are the
# "ground truth" the validator inverse-solves against; here they drive the
# physics-target ray only (never any TRECH physics).
HANDBOOK_N = {
    "air": 1.000293,
    "glass": 1.46,
    "water": 1.333,
}

# Demo-only colour overrides. The derived display_rgb values for this run
# collapse to the same brown for every material (cross-section integral
# degenerate at 2.25 eV); intuitive light-blue / azure beats a
# physically-derived but useless palette for a demo. Visualization only.
DISPLAY_OVERRIDE = {
    "glass": ("#b6d3e6", 0.22),  # light blue
    "water": ("#7cc5ea", 0.18),  # lighter azure
    "air":   (None, 0.0),         # invisible (it's the world atmosphere)
}

# Ray palette.
PHYSICS_COLOR = "#ffb347"     # amber — the "where physics says it should go" ray
TRECH_HEAD_COLOR = "#fff3a0"  # bright head for the simulated ray


# --------------------------------------------------------------------- geometry

@dataclass
class Segment:
    """One leg of the synthesised photon path."""

    start: np.ndarray         # mm
    end: np.ndarray           # mm
    direction: np.ndarray     # unit vector
    n_index: float            # refractive index in this segment
    medium: str               # "air" | "glass" | "water"

    @property
    def length_mm(self) -> float:
        return float(np.linalg.norm(self.end - self.start))


def _absolute_position(volume: Volume, by_name) -> Tuple[float, float, float]:
    parent = (volume.parent or "").lower()
    base = (0.0, 0.0, 0.0)
    if parent and parent in by_name:
        base = _absolute_position(by_name[parent], by_name)
    return (
        base[0] + volume.position_mm[0],
        base[1] + volume.position_mm[1],
        base[2] + volume.position_mm[2],
    )


def _bounds_for(volume: Volume, by_name) -> Tuple[np.ndarray, np.ndarray]:
    cx, cy, cz = _absolute_position(volume, by_name)
    sx, sy, sz = volume.size_mm
    lo = np.array([cx - sx / 2, cy - sy / 2, cz - sz / 2])
    hi = np.array([cx + sx / 2, cy + sy / 2, cz + sz / 2])
    return lo, hi


def _ray_aabb(origin: np.ndarray, direction: np.ndarray,
              lo: np.ndarray, hi: np.ndarray) -> Optional[Tuple[float, float, np.ndarray]]:
    """Slab intersection. Returns (t_enter, t_exit, entry_normal) or None.

    ``entry_normal`` points outward from the box at the entry face.
    """
    t_lo = np.empty(3)
    t_hi = np.empty(3)
    for i in range(3):
        d = direction[i]
        if abs(d) < 1e-12:
            if origin[i] < lo[i] or origin[i] > hi[i]:
                return None
            t_lo[i] = -math.inf
            t_hi[i] = math.inf
        else:
            t_lo[i] = (lo[i] - origin[i]) / d
            t_hi[i] = (hi[i] - origin[i]) / d
            if t_lo[i] > t_hi[i]:
                t_lo[i], t_hi[i] = t_hi[i], t_lo[i]
    t_enter = max(t_lo)
    t_exit = min(t_hi)
    if t_enter > t_exit or t_exit < 0:
        return None
    axis = int(np.argmax(t_lo))
    normal = np.zeros(3)
    normal[axis] = -1.0 if direction[axis] > 0 else 1.0
    return t_enter, t_exit, normal


def _refract(direction: np.ndarray, normal: np.ndarray,
             n1: float, n2: float) -> np.ndarray:
    """Classical Snell refraction. Returns the unit direction in the new
    medium; on total internal reflection returns the reflected direction so
    the demo still has a path to draw."""
    d = direction / np.linalg.norm(direction)
    n = normal / np.linalg.norm(normal)
    cos_i = -float(np.dot(d, n))
    if cos_i < 0:
        n = -n
        cos_i = -cos_i
    eta = n1 / n2
    sin2_t = eta * eta * (1.0 - cos_i * cos_i)
    if sin2_t > 1.0:
        return d + 2.0 * cos_i * n
    cos_t = math.sqrt(1.0 - sin2_t)
    return eta * d + (eta * cos_i - cos_t) * n


def _classify(point: np.ndarray, volumes: Sequence[Tuple[str, np.ndarray, np.ndarray]]) -> str:
    """Return the innermost medium containing the point. ``volumes`` is a list
    of (name, lo, hi) ordered outer-to-inner; later entries win on tie."""
    medium = "air"
    for name, lo, hi in volumes:
        if np.all(point >= lo - 1e-6) and np.all(point <= hi + 1e-6):
            medium = name
    return medium


def _exit_normal(pos: np.ndarray, direction: np.ndarray,
                 lo: np.ndarray, hi: np.ndarray) -> np.ndarray:
    """Outward normal of the AABB face the ray exits through."""
    t_hi = np.empty(3)
    for i in range(3):
        d = direction[i]
        if abs(d) < 1e-12:
            t_hi[i] = math.inf
        else:
            t_a = (lo[i] - pos[i]) / d
            t_b = (hi[i] - pos[i]) / d
            t_hi[i] = max(t_a, t_b)
    axis = int(np.argmin(t_hi))
    normal = np.zeros(3)
    normal[axis] = 1.0 if direction[axis] > 0 else -1.0
    return normal


def nested_media(scene: Scene) -> List[Tuple[str, np.ndarray, np.ndarray]]:
    by_name = {v.name.lower(): v for v in scene.volumes}
    glass = next(v for v in scene.volumes if v.material.lower() == "glass")
    water = next(v for v in scene.volumes if v.material.lower() == "water")
    return [
        ("glass", *_bounds_for(glass, by_name)),
        ("water", *_bounds_for(water, by_name)),
    ]


def synthesise_path(scene: Scene, n_table: dict,
                    source: Optional[np.ndarray] = None,
                    direction: Optional[np.ndarray] = None,
                    max_segments: int = 12) -> List[Segment]:
    """Refract a photon through the cup with the given index table.

    ``source`` / ``direction`` default to the scenario beam (origin + beam
    direction) so the synthesised ray starts exactly where the TRECH photons
    are emitted, making the two overlays directly comparable.
    """
    nested = nested_media(scene)

    beam = scene.beams[0]
    if direction is None:
        direction = np.array(beam.direction, dtype=float)
    direction = direction / np.linalg.norm(direction)

    if source is None:
        source = np.array([0.0, 0.0, 0.0], dtype=float)

    segments: List[Segment] = []
    pos = np.asarray(source, dtype=float).copy()
    dir_ = direction.copy()
    medium = _classify(pos, nested)
    n_here = n_table.get(medium, 1.0)

    for _ in range(max_segments):
        events: List[Tuple[float, np.ndarray, str, bool]] = []
        for name, lo, hi in nested:
            hit = _ray_aabb(pos, dir_, lo, hi)
            if hit is None:
                continue
            t_enter, t_exit, entry_normal = hit
            inside = np.all(pos >= lo - 1e-6) and np.all(pos <= hi + 1e-6)
            if inside:
                exit_normal = _exit_normal(pos, dir_, lo, hi)
                if t_exit > 1e-6:
                    events.append((t_exit, exit_normal, name, False))
            else:
                if t_enter > 1e-6:
                    events.append((t_enter, entry_normal, name, True))
        ws = scene.world_size_mm or 300.0
        world_lo = np.array([-ws / 2] * 3)
        world_hi = np.array([ws / 2] * 3)
        hit_world = _ray_aabb(pos, dir_, world_lo, world_hi)
        if hit_world is None:
            break
        _, t_world_exit, _ = hit_world
        events.append((t_world_exit, np.zeros(3), "world_exit", False))
        events.sort(key=lambda e: e[0])
        t_next, normal, hit_name, entering = events[0]
        end = pos + dir_ * t_next
        segments.append(Segment(
            start=pos.copy(), end=end.copy(), direction=dir_.copy(),
            n_index=n_here, medium=medium,
        ))
        if hit_name == "world_exit":
            break
        next_medium = _classify(end + dir_ * 1e-4, nested)
        n_next = n_table.get(next_medium, 1.0)
        dir_ = _refract(dir_, normal, n_here, n_next)
        dir_ /= np.linalg.norm(dir_)
        pos = end + dir_ * 1e-4
        medium = next_medium
        n_here = n_next

    return segments


def segments_to_points(segments: Sequence[Segment]) -> np.ndarray:
    if not segments:
        return np.zeros((0, 3))
    pts = [segments[0].start.copy()]
    for s in segments:
        pts.append(s.end.copy())
    return np.asarray(pts, dtype=float)


# ------------------------------------------------------------------- TRECH path

def pick_primary_trajectory(
    trajectories: Sequence[Trajectory],
    beam_direction: Optional[Sequence[float]] = None,
    world_size_mm: Optional[float] = None,
) -> Optional[Trajectory]:
    """Pick a representative *transmitted refraction* trajectory.

    With real refraction the run holds three populations: clean transmissions
    (air -> glass -> water -> glass -> air, the bulk of the photons), Fresnel
    reflections, and Rayleigh-scattered strays. The representative ray is a
    clean forward transmission: it crosses both the glass and the water, exits
    travelling parallel to the incident beam (parallel slabs), and runs all the
    way out to the far world boundary. We score candidates on (reaches the
    world boundary, beam alignment, arc length) so the chosen ray is a full
    edge-to-edge transmission rather than a short reflected stub or a stray that
    stopped mid-flight, and fall back to the longest world-reaching ray.
    """
    beam = None
    if beam_direction is not None:
        beam = np.asarray(beam_direction, dtype=float)
        nb = float(np.linalg.norm(beam))
        beam = beam / nb if nb > 1e-9 else None
    world_half = 0.5 * world_size_mm if world_size_mm else None

    best: Optional[Trajectory] = None
    best_key: Optional[Tuple[bool, float, float]] = None
    fallback: Optional[Trajectory] = None
    fallback_len = -1.0
    for traj in trajectories:
        if len(traj.points) < 2:
            continue
        if traj.particle and traj.particle.lower() not in ("opticalphoton", ""):
            continue
        pts = np.asarray(traj.points, dtype=float)
        arc = float(np.sum(np.linalg.norm(np.diff(pts, axis=0), axis=1)))
        reaches_world = any(v == "World" for v in traj.volumes)
        if reaches_world and arc > fallback_len:
            fallback_len = arc
            fallback = traj
        media = {m.lower() for m in traj.materials}
        crosses_cup = any("water" in m for m in media) and any(
            ("glass" in m or "silicon" in m) for m in media)
        if not (reaches_world and crosses_cup):
            continue
        exit_dir = pts[-1] - pts[-2]
        nrm = float(np.linalg.norm(exit_dir))
        if nrm < 1e-9:
            continue
        exit_dir = exit_dir / nrm
        align = float(np.dot(exit_dir, beam)) if beam is not None else 0.0
        # A clean transmission exits forward (align ~ +1); skip reflected rays
        # that leave back the way they came.
        if beam is not None and align <= 0.0:
            continue
        # Did the ray run out to the world boundary (last vertex on the AABB)?
        on_boundary = True
        if world_half is not None:
            on_boundary = bool(np.max(np.abs(pts[-1])) >= world_half - 1.0)
        # Maximize: reaches boundary, then beam alignment, then the *shortest*
        # arc -- the clean direct transmission, not a longer multi-bounce ray
        # that happens to leak out forwards.
        key = (on_boundary, align, -arc)
        if best_key is None or key > best_key:
            best_key = key
            best = traj
    return best or fallback


# --------------------------------------------------------------------- arc walk

def arc_lengths(points: np.ndarray) -> np.ndarray:
    """Cumulative arc length at each vertex (length == len(points))."""
    if len(points) < 2:
        return np.zeros(len(points))
    seg = np.linalg.norm(np.diff(points, axis=0), axis=1)
    return np.concatenate([[0.0], np.cumsum(seg)])


def polyline_upto(points: np.ndarray, frac: float) -> Tuple[np.ndarray, np.ndarray]:
    """Return (trail_points, head) for the first ``frac`` of the path's arc."""
    if len(points) < 2:
        return points.copy(), (points[-1] if len(points) else np.zeros(3))
    cum = arc_lengths(points)
    total = cum[-1]
    target = max(0.0, min(1.0, frac)) * total
    idx = int(np.searchsorted(cum, target))
    if idx <= 0:
        head = points[0].copy()
        return points[:1].copy(), head
    if idx >= len(points):
        return points.copy(), points[-1].copy()
    span = cum[idx] - cum[idx - 1]
    local = 0.0 if span <= 0 else (target - cum[idx - 1]) / span
    head = points[idx - 1] + (points[idx] - points[idx - 1]) * local
    trail = np.vstack([points[:idx], head[None, :]])
    return trail, head


def _polyline_mesh(points: np.ndarray) -> Optional[pv.PolyData]:
    if len(points) < 2:
        return None
    poly = pv.PolyData(points)
    cells = np.empty(len(points) + 1, dtype=np.int64)
    cells[0] = len(points)
    cells[1:] = np.arange(len(points))
    poly.lines = cells
    return poly


# --------------------------------------------------------------------- rendering

def build_volume_mesh(volume: Volume):
    shape = (volume.shape_type or "box").lower()
    if shape in ("box", "cube"):
        sx, sy, sz = volume.size_mm
        if sx <= 0 or sy <= 0 or sz <= 0:
            return None
        return pv.Box(bounds=(-sx / 2, sx / 2, -sy / 2, sy / 2, -sz / 2, sz / 2))
    if shape in ("tube", "cylinder", "cyl"):
        outer = volume.outer_radius_mm
        length = volume.length_mm or max(volume.size_mm) or 1.0
        if outer <= 0:
            return None
        return pv.Cylinder(center=(0, 0, 0), direction=(0, 0, 1),
                           radius=outer, height=length, resolution=48)
    if shape == "sphere":
        if volume.outer_radius_mm <= 0:
            return None
        return pv.Sphere(radius=volume.outer_radius_mm, center=(0, 0, 0))
    return None


def add_world_frame(plotter: pv.Plotter, scene: Scene):
    if scene.world_size_mm <= 0:
        return
    ws = scene.world_size_mm
    plotter.add_mesh(
        pv.Box(bounds=(-ws / 2, ws / 2, -ws / 2, ws / 2, -ws / 2, ws / 2)),
        style="wireframe", color="#3a4452", line_width=1.0, opacity=0.5,
    )


def add_volumes(plotter: pv.Plotter, scene: Scene):
    by_name = {v.name.lower(): v for v in scene.volumes}
    for volume in scene.volumes:
        pos = _absolute_position(volume, by_name)
        mesh = build_volume_mesh(volume)
        if mesh is None:
            continue
        try:
            mesh = mesh.translate(np.array(pos))
        except Exception:
            pass
        tags = {t.lower() for t in volume.tags}
        if "viz_forced_white" in tags or "viz_emitter" in tags:
            plotter.add_mesh(mesh, color="#fafad2", opacity=0.95, smooth_shading=True)
            continue
        material_key = volume.material.lower()
        if material_key in DISPLAY_OVERRIDE:
            color, opacity = DISPLAY_OVERRIDE[material_key]
            if color is None or opacity <= 0:
                continue
            plotter.add_mesh(mesh, color=color, opacity=opacity,
                             smooth_shading=True, specular=0.4, specular_power=20)
            continue
        plotter.add_mesh(mesh, color=(0.7, 0.85, 1.0), opacity=0.20,
                         smooth_shading=True)


# --------------------------------------------------------------------- gap data

@dataclass
class GapReport:
    incidence_deg: float
    physics_exit_deg: float
    trech_exit_deg: float
    exit_separation_mm: float
    recovered: Dict[str, float]      # material -> fraction of (n-1) recovered
    derived_n: Dict[str, float]
    handbook_n: Dict[str, float]


def _angle_from_z(direction: np.ndarray) -> float:
    d = direction / np.linalg.norm(direction)
    return math.degrees(math.acos(min(1.0, abs(float(d[2])))))


def derived_index_table(scene: Scene) -> Dict[str, float]:
    out: Dict[str, float] = {}
    for d in scene.derived_materials:
        for key in (d.config_material_key, d.material_name):
            if key:
                out[key.lower()] = d.mean_refractive_index
    return out


def compute_gap(scene: Scene, physics_pts: np.ndarray,
                trech_pts: np.ndarray) -> GapReport:
    derived = derived_index_table(scene)
    incidence = _angle_from_z(np.array(scene.beams[0].direction, dtype=float))

    def exit_dir(pts: np.ndarray) -> np.ndarray:
        return pts[-1] - pts[-2]

    physics_exit = _angle_from_z(exit_dir(physics_pts)) if len(physics_pts) >= 2 else incidence
    trech_exit = _angle_from_z(exit_dir(trech_pts)) if len(trech_pts) >= 2 else incidence
    # Separation between the two exit beams.  The rays leave the cup parallel
    # (clean refraction through parallel slabs), so the meaningful gap is the
    # perpendicular distance between the exit lines -- not the raw endpoint
    # distance, which would also pick up however far along the beam each ray's
    # last recorded vertex happens to sit.
    sep = 0.0
    if len(physics_pts) >= 2 and len(trech_pts) >= 2:
        d_phys = exit_dir(physics_pts)
        d_trech = exit_dir(trech_pts)
        d_common = d_phys / np.linalg.norm(d_phys) + d_trech / np.linalg.norm(d_trech)
        nrm = np.linalg.norm(d_common)
        if nrm > 1e-9:
            d_common /= nrm
            delta = physics_pts[-1] - trech_pts[-1]
            perp = delta - float(np.dot(delta, d_common)) * d_common
            sep = float(np.linalg.norm(perp))
        else:
            sep = float(np.linalg.norm(physics_pts[-1] - trech_pts[-1]))

    recovered: Dict[str, float] = {}
    for mat in ("water", "glass"):
        n_hand = HANDBOOK_N.get(mat, 1.0)
        n_der = derived.get(mat, 1.0)
        denom = (n_hand - 1.0)
        recovered[mat] = (n_der - 1.0) / denom if abs(denom) > 1e-12 else 0.0

    return GapReport(
        incidence_deg=incidence,
        physics_exit_deg=physics_exit,
        trech_exit_deg=trech_exit,
        exit_separation_mm=sep,
        recovered=recovered,
        derived_n={m: derived.get(m, 1.0) for m in ("water", "glass")},
        handbook_n={m: HANDBOOK_N[m] for m in ("water", "glass")},
    )


def gap_hud_lines(gap: GapReport, mode: str) -> List[str]:
    """Full lower-left HUD panel (monospace) for the given mode."""
    if mode == "physics":
        return [
            "PHYSICS TARGET - classical Snell (handbook n)",
            f"n_water = {gap.handbook_n['water']:.3f}   n_glass = {gap.handbook_n['glass']:.3f}",
            f"incidence {gap.incidence_deg:4.1f}deg  ->  exit {gap.physics_exit_deg:4.1f}deg",
            "",
            "illustrative reference - not a TRECH output",
        ]
    if mode == "trech":
        return [
            "TRECH SIMULATED - optics from Geant4 nanoscale",
            f"n_water = {gap.derived_n['water']:.4f}   n_glass = {gap.derived_n['glass']:.4f}",
            f"incidence {gap.incidence_deg:4.1f}deg  ->  exit {gap.trech_exit_deg:4.1f}deg",
            "",
            "faithful replay of trech_viz_trajectories.jsonl",
        ]
    # compare
    return [
        "material   n handbook   n TRECH   refraction",
        f"water        {gap.handbook_n['water']:.3f}     {gap.derived_n['water']:.4f}     {gap.recovered['water'] * 100:4.1f}%",
        f"glass        {gap.handbook_n['glass']:.3f}     {gap.derived_n['glass']:.4f}     {gap.recovered['glass'] * 100:4.1f}%",
        f"exit angle   physics {gap.physics_exit_deg:4.1f}deg   TRECH {gap.trech_exit_deg:4.1f}deg",
        f"ray gap at world boundary: {gap.exit_separation_mm:4.1f} mm",
        "",
        "amber = physics target (Snell, handbook n)",
        "green = TRECH simulated (Geant4 nanoscale optics)",
        f"TRECH recovers ~{0.5 * (gap.recovered['water'] + gap.recovered['glass']) * 100:.0f}% of visible refraction",
        "via the f-sum-rule valence oscillator.",
    ]


# --------------------------------------------------------------------- main loop

def parse_args():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--scene", type=Path,
                    default=DEFAULT_RUN_DIR / "trech_viz_scene.json")
    ap.add_argument("--trajectories", type=Path,
                    default=DEFAULT_RUN_DIR / "trech_viz_trajectories.jsonl")
    ap.add_argument("--mode", choices=("compare", "physics", "trech"),
                    default="compare",
                    help="compare = overlay both (default); physics = Snell "
                         "target only; trech = replay engine output only.")
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    ap.add_argument("--frames-dir", type=Path, default=None,
                    help="PNG frame output dir. Default: sibling of --out.")
    ap.add_argument("--duration", type=float, default=7.0)
    ap.add_argument("--fps", type=int, default=30)
    ap.add_argument("--width", type=int, default=1280)
    ap.add_argument("--height", type=int, default=720)
    ap.add_argument("--energy-ev", type=float, default=2.25,
                    help="Photon energy used for wavelength → RGB colour.")
    ap.add_argument("--keep-frames", action="store_true")
    return ap.parse_args()


def main() -> int:
    args = parse_args()
    if not args.scene.exists():
        print(f"scene file not found: {args.scene}", file=sys.stderr)
        return 2

    frames_dir = args.frames_dir or args.out.parent / (args.out.stem + "_frames")
    if frames_dir.exists():
        shutil.rmtree(frames_dir)
    frames_dir.mkdir(parents=True, exist_ok=True)

    print(f"loading scene {args.scene}")
    scene = load_scene(args.scene)

    # TRECH actual ray (faithful engine replay).
    trech_pts = np.zeros((0, 3))
    trech_traj: Optional[Trajectory] = None
    if args.mode in ("compare", "trech"):
        if not args.trajectories.exists():
            print(f"trajectory file not found: {args.trajectories}", file=sys.stderr)
            return 2
        trajs = load_trajectories(args.trajectories)
        beam_dir = scene.beams[0].direction if scene.beams else None
        trech_traj = pick_primary_trajectory(
            trajs, beam_direction=beam_dir, world_size_mm=scene.world_size_mm)
        if trech_traj is None:
            print("no usable TRECH trajectory found", file=sys.stderr)
            return 2
        trech_pts = np.asarray(trech_traj.points, dtype=float)
        print(f"replaying TRECH trajectory event={trech_traj.event_id} "
              f"track={trech_traj.track_id} ({len(trech_pts)} points)")

    # Physics target ray (Snell with handbook indices) from the same source.
    physics_segs: List[Segment] = []
    physics_pts = np.zeros((0, 3))
    if args.mode in ("compare", "physics"):
        source = trech_pts[0] if len(trech_pts) else None
        physics_segs = synthesise_path(scene, HANDBOOK_N, source=source)
        physics_pts = segments_to_points(physics_segs)
        for i, s in enumerate(physics_segs):
            ang = _angle_from_z(s.direction)
            print(f"  physics seg {i}: {s.medium:6s} len={s.length_mm:7.2f} mm "
                  f"n={s.n_index:.4f} angle-from-z={ang:5.2f}deg")

    # Gap report (needs both rays; fall back gracefully in single modes).
    if len(physics_pts) and len(trech_pts):
        gap = compute_gap(scene, physics_pts, trech_pts)
    else:
        # Build a partial report from whichever ray exists.
        derived = derived_index_table(scene)
        incidence = _angle_from_z(np.array(scene.beams[0].direction, dtype=float))
        ref_pts = physics_pts if len(physics_pts) else trech_pts
        exit_deg = _angle_from_z(ref_pts[-1] - ref_pts[-2]) if len(ref_pts) >= 2 else incidence
        gap = GapReport(
            incidence_deg=incidence,
            physics_exit_deg=exit_deg if len(physics_pts) else incidence,
            trech_exit_deg=exit_deg if len(trech_pts) else incidence,
            exit_separation_mm=0.0,
            recovered={m: ((derived.get(m, 1.0) - 1.0) / (HANDBOOK_N[m] - 1.0))
                       for m in ("water", "glass")},
            derived_n={m: derived.get(m, 1.0) for m in ("water", "glass")},
            handbook_n={m: HANDBOOK_N[m] for m in ("water", "glass")},
        )

    if args.mode == "compare":
        print(f"  recovered refraction: water {gap.recovered['water'] * 100:.1f}%  "
              f"glass {gap.recovered['glass'] * 100:.1f}%")
        print(f"  exit angle  physics {gap.physics_exit_deg:.2f}deg  "
              f"trech {gap.trech_exit_deg:.2f}deg  gap {gap.exit_separation_mm:.1f} mm")

    n_frames = int(args.duration * args.fps)
    ws = scene.world_size_mm or 300.0
    pre_hold_s = 0.4
    post_hold_s = 1.3
    sweep_window_s = max(args.duration - pre_hold_s - post_hold_s, 0.1)

    print(f"rendering {n_frames} frames @ {args.fps} fps ({args.duration}s), mode={args.mode}")

    head_radius_mm = max(ws * 0.009, 1.6)
    wl = wavelength_nm_for_energy_ev(args.energy_ev)
    trech_rgb = visible_rgb_for_wavelength(wl)
    hud_lines = gap_hud_lines(gap, args.mode)

    # Interface markers for the physics ray (small rings where it bends).
    physics_interface_pts = physics_pts[1:-1] if len(physics_pts) > 2 else np.zeros((0, 3))

    for i in range(n_frames):
        frame_t = i / args.fps
        if frame_t < pre_hold_s:
            frac = 0.0
        elif frame_t < args.duration - post_hold_s:
            frac = (frame_t - pre_hold_s) / sweep_window_s
        else:
            frac = 1.0

        orbit = i / max(n_frames - 1, 1)
        az = -78.0 + 15.0 * math.sin(orbit * 2 * math.pi * 0.5)
        el = 16.0 + 6.0 * math.sin(orbit * 2 * math.pi * 0.25)
        radius = ws * 1.55
        # Focal point raised toward +z so the rays' exit at the world top
        # (z = +ws/2) and the divergence connector stay inside the frame.
        focal = (0.0, 0.0, ws * 0.18)
        cam = (
            focal[0] + radius * math.cos(math.radians(el)) * math.cos(math.radians(az)),
            focal[1] + radius * math.cos(math.radians(el)) * math.sin(math.radians(az)),
            focal[2] + radius * math.sin(math.radians(el)),
        )

        plotter = pv.Plotter(off_screen=True, window_size=(args.width, args.height))
        plotter.set_background("#06080c")
        add_world_frame(plotter, scene)
        add_volumes(plotter, scene)

        # Physics target ray (amber, semi-transparent "should-go" reference).
        if len(physics_pts):
            trail, head = polyline_upto(physics_pts, frac)
            mesh = _polyline_mesh(trail)
            if mesh is not None:
                style = dict(color=PHYSICS_COLOR, line_width=4.0,
                             show_scalar_bar=False)
                if args.mode == "compare":
                    style.update(opacity=0.85)
                plotter.add_mesh(mesh, **style)
                plotter.add_mesh(pv.Sphere(radius=head_radius_mm * 0.85, center=head),
                                 color=PHYSICS_COLOR, smooth_shading=True)
            # bend markers
            for p in physics_interface_pts:
                plotter.add_mesh(pv.Sphere(radius=head_radius_mm * 0.55, center=p),
                                 color="#ffd9a0", opacity=0.7, smooth_shading=True)

        # TRECH simulated ray (wavelength-coloured, bright head).
        if len(trech_pts):
            trail, head = polyline_upto(trech_pts, frac)
            mesh = _polyline_mesh(trail)
            if mesh is not None:
                rgb = np.tile(np.array(trech_rgb, dtype=np.float32), (len(trail), 1))
                mesh.point_data["rgb"] = rgb
                plotter.add_mesh(mesh, scalars="rgb", rgb=True, line_width=3.6,
                                 show_scalar_bar=False)
                plotter.add_mesh(pv.Sphere(radius=head_radius_mm, center=head),
                                 color=TRECH_HEAD_COLOR, smooth_shading=True)

        # Divergence connector at the world boundary (compare mode, late).
        if args.mode == "compare" and frac > 0.6 and len(physics_pts) and len(trech_pts):
            conn = _polyline_mesh(np.vstack([physics_pts[-1], trech_pts[-1]]))
            if conn is not None:
                plotter.add_mesh(conn, color="#ff5d5d", line_width=2.0,
                                 opacity=0.55, show_scalar_bar=False)

        # Orientation triad in the empty bottom-right corner so it clears the
        # bottom-left HUD panel.
        plotter.add_axes(viewport=(0.82, 0.0, 1.0, 0.20))
        plotter.camera_position = [cam, focal, (0.0, 0.0, 1.0)]

        # HUD: title (top-left), progress (top-right), single mono panel
        # anchored bottom-left in normalised viewport coords (viewport=True,
        # since tuple positions are otherwise interpreted as pixels).
        title = {
            "compare": "Glass of water - physics target vs TRECH simulation",
            "physics": "Glass of water - physics target (Snell refraction)",
            "trech":   "Glass of water - TRECH simulated photon",
        }[args.mode]
        plotter.add_text(title, position="upper_left", font_size=12, color="#eef2f7")
        plotter.add_text(f"progress {frac * 100:3.0f}%", position="upper_right",
                         font_size=11, color="#ffffff")
        plotter.add_text("\n".join(hud_lines), position=(0.015, 0.04),
                         viewport=True, font_size=9, color="#cfd6e0", font="courier")

        plotter.show(screenshot=str(frames_dir / f"frame_{i:04d}.png"), auto_close=True)
        if (i + 1) % 30 == 0 or i == n_frames - 1:
            print(f"  frame {i + 1}/{n_frames}")

    args.out.parent.mkdir(parents=True, exist_ok=True)
    print(f"encoding {args.out}")
    subprocess.run([
        "ffmpeg", "-y",
        "-framerate", str(args.fps),
        "-i", str(frames_dir / "frame_%04d.png"),
        "-c:v", "libx264",
        "-pix_fmt", "yuv420p",
        "-crf", "20",
        "-movflags", "+faststart",
        str(args.out),
    ], check=True)
    print(f"wrote {args.out}")

    if not args.keep_frames:
        shutil.rmtree(frames_dir, ignore_errors=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
