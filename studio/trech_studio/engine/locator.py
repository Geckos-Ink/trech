"""Locate the TRECH engine binary without hard-coding absolute paths.

Search order (first hit wins):
  1. an explicit override (``--engine-bin`` / ``StudioSettings.engine_bin``)
  2. ``$TRECH_BIN``
  3. repo-relative ``build/**/trech`` (the AGENTS.md convention: no absolute paths in-repo;
     the current dev build is ``build/dev/trech``)
  4. ``trech`` on ``$PATH``

The engine is optional at launch: Studio can still view existing runs and edit code without
it, so a missing binary is reported, not fatal.
"""

from __future__ import annotations

import os
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional


@dataclass
class EngineLocation:
    path: Optional[Path]
    source: str  # human-readable provenance: "override" | "env" | "build" | "path" | "missing"

    @property
    def available(self) -> bool:
        return self.path is not None

    def describe(self) -> str:
        if self.path is None:
            return "engine binary not found (set $TRECH_BIN or build build/dev/trech)"
        return f"{self.path} (via {self.source})"


def _build_candidates(repo_root: Path) -> List[Path]:
    """Repo-relative build locations, most-likely first."""
    build = repo_root / "build"
    ordered = [
        build / "dev" / "trech",   # current dev build (see repo AGENTS.md)
        build / "trech",
        repo_root / "build-release" / "trech",
    ]
    # Fall back to a shallow glob so a differently-named build dir still resolves.
    if build.is_dir():
        for found in sorted(build.glob("*/trech")):
            if found not in ordered:
                ordered.append(found)
    return ordered


def locate_engine(
    repo_root: Path,
    override: Optional[Path] = None,
) -> EngineLocation:
    if override is not None:
        p = Path(override).expanduser()
        if p.is_file() and os.access(p, os.X_OK):
            return EngineLocation(p, "override")
        # Honour the explicit request even if it is not (yet) executable, so the
        # error surfaced to the user points at what they asked for.
        return EngineLocation(p if p.exists() else None, "override")

    env_bin = os.environ.get("TRECH_BIN")
    if env_bin:
        p = Path(env_bin).expanduser()
        if p.is_file():
            return EngineLocation(p, "env")

    for candidate in _build_candidates(repo_root):
        if candidate.is_file() and os.access(candidate, os.X_OK):
            return EngineLocation(candidate, "build")

    on_path = shutil.which("trech")
    if on_path:
        return EngineLocation(Path(on_path), "path")

    return EngineLocation(None, "missing")
