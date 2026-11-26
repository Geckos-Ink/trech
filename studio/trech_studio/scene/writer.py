"""Serialize a transport scene draft, preserving physics absent from the viz schema.

This is data authoring only. Recorded spectra/appearance are never converted to physics.
Loaded scenes require their canonical config; callback source cannot be recovered from it.
``scene_to_bundle`` also packages the recorded model files (see ``dependencies.py``).
"""

from __future__ import annotations

from copy import deepcopy
import json
import math
from pathlib import Path
from typing import Dict, List, Optional, Sequence

from .dependencies import DEFAULT_DEPENDENCY_DIR, SceneBundle, package_dependencies
from .loader import scene_from_viz_data
from .materials import material_references, validate_material
from .model import Beam, SceneModel, Shape, VolumeNode

_BUILTIN_PARENTS = {"world", "medium", "mediumbox", "medium_box"}


def _number(value: float, label: str, *, positive: bool = False) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError(f"{label} must be finite")
    if positive and value <= 0:
        raise ValueError(f"{label} must be positive")
    return value


def _vector(values, label: str):
    if len(values) != 3:
        raise ValueError(f"{label} must have three coordinates")
    return [_number(v, label) for v in values]


def _shape(shape: Shape) -> Dict:
    kind = shape.type.lower()
    if kind == "box":
        size = _vector(shape.size_mm, "box size")
        if min(size) <= 0:
            raise ValueError("box sizes must be positive")
        return {"type": kind, "sizeMm": size}
    if kind not in ("sphere", "tube", "cylinder"):
        raise ValueError(f"Unsupported scene shape: {shape.type}")
    outer = _number(shape.outer_radius_mm, "outer radius", positive=True)
    inner = _number(shape.inner_radius_mm, "inner radius")
    if not 0 <= inner < outer:
        raise ValueError("inner radius must be nonnegative and smaller than outer radius")
    result = {"type": kind, "outerRadiusMm": outer, "innerRadiusMm": inner}
    if kind != "sphere":
        result["lengthMm"] = _number(shape.length_mm, "length", positive=True)
    return result


def _beam(beam: Beam, base: Dict, old: Optional[Beam] = None) -> Dict:
    result = deepcopy(base)
    if old is None or beam.particle != old.particle:
        result["particle"] = beam.particle
    if old is None or beam.energy_ev != old.energy_ev:
        result["energyMeV"] = _number(beam.energy_ev, "beam energy", positive=True) / 1e6
    if old is None or beam.direction != old.direction:
        direction = _vector(beam.direction, "beam direction")
        if not any(direction):
            raise ValueError("beam direction must be nonzero")
        result["direction"] = direction
    if old is None or beam.active != old.active:
        result["active"] = beam.active
    if beam.name:
        result["name"] = beam.name
    else:
        result.pop("name", None)
    if beam.origin_mm is not None:
        result["originMm"] = _vector(beam.origin_mm, "beam origin")
    for attr, key in (("spot_radius_mm", "spotRadiusMm"), ("divergence_deg", "divergenceDeg"),
                      ("energy_spread_fractional", "energySpreadFractional")):
        value = getattr(beam, attr)
        if value is not None:
            _number(value, key)
            if value < 0 or (attr == "divergence_deg" and value > 180):
                raise ValueError(f"{key} must be between 0 and 180" if attr == "divergence_deg"
                                 else f"{key} must be nonnegative")
            result[key] = value
    return result


def _check_snapshot(scene: SceneModel, config: Dict) -> None:
    """Catch mixed/stale output dirs before pairing scene edits with another config."""
    detector = config.get("detector", {})
    run = config.get("run", {})
    if (scene.world_size_mm != detector.get("worldSizeMm")
            or scene.world_material != detector.get("worldMaterial")
            or scene.medium_size_mm != detector.get("mediumBoxMm", 0)
            or (scene.medium_size_mm > 0 and scene.medium_material != detector.get("mediumMaterial"))):
        raise ValueError("Recorded config and viz scene do not match; load a clean run output directory")
    if (scene.run.seed != run.get("seed") or scene.run.n_events != run.get("nEvents")
            or scene.run.determinism_mode != config.get("determinism", {}).get("mode", "strict")):
        raise ValueError("Recorded config and viz run identity do not match; load a clean run output directory")
    volumes = []
    for value in config.get("geometry", {}).get("volumes", []):
        shape, place = value.get("shape", {}), value.get("placement", {})
        volumes.append(VolumeNode(
            name=value["name"], material=value.get("material", ""), parent=place.get("parent", ""),
            position_mm=tuple(place.get("positionMm", (0., 0., 0.))),
            rotation_deg=tuple(place.get("rotationDeg", (0., 0., 0.))),
            shape=Shape(type=shape.get("type", "box"), size_mm=tuple(shape.get("sizeMm", (0., 0., 0.))),
                        outer_radius_mm=shape.get("outerRadiusMm", 0),
                        inner_radius_mm=shape.get("innerRadiusMm", 0), length_mm=shape.get("lengthMm", 0)),
            tags=value.get("tags", []), score_edep=value.get("scoreEdep", False)))
    beams = [Beam(name=b.get("name", ""), particle=b.get("particle", ""),
                  energy_ev=b.get("energyMeV", 0) * 1e6,
                  direction=tuple(b.get("direction", (0., 0., 1.))), active=b.get("active", False))
             for b in config.get("beams", [config.get("beam", {})])]
    if scene.volumes != volumes or scene.beams != beams:
        raise ValueError("Recorded config and viz scene do not match; load a clean run output directory")


