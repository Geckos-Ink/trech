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
from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np

RGB = Tuple[float, float, float]
RGBA = Tuple[float, float, float, float]

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
# emitted positions and the emit's *up axis*. ``fluid_frame`` positions are metres with **z up**
# (the glass fill/wall height runs along z in the fluid solver), whereas Studio's viewport and
# scene are **y up** — so those frames are remapped z-up→y-up (see ``_UP_AXIS_TO_YUP``) to stand
# the water column upright instead of laying it on its side. Fields: (tag, mm_scale, up_axis).
_PARTICLE_FAMILIES: Tuple[Tuple[str, float, str], ...] = (
    ("fluid_frame", 1000.0, "z"),
)
_FLUID_TINT: RGBA = (0.35, 0.62, 0.95, 0.85)


def _to_yup(pos: np.ndarray, up_axis: str) -> np.ndarray:
    """Remap an (M, 3) point cloud whose vertical axis is ``up_axis`` into the viewport's y-up
    frame (a pure axis relabel — a rendering choice, it moves no particle relative to another)."""
    up = (up_axis or "y").lower()
    if up == "z":                       # (x, y, z_up) -> (x, z_up, y)
        return np.ascontiguousarray(pos[:, [0, 2, 1]], dtype=np.float32)
    if up == "x":                       # (x_up, y, z) -> (y, x_up, z)
        return np.ascontiguousarray(pos[:, [1, 0, 2]], dtype=np.float32)
    return np.ascontiguousarray(pos, dtype=np.float32)  # already y-up


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
class ParticleSurface:
    """Scenario-emitted fused-surface representation for an unchanged particle frame."""

    mode: str = "metaball"
    kernel: str = "gaussian"
    grid_spacing_mm: float = 1.25
    sigma_mm: float = 2.0
    iso_level: float = 0.52
    clip_axis: str = "y"
    clip_radius_mm: Optional[float] = None
    clip_min_mm: Optional[float] = None
    clip_max_mm: Optional[float] = None
    fresnel_r0: float = 0.04
    gloss: float = 0.7
    opacity: float = 0.9
    positions_unmodified: bool = True
    policy: str = "representation only"


def _surface_to_yup(raw: Any, up_axis: str) -> Optional[ParticleSurface]:
    """Validate a compact surface hint and remap its clip axis beside the positions."""
    if not isinstance(raw, dict) or str(raw.get("mode") or "").lower() != "metaball":
        return None
    clip = raw.get("clip_cylinder")
    clip = clip if isinstance(clip, dict) else {}
    axis = str(clip.get("axis") or up_axis or "y").lower()
    source_up = (up_axis or "y").lower()
    if source_up == "z":
        axis = {"x": "x", "y": "z", "z": "y"}.get(axis, "y")
    elif source_up == "x":
        axis = {"x": "y", "y": "x", "z": "z"}.get(axis, "y")
    else:
        axis = axis if axis in ("x", "y", "z") else "y"
    try:
        grid = float(raw.get("grid_spacing_mm", 1.25))
        sigma = float(raw.get("sigma_mm", 2.0))
        iso = float(raw.get("iso_level", 0.52))
        radius_raw = clip.get("radius_mm")
        minimum_raw = clip.get("min_mm")
        maximum_raw = clip.get("max_mm")
        return ParticleSurface(
            mode="metaball", kernel=str(raw.get("kernel") or "gaussian").lower(),
            grid_spacing_mm=max(grid, 0.05), sigma_mm=max(sigma, 0.05),
            iso_level=max(iso, 1e-6), clip_axis=axis,
            clip_radius_mm=float(radius_raw) if radius_raw is not None else None,
            clip_min_mm=float(minimum_raw) if minimum_raw is not None else None,
            clip_max_mm=float(maximum_raw) if maximum_raw is not None else None,
            fresnel_r0=float(np.clip(raw.get("fresnel_r0", 0.04), 0.0, 1.0)),
            gloss=float(np.clip(raw.get("gloss", 0.7), 0.0, 1.0)),
            opacity=float(np.clip(raw.get("opacity", 0.9), 0.0, 1.0)),
            positions_unmodified=bool(raw.get("positions_unmodified", True)),
            policy=str(raw.get("policy") or "representation only"),
        )
    except (TypeError, ValueError):
        return None


