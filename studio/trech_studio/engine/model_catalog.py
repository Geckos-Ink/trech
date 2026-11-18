"""Find and read model files for the model browser (file IO only; parsing is ``model_catalog``).

Scans the repository's model folders, the ``trech-ml`` store and any folder the user added for
``generic_surrogate_v1/v2/v3`` JSON files and evolved TorchScript twins (``*.arch.json`` beside a
``.pt``), and reads ``trech_arch_outcome_v1`` records so each generated model shows what the
engine decided about it. Each file is hashed (SHA-256) so a loaded run's recorded model snapshot
can be matched by bytes, not by name. Nothing is executed or loaded as a model.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import json
import os
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence

from ..model_catalog import ModelEntry, describe_model, is_model_payload, outcome_decisions

REPOSITORY_ROOTS = ("data", "examples", "projects", "ml")
GENERATED_ROOT = "build/arch"
SKIP_DIRS = {".git", "node_modules", "__pycache__", ".venv", "venv", "thirds"}
MAX_BYTES = 32 * 1024 * 1024
MAX_FILES = 20000
MARKERS = (b"generic_surrogate_v", b"trech_evolved_arch_v1", b"trech_arch_outcome_v1")


@dataclass
class CatalogScan:
    entries: List[ModelEntry] = field(default_factory=list)
    roots: List[Path] = field(default_factory=list)
    skipped: List[str] = field(default_factory=list)   # "path: reason"
    outcomes: int = 0
    truncated: bool = False


def default_roots(repo_root: Path, store: Optional[Path]) -> List[Path]:
    roots = [Path(repo_root) / name for name in REPOSITORY_ROOTS]
    if store is not None:
        roots.append(Path(store))
    roots.append(Path(repo_root) / GENERATED_ROOT)
    return roots


def _sha256(path: Path) -> Optional[str]:
    digest = hashlib.sha256()
    try:
        with open(path, "rb") as handle:
            for chunk in iter(lambda: handle.read(1 << 20), b""):
                digest.update(chunk)
    except OSError:
        return None
    return digest.hexdigest()


def _within(path: Path, root: Optional[Path]) -> bool:
    if root is None:
        return False
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except (ValueError, OSError):
        return False


def _origin(path: Path, repo_root: Path, store: Optional[Path], generated: bool) -> str:
    if generated:
        return "generated"
    if _within(path, store):
        return "store"
    if any(_within(path, Path(repo_root) / name) for name in REPOSITORY_ROOTS):
        return "repository"
    return "folder"


def _walk(root: Path) -> Iterable[Path]:
    for directory, subdirs, files in os.walk(root):
        subdirs[:] = sorted(d for d in subdirs if d not in SKIP_DIRS and not d.startswith("."))
        for name in sorted(files):
            if name.endswith(".json"):
                yield Path(directory) / name


def scan_models(repo_root: Path, store: Optional[Path] = None,
                extra_roots: Sequence[Path] = ()) -> CatalogScan:
    repo_root = Path(repo_root)
    scan = CatalogScan()
    seen: set = set()
    roots = default_roots(repo_root, store) + [Path(p) for p in extra_roots]
    candidates: List[Path] = []
    for root in roots:
        if not root.is_dir() or root.resolve() in seen:
            continue
        seen.add(root.resolve())
        scan.roots.append(root)
        for path in _walk(root):
            candidates.append(path)
            if len(candidates) >= MAX_FILES:
                scan.truncated = True
                break
        if scan.truncated:
            break

    payloads: Dict[Path, dict] = {}
    decisions: Dict[str, list] = {}
    visited: set = set()
    for path in candidates:
        key = path.resolve()
        if key in visited:
            continue
        visited.add(key)
        if path.name.endswith((".manifest.json", ".pt.io.json", ".search.json", ".worker_request.json",
                               ".worker_result.json")):
            continue
        try:
            size = path.stat().st_size
            if size > MAX_BYTES:
                scan.skipped.append(f"{path}: larger than {MAX_BYTES // (1024 * 1024)} MiB")
                continue
            raw = path.read_bytes()
            # Writers may sort keys, so the schema can sit anywhere: search the bytes before
            # paying for a JSON parse.
            if not any(marker in raw for marker in MARKERS):
                continue
            data = json.loads(raw.decode("utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
            scan.skipped.append(f"{path}: {error}")
            continue
        if isinstance(data, dict) and data.get("schema") == "trech_arch_outcome_v1":
            scan.outcomes += 1
            for model, decision in outcome_decisions(data, path).items():
                decisions.setdefault(str(Path(model).resolve()), []).append(decision)
            continue
        if is_model_payload(data):
            payloads[path] = data

    for path, data in payloads.items():
        model_path = path
        if data.get("schema") == "trech_evolved_arch_v1" and path.name.endswith(".arch.json"):
            pt = path.with_name(path.name[: -len(".arch.json")] + ".pt")
            if pt.exists():
                model_path = pt
        resolved = str(model_path.resolve())
        trained = data.get("trained_from") if isinstance(data.get("trained_from"), dict) else {}
        generated = resolved in decisions or trained.get("generator") in ("evolvo_gfsl_nn", "classic_native")
        entry = describe_model(data, path, _origin(path, repo_root, store, generated))
        entry.path = model_path
        entry.decisions = decisions.get(resolved, [])
        entry.sha256 = _sha256(model_path)
        try:
            entry.size_bytes = model_path.stat().st_size
        except OSError:
            entry.size_bytes = None
        scan.entries.append(entry)
    scan.entries.sort(key=lambda e: str(e.path))
    return scan