def _parent_key(entry: Dict) -> str:
    return str(entry.get("placement", {}).get("parent", "") or "").lower()


def _check_recorded_hierarchy(volumes: List[Dict], kept: set) -> None:
    """The recorded run must not have relied on the engine's parent fallback.

    The engine places a volume whose parent is unknown or declared later in the world and
    records a ``parent_fallback`` issue. Reordering such a config on export would nest the
    volume and silently change the recorded geometry, so it is refused instead.
    """
    declared = set()
    names = {str(v.get("name", "")).lower() for v in volumes}
    for entry in volumes:
        parent = _parent_key(entry)
        if (str(entry.get("name", "")).lower() in kept and parent
                and parent not in _BUILTIN_PARENTS and parent not in declared):
            reason = "is declared after it" if parent in names else "is not a volume"
            raise ValueError(f"Recorded volume {entry.get('name')}'s parent {parent} {reason}; "
                             "the run placed it in the world. Fix the original scenario first")
        declared.add(str(entry.get("name", "")).lower())


def _order_volumes(volumes: List[Dict]) -> List[Dict]:
    """Parents before children, keeping the authored order wherever it is already valid.

    The engine builds volumes in list order and needs each parent built first. A Studio
    reparent can point a volume at a later one; this stable order moves only what must move.
    Unknown parents and parent cycles are rejected rather than left to the world fallback.
    """
    names = {str(v["name"]).lower() for v in volumes}
    for entry in volumes:
        parent = _parent_key(entry)
        if parent and parent not in _BUILTIN_PARENTS and parent not in names:
            raise ValueError(f"{entry['name']}'s parent {entry['placement']['parent']} is not a volume in this scene")
    ordered: List[Dict] = []
    built = set()
    pending = list(volumes)
    while pending:
        ready = [v for v in pending
                 if not _parent_key(v) or _parent_key(v) in _BUILTIN_PARENTS or _parent_key(v) in built]
        if not ready:
            cycle = ", ".join(str(v["name"]) for v in pending)
            raise ValueError(f"Volume parents form a cycle: {cycle}")
        # Take only the first ready volume so later siblings keep their relative order.
        first = ready[0]
        ordered.append(first)
        built.add(str(first["name"]).lower())
        pending.remove(first)
    return ordered


