"""Time-indexed playback data for the viewport (trajectories + particle frames).

This turns an already-parsed run (sampled trajectories and/or hook emits) into GPU-ready
arrays the renderer can draw at a given time cursor. It is the model behind the **timeline**:
scrubbing a cursor ``t`` selects how much of each trajectory has been traced, or which
particle frame is shown.

Honesty (studio/AGENTS.md): every position and time here comes straight from an engine output
— trajectory points/`time_ns` from ``trech_viz_trajectories.jsonl`` and particle frames from
``trech_hook_emits.jsonl`` (e.g. ``fluid_frame``). The only *rendering choices* are the
trajectory colour (wavelength→RGB for optical photons, a per-particle palette otherwise) and
the particle tint; both are look, not physics, exactly like ``scene.volume_color``.

Layering: this file is part of ``render`` and must not import ``engine``. Builders therefore
accept **duck-typed** inputs (objects exposing ``.points``/``.times_ns``/``.particle`` for
trajectories, ``.tag``/``.payload`` for emits), so the real ``engine.outputs`` types and plain
test stand-ins both work without a cross-layer import.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, List, Optional, Sequence, Tuple

import numpy as np

RGB = Tuple[float, float, float]

# Per-particle trajectory colours (a rendering choice). Optical photons are recoloured per
# segment from their energy (wavelength), so their entry here is only a fallback.
_PARTICLE_COLORS = {
    "opticalphoton": (0.95, 0.9, 0.5),
    "gamma": (0.45, 0.9, 0.55),
    "e-": (0.45, 0.7, 1.0),
    "e+": (1.0, 0.55, 0.55),
    "proton": (1.0, 0.72, 0.32),
    "neutron": (0.72, 0.72, 0.78),
    "geantino": (0.6, 0.6, 0.66),
}
_DEFAULT_PARTICLE_COLOR: RGB = (0.82, 0.84, 0.9)

# Particle-frame families we know how to place spatially, with the unit->mm scale of their
# emitted positions (fluid_frame positions are metres; the scene is millimetres).
_PARTICLE_FAMILIES: Tuple[Tuple[str, float], ...] = (
    ("fluid_frame", 1000.0),
)
_FLUID_TINT: RGB = (0.35, 0.62, 0.95)


def _particle_color(particle: str) -> RGB:
    return _PARTICLE_COLORS.get((particle or "").lower(), _DEFAULT_PARTICLE_COLOR)


def wavelength_rgb(energy_ev: float) -> RGB:
    """Approximate visible-wavelength → RGB (compact Bruton/CIE), matching tools/viz colours."""
    if energy_ev <= 0.0:
        return (1.0, 1.0, 1.0)
    wl = 1239.841984 / energy_ev
    if wl < 380.0:
        return (0.4, 0.0, 0.6)
    if wl > 780.0:
        return (0.35, 0.0, 0.0)
    if wl < 440.0:
        r, g, b = -(wl - 440.0) / 60.0, 0.0, 1.0
    elif wl < 490.0:
        r, g, b = 0.0, (wl - 440.0) / 50.0, 1.0
    elif wl < 510.0:
        r, g, b = 0.0, 1.0, -(wl - 510.0) / 20.0
    elif wl < 580.0:
        r, g, b = (wl - 510.0) / 70.0, 1.0, 0.0
    elif wl < 645.0:
        r, g, b = 1.0, -(wl - 645.0) / 65.0, 0.0
    else:
        r, g, b = 1.0, 0.0, 0.0
    clamp = lambda x: max(0.0, min(1.0, x))
    return (clamp(r), clamp(g), clamp(b))


@dataclass
class ParticleFrame:
    """One particle-cloud snapshot (e.g. a ``fluid_frame``) at a given time."""

    time: float                       # native units (seconds for fluid_frame)
    positions: np.ndarray             # (M, 3) float32, millimetres
    tag: str = ""
    phase: str = ""                   # scenario phase label ("pour"/"settle"/"shake"…)
    color: RGB = _FLUID_TINT


@dataclass
class Playback:
    """Time-indexed renderable derived from a run. ``kind`` selects how a cursor is read."""

    kind: str = "empty"               # "trajectory" | "particles" | "empty"
    unit: str = "ns"                  # display unit of the cursor ("ns" | "s" | "frame")
    t_min: float = 0.0
    t_max: float = 0.0

    # Trajectory mode: flat line-list, 2 verts/segment, each [x, y, z, r, g, b] (mm + colour),
    # sorted by segment end-time so a cursor maps to a prefix count via binary search.
    segment_vertices: Optional[np.ndarray] = None   # (2*S, 6) float32
    segment_t_end: Optional[np.ndarray] = None       # (S,)   float64, ascending

    # Particle mode.
    frames: List[ParticleFrame] = field(default_factory=list)
    frame_times: Optional[np.ndarray] = None         # (F,) float64, ascending

    label: str = ""
    source_tag: str = ""

    # --- queries ------------------------------------------------------------------------

    @property
    def is_empty(self) -> bool:
        return self.kind == "empty" or (self.segment_vertices is None and not self.frames)

    @property
    def segment_count(self) -> int:
        return 0 if self.segment_t_end is None else int(self.segment_t_end.shape[0])

    @property
    def frame_count(self) -> int:
        return len(self.frames)

    def count_at(self, t: float) -> int:
        """Trajectory mode: number of segments whose end-time is <= ``t`` (a growing beam)."""
        if self.segment_t_end is None:
            return 0
        return int(np.searchsorted(self.segment_t_end, t, side="right"))

    def frame_index_at(self, t: float) -> int:
        """Particle mode: index of the last frame at or before ``t`` (hold-last semantics)."""
        if self.frame_times is None or self.frame_times.shape[0] == 0:
            return 0
        idx = int(np.searchsorted(self.frame_times, t, side="right")) - 1
        return max(0, min(idx, self.frame_times.shape[0] - 1))


EMPTY = Playback(kind="empty")


def build_trajectory_playback(trajectories: Sequence[Any], max_segments: int = 400_000) -> Playback:
    """Flatten sampled trajectories into a time-sorted, coloured line-list."""
    seg_verts: List[Tuple[float, ...]] = []
    t_ends: List[float] = []
    for tr in trajectories:
        pts = list(getattr(tr, "points", None) or [])
        if len(pts) < 2:
            continue
        times = list(getattr(tr, "times_ns", None) or [])
        energies = list(getattr(tr, "energies_ev", None) or [])
        particle = getattr(tr, "particle", "") or ""
        optical = "optical" in particle.lower()
        base = _particle_color(particle)
        for i in range(len(pts) - 1):
            p0, p1 = pts[i], pts[i + 1]
            if optical and i + 1 < len(energies):
                color = wavelength_rgb(0.5 * (energies[i] + energies[i + 1]))
            else:
                color = base
            t_end = times[i + 1] if i + 1 < len(times) else float(i + 1)
            seg_verts.append((p0[0], p0[1], p0[2], color[0], color[1], color[2]))
            seg_verts.append((p1[0], p1[1], p1[2], color[0], color[1], color[2]))
            t_ends.append(t_end)
        if len(t_ends) >= max_segments:
            break
    if not t_ends:
        return Playback(kind="empty")

    t_arr = np.asarray(t_ends, dtype=np.float64)
    order = np.argsort(t_arr, kind="stable")
    verts = np.asarray(seg_verts, dtype=np.float32).reshape(-1, 2, 6)[order].reshape(-1, 6)
    t_sorted = t_arr[order]
    return Playback(
        kind="trajectory",
        unit="ns",
        t_min=0.0,
        t_max=float(t_sorted[-1]) if t_sorted[-1] > 0.0 else float(len(t_sorted)),
        segment_vertices=np.ascontiguousarray(verts),
        segment_t_end=np.ascontiguousarray(t_sorted),
        label=f"{len(t_ends)} trajectory segments",
        source_tag="trajectories",
    )


def build_particle_playback(emits: Sequence[Any], tag: str, unit_scale_mm: float) -> Playback:
    """Collect ``tag`` emits (each carrying an ``xyz`` position array) into ordered frames."""
    frames: List[ParticleFrame] = []
    for e in emits:
        if getattr(e, "tag", None) != tag:
            continue
        payload = getattr(e, "payload", None)
        if not isinstance(payload, dict):
            continue
        xyz = payload.get("xyz") or payload.get("positions") or payload.get("particles")
        if not xyz:
            continue
        pos = np.asarray(xyz, dtype=np.float32)
        if pos.ndim != 2 or pos.shape[1] < 3:
            continue
        pos = np.ascontiguousarray(pos[:, :3] * float(unit_scale_mm), dtype=np.float32)
        t = payload.get("time_s")
        if t is None:
            t = payload.get("time")
        if t is None:
            t = payload.get("tick")
        if t is None:
            t = float(len(frames))
        frames.append(
            ParticleFrame(time=float(t), positions=pos, tag=tag, phase=str(payload.get("phase") or ""))
        )
    if not frames:
        return Playback(kind="empty")

    frames.sort(key=lambda f: f.time)
    times = np.asarray([f.time for f in frames], dtype=np.float64)
    unit = "s" if any(getattr(e, "tag", None) == tag for e in emits) else "frame"
    return Playback(
        kind="particles",
        unit=unit,
        t_min=float(times[0]),
        t_max=float(times[-1]),
        frames=frames,
        frame_times=np.ascontiguousarray(times),
        label=f"{len(frames)} {tag} frames",
        source_tag=tag,
    )


def build_playback(trajectories: Optional[Sequence[Any]] = None,
                   emits: Optional[Sequence[Any]] = None) -> Playback:
    """Pick the richest available preview for a run: trajectories first, then particle frames.

    Trajectories (optics/particle runs) win when present because they carry per-step time;
    otherwise a known particle family (``fluid_frame`` — the shaken glass of water) is placed
    spatially. Returns :data:`EMPTY` when a run has neither.
    """
    pb = build_trajectory_playback(list(trajectories or []))
    if not pb.is_empty:
        return pb
    for tag, scale in _PARTICLE_FAMILIES:
        pb = build_particle_playback(list(emits or []), tag=tag, unit_scale_mm=scale)
        if not pb.is_empty:
            return pb
    return EMPTY
