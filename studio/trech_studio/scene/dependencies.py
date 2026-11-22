"""Package a transport scene's model dependencies beside its exported scenario.

A recorded config names its separately loaded model files by the path the scenario declared
(``models[].path``, ``optics.derive.surrogateModelPath``, ``stratify.modelPath``). That path
resolves against the directory the run started in, or the scenario's own directory, so it
breaks once the config is written somewhere else. Export therefore copies each file into a
dependency folder beside the new scenario and points the config at the copy.

The engine's ``model_artifacts`` manifest is the authority for *which* bytes the run used:
each file is found by its declared path and accepted only when its SHA-256 matches the one
the engine recorded while loading it. A TorchScript module's named-IO sidecar
(``<model>.io.json``, digest ``io_sidecar_sha256``) travels with it under the same rule. A
dependency the run did not load (strict mode, disabled loader, missing file) has no recorded
digest and is refused rather than guessed. Files a model might name internally are not
followed: the engine records no digest for them.
Pure data + hashlib: no Qt, no engine calls.
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
import hashlib
from pathlib import Path, PurePosixPath
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

DEFAULT_DEPENDENCY_DIR = "scene_deps"


@dataclass(frozen=True)
class Dependency:
    """One model file a recorded config loads, with the digest the engine recorded for it."""

    label: str                  # human-readable config field, e.g. ``models[0].path``
    pointer: Tuple              # keys from the config root to the path string
    declared: str               # the path exactly as the config declares it
    sha256: str                 # the engine's digest of the bytes it loaded
    sidecar_sha256: str = ""    # TorchScript named-IO sidecar digest, when one was loaded


@dataclass
class SceneBundle:
    """Exported scenario source plus the dependency files to copy beside it."""

    source: str
    # Bundle-relative POSIX path (as written into the config) -> located source file.
    files: Dict[str, Path]


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _refuse(label: str, declared: str, reason: str) -> ValueError:
    return ValueError(f"Cannot package {label} ({declared}): {reason}; "
                      "export the original scenario with its dependencies instead")


def _loaded_digest(entry: Optional[Dict], label: str, declared: str) -> str:
    if entry is None:
        raise _refuse(label, declared, "the run's model-artifact manifest does not list it")
    status = entry.get("status", "loaded" if entry.get("loaded") else "failed")
    if status != "loaded" or not entry.get("loaded", status == "loaded"):
        note = entry.get("load_note") or status
        raise _refuse(label, declared, f"the recorded run did not load it ({note})")
    digest = entry.get("sha256")
    if not isinstance(digest, str) or len(digest) != 64:
        raise _refuse(label, declared, "the recorded run has no SHA-256 for it")
    return digest.lower()


def recorded_dependencies(config: Dict, artifacts: Optional[Dict]) -> List[Dependency]:
    """Every model file ``config`` loads, matched to the engine's recorded digest.

    Raises ``ValueError`` when a dependency cannot be tied to bytes the run actually used.
    Returns an empty list for a config without model dependencies (no manifest needed).
    """
    wanted: List[Tuple[str, Tuple, str, str]] = []   # (label, pointer, declared, loader)
    for i, model in enumerate(config.get("models") or []):
        if isinstance(model, dict) and model.get("path"):
            wanted.append((f"models[{i}].path", ("models", i, "path"), model["path"], ""))
    surrogate = (config.get("optics") or {}).get("derive", {}).get("surrogateModelPath")
    if surrogate:
        wanted.append(("optics.derive.surrogateModelPath",
                       ("optics", "derive", "surrogateModelPath"), surrogate, "optics"))
    stratifier = (config.get("stratify") or {}).get("modelPath")
    if stratifier:
        wanted.append(("stratify.modelPath", ("stratify", "modelPath"), stratifier, "stratifier"))
    if not wanted:
        return []
    if not isinstance(artifacts, dict):
        label, _, declared, _ = wanted[0]
        raise _refuse(label, declared, "this run predates the engine's model-artifact manifest")

    models = [m for m in artifacts.get("models") or [] if isinstance(m, dict)]
    loaders = [m for m in artifacts.get("loaders") or [] if isinstance(m, dict)]
    out = []
    for label, pointer, declared, loader in wanted:
        if not isinstance(declared, str):
            raise _refuse(label, str(declared), "the path is not a string")
        if loader:
            entry = next((m for m in loaders
                          if m.get("loader") == loader and m.get("path") == declared), None)
        else:
            name = config["models"][pointer[1]].get("name")
            entry = next((m for m in models
                          if m.get("name") == name and m.get("path") == declared), None)
        digest = _loaded_digest(entry, label, declared)
        sidecar = entry.get("io_sidecar_sha256") or ""
        if sidecar and (not isinstance(sidecar, str) or len(sidecar) != 64):
            raise _refuse(label, declared, "its recorded sidecar digest is malformed")
        out.append(Dependency(label, pointer, declared, digest, sidecar.lower()))
    return out


def locate_dependency(dependency: Dependency, search_dirs: Sequence[Path]) -> Path:
    """Find the file the run loaded: its declared path under each search directory, by digest."""
    declared = Path(dependency.declared)
    candidates: Iterable[Path] = ([declared] if declared.is_absolute()
                                  else (Path(base) / declared for base in search_dirs))
    seen = set()
    for candidate in candidates:
        try:
            resolved = candidate.resolve()
        except OSError:
            continue
        if resolved in seen or not resolved.is_file():
            continue
        seen.add(resolved)
        if _sha256(resolved) == dependency.sha256:
            return resolved
    where = ", ".join(str(Path(d)) for d in search_dirs) or "no search directories"
    raise _refuse(dependency.label, dependency.declared,
                  f"no file there matches the recorded SHA-256 (searched {where})")


def run_search_dirs(provenance: Optional[Dict], roots: Sequence[Path]) -> List[Path]:
    """Directories a recorded run may have resolved its relative model paths from.

    The engine reads a relative path from its working directory, then from the experiment's
    directory. Provenance records the command line but not the working directory, so each
    candidate ``root`` (Studio's working directory, the repository) stands in for it.
    """
    args = list((provenance or {}).get("cli_args") or [])
    experiment = next((args[i + 1] for i, arg in enumerate(args[:-1]) if arg in ("run", "lab")), None)
    dirs: List[Path] = []
    if isinstance(experiment, str) and experiment:
        parent = Path(experiment).parent
        dirs += [parent] if parent.is_absolute() else [Path(root) / parent for root in roots]
    dirs += [Path(root) for root in roots]
    unique: List[Path] = []
    for directory in dirs:
        if directory not in unique:
            unique.append(directory)
    return unique


def _set(config: Dict, pointer: Tuple, value: str) -> None:
    node = config
    for key in pointer[:-1]:
        node = node[key]
    node[pointer[-1]] = value


def package_dependencies(config: Dict, artifacts: Optional[Dict], search_dirs: Sequence[Path],
                         dependency_dir: str = DEFAULT_DEPENDENCY_DIR) -> Tuple[Dict, Dict[str, Path]]:
    """Return ``(config copy, files)`` with every dependency pointed at its bundled copy.

    Identical bytes share one copy; different files with the same name get a digest suffix.
    Paths are relative POSIX paths, which the engine resolves beside the exported scenario.
    """
    folder = PurePosixPath(dependency_dir)
    if not dependency_dir or folder.is_absolute() or ".." in folder.parts:
        raise ValueError("The dependency folder must be a relative path inside the export directory")
    packaged = deepcopy(config)
    files: Dict[str, Path] = {}
    by_digest: Dict[Tuple[str, str], str] = {}
    for dependency in recorded_dependencies(config, artifacts):
        source = locate_dependency(dependency, search_dirs)
        key = (dependency.sha256, dependency.sidecar_sha256)
        target = by_digest.get(key)
        if target is None:
            name = PurePosixPath(source.name)
            target = str(folder / name)
            if target in files:
                target = str(folder / f"{name.stem}-{dependency.sha256[:12]}{name.suffix}")
            files[target] = source
            if dependency.sidecar_sha256:
                # The engine reads the sidecar at `<model path>.io.json`, beside the module.
                sidecar = Path(str(source) + ".io.json")
                if not sidecar.is_file() or _sha256(sidecar) != dependency.sidecar_sha256:
                    raise _refuse(dependency.label, dependency.declared,
                                  f"its sidecar {sidecar.name} does not match the recorded SHA-256")
                files[target + ".io.json"] = sidecar
            by_digest[key] = target
        _set(packaged, dependency.pointer, target)
    return packaged, files
