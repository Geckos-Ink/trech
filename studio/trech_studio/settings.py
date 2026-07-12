"""Studio-wide settings.

Small, explicit configuration object shared across panels. Anything that a user might
reasonably want to override (engine binary path, default output root, viewport look) lives
here rather than being hard-coded in a widget. Kept dependency-free so engine/scene/render
can import it without pulling in Qt.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


def _repo_root_guess() -> Path:
    """Best-effort repo root: studio/ lives directly under the TRECH checkout."""
    # studio/trech_studio/settings.py -> studio/ -> <repo root>
    return Path(__file__).resolve().parents[2]


@dataclass
class StudioSettings:
    """Runtime configuration for a Studio session."""

    # Repo root (used to resolve build/**/trech and examples/ relatively — never absolute).
    repo_root: Path = field(default_factory=_repo_root_guess)

    # Explicit engine binary override. When None, engine.locator searches build/**/trech.
    engine_bin: Optional[Path] = None

    # Where new runs write their output directories.
    output_root: Path = field(default_factory=lambda: _repo_root_guess() / "build" / "studio")

    # Real-time lab bootstrap config (JSON). Repo default ships one.
    lab_bootstrap: Optional[Path] = None

    # Viewport look.
    background: str = "dark"          # "dark" | "light"
    target_fps: int = 60

    def __post_init__(self) -> None:
        env_bin = os.environ.get("TRECH_BIN")
        if env_bin and self.engine_bin is None:
            self.engine_bin = Path(env_bin).expanduser()
        if self.lab_bootstrap is None:
            default = self.repo_root / "examples" / "lab" / "realtime_lab_bootstrap.json"
            self.lab_bootstrap = default if default.exists() else None

    def examples_dir(self) -> Path:
        return self.repo_root / "examples" / "experiments"

    def examples_root(self) -> Path:
        """Root of the shipped example scenarios (experiments/, lab/, macros/)."""
        return self.repo_root / "examples"
