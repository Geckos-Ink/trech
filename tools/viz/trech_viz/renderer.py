"""PyVista renderer for TRECH viz scenes."""

from __future__ import annotations

import math
from typing import Dict, Iterable, List, Optional, Tuple

import numpy as np

from .scene import Scene, Volume
from .trajectories import (
    Trajectory,
    visible_rgb_for_wavelength,
    wavelength_nm_for_energy_ev,
)


def _build_box(volume: Volume):
    import pyvista as pv

    sx, sy, sz = volume.size_mm
    return pv.Box(bounds=(-sx / 2, sx / 2, -sy / 2, sy / 2, -sz / 2, sz / 2))


def _build_tube(volume: Volume):
    import pyvista as pv

    outer = volume.outer_radius_mm
    inner = volume.inner_radius_mm
    length = volume.length_mm if volume.length_mm > 0 else max(volume.size_mm) or 1.0
    if outer <= 0:
        return None
    # Geant4 G4Tubs lies along its local z axis by default; PyVista Cylinder
    # builds along an axis we choose explicitly.
    outer_cyl = pv.Cylinder(
        center=(0.0, 0.0, 0.0),
        direction=(0.0, 0.0, 1.0),
        radius=outer,
        height=length,
        resolution=48,
    )
    if inner > 0 and inner < outer:
        inner_cyl = pv.Cylinder(
            center=(0.0, 0.0, 0.0),
            direction=(0.0, 0.0, 1.0),
            radius=inner,
            height=length * 1.001,
            resolution=48,
        )
        try:
            return outer_cyl.boolean_difference(inner_cyl)
        except Exception:
            # Boolean ops can fail with older VTK builds; fall back to outer only.
            return outer_cyl
    return outer_cyl


def _build_sphere(volume: Volume):
    import pyvista as pv

    outer = volume.outer_radius_mm
    if outer <= 0:
        return None
    return pv.Sphere(radius=outer, center=(0.0, 0.0, 0.0))


def _absolute_position(
    volume: Volume, by_name: dict
) -> Tuple[float, float, float]:
    parent = (volume.parent or "").lower()
    base = (0.0, 0.0, 0.0)
    if parent and parent in by_name:
        base = _absolute_position(by_name[parent], by_name)
    return (
        base[0] + volume.position_mm[0],
        base[1] + volume.position_mm[1],
        base[2] + volume.position_mm[2],
    )


def _opacity_from_absorption_mm(abs_length_mm: float, characteristic_mm: float) -> float:
    if abs_length_mm <= 0:
        return 0.85
    ratio = characteristic_mm / abs_length_mm
    transmittance = math.exp(-ratio)
    return max(0.05, min(0.85, 0.15 + 0.7 * (1.0 - transmittance)))


def _build_polyline_with_segment_colors(
    traj: Trajectory,
):
    """Build a PyVista polyline with per-segment wavelength colour scalars.

    Returns (poly, rgb_array) where rgb_array has one row per segment.
    """
    import pyvista as pv

    points = np.array(traj.points, dtype=float)
    n_seg = len(points) - 1
    if n_seg <= 0:
        return None, None
    # Polyline cell connectivity: [2, i, i+1] per segment.
    cells = np.empty(n_seg * 3, dtype=np.int64)
    for i in range(n_seg):
        cells[3 * i] = 2
        cells[3 * i + 1] = i
        cells[3 * i + 2] = i + 1
    poly = pv.PolyData(points)
    poly.lines = cells

    # Per-segment colour: average the energy of the two endpoints, convert to
    # wavelength, then to RGB.  This lets a Cherenkov-like blue-to-red energy
    # loss along the path show up naturally.
    rgb = np.zeros((n_seg, 3), dtype=np.float32)
    for i in range(n_seg):
        e_mid = 0.5 * (traj.energies_ev[i] + traj.energies_ev[i + 1])
        wl = wavelength_nm_for_energy_ev(e_mid)
        rgb[i] = visible_rgb_for_wavelength(wl)
    poly.cell_data["rgb"] = rgb
    return poly, rgb


def _max_global_time_ns(trajectories: Iterable[Trajectory]) -> float:
    t_max = 0.0
    for traj in trajectories:
        if traj.times_ns:
            t_max = max(t_max, traj.times_ns[-1])
    return t_max


def _truncate_trajectory_to_time(traj: Trajectory, t_ns: float) -> Trajectory:
    """Return a shallow Trajectory containing only segments whose end-time <= t_ns."""
    if not traj.times_ns:
        return traj
    keep = 0
    for i, t in enumerate(traj.times_ns):
        if t <= t_ns:
            keep = i + 1
        else:
            break
    if keep == len(traj.times_ns):
        return traj
    if keep < 2:
        # not enough points to draw a line — return empty stub
        clone = Trajectory(
            event_id=traj.event_id,
            track_id=traj.track_id,
            particle=traj.particle,
            capped=traj.capped,
        )
        return clone
    clone = Trajectory(
        event_id=traj.event_id,
        track_id=traj.track_id,
        particle=traj.particle,
        capped=traj.capped,
    )
    clone.points = traj.points[:keep]
    clone.energies_ev = traj.energies_ev[:keep]
    clone.times_ns = traj.times_ns[:keep]
    clone.materials = traj.materials[:keep]
    clone.volumes = traj.volumes[:keep]
    return clone


