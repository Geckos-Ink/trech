"""Representation scheduling from measured CPU frame cost; no simulated state."""
from __future__ import annotations

from dataclasses import dataclass
import math
import os


def suggested_memory_mib() -> int:
    """Conservative working allowance, with a portable fallback."""
    try:
        total = os.sysconf("SC_PHYS_PAGES") * os.sysconf("SC_PAGE_SIZE") / 2**20
        return int(max(64, min(1024, total / 32)))
    except (ValueError, OSError, AttributeError):
        return 256


@dataclass
class RenderBudget:
    adaptive: bool = True
    target_fps: int = 60
    detail: float = 1.0
    memory_mib: int = 256
    frame_seconds_ewma: float = 0.0
    observations: int = 0

    def observe(self, seconds: float) -> bool:
        if not math.isfinite(seconds) or seconds <= 0:
            return False
        self.frame_seconds_ewma = (seconds if self.observations == 0 else
                                   0.25 * seconds + 0.75 * self.frame_seconds_ewma)
        self.observations += 1
        if not self.adaptive or self.observations % 8:
            return False
        ratio = self.frame_seconds_ewma * max(1, self.target_fps)
        previous = self.detail
        if ratio > 1.15:
            self.detail = max(0.125, self.detail * max(0.65, ratio ** -0.5))
        elif ratio < 0.65:
            self.detail = min(8.0, self.detail * 1.12)
        return abs(previous - self.detail) > 1e-6

    def trajectory_limits(self) -> tuple[int, int]:
        # Conservative allowances for Python lists + numpy copies + GPU buffers.
        memory = max(16, self.memory_mib) * 2**20
        return max(1, memory // 32768), max(1, memory // 512)

    def cache_frames(self, bytes_per_frame: int) -> int:
        return max(1, min(8, int(max(16, self.memory_mib) * 2**20 /
                                 max(1, bytes_per_frame * 4))))

    def to_dict(self) -> dict:
        return {
            "adaptive_rendering": self.adaptive,
            "render_detail_factor": self.detail,
            "render_target_fps": self.target_fps,
            "preview_memory_budget_mib": self.memory_mib,
            "cpu_frame_seconds_ewma": self.frame_seconds_ewma,
            "render_timing_source": "CPU preparation and submission; GPU time unmeasured",
            "representation_only": True,
        }
