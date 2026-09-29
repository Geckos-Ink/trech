"""PyVista renderer for TRECH viz scenes."""

from __future__ import annotations

import math
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

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


def _rotation_matrix(degrees: Tuple[float, float, float]) -> np.ndarray:
    """Geant4/Studio-compatible Euler rotation (Rz @ Ry @ Rx)."""
    rx, ry, rz = (math.radians(value) for value in degrees)
    cx, sx = math.cos(rx), math.sin(rx)
    cy, sy = math.cos(ry), math.sin(ry)
    cz, sz = math.cos(rz), math.sin(rz)
    mx = np.array([[1, 0, 0], [0, cx, -sx], [0, sx, cx]], dtype=float)
    my = np.array([[cy, 0, sy], [0, 1, 0], [-sy, 0, cy]], dtype=float)
    mz = np.array([[cz, -sz, 0], [sz, cz, 0], [0, 0, 1]], dtype=float)
    result = np.eye(4, dtype=float)
    result[:3, :3] = mz @ my @ mx
    return result


def _world_transform(volume: Volume, by_name: dict, seen: Optional[set] = None) -> np.ndarray:
    """Full placed transform, including parent placement, for classic-viewer fidelity."""
    seen = set(seen or ())
    key = volume.name.lower()
    if key in seen:
        return np.eye(4, dtype=float)
    seen.add(key)
    local = _rotation_matrix(volume.rotation_deg)
    local[:3, 3] = np.asarray(volume.position_mm, dtype=float)
    parent_key = (volume.parent or "").lower()
    if parent_key and parent_key in by_name:
        return _world_transform(by_name[parent_key], by_name, seen) @ local
    return local


def _parse_color(value: str) -> Optional[Tuple[float, float, float]]:
    text = value.strip()
    if text.startswith("#"):
        digits = text[1:]
        if len(digits) == 3:
            digits = "".join(char * 2 for char in digits)
        if len(digits) == 6:
            try:
                return tuple(int(digits[i:i + 2], 16) / 255.0 for i in (0, 2, 4))
            except ValueError:
                return None
    parts = [part for part in text.replace(" ", "").split(",") if part]
    if len(parts) == 3:
        try:
            rgb = [float(part) for part in parts]
        except ValueError:
            return None
        if any(component > 1.0 for component in rgb):
            rgb = [component / 255.0 for component in rgb]
        return tuple(max(0.0, min(1.0, component)) for component in rgb)
    return None


def _render_hints(tags: Sequence[str]) -> dict:
    """Parse the shared Studio ``viz_*`` tag vocabulary (display choices, never physics)."""
    hints = {
        "hidden": False, "solid": False, "shell": False, "emissive": False,
        "opacity": None, "color": None, "tint": None,
    }
    for raw in tags:
        text = str(raw).strip()
        low = text.lower()
        key, _, value = text.partition("=")
        key = key.strip().lower()
        if low in ("viz_hidden", "viz_hide"):
            hints["hidden"] = True
        elif low == "viz_solid":
            hints["solid"] = True
        elif low in ("viz_shell", "viz_wireframe"):
            hints["shell"] = True
        elif low in ("viz_emissive", "viz_glow"):
            hints["emissive"] = True
        elif key == "viz_opacity":
            try:
                hints["opacity"] = max(0.0, min(1.0, float(value)))
            except ValueError:
                pass
        elif key == "viz_color":
            hints["color"] = _parse_color(value)
        elif key == "viz_tint":
            hints["tint"] = _parse_color(value)
    return hints


def _opacity_from_absorption_mm(abs_length_mm: float, characteristic_mm: float) -> float:
    if abs_length_mm <= 0:
        return 0.85
    ratio = characteristic_mm / abs_length_mm
    transmittance = math.exp(-ratio)
    return max(0.05, min(0.85, 0.15 + 0.7 * (1.0 - transmittance)))


def _encloses(mesh_bounds, region) -> bool:
    lo, hi = region
    return all(mesh_bounds[2 * axis] <= lo[axis] and mesh_bounds[2 * axis + 1] >= hi[axis]
               for axis in range(3))


