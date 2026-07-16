"""Observer-frame playback for the classic PyVista TRECH viewer.

The classic viewer reads the same ``material_frame`` sideband contract as Studio. Positions,
per-particle RGBA, phase, and physical/playback clocks remain scenario output; this module only
validates/loads them for held-frame replay.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

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
    clip_min_mm: Optional[float]
    clip_max_mm: Optional[float]
    fresnel_r0: float
    gloss: float
    opacity: float
    positions_unmodified: bool
    policy: str


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
        )
    except (TypeError, ValueError):
        return None


@dataclass
class MaterialFrame:
    playback_time_s: float
    physical_time_s: float
    time_scale: float
    phase: str
    positions_mm: np.ndarray
    colors_rgba: np.ndarray
    surface: Optional[MaterialSurface] = None


def load_material_frames(path: str | Path) -> List[MaterialFrame]:
    """Load ordered ``material_frame`` emits from ``trech_hook_emits.jsonl``.

    Empty frames are retained so a scenario can honestly begin with an empty apparatus. Invalid
    or mismatched position/colour payloads are ignored instead of being guessed into shape.
    """
    frames: List[MaterialFrame] = []
    with open(path, "r", encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            raw = json.loads(line)
            if raw.get("tag") != "material_frame":
                continue
            payload = raw.get("payload")
            if not isinstance(payload, dict):
                continue
            pos = np.asarray(payload.get("positions_mm") or [], dtype=np.float32)
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
            frames.append(MaterialFrame(
                playback_time_s=playback,
                physical_time_s=physical,
                time_scale=float(payload.get("time_scale", 1.0) or 1.0),
                phase=str(payload.get("phase") or ""),
                positions_mm=np.ascontiguousarray(pos[:, :3], dtype=np.float32),
                colors_rgba=np.ascontiguousarray(np.clip(col[:, :4], 0.0, 1.0), dtype=np.float32),
                surface=_material_surface(payload.get("render_surface")),
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