def scene_to_config(scene: SceneModel, base_config: Optional[Dict] = None, *,
                    allow_dependencies: bool = False) -> Dict:
    """Return a detached config containing the scene's authored edits.

    A loaded scene needs its complete provenance config. Unchanged fields retain the exact
    canonical values (including eV/MeV rounding, isotope composition and source spread).
    Registered callbacks are rejected rather than dropped. External model dependencies are
    rejected too unless ``allow_dependencies`` is set by ``scene_to_bundle``, which then
    repoints them at packaged copies. Volumes are written parents-first (``_order_volumes``).
    New scenes without ``raw`` can use engine defaults for unrepresented config fields.
    """
    if (scene.raw or scene.source_path) and base_config is None:
        raise ValueError("Loaded scenes need the full recorded config; viz geometry alone is incomplete")
    config = deepcopy(base_config) if base_config is not None else {}
    if not isinstance(config, dict):
        raise ValueError("The recorded config must be an object")
    if config.get("hooks", {}).get("registered"):
        raise ValueError("This run uses JS callbacks; edit/save the original scenario to retain its processes")
    if not allow_dependencies and (
            config.get("models") or config.get("stratify", {}).get("modelPath")
            or config.get("optics", {}).get("derive", {}).get("surrogateModelPath")):
        raise ValueError("This run uses external models; export their original scenario with its dependencies")
    baseline = scene_from_viz_data(scene.raw) if scene.raw else None
    if baseline is not None:
        _check_snapshot(baseline, config)

    detector = config.setdefault("detector", {})
    for attr, key in (("world_size_mm", "worldSizeMm"), ("world_material", "worldMaterial"),
                      ("medium_size_mm", "mediumBoxMm"), ("medium_material", "mediumMaterial")):
        value = getattr(scene, attr)
        if baseline is None or value != getattr(baseline, attr):
            if attr.endswith("size_mm"):
                _number(value, attr, positive=attr == "world_size_mm")
                if value < 0:
                    raise ValueError("medium size must be nonnegative")
            detector[key] = value

    recorded_volumes = config.get("geometry", {}).get("volumes", [])
    kept = {v.name.lower() for v in scene.volumes}
    _check_recorded_hierarchy(recorded_volumes, kept)
    originals = {v["name"]: v for v in recorded_volumes}
    old_volumes = {v.name: v for v in baseline.volumes} if baseline else {}
    volumes = []
    names = set()
    removed = {name.lower() for name in originals} - {v.name.lower() for v in scene.volumes}
    for volume in scene.volumes:
        key = volume.name.lower()
        if not key.strip() or key in names:
            raise ValueError("Volume names must be nonempty and unique, ignoring case")
        names.add(key)
        original = originals.get(volume.name, {})
        if not original and key in _BUILTIN_PARENTS:
            raise ValueError(f"{volume.name} is reserved for a built-in parent")
        parent = volume.parent.lower()
        if parent in removed and parent not in _BUILTIN_PARENTS:
            raise ValueError(f"Remove child volume {volume.name} before removing its parent {volume.parent}")
        if volume == old_volumes.get(volume.name) and original:
            volumes.append(deepcopy(original))
            continue
        entry = deepcopy(original)
        placement = deepcopy(entry.get("placement", {}))
        placement.update(positionMm=_vector(volume.position_mm, "volume position"),
                         rotationDeg=_vector(volume.rotation_deg, "volume rotation"))
        if volume.parent or "parent" in placement:
            placement["parent"] = volume.parent
        entry.update(name=volume.name, material=volume.material, scoreEdep=volume.score_edep,
                     tags=list(volume.tags), shape=_shape(volume.shape),
                     placement=placement)
        volumes.append(entry)
    if volumes or "geometry" in config:
        config.setdefault("geometry", {})["volumes"] = _order_volumes(volumes)

    originals = {m["name"].lower(): m for m in config.get("materials", [])}
    old_materials = {m.name.lower(): m for m in baseline.materials} if baseline else {}
    materials = []
    names = set()
    declared: List[str] = []  # authored materials before this one (engine build order)
    for material in scene.materials:
        key = material.name.lower()
        if not key or key in names:
            raise ValueError("Material names must be nonempty and unique")
        names.add(key)
        old = old_materials.get(key)
        original = originals.get(key)
        if original is None and old is not None:
            # Derived optics can create lookup aliases that are not authored materials.
            if material != old:
                raise ValueError(f"{material.name} is derived appearance, not an authored material")
            continue
        if not material.authored:
            raise ValueError(f"{material.name} is derived appearance, not an authored material")
        entry = deepcopy(original) if original is not None else {"name": material.name}
        changed = old is None or any(getattr(material, attr) != getattr(old, attr)
                                     for attr in ("density_gcm3", "smiles", "components"))
        for attr, field in (("density_gcm3", "densityGcm3"), ("smiles", "smiles"),
                            ("components", "components")):
            value = getattr(material, attr)
            if old is None or value != getattr(old, attr):
                if attr == "smiles" and not value and field not in entry:
                    continue  # an empty SMILES is the engine default; keep new entries minimal
                entry[field] = deepcopy(value)
        if changed:
            # A new or edited custom material must be one the engine builds as declared. Check
            # the written entry: unchanged fields keep the recorded (lossless) config values.
            validate_material(material.name, entry.get("densityGcm3", 0.0), entry.get("components", []),
                              earlier=declared, new=original is None)
        declared.append(material.name)
        materials.append(entry)
    for key, old in old_materials.items():
        if key not in names and key in originals:
            uses = material_references(old.name, world=scene.world_material,
                                       medium=scene.medium_material if scene.medium_size_mm else None,
                                       volumes=scene.volumes, materials=scene.materials)
            if uses:
                raise ValueError(f"Material {old.name} is still used by {', '.join(uses)}")
    # A partial/older viz snapshot may omit unused canonical materials. Their
    # absence from the editable model is not an authored deletion.
    materials.extend(deepcopy(value) for key, value in originals.items()
                     if key not in old_materials and key not in names)
    if materials or "materials" in config:
        config["materials"] = materials

    old_beams = baseline.beams if baseline else []
    original_beams = config.get("beams") or ([config["beam"]] if "beam" in config else [])
    original_names = [b.get("name", "") for b in original_beams]
    named_sources = bool(original_names) and all(original_names) and len(set(original_names)) == len(original_names)
    if baseline and len(old_beams) > 1 and not named_sources and scene.beams != old_beams:
        raise ValueError("Name every beam in the original scenario before editing ambiguous sources")
    if baseline and len(old_beams) == 1 and not named_sources:
        if len(scene.beams) != 1 or scene.beams[0].name != old_beams[0].name:
            raise ValueError("Change beam identities in the original scenario before exporting")
    named_indexes = {name: i for i, name in enumerate(original_names)} if named_sources else {}
    beams = []
    mapped_indexes = {}
    names = set()
    for i, beam in enumerate(scene.beams):
        if named_sources:
            if beam.name in names or (baseline and beam.name not in named_indexes):
                raise ValueError("Change beam identities in the original scenario before exporting")
            names.add(beam.name)
            old_index = named_indexes.get(beam.name)
        else:
            old_index = i if i < len(original_beams) else None
        original = original_beams[old_index] if old_index is not None else {}
        old = old_beams[old_index] if old_index is not None and old_index < len(old_beams) else None
        if old_index is not None:
            mapped_indexes[old_index] = i
        if beam == old and original:
            beams.append(deepcopy(original))
        else:
            beams.append(_beam(beam, original, old))
    if beams:
        if "beams" in config or len(beams) > 1:
            config["beams"] = beams
        # The primary config may be independent of the named display beams. Only
        # update its matching original; never guess away an unrepresented source.
        primary = config.get("beam")
        matches = [i for i, old in enumerate(original_beams) if old == primary]
        if matches:
            if matches[0] not in mapped_indexes:
                raise ValueError("Choose a new primary beam in the original scenario before removing this source")
            config["beam"] = deepcopy(beams[mapped_indexes[matches[0]]])
        elif primary is None:
            config["beam"] = deepcopy(next((b for b in beams if b.get("active")), beams[0]))
    elif original_beams:
        raise ValueError("A transport scene must retain at least one beam")

    for attr, key in (("n_events", "nEvents"), ("seed", "seed")):
        value = getattr(scene.run, attr)
        if not isinstance(value, int) or isinstance(value, bool) or value < 0:
            raise ValueError(f"{key} must be a nonnegative integer")
        if baseline is None or value != getattr(baseline.run, attr):
            config.setdefault("run", {})[key] = value
    if scene.run.determinism_mode not in ("strict", "predictive"):
        raise ValueError("determinism mode must be strict or predictive")
    if baseline is None or scene.run.determinism_mode != baseline.run.determinism_mode:
        config.setdefault("determinism", {})["mode"] = scene.run.determinism_mode
    # Reject nonfinite numbers anywhere, including opaque preserved fields.
    json.dumps(config, allow_nan=False)
    return config


