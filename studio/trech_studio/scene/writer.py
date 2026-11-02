"""Serialize a transport scene draft, preserving physics absent from the viz schema.

This is data authoring only. Recorded spectra/appearance are never converted to physics.
Loaded scenes require their canonical config; callback source cannot be recovered from it.
"""

from __future__ import annotations

from copy import deepcopy
import json
import math
from typing import Dict, Optional

from .loader import scene_from_viz_data
from .model import Beam, SceneModel, Shape, VolumeNode


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


def _beam(beam: Beam, base: Dict) -> Dict:
    result = deepcopy(base)
    result.update(particle=beam.particle, energyMeV=_number(beam.energy_ev, "beam energy", positive=True) / 1e6,
                  direction=_vector(beam.direction, "beam direction"))
    if beam.active or "active" in result:
        result["active"] = beam.active
    if not any(result["direction"]):
        raise ValueError("beam direction must be nonzero")
    if beam.name:
        result["name"] = beam.name
    else:
        result.pop("name", None)
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


def scene_to_config(scene: SceneModel, base_config: Optional[Dict] = None) -> Dict:
    """Return a detached config containing the scene's authored edits.

    A loaded scene needs its complete provenance config. Unchanged fields retain the exact
    canonical values (including eV/MeV rounding, isotope composition and source spread).
    Registered callbacks and external model dependencies are rejected rather than dropped.
    New scenes without ``raw`` can use engine defaults for unrepresented config fields.
    """
    if (scene.raw or scene.source_path) and base_config is None:
        raise ValueError("Loaded scenes need the full recorded config; viz geometry alone is incomplete")
    config = deepcopy(base_config) if base_config is not None else {}
    if not isinstance(config, dict):
        raise ValueError("The recorded config must be an object")
    if config.get("hooks", {}).get("registered"):
        raise ValueError("This run uses JS callbacks; edit/save the original scenario to retain its processes")
    if (config.get("models") or config.get("stratify", {}).get("modelPath")
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

    originals = {v["name"]: v for v in config.get("geometry", {}).get("volumes", [])}
    old_volumes = {v.name: v for v in baseline.volumes} if baseline else {}
    volumes = []
    names = set()
    for volume in scene.volumes:
        if not volume.name or volume.name in names:
            raise ValueError("Volume names must be nonempty and unique")
        names.add(volume.name)
        original = originals.get(volume.name, {})
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
        config.setdefault("geometry", {})["volumes"] = volumes

    originals = {m["name"].lower(): m for m in config.get("materials", [])}
    old_materials = {m.name.lower(): m for m in baseline.materials} if baseline else {}
    materials = []
    names = set()
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
        entry = deepcopy(original) if original is not None else {"name": material.name}
        for attr, field in (("density_gcm3", "densityGcm3"), ("smiles", "smiles"),
                            ("components", "components")):
            value = getattr(material, attr)
            if old is None or value != getattr(old, attr):
                if attr == "density_gcm3":
                    _number(value, "material density")
                    if value < 0:
                        raise ValueError("material density must be nonnegative")
                if attr == "components" and any(not (c.get("material") or c.get("element")) for c in value):
                    raise ValueError("Material components need an explicit material or element")
                entry[field] = deepcopy(value)
        materials.append(entry)
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
            beams.append(_beam(beam, original))
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
    config = scene_to_config(scene, base_config)

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
