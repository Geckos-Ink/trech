"""Observer-frame playback for the classic PyVista TRECH viewer.

The classic viewer reads the same ``material_frame`` sideband contract as Studio. Positions,
per-particle RGBA, phase, and physical/playback clocks remain scenario output; this module only
validates/loads them for held-frame replay.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np


@dataclass
class MaterialSurface:
    mode: str
    kernel: str
    grid_spacing_mm: float
    sigma_mm: float
    iso_level: float
    clip_axis: str
    clip_radius_mm: Optional[float]
    # Radial clip centre in the viewer frame (a moving container, e.g. a shaken glass).
    clip_min_mm: Optional[float]
    clip_max_mm: Optional[float]
    fresnel_r0: float
    gloss: float
    opacity: float
    positions_unmodified: bool
    policy: str
    neck_mode: str
    neck_min_distance_mm: float
    neck_max_distance_mm: float
    neck_samples: int
    neck_weight: float
    neck_preserves_topology: bool
    clip_center_mm: Tuple[float, float, float] = (0.0, 0.0, 0.0)


def _material_surface(raw) -> Optional[MaterialSurface]:
    if not isinstance(raw, dict) or str(raw.get("mode") or "").lower() != "metaball":
        return None
    clip = raw.get("clip_cylinder")
    clip = clip if isinstance(clip, dict) else {}
    # material_frame is z-up; classic playback relabels it to y-up.
    source_axis = str(clip.get("axis") or "z").lower()
    axis = {"x": "x", "y": "z", "z": "y"}.get(source_axis, "y")
    try:
        optional_float = lambda value: None if value is None else float(value)
        neck = raw.get("fluid_necking")
        neck = neck if isinstance(neck, dict) else {}
        return MaterialSurface(
            mode="metaball", kernel=str(raw.get("kernel") or "gaussian").lower(),
            grid_spacing_mm=max(float(raw.get("grid_spacing_mm", 1.25)), 0.05),
            sigma_mm=max(float(raw.get("sigma_mm", 2.0)), 0.05),
            iso_level=max(float(raw.get("iso_level", 0.52)), 1e-6),
            clip_axis=axis, clip_radius_mm=optional_float(clip.get("radius_mm")),
            clip_min_mm=optional_float(clip.get("min_mm")),
            clip_max_mm=optional_float(clip.get("max_mm")),
            fresnel_r0=float(np.clip(raw.get("fresnel_r0", 0.04), 0.0, 1.0)),
            gloss=float(np.clip(raw.get("gloss", 0.7), 0.0, 1.0)),
            opacity=float(np.clip(raw.get("opacity", 0.9), 0.0, 1.0)),
            positions_unmodified=bool(raw.get("positions_unmodified", True)),
            policy=str(raw.get("policy") or "representation only"),
            neck_mode=str(neck.get("mode") or "none").lower(),
            neck_min_distance_mm=max(float(neck.get("min_distance_mm", 0.0)), 0.0),
            neck_max_distance_mm=max(float(neck.get("max_distance_mm", 0.0)), 0.0),
            neck_samples=max(0, min(int(neck.get("samples_per_pair", 0)), 4)),
            neck_weight=float(np.clip(neck.get("weight", 0.0), 0.0, 1.0)),
            neck_preserves_topology=bool(neck.get("preserves_component_topology", True)),
            clip_center_mm=tuple(float(v) for v in to_view(
                np.asarray(clip.get("center_mm") or [0.0, 0.0, 0.0], dtype=np.float32)[:3],
                "z")[0]),
        )
    except (TypeError, ValueError):
        return None


@dataclass
class ApparatusPart:
    """Scenario-emitted apparatus state (a moving glass, a piston, a periodic box).

    Unlike ``trech_viz_scene.json`` volumes these may move frame to frame, because the scenario's
    own solver moves them. Coordinates share the frame's ``length_unit`` and axis convention.
    """

    shape: str
    center: np.ndarray
    size: np.ndarray
    radius: float
    height: float
    axis: str
    rgba: np.ndarray
    style: str
    label: str
    # shape == "mesh": a scenario-owned triangulated surface (e.g. a deforming membrane).
    vertices: Optional[np.ndarray] = None
    faces: Optional[np.ndarray] = None
    # mesh: optional per-vertex RGBA (e.g. a wall coloured by its own solver displacement).
    vertex_rgba: Optional[np.ndarray] = None


@dataclass
class PhaseGrid:
    """A scenario's cell grid with one integer class per cell (batch / melt / glass …).

    Drawn as one smooth surface per class (``solid``/``liquid``) or as grains, so a lattice
    solver's material reads as a continuum instead of a stack of balls. The class of every cell
    is the solver's; smoothing only shapes the drawn boundary between cell centres.
    """

    origin: np.ndarray
    spacing: np.ndarray           # (3,) cell pitch per frame axis
    shape: Tuple[int, int, int]
    values: np.ndarray            # (nx, ny, nz) int class ids
    classes: List[Dict]           # {id, label, rgba, style}
    # True: the grid IS the drawn material, so the per-cell point glyphs are not drawn.
    replaces_points: bool = False


@dataclass
class MaterialFrame:
    playback_time_s: float
    physical_time_s: float
    time_scale: float
    phase: str
    positions_mm: np.ndarray
    colors_rgba: np.ndarray
    surface: Optional[MaterialSurface] = None
    # Optional per-point sphere radii (same unit as positions): atoms/parcels drawn as real
    # 3D spheres of their declared size rather than screen-space dots.
    radii: Optional[np.ndarray] = None
    # Optional (K, 2) point-index pairs drawn as bonds/links between existing points.
    bonds: Optional[np.ndarray] = None
    # Optional per-point 3D vectors (e.g. magnetization, drift), drawn as arrows.
    vectors: Optional[np.ndarray] = None
    apparatus: List[ApparatusPart] = field(default_factory=list)
    legend: List[Tuple[str, Tuple[float, float, float]]] = field(default_factory=list)
    hud_lines: List[str] = field(default_factory=list)
    # "mm" (default) shares the Geant4 scene's unit; any other unit (e.g. "angstrom") marks a
    # scale-independent frame, so the mm apparatus scene is not drawn around it.
    length_unit: str = "mm"
    show_geant4_scene: bool = True
    up_axis: str = "z"
    # Scenario-declared clock text (e.g. "tick 1200 / 6000") for solvers whose clock is not SI
    # seconds; shown instead of the formatted physical time.
    clock_text: str = ""
    # Scalar observables of this frame (plotted by the side chart panel over time).
    samples: Dict[str, float] = field(default_factory=dict)
    # Chart declarations (any frame; the latest wins) and per-frame curve snapshots.
    charts: List[Dict] = field(default_factory=list)
    curves: List[Dict] = field(default_factory=list)
    # 3D text labels: (position in frame units, text, rgb).
    labels: List[Tuple[np.ndarray, str, Tuple[float, float, float]]] = field(default_factory=list)
    grid: Optional[PhaseGrid] = None

    def points_view(self) -> np.ndarray:
        """Positions in the viewer's y-up frame (z-up emits are relabelled, y-up kept)."""
        return to_view(self.positions_mm, self.up_axis)


