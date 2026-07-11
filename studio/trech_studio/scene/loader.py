"""Build a ``SceneModel`` from engine outputs.

The forward direction (engine output -> editable model) is what Studio needs to *view* runs.
The reverse (``SceneModel`` -> runnable ``.js``) is ROADMAP M2 and deliberately not here yet;
Studio edits scenario ``.js`` text directly until that writer exists.

Parsing mirrors ``tools/viz/trech_viz/scene.py`` so the two viewers stay in agreement.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, List, Optional, Sequence

from .model import Beam, MaterialDef, RunParams, SceneModel, Shape, Vec3, VolumeNode


def _triplet(values: Optional[Sequence[float]], default: float = 0.0) -> Vec3:
    arr = list(values or ())
    while len(arr) < 3:
        arr.append(default)
    return (float(arr[0]), float(arr[1]), float(arr[2]))


def _parse_shape(raw: Dict) -> Shape:
    shape = raw.get("shape") or {}
    return Shape(
        type=str(shape.get("type") or "box"),
        size_mm=_triplet(shape.get("size_mm")),
        outer_radius_mm=float(shape.get("outer_radius_mm") or 0.0),
        inner_radius_mm=float(shape.get("inner_radius_mm") or 0.0),
        length_mm=float(shape.get("length_mm") or 0.0),
    )


def _parse_volume(raw: Dict) -> VolumeNode:
    return VolumeNode(
        name=str(raw.get("name") or ""),
        material=str(raw.get("material") or ""),
        parent=str(raw.get("parent") or ""),
        position_mm=_triplet(raw.get("position_mm")),
        rotation_deg=_triplet(raw.get("rotation_deg")),
        shape=_parse_shape(raw),
        tags=list(raw.get("tags") or []),
        score_edep=bool(raw.get("score_edep", False)),
    )


def _parse_materials(raw: Dict) -> List[MaterialDef]:
    """Merge config-level ``materials`` with per-material ``derived_optics``."""
    materials: Dict[str, MaterialDef] = {}
    for m in raw.get("materials") or []:
        name = str(m.get("name") or "")
        if not name:
            continue
        materials[name.lower()] = MaterialDef(
            name=name,
            density_gcm3=float(m.get("density_gcm3") or 0.0),
            smiles=str(m.get("smiles") or ""),
            components=list(m.get("components") or []),
        )

    for d in raw.get("derived_optics") or []:
        rgb = d.get("display_rgb") or [1.0, 1.0, 1.0]
        for key in (d.get("material_name"), d.get("config_material_key")):
            if not key:
                continue
            mat = materials.get(str(key).lower())
            if mat is None:
                mat = MaterialDef(name=str(key), density_gcm3=float(d.get("density_gcm3") or 0.0))
                materials[str(key).lower()] = mat
            mat.display_rgb = _triplet(rgb, default=1.0)
            mat.mean_refractive_index = float(d.get("mean_refractive_index") or 1.0)
            mat.mean_absorption_length_mm = float(d.get("mean_absorption_length_mm") or 0.0)
            mat.optics_available = bool(d.get("available", True))
    return list(materials.values())


def _parse_beams(raw: Dict) -> List[Beam]:
    beams = []
    for b in raw.get("beams") or []:
        beams.append(
            Beam(
                name=str(b.get("name") or ""),
                particle=str(b.get("particle") or ""),
                energy_ev=float(b.get("energy_ev") or 0.0),
                direction=_triplet(b.get("direction"), default=0.0),
                active=bool(b.get("active", False)),
            )
        )
    return beams


def scene_from_viz_json(path: Path) -> SceneModel:
    """Parse a ``trech_viz_scene.json`` into an editable ``SceneModel``."""
    path = Path(path)
    with path.open("r", encoding="utf-8") as fh:
        raw = json.load(fh)

    world = raw.get("world") or {}
    medium = raw.get("medium") or {}

    return SceneModel(
        world_size_mm=float(world.get("size_mm") or 100.0),
        world_material=str(world.get("material") or "G4_AIR"),
        medium_size_mm=float(medium.get("size_mm") or 0.0),
        medium_material=str(medium.get("material") or ""),
        volumes=[_parse_volume(v) for v in raw.get("volumes") or []],
        materials=_parse_materials(raw),
        beams=_parse_beams(raw),
        run=RunParams(
            n_events=int(raw.get("n_events") or 0),
            seed=int(raw.get("seed") or 0),
            determinism_mode=str(raw.get("determinism_mode") or "strict"),
        ),
        source_path=str(path),
        raw=raw,
    )


def scene_from_output_dir(output_dir: Path) -> Optional[SceneModel]:
    """Convenience: load the viz scene from a run output directory, if present."""
    viz = Path(output_dir) / "trech_viz_scene.json"
    if not viz.is_file():
        return None
    return scene_from_viz_json(viz)


def placeholder_scene() -> SceneModel:
    """A tiny built-in scene so the viewport shows *something* before a run is loaded.

    Explicitly a rendering placeholder (labelled as such in the outliner), not a simulation:
    a world box with a single centred medium cube.
    """
    scene = SceneModel(world_size_mm=120.0, world_material="G4_AIR")
    scene.volumes.append(
        VolumeNode(
            name="medium (placeholder)",
            material="G4_WATER",
            shape=Shape(type="box", size_mm=(60.0, 60.0, 60.0)),
            tags=["placeholder"],
        )
    )
    scene.materials.append(MaterialDef(name="G4_WATER", density_gcm3=1.0))
    scene.source_path = None
    return scene