def _add_static_scene(
    plotter, scene: Scene, *, show_world: bool, show_volumes: bool, show_beams: bool,
    skip_enclosing=None,
) -> List[str]:
    """Add scene geometry with engine optics + shared authored render hints.

    ``skip_enclosing=(lo, hi)`` omits volumes that fully enclose that region (a zoomed camera
    would sit inside them); the omitted materials are returned so a caller can name them.
    """
    import pyvista as pv

    skipped: List[str] = []
    if show_world and scene.world_size_mm > 0:
        ws = scene.world_size_mm
        world_box = pv.Box(bounds=(-ws / 2, ws / 2, -ws / 2, ws / 2, -ws / 2, ws / 2))
        plotter.add_mesh(
            world_box, style="wireframe", color="#5f6873", line_width=1.2, opacity=0.6
        )

    derived_by_name = scene.derived_by_name()
    volumes_by_lname = {volume.name.lower(): volume for volume in scene.volumes}
    if show_volumes and scene.medium_size_mm > 0:
        # The Geant4 medium box (e.g. the Beer-Lambert water slab) is real transport geometry.
        ms = scene.medium_size_mm
        medium_bounds = (-ms / 2, ms / 2, -ms / 2, ms / 2, -ms / 2, ms / 2)
        if skip_enclosing is not None and _encloses(medium_bounds, skip_enclosing):
            skipped.append(scene.medium_material or "medium")
        else:
            derived = derived_by_name.get((scene.medium_material or "").lower())
            color = derived.display_rgb if derived is not None and derived.available else (
                (0.35, 0.62, 1.0) if "water" in (scene.medium_material or "").lower()
                else (0.7, 0.75, 0.85))
            plotter.add_mesh(
                pv.Box(bounds=medium_bounds),
                color=color, opacity=0.18, smooth_shading=True, show_edges=True,
                edge_color="#9fc4ff", label=f"medium ({scene.medium_material})",
            )
    if show_volumes:
        for volume in scene.volumes:
            hints = _render_hints(volume.tags)
            if hints["hidden"]:
                continue
            shape_lower = (volume.shape_type or "box").lower()
            mesh = None
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
                mesh = mesh.transform(_world_transform(volume, volumes_by_lname), inplace=False)
            except Exception:
                pass
            if skip_enclosing is not None and _encloses(mesh.bounds, skip_enclosing):
                skipped.append(volume.material or volume.name)
                continue

            tags_lower = {tag.lower() for tag in volume.tags}
            derived = derived_by_name.get(volume.material.lower())
            color = (0.7, 0.85, 1.0)
            opacity = 0.25
            label_extra = ""
            if derived is not None and derived.available:
                color = derived.display_rgb
                characteristic_mm = max(
                    max(volume.size_mm) if volume.size_mm else 0.0,
                    volume.outer_radius_mm or 0.0, volume.length_mm or 0.0, 1.0,
                )
                opacity = _opacity_from_absorption_mm(
                    derived.mean_absorption_length_mm, characteristic_mm
                )
                label_extra = f"  n≈{derived.mean_refractive_index:.3f}"
            if "viz_forced_white" in tags_lower or "viz_emitter" in tags_lower:
                color, opacity = (1.0, 1.0, 0.86), 0.9
            if hints["color"] is not None:
                color = hints["color"]
            if hints["tint"] is not None:
                color = tuple(color[i] * hints["tint"][i] for i in range(3))
            if hints["shell"]:
                opacity = min(opacity, 0.06)
            if hints["opacity"] is not None:
                opacity = hints["opacity"]
            if hints["solid"]:
                opacity = max(opacity, 0.95)
            plotter.add_mesh(
                mesh,
                color=color,
                opacity=opacity,
                smooth_shading=True,
                show_edges=bool(hints["shell"]),
                edge_color="#d9e8ff",
                lighting=not bool(hints["emissive"]),
                label=f"{volume.name} ({volume.material}){label_extra}",
            )

    if show_beams:
        for beam in scene.beams:
            if not beam.active and len(scene.beams) > 1:
                continue
            direction = np.array(beam.direction)
            norm = float(np.linalg.norm(direction))
            if norm <= 0:
                continue
            direction /= norm
            ws = scene.world_size_mm or 100.0
            arrow = pv.Arrow(
                start=-direction * (ws * 0.45), direction=direction, scale=ws * 0.9,
                tip_length=0.05, tip_radius=0.01, shaft_radius=0.003,
            )
            plotter.add_mesh(arrow, color="#fff7c0", label=f"beam {beam.particle}")
    return skipped


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
    # Build with only line cells. pv.PolyData(points) would also add one vertex
    # cell per point, so n_cells would be n_points + n_seg and the per-segment
    # cell_data below would fail the length check (rgb has n_seg rows).
    poly = pv.PolyData()
    poly.points = points
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
    show_world: bool = True,
    show_volumes: bool = True,
    show_beams: bool = True,
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

    _add_static_scene(
        plotter, scene, show_world=show_world, show_volumes=show_volumes, show_beams=show_beams
    )

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


# Held-frame / trajectory GIF capture lives in ``animate``; re-exported for existing callers.
from .animate import (  # noqa: E402,F401
    _gif_frame_duration_ms,
    render_material_animation,
    render_trajectory_animation,
)