def to_view(points: np.ndarray, up_axis: str = "z") -> np.ndarray:
    points = np.asarray(points, dtype=np.float32).reshape(-1, 3)
    if up_axis == "y":
        return np.ascontiguousarray(points)
    return np.ascontiguousarray(points[:, [0, 2, 1]])


def _float_array(raw, width: int) -> Optional[np.ndarray]:
    if raw is None:
        return None
    try:
        values = np.asarray(raw, dtype=np.float32)
    except (TypeError, ValueError):
        return None
    if width == 1:
        return values.reshape(-1) if values.ndim <= 1 else None
    if values.ndim != 2 or values.shape[1] < width:
        return None
    return np.ascontiguousarray(values[:, :width])


def _rgba(raw, default=(0.8, 0.85, 0.95, 0.35)) -> np.ndarray:
    values = list(raw) if isinstance(raw, (list, tuple)) else list(default)
    values = [float(v) for v in values[:4]]
    if len(values) == 3:
        values.append(float(default[3]))
    if len(values) != 4:
        values = list(default)
    return np.clip(np.asarray(values, dtype=np.float32), 0.0, 1.0)


def _apparatus(raw) -> List[ApparatusPart]:
    parts: List[ApparatusPart] = []
    for item in raw if isinstance(raw, list) else []:
        if not isinstance(item, dict):
            continue
        shape = str(item.get("shape") or "").lower()
        if shape not in ("box", "cylinder", "sphere", "segment", "mesh"):
            continue
        try:
            center = np.asarray(item.get("center") or [0, 0, 0], dtype=np.float32)[:3]
            size = np.asarray(item.get("size") or [0, 0, 0], dtype=np.float32)[:3]
            if shape == "segment":
                # A segment carries its two end points in ``from``/``to``.
                start = np.asarray(item.get("from") or [0, 0, 0], dtype=np.float32)[:3]
                end = np.asarray(item.get("to") or [0, 0, 0], dtype=np.float32)[:3]
                center, size = start, end
            vertices = faces = None
            if shape == "mesh":
                vertices = _float_array(item.get("vertices"), 3)
                try:
                    faces = np.asarray(item.get("faces") or [], dtype=np.int64)
                except (TypeError, ValueError):
                    faces = None
                if (vertices is None or faces is None or faces.ndim != 2 or faces.shape[1] != 3
                        or faces.size == 0 or faces.min() < 0
                        or faces.max() >= vertices.shape[0]):
                    continue
            vertex_rgba = None
            if shape == "mesh" and item.get("vertex_rgba") is not None:
                vertex_rgba = _float_array(item.get("vertex_rgba"), 4)
                if vertex_rgba is not None and vertex_rgba.shape[0] != vertices.shape[0]:
                    vertex_rgba = None
            parts.append(ApparatusPart(
                vertices=vertices, faces=faces, vertex_rgba=vertex_rgba,
                shape=shape, center=center, size=size,
                radius=float(item.get("radius", 0.0) or 0.0),
                height=float(item.get("height", 0.0) or 0.0),
                axis=str(item.get("axis") or "z").lower(),
                rgba=_rgba(item.get("color_rgba")),
                style=str(item.get("style") or "surface").lower(),
                label=str(item.get("label") or ""),
            ))
        except (TypeError, ValueError):
            continue
    return parts


