"""Trajectory JSONL parsing."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, List, Tuple


@dataclass
class Trajectory:
    event_id: int
    track_id: int
    particle: str
    capped: bool
    points: List[Tuple[float, float, float]] = field(default_factory=list)
    energies_ev: List[float] = field(default_factory=list)
    times_ns: List[float] = field(default_factory=list)
    materials: List[str] = field(default_factory=list)
    volumes: List[str] = field(default_factory=list)

    def mean_energy_ev(self) -> float:
        if not self.energies_ev:
            return 0.0
        return sum(self.energies_ev) / len(self.energies_ev)


def load_trajectories(path: str | Path) -> List[Trajectory]:
    out: List[Trajectory] = []
    with open(path, "r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                raw = json.loads(line)
            except json.JSONDecodeError:
                continue
            traj = Trajectory(
                event_id=int(raw.get("event_id", -1)),
                track_id=int(raw.get("track_id", -1)),
                particle=str(raw.get("particle") or ""),
                capped=bool(raw.get("capped") or False),
            )
            for point in raw.get("points") or []:
                traj.points.append(
                    (
                        float(point.get("x_mm") or 0.0),
                        float(point.get("y_mm") or 0.0),
                        float(point.get("z_mm") or 0.0),
                    )
                )
                traj.energies_ev.append(float(point.get("energy_ev") or 0.0))
                traj.times_ns.append(float(point.get("time_ns") or 0.0))
                traj.materials.append(str(point.get("material") or ""))
                traj.volumes.append(str(point.get("volume") or ""))
            if traj.points:
                out.append(traj)
    return out


def wavelength_nm_for_energy_ev(energy_ev: float) -> float:
    if energy_ev <= 0.0:
        return 0.0
    return 1239.841984 / energy_ev


def visible_rgb_for_wavelength(wavelength_nm: float) -> Tuple[float, float, float]:
    """A simple wavelength -> RGB approximation (Bruton / CIE simplified)."""
    if wavelength_nm <= 0:
        return (1.0, 1.0, 1.0)
    if wavelength_nm < 380:
        return (0.4, 0.0, 0.6)  # near-UV
    if wavelength_nm > 780:
        return (0.3, 0.0, 0.0)  # near-IR
    if wavelength_nm < 440:
        r = -(wavelength_nm - 440) / (440 - 380)
        g = 0.0
        b = 1.0
    elif wavelength_nm < 490:
        r = 0.0
        g = (wavelength_nm - 440) / (490 - 440)
        b = 1.0
    elif wavelength_nm < 510:
        r = 0.0
        g = 1.0
        b = -(wavelength_nm - 510) / (510 - 490)
    elif wavelength_nm < 580:
        r = (wavelength_nm - 510) / (580 - 510)
        g = 1.0
        b = 0.0
    elif wavelength_nm < 645:
        r = 1.0
        g = -(wavelength_nm - 645) / (645 - 580)
        b = 0.0
    else:
        r = 1.0
        g = 0.0
        b = 0.0
    return (max(0.0, min(1.0, r)), max(0.0, min(1.0, g)), max(0.0, min(1.0, b)))
