"""Render a short video illustrating the glass-of-water beam scenario.

This script synthesises a single photon path through the geometry from
``examples/experiments/validation_glass_of_water.js`` using classical Snell
refraction at every interface, then animates that photon advancing at c/n
through air → glass → water → glass → air with a wavelength-coloured trail
drawn behind it.

Why a synthesis instead of replaying ``trech_viz_trajectories.jsonl``?
The trajectory file is faithfully rendered by the interactive ``trech-viz``
tool, but in the current run the MolecularOptics derivation produces a
refractive index essentially equal to 1.0 for air / glass / water (the
visible-band Kramers-Kronig integral is dominated by low cross sections),
so the simulated photons travel in straight lines with no visible
refraction. That is correct given the derived constants, but useless as a
demo of "what a beam through a glass of water should look like". This
script uses the handbook indices the scenario itself records under
``optics.derive.validate.references`` — i.e. the values the validation
suite checks the inverse-solver against — to draw the *expected* shape.

The geometry, beam direction, world size, and emitter pose are read from
``trech_viz_scene.json`` so any tweak to the scenario propagates here.

Run::

    cd tools/viz
    source .venv/bin/activate            # see tools/viz/README.md
    python demos/render_glass_of_water.py

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
from typing import Iterable, List, Optional, Sequence, Tuple

import numpy as np
import pyvista as pv

from trech_viz.scene import Scene, Volume, load_scene
from trech_viz.trajectories import (
    visible_rgb_for_wavelength,
    wavelength_nm_for_energy_ev,
)


REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_RUN_DIR = REPO_ROOT / "build" / "dev" / "out_validation_gow"
DEFAULT_OUT = Path(__file__).resolve().parent / "glass_of_water_beam.mp4"

C_MM_PER_NS = 299.792458  # speed of light in vacuum, mm/ns

# Handbook indices from validate.references in the scenario JS. Matching
# this short list keeps the demo aligned with what the inverse-solver in
# scripts/validate_glass_of_water.py treats as ground truth.
HANDBOOK_N = {
    "air": 1.000293,
    "glass": 1.46,
    "water": 1.333,
}

# Demo-only colour overrides. The derived display_rgb values for this
# run collapse to the same brown for every material (cross-section
# integral degenerate at 2.25 eV); intuitive light-blue / azure beats a
# physically-derived but useless palette for a demo.
DISPLAY_OVERRIDE = {
    "glass": ("#b6d3e6", 0.22),  # light blue
    "water": ("#7cc5ea", 0.18),  # lighter azure
    "air":   (None, 0.0),         # invisible (it's the world atmosphere)
}


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

    @property
    def duration_ns(self) -> float:
        return self.length_mm * self.n_index / C_MM_PER_NS


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
    # The axis whose t_lo equals t_enter is the entry face.
    axis = int(np.argmax(t_lo))
    normal = np.zeros(3)
    normal[axis] = -1.0 if direction[axis] > 0 else 1.0
    return t_enter, t_exit, normal


def _refract(direction: np.ndarray, normal: np.ndarray,
             n1: float, n2: float) -> np.ndarray:
    """Classical Snell refraction. ``normal`` points away from the medium the
    ray is coming from (i.e. against the ray). Returns the unit direction in
    the new medium; if total internal reflection would occur, returns the
    reflected direction so the demo still has a path to draw.
    """
    d = direction / np.linalg.norm(direction)
    # ensure normal opposes d (faces the incident ray)
    n = normal / np.linalg.norm(normal)
    cos_i = -float(np.dot(d, n))
    if cos_i < 0:
        n = -n
        cos_i = -cos_i
    eta = n1 / n2
    sin2_t = eta * eta * (1.0 - cos_i * cos_i)
    if sin2_t > 1.0:
        # TIR — reflect instead.
        return d + 2.0 * cos_i * n
    cos_t = math.sqrt(1.0 - sin2_t)
    return eta * d + (eta * cos_i - cos_t) * n


def _classify(point: np.ndarray, volumes: Sequence[Tuple[str, np.ndarray, np.ndarray]]) -> str:
    """Return the innermost medium containing the point. Volumes is a list of
    (name, lo, hi) ordered outer-to-inner; later entries win on tie."""
    medium = "air"
    for name, lo, hi in volumes:
        if np.all(point >= lo - 1e-6) and np.all(point <= hi + 1e-6):
            medium = name
    return medium


def synthesise_path(scene: Scene, n_table: dict, max_segments: int = 12) -> Tuple[List[Segment], np.ndarray, np.ndarray]:
    """Build the refracted photon path for the glass-of-water scenario.

    Returns (segments, source_point, beam_direction). The path runs from a
    point just outside the cup (lined up with the emitter slab) through the
    glass + water and out to the world boundary.
    """
    by_name = {v.name.lower(): v for v in scene.volumes}
    glass = next(v for v in scene.volumes if v.material.lower() == "glass")
    water = next(v for v in scene.volumes if v.material.lower() == "water")
    glass_lo, glass_hi = _bounds_for(glass, by_name)
    water_lo, water_hi = _bounds_for(water, by_name)

    beam = scene.beams[0]
    direction = np.array(beam.direction, dtype=float)
    direction /= np.linalg.norm(direction)

    # Place the source at the emitter (visual hint volume) if present;
    # otherwise behind the world by a comfortable margin.
    emitter = next(
        (v for v in scene.volumes
         if "viz_emitter" in [t.lower() for t in v.tags]),
        None,
    )
    if emitter is not None:
        source = np.array(_absolute_position(emitter, by_name), dtype=float)
    else:
        ws = scene.world_size_mm or 100.0
        source = -direction * (ws * 0.45)

    nested = [
        ("glass", glass_lo, glass_hi),
        ("water", water_lo, water_hi),
    ]

    segments: List[Segment] = []
    pos = source.copy()
    dir_ = direction.copy()
    medium = _classify(pos, nested)
    n_here = n_table.get(medium, 1.0)

    for _ in range(max_segments):
        # Build the list of upcoming boundary t-values: every nested
        # box's enter face if we are outside it, exit face if inside.
        events: List[Tuple[float, np.ndarray, str, bool]] = []
        for name, lo, hi in nested:
            hit = _ray_aabb(pos, dir_, lo, hi)
            if hit is None:
                continue
            t_enter, t_exit, entry_normal = hit
            inside = np.all(pos >= lo - 1e-6) and np.all(pos <= hi + 1e-6)
            if inside:
                # We exit this box at t_exit; compute the exit normal
                # (axis of t_hi minimum).
                exit_normal = _exit_normal(pos, dir_, lo, hi)
                if t_exit > 1e-6:
                    events.append((t_exit, exit_normal, name, False))
            else:
                if t_enter > 1e-6:
                    events.append((t_enter, entry_normal, name, True))
        # World boundary as a final stop.
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
        # Cross the interface.
        next_medium = hit_name if entering else _classify(
            end + dir_ * 1e-4,
            [v for v in nested if v[0] != hit_name] if not entering else nested,
        )
        # Recompute medium properly at the new position by classifying just
        # past the interface.
        next_medium = _classify(end + dir_ * 1e-4, nested)
        n_next = n_table.get(next_medium, 1.0)
        dir_ = _refract(dir_, normal, n_here, n_next)
        dir_ /= np.linalg.norm(dir_)
        pos = end + dir_ * 1e-4
        medium = next_medium
        n_here = n_next

    return segments, source, direction


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
        return pv.Cylinder(
            center=(0, 0, 0),
            direction=(0, 0, 1),
            radius=outer,
            height=length,
            resolution=48,
        )
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


def position_at_time(segments: Sequence[Segment], t_ns: float) -> Tuple[np.ndarray, int, float]:
    """Photon position at simulation-time t_ns. Returns (point, segment_idx, t_in_segment)."""
    acc = 0.0
    for i, seg in enumerate(segments):
        dur = seg.duration_ns
        if t_ns <= acc + dur:
            frac = 0.0 if dur <= 0 else (t_ns - acc) / dur
            return seg.start + (seg.end - seg.start) * frac, i, t_ns - acc
        acc += dur
    last = segments[-1]
    return last.end.copy(), len(segments) - 1, 0.0


def trail_polyline(segments: Sequence[Segment], t_ns: float, energy_ev: float):
    """Build the polyline from the source to the current photon position."""
    if not segments:
        return None
    head, idx, _ = position_at_time(segments, t_ns)
    pts: List[np.ndarray] = [segments[0].start.copy()]
    for i in range(idx):
        pts.append(segments[i].end.copy())
    pts.append(head)
    if len(pts) < 2:
        return None
    arr = np.asarray(pts, dtype=float)
    cells = np.empty(len(arr) + 1, dtype=np.int64)
    cells[0] = len(arr)
    for i in range(len(arr)):
        cells[i + 1] = i
    poly = pv.PolyData(arr)
    poly.lines = cells
    wl = wavelength_nm_for_energy_ev(energy_ev)
    rgb = np.tile(np.array(visible_rgb_for_wavelength(wl), dtype=np.float32),
                  (len(arr), 1))
    poly.point_data["rgb"] = rgb
    return poly, head


def parse_args():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--scene", type=Path,
                    default=DEFAULT_RUN_DIR / "trech_viz_scene.json")
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    ap.add_argument("--frames-dir", type=Path, default=None,
                    help="PNG frame output dir. Default: sibling of --out.")
    ap.add_argument("--duration", type=float, default=6.0)
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
    segments, source, beam_dir = synthesise_path(scene, HANDBOOK_N)
    total_ns = sum(s.duration_ns for s in segments)
    print(f"synthesised {len(segments)} segments, total flight {total_ns:.4f} ns")
    for i, s in enumerate(segments):
        ang_deg = math.degrees(math.acos(min(1.0, abs(float(np.dot(
            s.direction, np.array([0, 0, 1])))))))
        print(f"  seg {i}: {s.medium:6s} len={s.length_mm:7.2f} mm  n={s.n_index:.4f}"
              f"  angle-from-z={ang_deg:5.2f}°  dt={s.duration_ns:.4f} ns")

    n_frames = int(args.duration * args.fps)
    ws = scene.world_size_mm or 300.0
    pre_hold_s = 0.35
    post_hold_s = 1.0
    sweep_window_s = max(args.duration - pre_hold_s - post_hold_s, 0.1)

    print(f"rendering {n_frames} frames @ {args.fps} fps ({args.duration}s)")

    head_radius_mm = max(ws * 0.008, 1.5)

    for i in range(n_frames):
        frame_t = i / args.fps
        if frame_t < pre_hold_s:
            t_ns = 0.0
        elif frame_t < args.duration - post_hold_s:
            sweep_frac = (frame_t - pre_hold_s) / sweep_window_s
            t_ns = sweep_frac * total_ns
        else:
            t_ns = total_ns

        # Camera: orbit slowly around z, mostly side-on so the x-z refraction
        # plane is foreshortened minimally.
        orbit = i / max(n_frames - 1, 1)
        az = -78.0 + 15.0 * math.sin(orbit * 2 * math.pi * 0.5)
        el = 14.0 + 6.0 * math.sin(orbit * 2 * math.pi * 0.25)
        radius = ws * 1.40
        cam = (
            radius * math.cos(math.radians(el)) * math.cos(math.radians(az)),
            radius * math.cos(math.radians(el)) * math.sin(math.radians(az)),
            radius * math.sin(math.radians(el)),
        )

        plotter = pv.Plotter(off_screen=True, window_size=(args.width, args.height))
        plotter.set_background("#06080c")
        add_world_frame(plotter, scene)
        add_volumes(plotter, scene)

        # Trail + head.
        trail = trail_polyline(segments, t_ns, args.energy_ev)
        if trail is not None:
            poly, head = trail
            plotter.add_mesh(poly, scalars="rgb", rgb=True, line_width=3.4,
                             show_scalar_bar=False)
            plotter.add_mesh(pv.Sphere(radius=head_radius_mm, center=head),
                             color="#fff3a0", smooth_shading=True)

        plotter.add_axes()
        plotter.camera_position = [cam, (0.0, 0.0, 0.0), (0.0, 0.0, 1.0)]
        plotter.add_text(
            f"t = {t_ns * 1000.0:6.1f} ps",
            position="upper_right", font_size=12, color="#ffffff",
        )
        plotter.add_text(
            "Glass of water — 2.25 eV photon, 30° incidence",
            position="upper_left", font_size=11, color="#cfd6e0",
        )
        plotter.add_text(
            "synthesised Snell path (n_air=1.000, n_glass=1.46, n_water=1.333)",
            position="lower_left", font_size=9, color="#7d8794",
        )
        plotter.show(screenshot=str(frames_dir / f"frame_{i:04d}.png"),
                     auto_close=True)
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