def _samples(raw) -> Dict[str, float]:
    out: Dict[str, float] = {}
    if isinstance(raw, dict):
        for key, value in raw.items():
            if isinstance(value, (int, float)) and np.isfinite(value):
                out[str(key)] = float(value)
    return out


def _labels(raw) -> List[Tuple[np.ndarray, str, Tuple[float, float, float]]]:
    out = []
    for item in raw if isinstance(raw, list) else []:
        if not isinstance(item, dict) or not item.get("text"):
            continue
        try:
            position = np.asarray(item.get("position") or [0, 0, 0], dtype=np.float32)[:3]
        except (TypeError, ValueError):
            continue
        rgb = _rgba(item.get("color_rgba"), (1, 1, 1, 1))[:3]
        out.append((position, str(item["text"]), tuple(float(c) for c in rgb)))
    return out[:48]


def _phase_grid(raw) -> Optional[PhaseGrid]:
    if not isinstance(raw, dict):
        return None
    try:
        shape = tuple(int(v) for v in raw.get("shape") or [])
        values = np.asarray(raw.get("values") or [], dtype=np.int64)
        if len(shape) != 3 or values.size != shape[0] * shape[1] * shape[2]:
            return None
        classes = []
        for entry in raw.get("classes") or []:
            if isinstance(entry, dict) and "id" in entry:
                classes.append({"id": int(entry["id"]), "label": str(entry.get("label") or ""),
                                "rgba": _rgba(entry.get("color_rgba"), (0.8, 0.8, 0.8, 0.9)),
                                "style": str(entry.get("style") or "solid").lower()})
        spacing = raw.get("spacing") or 1.0
        spacing = np.broadcast_to(np.asarray(spacing, dtype=np.float32).reshape(-1)[:3]
                                  if isinstance(spacing, list) else np.float32(spacing), (3,))
        return PhaseGrid(origin=np.asarray(raw.get("origin") or [0, 0, 0], dtype=np.float32)[:3],
                         spacing=np.array(spacing, dtype=np.float32), shape=shape,  # type: ignore
                         values=values.reshape(shape, order="F"), classes=classes,
                         replaces_points=bool(raw.get("replaces_points", False)))
    except (TypeError, ValueError):
        return None


def material_frame_streams(path: str | Path) -> List[str]:
    """Distinct ``stream`` names of a run's material frames, in first-seen order ("" = unnamed)."""
    streams: List[str] = []
    with open(path, "r", encoding="utf-8") as handle:
        for line in handle:
            if '"material_frame"' not in line:
                continue
            raw = json.loads(line)
            payload = raw.get("payload") if raw.get("tag") == "material_frame" else None
            if isinstance(payload, dict):
                name = str(payload.get("stream") or "")
                if name not in streams:
                    streams.append(name)
    return streams


