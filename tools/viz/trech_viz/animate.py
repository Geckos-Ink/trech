"""Off-screen 3D GIF capture for the classic TRECH viewer.

Two faithful replay sources, one camera/HUD/GIF pipeline:

* ``render_material_animation`` — held ``material_frame`` hook emits (hook-layer solver state:
  MD atoms and bonds, persistent parcels, membranes, moving apparatus, magnetization vectors).
* ``render_trajectory_animation`` — Geant4 ``trech_viz_trajectories.jsonl`` polylines revealed on
  their own recorded Geant4 clock, with the recorded interaction vertices.

Neither path creates motion: positions, colours, radii, bonds, vectors and apparatus come from the
run; the viewer only chooses a camera orbit, lighting, a ground grid and text. Held frames are
never interpolated. A trajectory polyline is revealed up to the playback clock by linear
interpolation along the recorded Geant4 step it is currently on — the straight chord Geant4 itself
recorded, never a synthesized path.
"""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

import numpy as np

from .metaballs import gaussian_density_grid
from .playback import ApparatusPart, MaterialFrame, sample_animation_frames, to_view
from .scene import Scene
from .trajectories import Trajectory, visible_rgb_for_wavelength, wavelength_nm_for_energy_ev

HUD_COLOR = "#f4d6af"


def unicode_font() -> Optional[str]:
    """A TrueType font with sub/superscripts and Greek (matplotlib ships DejaVu Sans)."""
    try:
        import os

        import matplotlib

        path = os.path.join(matplotlib.get_data_path(), "fonts", "ttf", "DejaVuSans.ttf")
        return path if os.path.exists(path) else None
    except Exception:  # noqa: BLE001 - VTK's built-in font is the fallback
        return None


def text_kwargs() -> Dict[str, str]:
    font = unicode_font()
    return {"font_file": font} if font else {}


def boxed(actor, opacity: float = 0.55) -> None:
    """Give a 2D text actor a translucent dark backing so it stays legible over tracks."""
    try:
        prop = actor.GetTextProperty()
        prop.SetBackgroundColor(0.03, 0.04, 0.07)
        prop.SetBackgroundOpacity(opacity)
    except Exception:  # noqa: BLE001 - legibility only
        pass


# --------------------------------------------------------------------------- clocks / text

_SI_TIME = [(1e-18, "as"), (1e-15, "fs"), (1e-12, "ps"), (1e-9, "ns"), (1e-6, "µs"),
            (1e-3, "ms"), (1.0, "s")]


