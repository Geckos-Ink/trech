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

from . import appearance as _appearance
from .appearance import MaterialAppearance, OpticSample

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
    mean_scatter_length_mm: Optional[float] = None
    spectrum: List[OpticSample] = field(default_factory=list)  # visible-band samples
    optics_available: bool = False

    def appearance(self, path_mm: float = 10.0) -> MaterialAppearance:
        """Derive this material's look for a body of thickness ``path_mm`` (a physics read)."""
        return _appearance.derive_appearance(
            refractive_index=self.mean_refractive_index,
            absorption_length_mm=self.mean_absorption_length_mm,
            scatter_length_mm=self.mean_scatter_length_mm,
            spectrum=self.spectrum,
            path_mm=path_mm,
            optics_available=self.optics_available,
        )


def _parse_color(text: str) -> Optional[Vec3]:
    """Parse ``#rgb`` / ``#rrggbb`` / ``r,g,b`` (0..1 floats or 0..255 ints) into an RGB triple."""
    text = text.strip()
    if text.startswith("#"):
        hexs = text[1:]
        if len(hexs) == 3:
            hexs = "".join(c * 2 for c in hexs)
        if len(hexs) == 6:
            try:
                return tuple(int(hexs[i:i + 2], 16) / 255.0 for i in (0, 2, 4))  # type: ignore[return-value]
            except ValueError:
                return None
        return None
    parts = [p for p in text.replace(" ", "").split(",") if p]
    if len(parts) == 3:
        try:
            vals = [float(p) for p in parts]
        except ValueError:
            return None
        if any(v > 1.0 for v in vals):
            vals = [v / 255.0 for v in vals]
        return (max(0.0, min(1.0, vals[0])), max(0.0, min(1.0, vals[1])), max(0.0, min(1.0, vals[2])))
    return None