def load_material_frames(path: str | Path, stream: Optional[str] = None) -> List[MaterialFrame]:
    """Load ordered ``material_frame`` emits from ``trech_hook_emits.jsonl``.

    Empty frames are retained so a scenario can honestly begin with an empty apparatus. Invalid
    or mismatched position/colour payloads are ignored instead of being guessed into shape.
    A run may emit several independent timelines distinguished by ``payload.stream``; one is
    replayed at a time (``stream``, else the first stream the run emitted).
    """
    if stream is None:
        streams = material_frame_streams(path)
        stream = streams[0] if streams else ""
    frames: List[MaterialFrame] = []
    with open(path, "r", encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            raw = json.loads(line)
            if raw.get("tag") != "material_frame":
                continue
            payload = raw.get("payload")
            if not isinstance(payload, dict) or str(payload.get("stream") or "") != stream:
                continue
            pos = np.asarray(
                payload.get("positions_mm") or payload.get("positions") or [], dtype=np.float32
            )
            col = np.asarray(payload.get("colors_rgba") or [], dtype=np.float32)
            if pos.size == 0 and col.size == 0:
                pos = np.empty((0, 3), dtype=np.float32)
                col = np.empty((0, 4), dtype=np.float32)
            if pos.ndim != 2 or pos.shape[1] < 3 or col.ndim != 2 or col.shape[0] != pos.shape[0]:
                continue
            if col.shape[1] == 3:
                col = np.concatenate(
                    [col, np.full((col.shape[0], 1), 0.75, dtype=np.float32)], axis=1
                )
            if col.shape[1] < 4:
                continue
            physical = float(payload.get("physical_time_s", payload.get("time_s", len(frames))))
            playback = float(payload.get("playback_time_s", payload.get("time_s", physical)))
            count = pos.shape[0]
            radii = _float_array(payload.get("radii"), 1)
            if radii is not None and radii.shape[0] != count:
                radii = None
            vectors = _float_array(payload.get("vectors"), 3)
            if vectors is not None and vectors.shape[0] != count:
                vectors = None
            bonds = None
            raw_bonds = payload.get("bonds")
            if raw_bonds:
                try:
                    pairs = np.asarray(raw_bonds, dtype=np.int64)
                    if pairs.ndim == 2 and pairs.shape[1] == 2:
                        valid = (pairs >= 0).all(axis=1) & (pairs < count).all(axis=1)
                        bonds = np.ascontiguousarray(pairs[valid])
                except (TypeError, ValueError):
                    bonds = None
            legend = []
            for entry in payload.get("legend") or []:
                if isinstance(entry, dict) and entry.get("label"):
                    rgb = _rgba(entry.get("color_rgba"), (1, 1, 1, 1))[:3]
                    legend.append((str(entry["label"]), tuple(float(c) for c in rgb)))
            frames.append(MaterialFrame(
                playback_time_s=playback,
                physical_time_s=physical,
                time_scale=float(payload.get("time_scale", 1.0) or 1.0),
                phase=str(payload.get("phase") or ""),
                positions_mm=np.ascontiguousarray(pos[:, :3], dtype=np.float32),
                colors_rgba=np.ascontiguousarray(np.clip(col[:, :4], 0.0, 1.0), dtype=np.float32),
                surface=_material_surface(payload.get("render_surface")),
                radii=radii,
                bonds=bonds,
                vectors=vectors,
                apparatus=_apparatus(payload.get("apparatus")),
                legend=legend,
                hud_lines=[str(line) for line in payload.get("hud_lines") or []][:6],
                length_unit=str(payload.get("length_unit") or "mm").lower(),
                show_geant4_scene=payload.get("show_geant4_scene") is not False,
                up_axis="y" if str(payload.get("up_axis") or "z").lower() == "y" else "z",
                clock_text=str(payload.get("clock_text") or ""),
                samples=_samples(payload.get("samples")),
                charts=[c for c in payload.get("charts") or [] if isinstance(c, dict)],
                curves=[c for c in payload.get("curves") or [] if isinstance(c, dict)],
                labels=_labels(payload.get("labels")),
                grid=_phase_grid(payload.get("grid")),
            ))
    frames.sort(key=lambda frame: frame.playback_time_s)
    return frames


def select_physical_window(
    frames: List[MaterialFrame], start_s: float | None = None, duration_s: float | None = None
) -> List[MaterialFrame]:
    """Select a held-frame physical-time excerpt without changing any emitted clock value."""
    if start_s is None and duration_s is None:
        return list(frames)
    if duration_s is not None and duration_s <= 0.0:
        raise ValueError("physical duration must be positive")
    if not frames:
        return []
    start = frames[0].physical_time_s if start_s is None else float(start_s)
    end = frames[-1].physical_time_s if duration_s is None else start + float(duration_s)
    selected = [frame for frame in frames if start <= frame.physical_time_s <= end]
    if not selected:
        raise ValueError("physical-time excerpt does not overlap material frames")
    return selected


def sample_animation_frames(
    frames: List[MaterialFrame], output_count: int
) -> List[MaterialFrame]:
    """Sample held frames, aligning N outputs to N post-tick states when N+1 exist."""
    output_count = max(1, int(output_count))
    if not frames:
        return []
    if len(frames) == output_count + 1:
        return list(frames[1:])
    times = np.asarray([frame.playback_time_s for frame in frames], dtype=np.float64)
    targets = np.linspace(times[0], times[-1], output_count, dtype=np.float64)
    indices = np.searchsorted(times, targets, side="right") - 1
    indices = np.clip(indices, 0, len(frames) - 1)
    return [frames[int(index)] for index in indices]
