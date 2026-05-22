"""PyVista renderer for TRECH viz scenes."""

from __future__ import annotations

import math
from typing import Iterable, List, Optional, Tuple

import numpy as np

from .scene import Scene, Volume
from .trajectories import (
    Trajectory,
    visible_rgb_for_wavelength,
    wavelength_nm_for_energy_ev,
)


def _build_box(volume: Volume) -> "pyvista.PolyData":  # type: ignore[name-defined]
    import pyvista as pv

    sx, sy, sz = volume.size_mm
    return pv.Box(
        bounds=(-sx / 2, sx / 2, -sy / 2, sy / 2, -sz / 2, sz / 2)
    )


def _absolute_position(
    volume: Volume, by_name: dict, accum: Optional[Tuple[float, float, float]] = None
) -> Tuple[float, float, float]:
    parent = (volume.parent or "").lower()
    base = (0.0, 0.0, 0.0)
    if parent and parent in by_name:
        base = _absolute_position(by_name[parent], by_name, accum)
    return (
        base[0] + volume.position_mm[0],
        base[1] + volume.position_mm[1],
        base[2] + volume.position_mm[2],
    )


def _opacity_from_absorption_mm(abs_length_mm: float, characteristic_mm: float) -> float:
    if abs_length_mm <= 0:
        return 0.85
    ratio = characteristic_mm / abs_length_mm
    # Effective transmittance through one characteristic length.
    transmittance = math.exp(-ratio)
    # Convert: highly transmissive -> low opacity in the renderer.
    return max(0.05, min(0.85, 0.15 + 0.7 * (1.0 - transmittance)))


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
) -> None:
    """Render the scene + trajectories with PyVista."""
    import pyvista as pv

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
            if volume.shape_type != "box":
                # MVP: only boxes get rendered.  Tubes/spheres can be added next.
                continue
            sx, sy, sz = volume.size_mm
            if sx <= 0 or sy <= 0 or sz <= 0:
                continue
            pos = _absolute_position(volume, volumes_by_lname)
            mesh = _build_box(volume).translate(np.array(pos))

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
                characteristic_mm = max(volume.size_mm)
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

    # Trajectories.
    if show_trajectories:
        count = 0
        for traj in trajectories:
            if trajectory_limit is not None and count >= trajectory_limit:
                break
            if len(traj.points) < 2:
                continue
            points = np.array(traj.points, dtype=float)
            lines = np.empty((len(points) - 1) * 3, dtype=int)
            for i in range(len(points) - 1):
                lines[3 * i] = 2
                lines[3 * i + 1] = i
                lines[3 * i + 2] = i + 1
            poly = pv.PolyData(points)
            poly.lines = lines
            wl = wavelength_nm_for_energy_ev(traj.mean_energy_ev())
            rgb = visible_rgb_for_wavelength(wl)
            plotter.add_mesh(poly, color=rgb, line_width=1.5)
            count += 1

    plotter.add_axes()
    plotter.add_legend(bcolor=None, face=None, size=(0.18, 0.22))
    plotter.camera_position = "iso"

    if screenshot:
        plotter.show(screenshot=screenshot, auto_close=True)
    else:
        plotter.show()