def scene_to_js(scene: SceneModel, base_config: Optional[Dict] = None) -> str:
    """Return deterministic, reviewable standalone JS for a transport scene draft."""
    return _config_to_js(scene_to_config(scene, base_config))


def scene_to_bundle(scene: SceneModel, base_config: Optional[Dict], *,
                    artifacts: Optional[Dict], search_dirs: Sequence[Path],
                    dependency_dir: str = DEFAULT_DEPENDENCY_DIR) -> SceneBundle:
    """Return the scenario JS plus the model files it needs, for a multi-file export.

    ``artifacts`` is the run's ``model_artifacts`` manifest; each dependency is found under
    ``search_dirs`` by its declared path and must match the SHA-256 recorded there. Paths in
    the JS point into ``dependency_dir`` beside the scenario, where the engine resolves them.
    A scene without dependencies yields exactly ``scene_to_js`` and no files.
    """
    config = scene_to_config(scene, base_config, allow_dependencies=True)
    packaged, files = package_dependencies(config, artifacts, search_dirs, dependency_dir)
    return SceneBundle(source=_config_to_js(packaged), files=files)


def _config_to_js(config: Dict) -> str:

    def check_js_value(value):
        if isinstance(value, dict):
            if "__proto__" in value:
                raise ValueError("Cannot export __proto__ fields as a JS object literal")
            for item in value.values():
                check_js_value(item)
        elif isinstance(value, list):
            for item in value:
                check_js_value(item)
        elif isinstance(value, int) and abs(value) > 2 ** 53 - 1:
            raise ValueError("An integer exceeds JavaScript's exact numeric range")

    check_js_value(config)
    return ("// TRECH Studio transport scene draft. Run with: trech run <this-file.js>\n"
            "// Geometry/config export; recorded results and derived appearance are not authored physics.\n"
            "globalThis.TRECH_CONFIG = " + json.dumps(config, indent=2, ensure_ascii=True, allow_nan=False) + ";\n")