@dataclass
class ParticleFrame:
    """One particle-cloud snapshot (e.g. a ``fluid_frame``) at a given time."""

    time: float                       # native units (seconds for fluid_frame)
    positions: np.ndarray             # (M, 3) float32, millimetres
    tag: str = ""
    phase: str = ""                   # scenario phase label ("pour"/"settle"/"shake"…)
    color: RGBA = _FLUID_TINT
    colors: Optional[np.ndarray] = None  # (M, 4) float32; engine/scenario-emitted per particle
    physical_time_s: Optional[float] = None  # retained when an emitted playback clock is accelerated
    time_scale: float = 1.0                # physical seconds / playback second, scenario-emitted
    surface: Optional[ParticleSurface] = None  # scenario-emitted representation; never feeds physics


@dataclass
class Playback:
    """Time-indexed renderable derived from a run. ``kind`` selects how a cursor is read."""

    kind: str = "empty"               # "trajectory" | "particles" | "empty"
    unit: str = "ns"                  # display unit of the cursor ("ns" | "s" | "frame")
    t_min: float = 0.0
    t_max: float = 0.0

    # Trajectory mode: flat segment instances, 2 rows/segment, each
    # [x,y,z,r,g,b,width_scale,opacity]. Medium + measured beam strength select
    # only the last two *rendering-choice* fields; positions/times/colour remain engine output.
    segment_vertices: Optional[np.ndarray] = None   # (2*S, 8) float32
    segment_t_end: Optional[np.ndarray] = None       # (S,)   float64, ascending
    medium_counts: Dict[str, int] = field(default_factory=dict)
    interaction_counts: Dict[str, int] = field(default_factory=dict)
    medium_interaction_counts: Dict[str, int] = field(default_factory=dict)
    material_label_coverage: float = 0.0
    interaction_label_coverage: float = 0.0
    source_track_count: int = 0
    optical_track_count: int = 0
    display_strength: float = 0.0
    ribbon_width_scale: float = 0.0
    ribbon_opacity: float = 0.0
    mean_step_length_mm: float = 0.0
    segment_budget: int = 0
    segment_budget_reached: bool = False

    # Particle mode.
    frames: List[ParticleFrame] = field(default_factory=list)
    frame_times: Optional[np.ndarray] = None         # (F,) float64, ascending

    label: str = ""
    source_tag: str = ""
    physical_t_min: Optional[float] = None
    physical_t_max: Optional[float] = None
    time_accelerated: bool = False

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

    def particle_bounds(self) -> Optional[Tuple[np.ndarray, np.ndarray]]:
        """(lo, hi) mm over a few sampled particle frames, for camera framing (particle mode).

        Samples the first / middle / last frame so a growing or sloshing cloud is framed on its
        full motion extent, not one instant. ``None`` when this playback has no particle frames.
        """
        if not self.frames:
            return None
        n = len(self.frames)
        idxs = sorted({0, n // 2, n - 1})
        sampled = [self.frames[i].positions for i in idxs if self.frames[i].positions.shape[0] > 0]
        if not sampled:
            return None
        pts = np.concatenate(sampled, axis=0)
        return pts.min(axis=0), pts.max(axis=0)


EMPTY = Playback(kind="empty")


def build_trajectory_playback(trajectories: Sequence[Any], max_segments: int = 400_000) -> Playback:
    """Flatten sampled trajectories into time-sorted, medium-aware ribbon instances.

    Geant4 owns each segment's medium and the process ending it. Studio uses that metadata to
    make air paths visibly finer/more transparent and to report real scatter separately from
    boundary refraction. Ribbon width/opacity also follow sampled optical-track count: a weak
    beam is tight and transparent; many overlapping photons build a broader/brighter beam.
    """
    source_tracks = len(trajectories)
    optical_tracks = sum(
        1 for tr in trajectories if "optical" in (getattr(tr, "particle", "") or "").lower()
    )
    strength_tracks = optical_tracks or source_tracks
    # 192 is the shipped focused-optics budget. sqrt gives a gentle intensity response while
    # preserving a visible single-photon trace. These are labelled rendering choices.
    display_strength = float(np.clip(np.sqrt(strength_tracks / 192.0), 0.08, 1.0))
    base_width_scale = 0.14 + 0.86 * display_strength
    base_opacity = 0.055 + 0.34 * display_strength

    seg_verts: List[Tuple[float, ...]] = []
    t_ends: List[float] = []
    medium_counts: Dict[str, int] = {}
    interaction_counts: Dict[str, int] = {}
    medium_interactions: Dict[str, int] = {}
    labelled_materials = 0
    labelled_interactions = 0
    step_lengths: List[float] = []
    segment_budget_reached = False
    for tr in trajectories:
        pts = list(getattr(tr, "points", None) or [])
        if len(pts) < 2:
            continue
        times = list(getattr(tr, "times_ns", None) or [])
        energies = list(getattr(tr, "energies_ev", None) or [])
        particle = getattr(tr, "particle", "") or ""
        materials = list(getattr(tr, "materials", None) or [])
        interactions = list(getattr(tr, "interactions", None) or [])
        optical = "optical" in particle.lower()
        base = _particle_color(particle)
        for i in range(len(pts) - 1):
            if len(t_ends) >= max_segments:
                segment_budget_reached = True
                break
            p0, p1 = pts[i], pts[i + 1]
            if optical and i + 1 < len(energies):
                color = wavelength_rgb(0.5 * (energies[i] + energies[i + 1]))
            else:
                color = base
            material = materials[i] if i < len(materials) else ""
            # The process/interaction stored at p1 ended this incoming segment.
            interaction = interactions[i + 1] if i + 1 < len(interactions) else ""
            medium_label = material or "(unlabelled medium)"
            interaction_label = interaction or "unknown"
            medium_counts[medium_label] = medium_counts.get(medium_label, 0) + 1
            interaction_counts[interaction_label] = interaction_counts.get(interaction_label, 0) + 1
            pair = f"{medium_label}:{interaction_label}"
            medium_interactions[pair] = medium_interactions.get(pair, 0) + 1
            labelled_materials += int(bool(material))
            labelled_interactions += int(bool(interaction))

            is_air = "air" in material.lower()
            width_scale = base_width_scale * (0.58 if is_air else 1.0)
            opacity = base_opacity * (0.72 if is_air else 1.0)
            if interaction == "scatter":
                # A modest halo on the outgoing vertex-adjacent segment, backed by the recorded
                # Geant4 process. This does not invent scattering from a visual bend.
                width_scale *= 1.18
                opacity *= 1.12
            opacity = min(opacity, 0.72)
            t_end = times[i + 1] if i + 1 < len(times) else float(i + 1)
            seg_verts.append((p0[0], p0[1], p0[2], color[0], color[1], color[2],
                              width_scale, opacity))
            seg_verts.append((p1[0], p1[1], p1[2], color[0], color[1], color[2],
                              width_scale, opacity))
            t_ends.append(t_end)
            step_lengths.append(float(np.linalg.norm(np.asarray(p1) - np.asarray(p0))))
        if segment_budget_reached:
            break
    if not t_ends:
        return Playback(kind="empty")

    t_arr = np.asarray(t_ends, dtype=np.float64)
    order = np.argsort(t_arr, kind="stable")
    verts = np.asarray(seg_verts, dtype=np.float32).reshape(-1, 2, 8)[order].reshape(-1, 8)
    t_sorted = t_arr[order]
    media_label = ", ".join(f"{k} {v}" for k, v in sorted(medium_counts.items()))
    return Playback(
        kind="trajectory",
        unit="ns",
        t_min=0.0,
        t_max=float(t_sorted[-1]) if t_sorted[-1] > 0.0 else float(len(t_sorted)),
        segment_vertices=np.ascontiguousarray(verts),
        segment_t_end=np.ascontiguousarray(t_sorted),
        medium_counts=medium_counts,
        interaction_counts=interaction_counts,
        medium_interaction_counts=medium_interactions,
        material_label_coverage=labelled_materials / len(t_ends),
        interaction_label_coverage=labelled_interactions / len(t_ends),
        source_track_count=source_tracks,
        optical_track_count=optical_tracks,
        display_strength=display_strength,
        ribbon_width_scale=base_width_scale,
        ribbon_opacity=base_opacity,
        mean_step_length_mm=float(np.mean(step_lengths)) if step_lengths else 0.0,
        segment_budget=max_segments,
        segment_budget_reached=segment_budget_reached,
        label=(f"{len(t_ends)} trajectory segments · strength {display_strength:.0%} · "
               f"media {media_label}"),
        source_tag="trajectories",
    )


def build_particle_playback(emits: Sequence[Any], tag: str, unit_scale_mm: float,
                            up_axis: str = "y") -> Playback:
    """Collect ``tag`` emits (each carrying an ``xyz`` position array) into ordered frames.

    ``up_axis`` names the emit's vertical axis; frames are remapped to the viewport's y-up frame
    so an emit that uses z-up (e.g. ``fluid_frame``) stands upright instead of lying flat.
    """
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
        pos = _to_yup(pos[:, :3] * float(unit_scale_mm), up_axis)
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


def build_material_frame_playback(emits: Sequence[Any], tag: str = "material_frame",
                                  up_axis: str = "z") -> Playback:
    """Build multi-material particle frames emitted with per-particle RGBA.

    Contract: payload ``positions_mm`` is Mx3 and ``colors_rgba`` is Mx3/Mx4. The scenario/engine
    owns both positions and derived colours; Studio only remaps the declared up axis. Frames may
    additionally request a labelled fused density surface; frames without that hint remain sprites.
    """
    frames: List[ParticleFrame] = []
    for emit in emits:
        if getattr(emit, "tag", None) != tag:
            continue
        payload = getattr(emit, "payload", None)
        if not isinstance(payload, dict):
            continue
        raw_pos = payload.get("positions_mm")
        raw_col = payload.get("colors_rgba")
        if raw_pos is None or raw_col is None:
            continue
        pos = np.asarray(raw_pos, dtype=np.float32)
        colors = np.asarray(raw_col, dtype=np.float32)
        if pos.size == 0 and colors.size == 0:
            pos = np.empty((0, 3), dtype=np.float32)
            colors = np.empty((0, 4), dtype=np.float32)
        if pos.ndim != 2 or pos.shape[1] < 3 or colors.ndim != 2 or colors.shape[0] != pos.shape[0]:
            continue
        if colors.shape[1] == 3:
            colors = np.concatenate(
                [colors, np.full((colors.shape[0], 1), 0.75, dtype=np.float32)], axis=1
            )
        if colors.shape[1] < 4:
            continue
        pos = _to_yup(pos[:, :3], up_axis)
        colors = np.ascontiguousarray(np.clip(colors[:, :4], 0.0, 1.0), dtype=np.float32)
        # A scenario may emit a shortened, observer-readable clock while retaining physical
        # time. Studio follows that emitted mapping; it does not choose or infer acceleration.
        time = payload.get(
            "playback_time_s",
            payload.get("time_s", payload.get("time", payload.get("minute", len(frames)))),
        )
        physical_time = payload.get("physical_time_s", payload.get("time_s"))
        time_scale = float(payload.get("time_scale", 1.0) or 1.0)
        frames.append(ParticleFrame(
            time=float(time), positions=pos, tag=tag,
            phase=str(payload.get("phase") or ""), colors=colors,
            physical_time_s=float(physical_time) if physical_time is not None else None,
            time_scale=time_scale,
            surface=_surface_to_yup(payload.get("render_surface"), up_axis),
        ))
    if not frames:
        return Playback(kind="empty")
    frames.sort(key=lambda frame: frame.time)
    times = np.asarray([frame.time for frame in frames], dtype=np.float64)
    physical_times = [frame.physical_time_s for frame in frames if frame.physical_time_s is not None]
    accelerated = any(frame.time_scale > 1.0 + 1e-9 for frame in frames)
    return Playback(
        kind="particles", unit="playback s" if accelerated else "s",
        t_min=float(times[0]), t_max=float(times[-1]),
        frames=frames, frame_times=np.ascontiguousarray(times),
        label=(f"{len(frames)} material-resolved frames" +
               (" · emitted accelerated observer clock" if accelerated else "")),
        source_tag=tag,
        physical_t_min=min(physical_times) if physical_times else None,
        physical_t_max=max(physical_times) if physical_times else None,
        time_accelerated=accelerated,
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
    pb = build_material_frame_playback(list(emits or []))
    if not pb.is_empty:
        return pb
    for tag, scale, up_axis in _PARTICLE_FAMILIES:
        pb = build_particle_playback(list(emits or []), tag=tag, unit_scale_mm=scale, up_axis=up_axis)
        if not pb.is_empty:
            return pb
    return EMPTY