@dataclass
class RenderHint:
    """An *authored* rendering override a scenario attaches via ``viz_*`` volume tags.

    These are rendering choices, never physics: a scenario can make a volume more legible
    (bump opacity, tint it, hide it, make it glow) without changing what the engine simulated.
    Studio labels anything driven by a hint as authored (see the inspector). Recognised tags::

        viz_hidden              do not draw this volume
        viz_solid               force an opaque body (alpha ~1)
        viz_emissive|viz_glow   render as self-lit (ignores shading), for beacons/collectors
        viz_opacity=<0..1>      force display alpha
        viz_color=<colour>      replace the base colour  (#rgb, #rrggbb, or r,g,b)
        viz_tint=<colour>       multiply the derived colour by this tint
    """

    hidden: bool = False
    solid: bool = False
    emissive: bool = False
    opacity: Optional[float] = None
    color: Optional[Vec3] = None
    tint: Optional[Vec3] = None

    @property
    def is_empty(self) -> bool:
        return not (self.hidden or self.solid or self.emissive
                    or self.opacity is not None or self.color is not None or self.tint is not None)

    @classmethod
    def from_tags(cls, tags: List[str]) -> "RenderHint":
        hint = cls()
        for raw in tags:
            tag = str(raw).strip()
            low = tag.lower()
            key, _, value = tag.partition("=")
            key = key.strip().lower()
            value = value.strip()
            if low in ("viz_hidden", "viz_hide"):
                hint.hidden = True
            elif low == "viz_solid":
                hint.solid = True
            elif low in ("viz_emissive", "viz_glow"):
                hint.emissive = True
            elif key == "viz_opacity" and value:
                try:
                    hint.opacity = max(0.0, min(1.0, float(value)))
                except ValueError:
                    pass
            elif key == "viz_color" and value:
                hint.color = _parse_color(value)
            elif key == "viz_tint" and value:
                hint.tint = _parse_color(value)
        return hint


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

    def render_hint(self) -> RenderHint:
        return RenderHint.from_tags(self.tags)

    @property
    def is_hidden(self) -> bool:
        return self.render_hint().hidden

    def path_length_mm(self) -> float:
        """Characteristic thickness a photon crosses through this volume (for Beer–Lambert).

        A rough single number: the mean positive box extent, or the diameter of a
        round shape. Used only to scale the *look's* transparency, never physics.
        """
        s = self.shape
        extents = [e for e in s.size_mm if e > 0.0]
        if extents:
            return float(sum(extents) / len(extents))
        if s.outer_radius_mm > 0.0:
            return float(2.0 * s.outer_radius_mm)
        if s.length_mm > 0.0:
            return float(s.length_mm)
        return 10.0

    def half_extent_mm(self) -> Vec3:
        """Half-extent of this volume's local AABB (before placement), for camera fitting.

        Matches ``render.mesh.for_shape``: box uses half its size; sphere is its radius on
        every axis; a tube/cylinder is (radius, radius, half-length) about its +Z axis.
        """
        s = self.shape
        t = (s.type or "box").lower()
        if t == "sphere":
            r = s.outer_radius_mm or (max(s.size_mm) * 0.5) or 1.0
            return (r, r, r)
        if t in ("tube", "cylinder"):
            r = s.outer_radius_mm or 1.0
            hz = (s.length_mm or max(s.size_mm) or 1.0) * 0.5
            return (r, r, hz)
        size = s.size_mm if any(s.size_mm) else (10.0, 10.0, 10.0)
        return (size[0] * 0.5, size[1] * 0.5, size[2] * 0.5)


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

    def volume_appearance(self, vol: VolumeNode) -> Optional[MaterialAppearance]:
        """The physics-derived look for ``vol`` (or None if the material has no derived optics)."""
        mat = self.material_by_name(vol.material)
        if mat is None or not mat.optics_available:
            return None
        return mat.appearance(path_mm=vol.path_length_mm())

    def volume_color(self, vol: VolumeNode, fallback: RGBA = (0.6, 0.62, 0.66, 1.0)) -> RGBA:
        """RGBA a volume should render with (colour, alpha), before surface params.

        Order of precedence: an authored ``viz_*`` render hint wins where it speaks; then the
        material's **physics-derived** appearance (colour from the transmission spectrum,
        opacity from Beer–Lambert over the volume thickness, per ``scene.appearance``); then
        the engine's ``viz_forced_white``/``viz_emitter`` tags; then a neutral fallback.
        """
        hint = vol.render_hint()

        # 1) Physics-derived base look (None when no optics were derived this run).
        appear = self.volume_appearance(vol)
        if appear is not None:
            r, g, b, a = appear.rgba()
        else:
            r, g, b, a = fallback

        # 2) Engine viz tags (viz_forced_white / viz_emitter) are themselves an authored intent:
        #    a bright, opaque marker. They override the physics-derived transparency.
        if vol.forced_white or vol.is_emitter:
            r, g, b, a = 1.0, 1.0, 1.0, 1.0

        # 3) Scenario viz_* render hints win last (highest precedence, labelled as authored).
        if hint.color is not None:
            r, g, b = hint.color
        if hint.tint is not None:
            r, g, b = r * hint.tint[0], g * hint.tint[1], b * hint.tint[2]
        if hint.opacity is not None:
            a = hint.opacity
        if hint.solid:
            a = max(a, 0.95)
        return (float(r), float(g), float(b), float(a))

    def volume_surface(self, vol: VolumeNode) -> Tuple[RGBA, Tuple[float, float, float, float]]:
        """(rgba, params) for the renderer. ``params`` = (reflectance R0, gloss, emissive, _).

        ``reflectance``/``gloss`` come from the derived refractive index (Fresnel) so glass and
        water get a specular highlight; ``emissive`` flags a self-lit body (emitter tag or a
        ``viz_emissive`` hint) that skips shading.
        """
        rgba = self.volume_color(vol)
        hint = vol.render_hint()
        appear = self.volume_appearance(vol)
        reflectance = appear.reflectance if appear is not None else 0.0
        gloss = appear.gloss if appear is not None else 0.0
        emissive = 1.0 if (hint.emissive or vol.is_emitter or vol.forced_white) else 0.0
        return rgba, (float(reflectance), float(gloss), float(emissive), 0.0)

    def bounds_mm(self) -> Tuple[Vec3, Vec3]:
        """Axis-aligned bounds for camera fitting.

        Fits the **placed, visible volumes** (their local AABB offset by position) so the
        subject fills the frame — the earlier behaviour fit the whole world box, which left the
        actual geometry tiny in a sea of grid. Rotation is treated as axis-aligned (a small
        framing margin, not physics); the world box is the fallback when a scene has no volumes.
        """
        drawn = [v for v in self.volumes if not v.is_hidden]
        if not drawn:
            half = self.world_size_mm * 0.5
            return ((-half, -half, -half), (half, half, half))
        lo = [float("inf"), float("inf"), float("inf")]
        hi = [float("-inf"), float("-inf"), float("-inf")]
        for v in drawn:
            he = v.half_extent_mm()
            for i in range(3):
                lo[i] = min(lo[i], v.position_mm[i] - he[i])
                hi[i] = max(hi[i], v.position_mm[i] + he[i])
        return ((lo[0], lo[1], lo[2]), (hi[0], hi[1], hi[2]))
