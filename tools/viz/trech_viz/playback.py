"""Observer-frame playback for the classic PyVista TRECH viewer.

The classic viewer reads the same ``material_frame`` sideband contract as Studio. Positions,
per-particle RGBA, phase, and physical/playback clocks remain scenario output; this module only
validates/loads them for held-frame replay.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import List

import numpy as np


@dataclass
class MaterialFrame:
    playback_time_s: float
    physical_time_s: float
    time_scale: float
    phase: str
    positions_mm: np.ndarray
    colors_rgba: np.ndarray


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
            ))
    frames.sort(key=lambda frame: frame.playback_time_s)
    return frames