def render(
    scene: Scene,
    trajectories: Iterable[Trajectory],
    *,
    screenshot: Optional[str] = None,
    background: str = "dark",
    show_volumes: bool = True,
    show_trajectories: bool = True,
    trajectory_limit: Optional[int] = None,
    window_size: Tuple[int, int] = (1280, 800),
    enable_time_slider: bool = True,
) -> None:
    """Render the scene + trajectories with PyVista."""
    import pyvista as pv

    trajectories = list(trajectories)
    off_screen = screenshot is not None
    plotter = pv.Plotter(off_screen=off_screen, window_size=window_size)
    if background == "light":
        plotter.set_background("white")
    else:
        plotter.set_background("black")

    # World wireframe.
    if scene.world_size_mm > 0:
        ws = scene.world_size_mm
        world_box = pv.Box(
            bounds=(-ws / 2, ws / 2, -ws / 2, ws / 2, -ws / 2, ws / 2)
        )
        plotter.add_mesh(
            world_box, style="wireframe", color="#5f6873", line_width=1.2, opacity=0.6
        )

    derived_by_name = scene.derived_by_name()
    volumes_by_lname = {v.name.lower(): v for v in scene.volumes}

    if show_volumes:
        for volume in scene.volumes:
            pos = _absolute_position(volume, volumes_by_lname)
            mesh = None
            shape_lower = (volume.shape_type or "box").lower()
            if shape_lower in ("box", "cube"):
                sx, sy, sz = volume.size_mm
                if sx <= 0 or sy <= 0 or sz <= 0:
                    continue
                mesh = _build_box(volume)
            elif shape_lower in ("tube", "cylinder", "cyl"):
                mesh = _build_tube(volume)
            elif shape_lower == "sphere":
                mesh = _build_sphere(volume)
            if mesh is None:
                continue
            try:
                mesh = mesh.translate(np.array(pos))
            except Exception:
                pass

            tags = {t.lower() for t in volume.tags}
            if "viz_forced_white" in tags or "viz_emitter" in tags:
                plotter.add_mesh(
                    mesh,
                    color="#fafad2",
                    opacity=0.9,
                    smooth_shading=True,
                    label=f"{volume.name} (emitter)",
                )
                continue

            material_key = volume.material.lower()
            derived = derived_by_name.get(material_key)
            color = (0.7, 0.85, 1.0)
            opacity = 0.25
            label_extra = ""
            if derived is not None and derived.available:
                color = derived.display_rgb
                if volume.size_mm and max(volume.size_mm) > 0:
                    characteristic_mm = max(volume.size_mm)
                else:
                    characteristic_mm = max(
                        volume.outer_radius_mm or 0.0, volume.length_mm or 0.0, 1.0
                    )
                opacity = _opacity_from_absorption_mm(
                    derived.mean_absorption_length_mm, characteristic_mm
                )
                label_extra = f"  n≈{derived.mean_refractive_index:.3f}"
            plotter.add_mesh(
                mesh,
                color=color,
                opacity=opacity,
                smooth_shading=True,
                label=f"{volume.name} ({volume.material}){label_extra}",
            )

    # Beams.
    for beam in scene.beams:
        if not beam.active and len(scene.beams) > 1:
            continue
        d = np.array(beam.direction)
        norm = float(np.linalg.norm(d))
        if norm <= 0:
            continue
        d = d / norm
        ws = scene.world_size_mm or 100.0
        origin = -d * (ws * 0.45)
        length = ws * 0.9
        arrow = pv.Arrow(
            start=origin, direction=d, scale=length, tip_length=0.05, tip_radius=0.01,
            shaft_radius=0.003,
        )
        plotter.add_mesh(arrow, color="#fff7c0", label=f"beam {beam.particle}")

    # Trajectory rendering with per-segment wavelength color.  We track the
    # actor returned so the time-slider callback can remove/replace them.
    trajectory_state: Dict[str, object] = {"actors": [], "limit": trajectory_limit}

    def _add_trajectories(current_max_time_ns: Optional[float]):
        # Remove previous trajectory actors.
        for actor in trajectory_state["actors"]:
            try:
                plotter.remove_actor(actor)
            except Exception:
                pass
        trajectory_state["actors"] = []
        if not show_trajectories:
            return
        count = 0
        for traj in trajectories:
            if (
                trajectory_state["limit"] is not None
                and count >= trajectory_state["limit"]
            ):
                break
            t = traj
            if current_max_time_ns is not None:
                t = _truncate_trajectory_to_time(traj, current_max_time_ns)
            if len(t.points) < 2:
                continue
            poly, _ = _build_polyline_with_segment_colors(t)
            if poly is None:
                continue
            actor = plotter.add_mesh(
                poly,
                scalars="rgb",
                rgb=True,
                line_width=1.5,
                show_scalar_bar=False,
            )
            trajectory_state["actors"].append(actor)
            count += 1

    t_max = _max_global_time_ns(trajectories) if show_trajectories else 0.0

    if show_trajectories and enable_time_slider and not off_screen and t_max > 0:
        # Initialize at end-of-run so the user sees the full picture; sliding
        # backward animates the propagation up to a chosen time.
        _add_trajectories(t_max)

        def _on_slider(value):
            _add_trajectories(float(value))

        plotter.add_slider_widget(
            callback=_on_slider,
            rng=(0.0, t_max),
            value=t_max,
            title="time (ns)",
            pointa=(0.025, 0.08),
            pointb=(0.32, 0.08),
            style="modern",
        )
    else:
        _add_trajectories(None)

    plotter.add_axes()
    try:
        plotter.add_legend(bcolor=None, face=None, size=(0.18, 0.22))
    except Exception:
        # Older PyVista versions reject the kwargs.
        pass
    plotter.camera_position = "iso"

    if screenshot:
        plotter.show(screenshot=screenshot, auto_close=True)
    else:
        plotter.show()