def format_clock(value_s: float, span_s: float) -> str:
    """Human clock in the unit the whole clip spans (mm:ss for minute-scale clips)."""
    span_s = abs(float(span_s))
    value_s = float(value_s)
    if span_s >= 3.15e7:
        # A clip spanning ns reactions and millennia of decay: each value in its own unit.
        magnitude = abs(value_s)
        if magnitude >= 3.15e7:
            return f"{value_s / 3.156e7:.4g} yr"
        if magnitude >= 86400.0:
            return f"{value_s / 86400.0:.3g} d"
        return format_clock(value_s, max(magnitude, 1e-18))
    if span_s >= 60.0:
        minutes = int(value_s // 60.0)
        seconds_part = int(round(value_s - minutes * 60.0))
        if seconds_part == 60:
            minutes, seconds_part = minutes + 1, 0
        return f"{minutes:02d}:{seconds_part:02d}"
    scale, unit = _SI_TIME[0]
    for candidate_scale, candidate_unit in _SI_TIME:
        if span_s >= candidate_scale:
            scale, unit = candidate_scale, candidate_unit
    return f"{value_s / scale:7.2f} {unit}"


def _gif_frame_duration_ms(fps: int) -> int:
    """ImageIO's Pillow GIF writer expects milliseconds, unlike video APIs using seconds."""
    return max(10, int(round(1000.0 / max(1, int(fps)))))


GIF_COLORS = 64


def write_gif(path: str, images: Sequence[np.ndarray], fps: int,
              colors: Optional[int] = None) -> None:
    """Write a looping GIF on one shared adaptive palette (file-size only; content unchanged)."""
    import imageio.v2 as imageio

    imageio.mimsave(path, list(images), duration=_gif_frame_duration_ms(fps), loop=0)
    try:
        from PIL import Image

        rgb_frames = [Image.fromarray(image) for image in images]
        palette_source = rgb_frames[int(len(rgb_frames) * 0.7)]
        palette = palette_source.quantize(colors=int(colors or GIF_COLORS),
                                          method=Image.FASTOCTREE)
        quantized = [frame.quantize(palette=palette, dither=Image.NONE) for frame in rgb_frames]
        quantized[0].save(
            path, save_all=True, append_images=quantized[1:], loop=0,
            duration=_gif_frame_duration_ms(fps), disposal=1, optimize=True,
        )
    except Exception as exc:  # noqa: BLE001 - the unquantized GIF is already valid
        print(f"  (palette optimize skipped: {exc})")


def draw_caption(image: np.ndarray, lines: Sequence[str]) -> np.ndarray:
    """Explanatory text lower-left across the whole 3D area (drawn on the frame image)."""
    from PIL import Image, ImageDraw, ImageFont

    height = image.shape[0]
    size = max(11, int(height / 50))
    try:
        font = ImageFont.truetype(unicode_font() or "", size)
    except Exception:  # noqa: BLE001
        font = ImageFont.load_default()
    canvas = Image.fromarray(image).convert("RGBA")
    overlay = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    step = int(size * 1.3)
    widths = [draw.textlength(line, font=font) for line in lines]
    top = height - 8 - step * len(lines)
    draw.rectangle([0, top - 5, int(max(widths)) + 16, height], fill=(8, 10, 18, 150))
    for index, line in enumerate(lines):
        draw.text((8, top + index * step), line, font=font, fill=(201, 211, 230, 255))
    return np.asarray(Image.alpha_composite(canvas, overlay).convert("RGB"))



# --------------------------------------------------------------------------- plotter setup

def _new_plotter(width: int, height: int, background: str):
    import pyvista as pv

    plotter = pv.Plotter(off_screen=True, window_size=(width, height))
    if background == "light":
        plotter.set_background("#e8ebef", top="#ffffff")
    else:
        plotter.set_background("#080a11", top="#161b2a")
    try:
        plotter.enable_anti_aliasing("ssaa")
    except Exception:
        pass
    try:
        plotter.enable_depth_peeling(number_of_peels=8, occlusion_ratio=0.0)
    except Exception:
        pass
    return plotter


def _merge_bounds(bounds: Optional[List[float]], mins, maxs) -> List[float]:
    mins = np.asarray(mins, dtype=float)
    maxs = np.asarray(maxs, dtype=float)
    if bounds is None:
        return [float(mins[0]), float(maxs[0]), float(mins[1]), float(maxs[1]),
                float(mins[2]), float(maxs[2])]
    for axis in range(3):
        bounds[2 * axis] = min(bounds[2 * axis], float(mins[axis]))
        bounds[2 * axis + 1] = max(bounds[2 * axis + 1], float(maxs[axis]))
    return bounds


class _Turntable:
    """Camera framing + a labelled orbit (a rendering choice; never moves emitted data)."""

    def __init__(self, plotter, bounds: Sequence[float], width: int, height: int,
                 orbit_deg: float, elevation: float = 0.10, ground: bool = True,
                 ground_min_size: float = 0.0, view_dir: Optional[Sequence[float]] = None):
        import pyvista as pv

        self.plotter = plotter
        self.orbit_deg = float(orbit_deg)
        b = [float(v) for v in bounds]
        self.centre = np.array([0.5 * (b[0] + b[1]), 0.5 * (b[2] + b[3]), 0.5 * (b[4] + b[5])])
        span_y = max(b[3] - b[2], 1e-9)
        span_xz = max(b[1] - b[0], b[5] - b[4], 1e-9)
        if ground:
            ground_size = max(span_xz * 2.4, ground_min_size)
            plane = pv.Plane(
                center=(self.centre[0], b[2] - 0.004 * max(span_y, span_xz), self.centre[2]),
                direction=(0.0, 1.0, 0.0), i_size=ground_size, j_size=ground_size,
                i_resolution=12, j_resolution=12,
            )
            plotter.add_mesh(plane, color="#151925", opacity=0.72, show_edges=True,
                             edge_color="#30384a", line_width=0.6, lighting=False)
        self.width, self.height, self.elevation, self.view_dir = width, height, elevation, view_dir
        self.fit(b)

    def fit(self, bounds: Sequence[float]) -> None:
        """Frame ``bounds`` (also used per frame by ``reframe`` captures)."""
        b = [float(v) for v in bounds]
        width, height, elevation, view_dir = self.width, self.height, self.elevation, self.view_dir
        plotter = self.plotter
        self.centre = np.array([0.5 * (b[0] + b[1]), 0.5 * (b[2] + b[3]), 0.5 * (b[4] + b[5])])
        span_y = max(b[3] - b[2], 1e-9)
        span_xz = max(b[1] - b[0], b[5] - b[4], 1e-9)
        # Pull back far enough that the framed bounds fit the viewport, from the vertical FOV
        # and window aspect (plus the turntable's worst-case footprint circle).
        view_angle_deg = 27.0
        tan_half_v = math.tan(math.radians(view_angle_deg) * 0.5)
        tan_half_h = tan_half_v * (width / max(height, 1))
        half_horizontal = 0.5 * math.hypot(max(b[1] - b[0], 1e-9), max(b[5] - b[4], 1e-9))
        distance = 1.08 * max((0.5 * span_y) / tan_half_v, half_horizontal / tan_half_h,
                              span_xz * 1.2)
        direction = (np.array([0.78, float(elevation), 1.0]) if view_dir is None
                     else np.asarray(view_dir, dtype=float))
        self.base_vector = direction * (distance / float(np.linalg.norm(direction)))
        camera = plotter.camera
        camera.focal_point = tuple(self.centre)
        camera.position = tuple(self.centre + self.base_vector)
        camera.up = (0.0, 1.0, 0.0)
        camera.view_angle = view_angle_deg
        # Keep near/far clipping sane for Å-scale and metre-scale frames alike.
        try:
            camera.clipping_range = (distance * 1e-3, distance * 10.0)
        except Exception:
            pass

    def place(self, fraction: float) -> None:
        angle = math.radians(self.orbit_deg * (fraction - 0.5))
        ca, sa = math.cos(angle), math.sin(angle)
        v = self.base_vector
        orbit = np.array([ca * v[0] + sa * v[2], v[1], -sa * v[0] + ca * v[2]])
        self.plotter.camera.position = tuple(self.centre + orbit)


def _hud(plotter, lines: Sequence[str], height: int) -> None:
    plotter.remove_actor("observer_clock")
    boxed(plotter.add_text("\n".join(line for line in lines if line), position="upper_left",
                           font_size=max(8, int(height / 60)), color=HUD_COLOR,
                           name="observer_clock", **text_kwargs()), 0.45)


def _legend(plotter, entries: Sequence[Tuple[str, Tuple[float, float, float]]],
            anchor: str = "lower_right") -> None:
    """Colour-keyed legend as pixel-placed text (PyVista's legend box mis-scales long labels)."""
    if not entries:
        return
    width, height = (int(v) for v in plotter.window_size)
    font = max(8, int(height / 70))
    line = int(font * 1.75)
    longest = max(len(label) for label, _ in entries) + 1
    x = max(4, int(width - 10 - longest * font * 1.08))
    shown = entries[:8]
    for index, (label, color) in enumerate(shown):
        # Lower-right (clear of the upper-left HUD block) or upper-right.
        y = int(8 + (len(shown) - 1 - index) * line)
        if anchor == "upper_right":
            # Below a typical 4-5 line HUD block so the two never collide.
            y = int(height * 0.83 - (index + 1) * line)
        boxed(plotter.add_text(label, position=(x, y), font_size=font,
                               color=tuple(float(c) for c in color), name=f"legend_{index}",
                               **text_kwargs()))


def _screenshot(plotter) -> np.ndarray:
    plotter.render()
    image = plotter.screenshot(return_img=True, transparent_background=False)
    return np.ascontiguousarray(image[:, :, :3], dtype=np.uint8)


# --------------------------------------------------------------------------- material frames

_AXIS_VECTORS = {"x": (1.0, 0.0, 0.0), "y": (0.0, 1.0, 0.0), "z": (0.0, 0.0, 1.0)}


def _apparatus_mesh(part: ApparatusPart, up_axis: str):
    import pyvista as pv

    if part.shape == "mesh":
        cells = np.hstack([np.full((part.faces.shape[0], 1), 3, dtype=np.int64), part.faces])
        return pv.PolyData(to_view(part.vertices, up_axis), cells.ravel())
    centre = to_view(part.center, up_axis)[0]
    if part.shape == "segment":
        end = to_view(part.size, up_axis)[0]
        return pv.Line(tuple(centre), tuple(end))
    if part.shape == "box":
        size = np.abs(to_view(part.size, up_axis)[0])
        lo, hi = centre - 0.5 * size, centre + 0.5 * size
        return pv.Box(bounds=(lo[0], hi[0], lo[1], hi[1], lo[2], hi[2]))
    if part.shape == "sphere":
        wire = part.style == "wire"
        return pv.Sphere(radius=max(part.radius, 1e-9), center=tuple(centre),
                         theta_resolution=14 if wire else 32, phi_resolution=9 if wire else 24)
    axis = to_view(np.asarray(_AXIS_VECTORS.get(part.axis, (0, 0, 1))), up_axis)[0]
    try:
        return pv.Cylinder(center=tuple(centre), direction=tuple(axis),
                           radius=max(part.radius, 1e-9), height=max(part.height, 1e-9),
                           resolution=48, capping=part.style != "open")
    except TypeError:  # older PyVista without ``capping``
        return pv.Cylinder(center=tuple(centre), direction=tuple(axis),
                           radius=max(part.radius, 1e-9), height=max(part.height, 1e-9),
                           resolution=48)


def _apparatus_extent(part: ApparatusPart, up_axis: str) -> Tuple[np.ndarray, np.ndarray]:
    if part.shape == "mesh":
        view = to_view(part.vertices, up_axis)
        return view.min(axis=0), view.max(axis=0)
    centre = to_view(part.center, up_axis)[0]
    if part.shape == "segment":
        end = to_view(part.size, up_axis)[0]
        return np.minimum(centre, end), np.maximum(centre, end)
    if part.shape == "box":
        half = 0.5 * np.abs(to_view(part.size, up_axis)[0])
    else:
        reach = max(part.radius, 0.5 * part.height)
        half = np.full(3, reach, dtype=np.float32)
    return centre - half, centre + half


def _frame_actors(plotter, frame: MaterialFrame, point_size: float, line_width: float) -> list:
    """Add one held frame's material; return the actors so the next frame can replace them."""
    import pyvista as pv

    actors = []
    up = frame.up_axis
    segments = [part for part in frame.apparatus if part.shape == "segment"]
    if segments:
        # All segments in one mesh (trails, contacts): per-endpoint RGBA, one actor.
        ends = np.empty((2 * len(segments), 3), dtype=np.float32)
        seg_rgba = np.empty((2 * len(segments), 4), dtype=np.uint8)
        for index, part in enumerate(segments):
            ends[2 * index] = to_view(part.center, up)[0]
            ends[2 * index + 1] = to_view(part.size, up)[0]
            seg_rgba[2 * index:2 * index + 2] = np.rint(part.rgba * 255.0).astype(np.uint8)
        cells = np.empty((len(segments), 3), dtype=np.int64)
        cells[:, 0] = 2
        cells[:, 1] = np.arange(0, 2 * len(segments), 2)
        cells[:, 2] = cells[:, 1] + 1
        lines = pv.PolyData()
        lines.points = ends
        lines.lines = cells.ravel()
        lines.point_data["rgba"] = seg_rgba
        actors.append(plotter.add_mesh(lines, scalars="rgba", rgba=True,
                                       line_width=line_width * 1.2, render_lines_as_tubes=True,
                                       show_scalar_bar=False))
    for part in frame.apparatus:
        if part.shape == "segment":
            continue
        mesh = _apparatus_mesh(part, up)
        rgb, alpha = tuple(float(c) for c in part.rgba[:3]), float(part.rgba[3])
        if part.shape == "mesh" and part.vertex_rgba is not None:
            mesh.point_data["rgba"] = np.ascontiguousarray(
                np.rint(np.clip(part.vertex_rgba, 0, 1) * 255.0), dtype=np.uint8)
            actors.append(plotter.add_mesh(mesh, scalars="rgba", rgba=True, smooth_shading=True,
                                           specular=0.35, specular_power=24.0,
                                           show_scalar_bar=False))
            continue
        if part.style == "wire":
            actors.append(plotter.add_mesh(mesh, color=rgb, opacity=alpha, style="wireframe",
                                           line_width=max(1.0, line_width * 0.5)))
        else:
            actors.append(plotter.add_mesh(mesh, color=rgb, opacity=alpha, smooth_shading=True,
                                           specular=0.35, specular_power=24.0))
    if frame.grid is not None:
        actors += _grid_actors(plotter, frame.grid, up)
    if frame.labels:
        by_color: Dict[Tuple, List] = {}
        for position, text, rgb in frame.labels:
            by_color.setdefault(rgb, []).append((to_view(position, up)[0], text))
        height = int(plotter.window_size[1])
        for index, (rgb, items) in enumerate(by_color.items()):
            actors.append(plotter.add_point_labels(
                np.asarray([p for p, _ in items]), [t for _, t in items],
                font_size=max(10, int(height / 46)), text_color=rgb, shape_color="#0b1220",
                shape_opacity=0.55, show_points=False, always_visible=True,
                name=f"frame_labels_{index}", **text_kwargs()))
    if frame.positions_mm.shape[0] == 0 or (frame.grid is not None and frame.grid.replaces_points):
        return actors
    points = frame.points_view()
    source_frame = frame
    if frame.material_groups:
        from dataclasses import replace
        keep = np.ones(len(points), dtype=bool)
        for group in frame.material_groups:
            indices = group['indices']
            keep[indices] = False
            if not len(indices):
                continue
            # Reuse the ordinary fused-surface path with each group's unchanged centres.
            part = replace(frame, positions_mm=frame.positions_mm[indices],
                colors_rgba=np.tile(group['rgba'], (len(indices), 1)),
                surface=replace(group['surface'], opacity=float(group['rgba'][3])),
                material_groups=[], apparatus=[], labels=[], grid=None, bonds=None, vectors=None,
                radii=None)
            actors += _frame_actors(plotter, part, point_size, line_width)
        frame = replace(frame, positions_mm=frame.positions_mm[keep], colors_rgba=frame.colors_rgba[keep],
                        radii=frame.radii[keep] if frame.radii is not None else None,
                        bonds=None, vectors=None, material_groups=[])
        points = frame.points_view()
    rgba8 = np.ascontiguousarray(np.rint(frame.colors_rgba * 255.0), dtype=np.uint8)

    surface_hint = frame.surface if (
        frame.surface is not None and frame.surface.positions_unmodified
    ) else None
    if surface_hint is not None:
        density = gaussian_density_grid(points, surface_hint)
        grid = pv.ImageData(dimensions=density.values.shape, spacing=(density.spacing_mm,) * 3,
                            origin=tuple(float(value) for value in density.origin_mm))
        grid.point_data["density"] = density.values.flatten(order="F")
        surface = grid.contour([surface_hint.iso_level], scalars="density")
        if surface.n_points > 0:
            rgb = tuple(float(value) for value in np.mean(frame.colors_rgba[:, :3], axis=0))
            actors.append(plotter.add_mesh(
                surface, color=rgb, opacity=surface_hint.opacity, smooth_shading=True,
                ambient=0.18, diffuse=0.72, specular=0.15 + 0.7 * surface_hint.gloss,
                specular_power=8.0 + 56.0 * surface_hint.gloss, show_scalar_bar=False,
            ))
            return actors

    cloud = pv.PolyData(points)
    if len(points):
        cloud.point_data["rgba"] = rgba8
    if frame.radii is not None and len(points):
        # True 3D spheres of the emitted size (atoms, parcels) — depth-correct, lit.
        cloud.point_data["radius"] = np.maximum(frame.radii.astype(np.float32), 0.0)
        resolution = 14 if points.shape[0] < 1500 else 8
        sphere = pv.Sphere(radius=1.0, theta_resolution=resolution, phi_resolution=resolution)
        glyphs = cloud.glyph(geom=sphere, scale="radius", orient=False)
        if glyphs.n_points > 0:
            actors.append(plotter.add_mesh(glyphs, scalars="rgba", rgba=True, smooth_shading=True,
                                           specular=0.45, specular_power=30.0,
                                           show_scalar_bar=False))
    elif len(points):
        actors.append(plotter.add_points(cloud, scalars="rgba", rgba=True, point_size=point_size,
                                         render_points_as_spheres=True, emissive=True,
                                         show_scalar_bar=False))
    if source_frame.material_groups:
        # Declared bonds/vectors still address the original emitted centres, even when the
        # material body replaced all point glyphs.
        frame = source_frame
        points = frame.points_view()
        rgba8 = np.ascontiguousarray(np.rint(frame.colors_rgba * 255.0), dtype=np.uint8)
    if frame.bonds is not None and frame.bonds.shape[0] > 0:
        cells = np.empty((frame.bonds.shape[0], 3), dtype=np.int64)
        cells[:, 0] = 2
        cells[:, 1:] = frame.bonds
        lines = pv.PolyData()
        lines.points = points
        lines.lines = cells.ravel()
        lines.point_data["rgba"] = rgba8
        if frame.radii is not None and frame.radii.size:
            # Ball-and-stick: world-size bond cylinders scaled to the smallest emitted atom.
            positive = frame.radii[frame.radii > 0]
            stick = 0.32 * float(positive.min()) if positive.size else 0.1
            tubes = lines.tube(radius=stick, n_sides=12)
            actors.append(plotter.add_mesh(tubes, scalars="rgba", rgba=True, smooth_shading=True,
                                           specular=0.3, show_scalar_bar=False))
        else:
            actors.append(plotter.add_mesh(lines, scalars="rgba", rgba=True,
                                           line_width=line_width, render_lines_as_tubes=True,
                                           show_scalar_bar=False))
    if frame.vectors is not None:
        vectors = to_view(frame.vectors, up)
        magnitude = np.linalg.norm(vectors, axis=1)
        keep = magnitude > 1e-12
        if keep.any():
            arrows_src = pv.PolyData(points[keep])
            arrows_src.point_data["vec"] = vectors[keep]
            arrows_src.point_data["mag"] = magnitude[keep]
            arrows_src.point_data["rgba"] = rgba8[keep]
            arrows = arrows_src.glyph(orient="vec", scale="mag", factor=1.0,
                                      geom=pv.Arrow(tip_length=0.3, tip_radius=0.12,
                                                    shaft_radius=0.045))
            actors.append(plotter.add_mesh(arrows, scalars="rgba", rgba=True,
                                           smooth_shading=True, show_scalar_bar=False))
    return actors


def _upsample(values: np.ndarray, factor: int) -> np.ndarray:
    """Separable linear upsampling (numpy only) of a small cell-centred grid."""
    out = values.astype(np.float32)
    for axis in range(3):
        n = out.shape[axis]
        src = np.arange(n, dtype=np.float32)
        dst = np.linspace(0.0, n - 1.0, (n - 1) * factor + 1, dtype=np.float32)
        out = np.apply_along_axis(lambda line: np.interp(dst, src, line), axis, out)
    return out


def _grid_actors(plotter, grid, up: str) -> list:
    """One smooth surface (or grain cloud) per solver cell class of a ``PhaseGrid``."""
    import pyvista as pv

    actors = []
    values = grid.values
    if up != "y":  # frame x,y,z -> view x,z,y
        values = values.transpose(0, 2, 1)
    origin = to_view(np.asarray(grid.origin, dtype=np.float32), up)[0]
    spacing = np.abs(to_view(np.asarray(grid.spacing, dtype=np.float32), up)[0])
    rng = np.random.default_rng(11)
    for cls in grid.classes:
        indicator = (values == cls["id"]).astype(np.float32)
        if not indicator.any():
            continue
        rgba = cls["rgba"]
        rgb, alpha = tuple(float(c) for c in rgba[:3]), float(rgba[3])
        if cls["style"] == "grains":
            cells = np.argwhere(indicator > 0).astype(np.float32)
            per = 26
            jitter = rng.uniform(-0.47, 0.47, size=(cells.shape[0] * per, 3)).astype(np.float32)
            centres = origin + (np.repeat(cells, per, axis=0) + jitter) * spacing
            cloud = pv.PolyData(centres)
            cloud.point_data["r"] = (rng.uniform(0.06, 0.11, centres.shape[0]).astype(np.float32)
                                     * float(spacing.min()))
            glyphs = cloud.glyph(geom=pv.Icosphere(radius=1.0, nsub=1), scale="r", orient=False)
            actors.append(plotter.add_mesh(glyphs, color=rgb, opacity=alpha, smooth_shading=False,
                                           specular=0.1))
            continue
        padded = np.pad(indicator, 1)
        factor = max(1, min(24, round(3 * grid.render_detail)))
        fine = _upsample(padded, factor)
        image = pv.ImageData(dimensions=fine.shape, spacing=tuple(float(v) for v in spacing / factor),
                             origin=tuple(float(v) for v in origin - spacing))
        image.point_data["v"] = fine.flatten(order="F")
        surface = image.contour([0.5], scalars="v")
        if surface.n_points == 0:
            continue
        try:
            surface = surface.smooth_taubin(n_iter=25, pass_band=0.08)
        except Exception:  # noqa: BLE001 - an unsmoothed surface is still the solver's cells
            pass
        liquid = cls["style"] == "liquid"
        actors.append(plotter.add_mesh(
            surface, color=rgb, opacity=alpha, smooth_shading=True,
            ambient=0.45 if liquid else 0.15, diffuse=0.7, specular=0.6 if liquid else 0.9,
            specular_power=40.0 if liquid else 80.0))
    return actors


def _frame_extent(frame: MaterialFrame) -> Optional[Tuple[np.ndarray, np.ndarray]]:
    mins, maxs = [], []
    if frame.positions_mm.shape[0] > 0:
        points = frame.points_view()
        pad = 0.0
        if frame.radii is not None and frame.radii.size:
            pad = float(np.max(frame.radii))
        if frame.surface is not None:
            pad = max(pad, frame.surface.sigma_mm * 1.5 + 4.0)
        if frame.material_groups:
            pad = max(pad, max(g['surface'].sigma_mm * 1.5 + 4 for g in frame.material_groups))
        mins.append(points.min(axis=0) - pad)
        maxs.append(points.max(axis=0) + pad)
        if frame.vectors is not None:
            tips = points + to_view(frame.vectors, frame.up_axis)
            mins.append(tips.min(axis=0))
            maxs.append(tips.max(axis=0))
    for part in frame.apparatus:
        lo, hi = _apparatus_extent(part, frame.up_axis)
        mins.append(lo)
        maxs.append(hi)
    if frame.grid is not None:
        lo = to_view(np.asarray(frame.grid.origin, dtype=np.float32), frame.up_axis)[0]
        pitch = np.abs(to_view(np.asarray(frame.grid.spacing, dtype=np.float32), frame.up_axis)[0])
        extent = to_view(np.asarray(frame.grid.shape, dtype=np.float32) * frame.grid.spacing,
                         frame.up_axis)[0]
        mins.append(lo - pitch)
        maxs.append(lo + np.abs(extent))
    if not mins:
        return None
    return np.min(np.asarray(mins), axis=0), np.max(np.asarray(maxs), axis=0)


def render_material_animation(
    scene: Optional[Scene],
    frames: Sequence[MaterialFrame],
    *,
    gif: str,
    screenshot: Optional[str] = None,
    background: str = "dark",
    show_volumes: bool = True,
    window_size: Tuple[int, int] = (480, 640),
    fps: int = 10,
    seconds: float = 4.0,
    orbit_deg: float = 16.0,
    title: Optional[str] = None,
    elevation: float = 0.10,
    reframe: bool = False,
    chart_width: int = 0,
    caption: Sequence[str] = (),
    render_detail: float = 1.0,
    merge_radius_scale: float = 1.0,
) -> None:
    """Render held ``material_frame`` output as a classic trech-viz GIF.

    This is the same engine/scenario output Studio consumes. The classic renderer adds only a
    camera orbit, ground grid, legend and text; positions, RGBA, radii, bonds, vectors, moving
    apparatus, phase, HUD observables and the physical/observer clock mapping are replayed
    verbatim. A scenario may request the same Gaussian-density merging used by TRECH's water
    renderer; otherwise points render as spheres (true-size when ``radii`` are emitted).
    z-up frames are axis-relabelled to the viewer's y-up apparatus.
    """
    if not frames:
        raise ValueError("material animation requires at least one material_frame")
    from .playback import material_render_options
    frames = material_render_options(frames, render_detail, merge_radius_scale)
    from .renderer import _add_static_scene

    fps = max(1, int(fps))
    frame_count = max(2, int(round(max(seconds, 0.2) * fps)))
    output_frames = sample_animation_frames(list(frames), frame_count)
    width, height = max(64, int(window_size[0])), max(64, int(window_size[1]))
    from .charts import FrameCharts, compose

    panel = FrameCharts(frames, chart_width or int(width * 0.36), height)
    if panel:
        width -= panel.width
    else:
        panel = None
    plotter = _new_plotter(width, height, background)

    # A non-mm frame (Å-scale MD, a unit-less membrane model) is scale-independent of the
    # Geant4 mm apparatus, so drawing that scene around it would be meaningless.
    mm_frames = all(frame.length_unit == "mm" for frame in frames)
    bounds: Optional[List[float]] = None
    if scene is not None and mm_frames and show_volumes and all(frame.show_geant4_scene for frame in frames):
        _add_static_scene(plotter, scene, show_world=False, show_volumes=True, show_beams=False)
        if plotter.renderer.actors:
            bounds = list(float(value) for value in plotter.bounds)
    for frame in frames:
        extent = _frame_extent(frame)
        if extent is not None:
            bounds = _merge_bounds(bounds, *extent)
    if bounds is None:
        bounds = [-1.0, 1.0, -1.0, 1.0, -1.0, 1.0]
    turntable = _Turntable(plotter, bounds, width, height, orbit_deg, elevation=elevation,
                           ground_min_size=130.0 if (mm_frames and scene is not None) else 0.0)
    _legend(plotter, next((frame.legend for frame in frames if frame.legend), []),
            anchor="upper_right" if caption else "lower_right")
    plotter.show(auto_close=False, interactive=False)

    # Screen-space sizes only (points without radii, bond tubes); world sizes stay emitted.
    point_size = max(7.0, min(15.0, 9.0 * height / 420.0))
    line_width = max(2.0, min(6.0, 3.0 * height / 420.0))
    clip_start = frames[0].physical_time_s
    clip_end = frames[-1].physical_time_s
    clock_span = max(abs(clip_end), abs(clip_end - clip_start))
    unit_note = "" if mm_frames else f"  ·  lengths in {frames[0].length_unit}"
    images = []
    actors: list = []
    for output_index, frame in enumerate(output_frames):
        fraction = output_index / max(1, len(output_frames) - 1)
        for actor in actors:
            plotter.remove_actor(actor)
        actors = _frame_actors(plotter, frame, point_size, line_width)
        if reframe:
            # Streams whose frames are different objects (one circuit per gate) frame each one.
            extent = _frame_extent(frame)
            if extent is not None:
                turntable.fit(_merge_bounds(None, *extent))
        turntable.place(fraction)
        phase = frame.phase.split(":", 1)[-1].replace("_", " ")
        lines = [
            (title + "\n" if title else "")
            + ("TRECH 3D  |  " + (frame.clock_text or (
                f"{format_clock(frame.physical_time_s, clock_span)} / "
                f"{format_clock(clip_end, clock_span)}")) + unit_note),
            phase,
        ] + list(frame.hud_lines)
        _hud(plotter, lines, height)
        image = _screenshot(plotter)
        if caption:
            image = draw_caption(image, caption)
        if panel is not None:
            image = compose(image, panel.render(frame.playback_time_s, frame.physical_time_s))
        images.append(image)

    plotter.close()
    write_gif(gif, images, fps)
    Path(gif).with_suffix('.render.json').write_text(json.dumps(dict(
        render_detail=render_detail, merge_radius_scale=merge_radius_scale,
        representation_only=True, recorded_positions_modified=False,
        topology_scope='emitted topology counts remain authored values; width overrides can change apparent connections',
        neck_samples_disabled=merge_radius_scale != 1), indent=2) + '\n')
    if screenshot:
        import imageio.v2 as imageio

        imageio.imwrite(screenshot, images[-1])


# --------------------------------------------------------------------------- trajectories

SPECIES_COLORS: Dict[str, Tuple[float, float, float]] = {
    "gamma": (1.0, 0.84, 0.28),
    "e-": (0.25, 0.85, 1.0),
    "e+": (1.0, 0.38, 0.82),
    "proton": (1.0, 0.42, 0.2),
    "neutron": (0.82, 0.84, 0.9),
    "alpha": (0.72, 0.5, 1.0),
    "anti_nu_e": (0.45, 0.48, 0.55),
    "nu_e": (0.45, 0.48, 0.55),
}
ION_COLOR = (0.72, 0.5, 1.0)
DEFAULT_COLOR = (0.9, 0.9, 0.9)
# Neutral quanta whose discrete Geant4 interaction vertices are worth marking; a charged track's
# every step is a continuous-loss "interaction", so marking those would only paint the track.
MARKED_SPECIES = {"gamma", "opticalphoton", "neutron"}


def species_label(particle: str) -> str:
    name = particle.strip()
    if name in SPECIES_COLORS or name == "opticalphoton":
        return name
    if any(ch.isdigit() for ch in name) or name == "GenericIon":
        return "ion"
    return name or "?"


def species_color(particle: str, energy_ev: float = 0.0) -> Tuple[float, float, float]:
    if particle == "opticalphoton":
        return visible_rgb_for_wavelength(wavelength_nm_for_energy_ev(energy_ev))
    label = species_label(particle)
    if label == "ion":
        return ION_COLOR
    return SPECIES_COLORS.get(label, DEFAULT_COLOR)


class _Track:
    __slots__ = ("points", "times", "energy", "particle", "primary", "marks", "color", "event_id",
                 "baseline")

    def __init__(self, traj: Trajectory):
        self.event_id = traj.event_id
        self.baseline = False
        self.points = np.asarray(traj.points, dtype=np.float64)
        times = np.asarray(traj.times_ns, dtype=np.float64)
        self.times = np.maximum.accumulate(times) if times.size else times
        self.energy = np.asarray(traj.energies_ev, dtype=np.float64)
        self.particle = traj.particle
        self.primary = traj.track_id == 1
        self.color = species_color(traj.particle, float(self.energy[0]) if self.energy.size else 0.0)
        self.marks = []
        if traj.particle in MARKED_SPECIES:
            for index, kind in enumerate(traj.interactions):
                if kind in ("scatter", "interaction") and 0 < index:
                    self.marks.append((index, kind))

    def prefix(self, t_ns: float) -> Tuple[Optional[np.ndarray], Optional[np.ndarray]]:
        """Recorded points up to ``t_ns`` plus the head on the current recorded step."""
        if self.points.shape[0] == 0 or t_ns < self.times[0]:
            return None, None
        k = int(np.searchsorted(self.times, t_ns, side="right"))
        if k >= self.points.shape[0]:
            return self.points, None
        t0, t1 = self.times[k - 1], self.times[k]
        fraction = 0.0 if t1 <= t0 else (t_ns - t0) / (t1 - t0)
        head = self.points[k - 1] + fraction * (self.points[k] - self.points[k - 1])
        return np.vstack([self.points[:k], head[None, :]]), head


DISPLAY_NAMES = {"opticalphoton": "optical photon", "anti_nu_e": "anti-nu_e", "gamma": "gamma"}

# Kinetic-energy ramp (low → high): deep violet, red, orange, yellow, white-hot.
_ENERGY_STOPS = np.array([
    [0.55, 0.3, 0.95], [0.9, 0.2, 0.45], [1.0, 0.45, 0.1], [1.0, 0.85, 0.25], [1.0, 1.0, 0.92],
], dtype=np.float32)


def energy_colors(energy_ev: np.ndarray, reference_ev: float) -> np.ndarray:
    """Map recorded kinetic energy (fraction of the run's highest primary energy) to RGB."""
    fraction = np.clip(np.asarray(energy_ev, dtype=np.float64).reshape(-1)
                       / max(reference_ev, 1e-30), 0.0, 1.0)
    position = fraction * (len(_ENERGY_STOPS) - 1)
    low = np.clip(np.floor(position).astype(int), 0, len(_ENERGY_STOPS) - 2)
    weight = (position - low)[:, None]
    return ((1.0 - weight) * _ENERGY_STOPS[low] + weight * _ENERGY_STOPS[low + 1]).astype(np.float32)


def _polyline_batch(tracks: Sequence[Tuple[np.ndarray, np.ndarray]]):
    """One PolyData of many polylines; each entry pairs points (n,3) with RGB (3,) or (n,3)."""
    import pyvista as pv

    pts, cells, colors = [], [], []
    offset = 0
    for points, rgb in tracks:
        n = points.shape[0]
        if n < 2:
            continue
        pts.append(points)
        cells.append(np.concatenate([[n], np.arange(offset, offset + n)]))
        colors.append(np.broadcast_to(np.asarray(rgb, dtype=np.float32), (n, 3)))
        offset += n
    if not pts:
        return None
    poly = pv.PolyData()
    poly.points = np.vstack(pts)
    poly.lines = np.concatenate(cells).astype(np.int64)
    poly.point_data["rgb"] = np.ascontiguousarray(np.vstack(colors))
    return poly


def select_events(trajectories: Sequence[Trajectory], with_particle: Optional[str],
                  context_events: int = 0) -> Tuple[List[Trajectory], Optional[str]]:
    """Keep whole events containing ``with_particle`` (+ the first ``context_events`` others).

    A display selection for rare outcomes (e.g. the few events where Geant4 produced an (n,p)
    proton); it never edits a track, and the returned note states the selection for the HUD.
    """
    if not with_particle:
        return list(trajectories), None
    by_event: Dict[int, List[Trajectory]] = {}
    for traj in trajectories:
        by_event.setdefault(traj.event_id, []).append(traj)
    wanted = [eid for eid, group in by_event.items()
              if any(traj.particle == with_particle for traj in group)]
    wanted_set = set(wanted)
    others = [eid for eid in by_event if eid not in wanted_set][:max(0, int(context_events))]
    keep = wanted_set | set(others)
    note = (f"selection: {len(wanted)} of {len(by_event)} recorded events contain a "
            f"{DISPLAY_NAMES.get(with_particle, with_particle)}"
            + (f" (+{len(others)} ordinary events)" if others else ""))
    return [traj for traj in trajectories if traj.event_id in keep], note


def activity_clock(tracks: Sequence[_Track], frame_count: int, mode: str = "activity") -> np.ndarray:
    """Geant4 times (ns) sampled at each playback frame.

    ``activity`` maps playback fraction to the quantiles of all recorded step times, so a clip
    spanning picoseconds of ionisation and years of β decay spends frames where Geant4 recorded
    steps; ``linear`` is uniform. Either way the HUD prints the true recorded Geant4 time.
    """
    times = np.concatenate([track.times for track in tracks if track.times.size])
    if times.size == 0:
        return np.zeros(frame_count)
    fractions = np.linspace(0.0, 1.0, frame_count)
    if mode == "linear":
        return times.min() + fractions * (times.max() - times.min())
    return np.quantile(times, fractions)


def _side_view(tracks: Sequence[_Track], elevation: float) -> np.ndarray:
    """Camera direction perpendicular to the recorded primaries' mean emission direction.

    A beam seen end-on collapses to a dot; framing it side-on shows depth along the beam.
    """
    directions = []
    for track in tracks:
        if track.primary and track.points.shape[0] >= 2:
            step = track.points[1] - track.points[0]
            norm = float(np.linalg.norm(step))
            if norm > 0:
                directions.append(step / norm)
    up = np.array([0.0, 1.0, 0.0])
    beam = np.mean(directions, axis=0) if directions else np.array([0.0, 0.0, 1.0])
    if float(np.linalg.norm(beam)) < 0.3:  # isotropic source: keep the default oblique view
        return np.array([0.78, float(elevation), 1.0])
    beam = beam / float(np.linalg.norm(beam))
    side = np.cross(beam, up)
    if float(np.linalg.norm(side)) < 1e-3:  # beam along the vertical
        side = np.array([1.0, 0.0, 0.0])
    side = side / float(np.linalg.norm(side))
    return side + float(elevation) * up - 0.3 * beam


def render_trajectory_animation(
    scene: Optional[Scene],
    trajectories: Iterable[Trajectory],
    *,
    gif: str,
    screenshot: Optional[str] = None,
    background: str = "dark",
    show_volumes: bool = True,
    window_size: Tuple[int, int] = (640, 480),
    fps: int = 12,
    seconds: float = 6.0,
    orbit_deg: float = 30.0,
    title: Optional[str] = None,
    hud_lines: Sequence[str] = (),
    clock: str = "activity",
    hold_fraction: float = 0.18,
    elevation: float = 0.35,
    color_by: str = "species",
    zoom_ratio: float = 5.0,
    compare: Iterable[Trajectory] = (),
    labels: Tuple[str, str] = ("", ""),
) -> None:
    """Reveal recorded Geant4 trajectories in 3D on their own recorded clock.

    Every event is overlaid from its own t=0 (Geant4 event time), so the GIF shows the sampled
    population of the run rather than one hand-picked history. Discrete interaction vertices of
    neutral quanta are marked where Geant4 recorded them (white: scatter, red: other discrete
    interaction). ``color_by="energy"`` colours every recorded point by its recorded kinetic
    energy, so slowing down (a Bragg stop) is read straight off the Geant4 record.

    When the apparatus is ``zoom_ratio`` times larger than where the tracks are (a 4 mm proton
    range inside a 20 cm water medium), the camera frames the tracks, and volumes enclosing the
    whole framed region are not drawn (they would only fog the view); the HUD names them.

    ``compare`` overlays a second run's recorded trajectories (same geometry, one changed
    condition) in a single contrasting colour on the same clock, so a difference between two
    real Geant4 runs is shown side by side instead of being drawn from a formula.
    """
    import pyvista as pv
    from .renderer import _add_static_scene

    tracks = [_Track(traj) for traj in trajectories if len(traj.points) >= 1]
    if not tracks:
        raise ValueError("trajectory animation requires at least one recorded trajectory")
    baseline = [_Track(traj) for traj in compare if len(traj.points) >= 1]
    baseline_rgb = (1.0, 0.62, 0.18)
    if baseline and tracks[0].particle != "opticalphoton":
        # Two non-optical runs: one clearly distinct colour per run (species is the same).
        baseline_rgb = (0.95, 0.35, 0.9)
        for track in tracks:
            track.color = (0.3, 0.9, 1.0)
    for track in baseline:
        track.color = baseline_rgb
        track.baseline = True
    everything = tracks + baseline
    fps = max(1, int(fps))
    total = max(2, int(round(max(seconds, 0.2) * fps)))
    hold = int(round(total * max(0.0, min(0.6, hold_fraction))))
    reveal = max(2, total - hold)
    clock_ns = activity_clock(everything, reveal, clock)
    clock_ns = np.concatenate([clock_ns, np.full(total - reveal, clock_ns[-1])])
    width, height = max(64, int(window_size[0])), max(64, int(window_size[1]))
    plotter = _new_plotter(width, height, background)

    # Frame the apparatus plus where most recorded steps are; rare world-escaping rays may
    # leave the frame (a camera choice — every recorded track is still drawn).
    all_points = np.vstack([track.points for track in everything])
    track_lo = np.percentile(all_points, 2.0, axis=0)
    track_hi = np.percentile(all_points, 98.0, axis=0)
    track_span = max(float(np.max(track_hi - track_lo)), 1e-6)
    track_lo, track_hi = track_lo - 0.08 * track_span, track_hi + 0.08 * track_span
    bounds: Optional[List[float]] = None
    enclosing: List[str] = []
    if scene is not None and show_volumes:
        _add_static_scene(plotter, scene, show_world=False, show_volumes=True, show_beams=False)
        if plotter.renderer.actors:
            scene_bounds = list(float(value) for value in plotter.bounds)
            scene_span = max(scene_bounds[1] - scene_bounds[0], scene_bounds[3] - scene_bounds[2],
                             scene_bounds[5] - scene_bounds[4])
            if scene_span > zoom_ratio * track_span:
                plotter.clear_actors()
                enclosing = _add_static_scene(
                    plotter, scene, show_world=False, show_volumes=True, show_beams=False,
                    skip_enclosing=(tuple(track_lo), tuple(track_hi)),
                ) or []
            else:
                bounds = scene_bounds
    bounds = _merge_bounds(bounds, track_lo, track_hi)
    turntable = _Turntable(plotter, bounds, width, height, orbit_deg, elevation=elevation,
                           ground=False, view_dir=_side_view(tracks, elevation))
    reference_ev = max((float(track.energy[0]) for track in tracks
                        if track.primary and track.energy.size), default=1.0)
    if color_by == "energy":
        ramp = energy_colors(np.array([1.0, 0.5, 0.15, 0.0]), 1.0)
        _legend(plotter, [("E = primary", tuple(ramp[0])), ("E/2", tuple(ramp[1])),
                          ("slowing", tuple(ramp[2])), ("stopped", tuple(ramp[3]))])
    elif baseline:
        main_rgb = (0.4, 1.0, 0.4) if tracks[0].particle == "opticalphoton" else tracks[0].color
        _legend(plotter, [(labels[0] or "this run", main_rgb),
                          (labels[1] or "comparison run", baseline_rgb)])
    else:
        seen: List[Tuple[str, Tuple[float, float, float]]] = []
        for track in tracks:
            label = DISPLAY_NAMES.get(species_label(track.particle), species_label(track.particle))
            if label not in [entry[0] for entry in seen]:
                seen.append((label, track.color if track.particle != "opticalphoton"
                             else (0.4, 1.0, 0.4)))
        _legend(plotter, seen[:7])
    plotter.show(auto_close=False, interactive=False)

    line_width = max(1.5, min(4.0, 2.2 * height / 480.0))
    head_size = max(6.0, min(14.0, 9.0 * height / 480.0))
    event_count = len({track.event_id for track in tracks})
    t_span = float(clock_ns[-1] * 1e-9)
    medium_note = f"inside {', '.join(enclosing)}" if enclosing else ""
    images = []
    actors: list = []
    for index, t_ns in enumerate(clock_ns):
        for actor in actors:
            plotter.remove_actor(actor)
        actors = []
        primaries, secondaries, heads, head_colors = [], [], [], []
        scatters, absorptions = [], []
        for track in everything:
            prefix, head = track.prefix(float(t_ns))
            if prefix is None:
                continue
            # Per-point recorded energy; the interpolated head carries its step's start energy.
            n = prefix.shape[0]
            recorded = track.energy[:n] if head is None else np.concatenate(
                [track.energy[:n - 1], track.energy[n - 2:n - 1]])
            if track.baseline:
                rgb = np.asarray(baseline_rgb, dtype=np.float32)
            elif color_by == "energy" and recorded.size == n:
                rgb = energy_colors(recorded, reference_ev)
            elif track.particle == "opticalphoton" and recorded.size == n:
                rgb = np.asarray([visible_rgb_for_wavelength(wavelength_nm_for_energy_ev(e))
                                  for e in recorded], dtype=np.float32)
            else:
                rgb = np.asarray(track.color, dtype=np.float32)
            (primaries if track.primary else secondaries).append((prefix, rgb))
            if head is not None:
                heads.append(head)
                head_colors.append(np.asarray(rgb, dtype=np.float32).reshape(-1, 3)[-1])
            for mark_index, kind in track.marks:
                if track.times[mark_index] <= t_ns:
                    (scatters if kind == "scatter" else absorptions).append(track.points[mark_index])
        for batch, width_scale, opacity in ((secondaries, 0.55, 0.75), (primaries, 1.0, 0.95)):
            poly = _polyline_batch(batch)
            if poly is not None:
                actors.append(plotter.add_mesh(poly, scalars="rgb", rgb=True,
                                               line_width=line_width * width_scale,
                                               opacity=opacity, show_scalar_bar=False,
                                               render_lines_as_tubes=True))
        if heads:
            cloud = pv.PolyData(np.asarray(heads))
            cloud.point_data["rgb"] = np.asarray(head_colors, dtype=np.float32)
            actors.append(plotter.add_points(cloud, scalars="rgb", rgb=True, point_size=head_size,
                                             render_points_as_spheres=True, emissive=True,
                                             show_scalar_bar=False))
        for marks, color in ((scatters, "#ffffff"), (absorptions, "#ff4d4d")):
            if marks:
                actors.append(plotter.add_points(np.asarray(marks), color=color,
                                                 point_size=head_size * 0.7,
                                                 render_points_as_spheres=True, emissive=True))
        turntable.place(index / max(1, total - 1))
        lines = [
            (title or "TRECH 3D  |  Geant4 trajectories"),
            f"Geant4 clock t = {format_clock(t_ns * 1e-9, t_span)}"
            f"   ({event_count} events overlaid, each on its own event clock)",
            f"alive {len(heads)}  ·  discrete vertices {len(scatters) + len(absorptions)}"
            + (f"  ·  {medium_note}" if medium_note else ""),
        ] + list(hud_lines)
        _hud(plotter, lines, height)
        images.append(_screenshot(plotter))

    plotter.close()
    write_gif(gif, images, fps)
    if screenshot:
        import imageio.v2 as imageio

        imageio.imwrite(screenshot, images[-1])


# --------------------------------------------------------------------------- run HUD

def score_hud_lines(scores_path: str | Path, limit: int = 3) -> List[str]:
    """Engine-reported predicted-vs-measured lines from ``trech_scores.jsonl`` (never typed)."""
    path = Path(scores_path)
    if not path.exists():
        return []
    record = None
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue
    if not isinstance(record, dict):
        return []
    lines: List[str] = []
    for check in record.get("analytic_checks") or []:
        if not isinstance(check, dict):
            continue
        name = str(check.get("type") or check.get("name") or check.get("label") or "check")
        predicted = check.get("predicted", check.get("classical_predicted"))
        measured = check.get("measured", check.get("geant4_measured"))
        if isinstance(predicted, (int, float)) and isinstance(measured, (int, float)):
            gap = abs(measured - predicted) / abs(predicted) * 100.0 if predicted else float("nan")
            verdict = "within tol" if check.get("within_tolerance") else "outside tol"
            lines.append(f"{name}: formula {predicted:.4g} vs Geant4 {measured:.4g} "
                         f"(Δ {gap:.2f}%, {verdict})")
    for cycle in record.get("nuclear_cycles") or []:
        if not isinstance(cycle, dict):
            continue
        parts = []
        for leg in ("forward", "backward"):
            entry = cycle.get(leg) or {}
            if isinstance(entry.get("q_value_mev"), (int, float)):
                conserved = entry.get("baryon_conserved") and entry.get("charge_conserved")
                parts.append(f"{entry.get('name', leg)} Q={entry['q_value_mev']:.3f} MeV"
                             + (" (B,Z conserved)" if conserved else " (NOT conserved)"))
        if parts:
            lines.append("Geant4 masses: " + "; ".join(parts))
    return lines[:limit]


def edep_hud_line(scores_path: str | Path, prefix: str, label: str = "") -> str:
    """Geant4-scored energy deposit summed over volumes whose name starts with ``prefix``."""
    path = Path(scores_path)
    if not path.exists() or not prefix:
        return ""
    record = None
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue
    volumes = (record or {}).get("volume_edep_mev") or {}
    total = sum(float(v) for k, v in volumes.items() if str(k).startswith(prefix))
    events = (record or {}).get("n_events")
    return (f"{label + ': ' if label else ''}Geant4-detected edep in {prefix}* = {total:.3f} MeV"
            + (f" over {events} events" if events else ""))


def derived_index_line(scene: Optional[Scene], materials: Sequence[str], label: str = "") -> str:
    """``n`` the engine derived for named materials, read from the scene manifest."""
    if scene is None or not materials:
        return ""
    derived = scene.derived_by_name()
    parts = []
    for name in materials:
        entry = derived.get(name.lower())
        if entry is not None and entry.available:
            parts.append(f"n({name}) = {entry.mean_refractive_index:.3f}")
    if not parts:
        return ""
    return (f"{label}: " if label else "engine-derived ") + ", ".join(parts)
