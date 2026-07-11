"""The editable scenario model.

Kept intentionally close to the engine config / viz-scene layout (world, volumes, materials,
beams) so the mapping to and from ``trech_viz_scene.json`` is mechanical. Units are
millimetres and degrees throughout, matching the engine's viz schema.

Display colour/opacity come from the run's ``derived_optics`` (the same channel the PyVista
viewer in ``tools/viz/`` uses) so Studio and that viewer agree on how a material looks — and
so the look is *derived from the physics*, never invented here.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

Vec3 = Tuple[float, float, float]
RGBA = Tuple[float, float, float, float]


@dataclass
class Shape:
    """Geometric primitive of a volume (mirrors viz_scene ``shape``)."""

    type: str = "box"                       # box | sphere | tube | cylinder
    size_mm: Vec3 = (0.0, 0.0, 0.0)         # full extents for box
    outer_radius_mm: float = 0.0
    inner_radius_mm: float = 0.0
    length_mm: float = 0.0


@dataclass
class MaterialDef:
    """Config-level material composition + its derived optical look (if the run derived one)."""

    name: str
    density_gcm3: float = 0.0
    smiles: str = ""
    components: List[Dict] = field(default_factory=list)
    # Derived (never authored) — filled from derived_optics when present.
    display_rgb: Optional[Vec3] = None
    mean_refractive_index: Optional[float] = None
    mean_absorption_length_mm: Optional[float] = None
    optics_available: bool = False


@dataclass
class VolumeNode:
    """One placed volume in the scene tree."""

    name: str
    material: str
    parent: str = ""
    position_mm: Vec3 = (0.0, 0.0, 0.0)
    rotation_deg: Vec3 = (0.0, 0.0, 0.0)
    shape: Shape = field(default_factory=Shape)
    tags: List[str] = field(default_factory=list)
    score_edep: bool = False

    @property
    def is_emitter(self) -> bool:
        return "viz_emitter" in self.tags

    @property
    def forced_white(self) -> bool:
        return "viz_forced_white" in self.tags


@dataclass
class Beam:
    name: str
    particle: str
    energy_ev: float = 0.0
    direction: Vec3 = (0.0, 0.0, 1.0)
    active: bool = False


@dataclass
class RunParams:
    n_events: int = 0
    seed: int = 0
    determinism_mode: str = "strict"


@dataclass
class SceneModel:
    """Studio's editable in-memory scenario. The single source of truth for the viewport."""

    world_size_mm: float = 100.0
    world_material: str = "G4_AIR"
    medium_size_mm: float = 0.0
    medium_material: str = ""

    volumes: List[VolumeNode] = field(default_factory=list)
    materials: List[MaterialDef] = field(default_factory=list)
    beams: List[Beam] = field(default_factory=list)
    run: RunParams = field(default_factory=RunParams)

    # Provenance of where this model came from (a viz scene, an output dir, or authored).
    source_path: Optional[str] = None
    raw: Dict = field(default_factory=dict)

    # --- lookups ------------------------------------------------------------------------

    def material_by_name(self, name: str) -> Optional[MaterialDef]:
        key = (name or "").lower()
        for m in self.materials:
            if m.name.lower() == key:
                return m
        return None

    def volume_by_name(self, name: str) -> Optional[VolumeNode]:
        for v in self.volumes:
            if v.name == name:
                return v
        return None

    # --- display helpers (rendering choices, not physics) --------------------------------

    def volume_color(self, vol: VolumeNode, fallback: RGBA = (0.6, 0.62, 0.66, 1.0)) -> RGBA:
        """RGBA a volume should render with.

        Emitters and ``viz_forced_white`` volumes get a forced look (a *viz choice*, per the
        engine's own tag semantics). Everything else takes colour from its material's derived
        optics; opacity from the derived refractive index (higher n -> more solid-looking),
        clamped so nothing disappears. When no optics were derived, use the neutral fallback.
        """
        if vol.forced_white or vol.is_emitter:
            return (1.0, 1.0, 1.0, 1.0)
        mat = self.material_by_name(vol.material)
        if mat is None or not mat.optics_available or mat.display_rgb is None:
            return fallback
        r, g, b = mat.display_rgb
        n = mat.mean_refractive_index or 1.0
        # Map n in ~[1.0, 1.6] to alpha in [0.35, 0.9]; transparent media stay see-through.
        alpha = max(0.35, min(0.9, 0.35 + (n - 1.0) * 0.9))
        return (float(r), float(g), float(b), float(alpha))

    def bounds_mm(self) -> Tuple[Vec3, Vec3]:
        """Axis-aligned world bounds for camera fitting (half the world box by default)."""
        half = self.world_size_mm * 0.5
        return ((-half, -half, -half), (half, half, half))
