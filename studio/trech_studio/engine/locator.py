"""Locate the TRECH engine binary without hard-coding absolute paths.

Search order:
  1. an explicit override (``--engine-bin`` / ``StudioSettings.engine_bin``)
  2. ``$TRECH_BIN``
  3. newest repo-relative build that passes the Studio inspection protocol probe
  4. ``trech`` on ``$PATH``

The engine is optional at launch: Studio can still view existing runs and edit code without
it, so a missing binary is reported, not fatal.
"""

from __future__ import annotations

import json
import os
import shutil
import stat
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional


@dataclass
class EngineLocation:
    path: Optional[Path]
    source: str  # human-readable provenance: "override" | "env" | "build" | "path" | "missing"
    error: str = ""

    def __post_init__(self) -> None:
        # Freeze the caller's working-directory interpretation before any engine
        # operation switches to the scenario directory (also for direct callers).
        if self.path is not None:
            try:
                self.path = Path(self.path).expanduser().resolve()
            except (OSError, RuntimeError) as exc:
                self.error = f"could not resolve engine binary {self.path}: {exc}"

    @property
    def available(self) -> bool:
        return self.path is not None and not self.error

    def describe(self) -> str:
        if self.error:
            return self.error
        if self.path is None:
            return "engine binary not found (set $TRECH_BIN or build build/dev/trech)"
        return f"{self.path} (via {self.source})"


def _build_candidates(repo_root: Path) -> List[Path]:
    """Executable builds, newest first; conventional paths break timestamp ties."""
    build = repo_root / "build"
    ordered = [
        build / "dev" / "trech",   # current dev build (see repo AGENTS.md)
        build / "trech",
        repo_root / "build-release" / "trech",
    ]
    # Fall back to a shallow scan so a differently-named build dir still resolves.
    try:
        if build.is_dir():
            for directory in sorted(build.iterdir()):
                found = directory / "trech"
                if found not in ordered:
                    ordered.append(found)
    except OSError:
        # Known build paths and PATH may still be accessible even if directory
        # enumeration is denied or the build tree is removed during discovery.
        pass
    candidates = []
    for path in ordered:
        try:
            # Read metadata once: a concurrent rebuild can remove/replace a
            # candidate between discovery and sorting. Its later launch is also
            # guarded by the inspection probe.
            metadata = path.stat()
            if stat.S_ISREG(metadata.st_mode) and os.access(path, os.X_OK):
                candidates.append((path, metadata.st_mtime_ns))
        except OSError:
            continue
    return [path for path, _ in sorted(candidates, key=lambda item: item[1], reverse=True)]


def _explicit_location(path: Path, source: str) -> EngineLocation:
    location = EngineLocation(path, source)
    if location.error:
        return location
    p = location.path
    try:
        if not p.is_file() or not os.access(p, os.X_OK):
            location.error = f"engine binary is not an executable file: {p} (via {source})"
    except OSError as exc:
        location.error = f"could not inspect engine binary {p} (via {source}): {exc}"
    return location


def _probe_inspection(path: Path, experiment: Path) -> Optional[str]:
    """Check the bridge protocol without initializing Geant4 or loading models.

    This is a protocol check, not a claim that every scenario or optional engine
    backend is supported. Discovery runs it once; ordinary Run/Inspect reuse the
    selected EngineLocation.
    """
    try:
        result = subprocess.run(
            [str(path), "inspect", str(experiment), "--param", "studio_probe=124"],
            cwd=str(experiment.parent), capture_output=True, text=True, timeout=3,
            check=False,
        )
        if result.returncode:
            detail = result.stderr.strip() or result.stdout.strip() or f"exit {result.returncode}"
            return detail.splitlines()[0][:240]
        raw = json.loads(result.stdout)
        authoring = raw["authoring"]
        parameters = raw["parameters"]
        if (raw["config"]["detector"]["worldSizeMm"] != 124
                or not isinstance(parameters, list)
                or not any(p.get("id") == "studio_probe" and p.get("value") == 124
                           for p in parameters if isinstance(p, dict))
                or authoring["studio"].get("schema") != "trech_studio_v1"
                or authoring["studio"].get("title") != "Studio engine probe"
                or not isinstance(authoring["sources"], list)
                or not {experiment.name, "studio_probe.ui.js"}.issubset(
                    {Path(p).name for p in authoring["sources"] if isinstance(p, str)})):
            return "inspection lacks typed overrides, bundle sources or Studio metadata"
    except subprocess.TimeoutExpired:
        return "Studio inspection probe timed out after 3 seconds"
    except (OSError, ValueError, KeyError, TypeError, AttributeError) as exc:
        return f"Studio inspection probe failed: {exc}"
    return None


def _compatible_location(candidates: List[tuple[Path, str]]) -> EngineLocation:
    rejected = []
    if not candidates:
        return EngineLocation(None, "missing")
    with tempfile.TemporaryDirectory(prefix="trech_studio_probe_") as temporary:
        directory = Path(temporary).resolve()
        experiment = directory / "studio_probe.js"
        experiment.write_text(
            "const size = TRECH_VALUE.integer('studio_probe', {default:123,min:1,max:200});\n"
            "globalThis.TRECH_CONFIG = {detector:{worldSizeMm:size}};\n",
            encoding="utf-8",
        )
        (directory / "studio_probe.ui.js").write_text(
            "globalThis.TRECH_STUDIO = {schema:'trech_studio_v1',title:'Studio engine probe'};\n",
            encoding="utf-8",
        )
        for candidate, source in candidates:
            try:
                path = candidate.resolve()
            except (OSError, RuntimeError) as exc:
                rejected.append(f"{candidate}: could not resolve binary: {exc}")
                continue
            error = _probe_inspection(path, experiment)
            if error is None:
                return EngineLocation(path, source)
            rejected.append(f"{path}: {error}")
    return EngineLocation(None, "missing", "No engine passed Studio's inspection protocol. "
        "Rebuild TRECH or set an explicit --engine-bin / $TRECH_BIN. " + "; ".join(rejected))


def locate_engine(
    repo_root: Path,
    override: Optional[Path] = None,
) -> EngineLocation:
    if override is not None:
        return _explicit_location(override, "override")

    env_bin = os.environ.get("TRECH_BIN")
    if env_bin:
        return _explicit_location(Path(env_bin), "env")

    try:
        candidates = [(path, "build") for path in _build_candidates(Path(repo_root).resolve())]

        on_path = shutil.which("trech")
        # A duplicate via a symlink is harmless; avoid resolving candidates here
        # so one broken link cannot prevent trying another valid engine.
        if on_path and Path(on_path).absolute() not in {p.absolute() for p, _ in candidates}:
            candidates.append((Path(on_path), "path"))

        return _compatible_location(candidates)
    except (OSError, RuntimeError) as exc:
        # The engine remains optional even if the build directory or temporary
        # probe files cannot be read/written.
        return EngineLocation(None, "missing", f"Could not discover a Studio engine: {exc}")
