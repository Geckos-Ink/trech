"""Scene manifest parsing.

The scene JSON layout is intentionally close to the engine config (boxes,
volumes, beams, materials) plus a `derived_optics` block that carries the
per-material refractive index / absorption / scatter samples that TRECH
computed from Geant4 atomic cross sections (Kramers-Kronig on the
photoelectric + Compton + Rayleigh extinction spectrum).
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple


@dataclass
class Volume:
    name: str
    material: str
    parent: str
    position_mm: Tuple[float, float, float]
    rotation_deg: Tuple[float, float, float]
    shape_type: str
    size_mm: Tuple[float, float, float]
    outer_radius_mm: float
    inner_radius_mm: float
    length_mm: float
    tags: List[str] = field(default_factory=list)


@dataclass
class DerivedSample:
    energy_ev: float
    wavelength_nm: float
    refractive_index: float
    absorption_length_mm: float
    scatter_length_mm: float


@dataclass
class DerivedMaterial:
    material_name: str
    config_material_key: str
    density_gcm3: float
    mean_refractive_index: float
    mean_absorption_length_mm: float
    mean_scatter_length_mm: float
    display_rgb: Tuple[float, float, float]
    samples: List[DerivedSample]
    available: bool = True
    note: str = ""


@dataclass
class Beam:
    name: str
    particle: str
    energy_ev: float
    direction: Tuple[float, float, float]


@dataclass
class Scene:
    seed: int
    n_events: int
    world_size_mm: float
    world_material: str
    medium_size_mm: float
    medium_material: str
    volumes: List[Volume]
    materials: List[Dict]
    derived_materials: List[DerivedMaterial]
    beams: List[Beam]
    viz: Dict
    raw: Dict

    def derived_by_name(self) -> Dict[str, DerivedMaterial]:
        out: Dict[str, DerivedMaterial] = {}
        for d in self.derived_materials:
            keys = {d.material_name, d.config_material_key}
            for key in keys:
                if key:
                    out[key.lower()] = d
        return out


def _as_triplet(values: Sequence[float], default: float = 0.0) -> Tuple[float, float, float]:
    arr = list(values or ())
    while len(arr) < 3:
        arr.append(default)
    return float(arr[0]), float(arr[1]), float(arr[2])


def _parse_volume(raw: Dict) -> Volume:
    shape = raw.get("shape") or {}
    return Volume(
        name=str(raw.get("name") or ""),
        material=str(raw.get("material") or ""),
        parent=str(raw.get("parent") or ""),
        position_mm=_as_triplet(raw.get("position_mm") or ()),
        rotation_deg=_as_triplet(raw.get("rotation_deg") or ()),
        shape_type=str(shape.get("type") or "box"),
        size_mm=_as_triplet(shape.get("size_mm") or ()),
        outer_radius_mm=float(shape.get("outer_radius_mm") or 0.0),
        inner_radius_mm=float(shape.get("inner_radius_mm") or 0.0),
        length_mm=float(shape.get("length_mm") or 0.0),
        tags=list(raw.get("tags") or []),
    )


def _parse_derived(raw: Dict) -> DerivedMaterial:
    samples = []
    for sraw in raw.get("samples") or []:
        samples.append(
            DerivedSample(
                energy_ev=float(sraw.get("energy_ev") or 0.0),
                wavelength_nm=float(sraw.get("wavelength_nm") or 0.0),
                refractive_index=float(sraw.get("refractive_index") or 1.0),
                absorption_length_mm=float(sraw.get("absorption_length_mm") or 0.0),
                scatter_length_mm=float(sraw.get("scatter_length_mm") or 0.0),
            )
        )
    rgb = raw.get("display_rgb") or [1.0, 1.0, 1.0]
    rgb_triplet = _as_triplet(rgb, default=1.0)
    return DerivedMaterial(
        material_name=str(raw.get("material_name") or ""),
        config_material_key=str(raw.get("config_material_key") or ""),
        density_gcm3=float(raw.get("density_gcm3") or 0.0),
        mean_refractive_index=float(raw.get("mean_refractive_index") or 1.0),
        mean_absorption_length_mm=float(raw.get("mean_absorption_length_mm") or 0.0),
        mean_scatter_length_mm=float(raw.get("mean_scatter_length_mm") or 0.0),
        display_rgb=rgb_triplet,
        samples=samples,
        available=bool(raw.get("available", True)),
        note=str(raw.get("note") or ""),
    )


def _parse_beam(raw: Dict) -> Beam:
    return Beam(
        name=str(raw.get("name") or ""),
        particle=str(raw.get("particle") or ""),
        energy_ev=float(raw.get("energy_ev") or 0.0),
        direction=_as_triplet(raw.get("direction") or (0.0, 0.0, 1.0)),
    )


def load_scene(path: str | Path) -> Scene:
    with open(path, "r", encoding="utf-8") as fh:
        raw = json.load(fh)
    world = raw.get("world") or {}
    medium = raw.get("medium") or {}
    volumes = [_parse_volume(v) for v in raw.get("volumes") or []]
    derived = [_parse_derived(d) for d in raw.get("derived_optics") or []]
    beams = [_parse_beam(b) for b in raw.get("beams") or []]
    return Scene(
        seed=int(raw.get("seed") or 0),
        n_events=int(raw.get("n_events") or 0),
        world_size_mm=float(world.get("size_mm") or 0.0),
        world_material=str(world.get("material") or ""),
        medium_size_mm=float(medium.get("size_mm") or 0.0),
        medium_material=str(medium.get("material") or ""),
        volumes=volumes,
        materials=list(raw.get("materials") or []),
        derived_materials=derived,
        beams=beams,
        viz=dict(raw.get("viz") or {}),
        raw=raw,
    )
