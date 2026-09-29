"""Readable 3D replay of recorded Geant4 trajectories.

Everything drawn from the run is taken verbatim from ``trech_viz_trajectories.jsonl``: recorded
points, Geant4 step times, kinetic energies, the process that ended each step, and (for optical
photons) the ``G4OpBoundaryProcess`` outcome. What this module adds is *legibility*:

* **fading trails** — each recorded point dims with playback age, so one photon's many
  reflections read as a history instead of a tangle;
* **history colouring** — a primary photon is bright before its first discrete interaction and
  turns orange once scattered; vertices are marked by the recorded process (photoelectric
  absorption, Compton, Rayleigh, neutron reaction, radioactive decay) and flash when they occur;
* **nuclide glyphs + reaction labels** — ions are drawn as labelled nuclei and a reaction vertex
  is labelled from the recorded products (``n + ¹⁴N → ¹⁴C + p``, the target inferred from baryon /
  charge conservation of what Geant4 produced);
* **bundled optical rays** (opt-in) — photons sharing a wavelength band and the same recorded
  boundary history are drawn as one mean path whose width grows with the count; segments after a
  recorded reflection are drawn faint, refracted segments solid;
* **composition glyphs** (opt-in) — sparse ball-and-stick molecules showing what each Geant4
  material is made of. They are a *representation* (not to scale, not transported) and the
  legend says so.

Side-by-side comparison of two runs, a caption, and chart panels (``charts.py``) complete the
frame. Nothing here moves a recorded point or invents a track.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np

from .animate import (
    DISPLAY_NAMES, HUD_COLOR, _Turntable, _hud, _legend, _merge_bounds, _new_plotter,
    _screenshot, activity_clock, text_kwargs, boxed, draw_caption, energy_colors, format_clock, species_color, species_label,
    write_gif,
)
from .charts import ChartPanel, compose
from .scene import Scene
from .trajectories import Trajectory, visible_rgb_for_wavelength, wavelength_nm_for_energy_ev

BG_RGB = np.array([0.035, 0.045, 0.075], dtype=np.float32)
UNCOLLIDED_RGB = (1.0, 0.86, 0.3)
SCATTERED_RGB = (1.0, 0.5, 0.16)
VERTEX_STYLE = {
    # recorded process -> (colour, legend label)
    "phot": ("#ff4040", "photoelectric absorption"),
    "compt": ("#ffffff", "Compton scatter"),
    "Rayl": ("#8fd0ff", "Rayleigh scatter"),
    "conv": ("#ff9cf0", "pair production"),
    "neutronInelastic": ("#ff5cf2", "neutron reaction"),
    "nCaptureHP": ("#ff5cf2", "neutron capture"),
    "nCapture": ("#ff5cf2", "neutron capture"),
    "RadioactiveDecay": ("#5dff8a", "radioactive decay"),
    "hadElastic": ("#9aa4b8", "elastic recoil"),
    "neutronElastic": ("#9aa4b8", "elastic recoil"),
}

_ELEMENTS = ["n", "H", "He", "Li", "Be", "B", "C", "N", "O", "F", "Ne", "Na", "Mg", "Al", "Si",
             "P", "S", "Cl", "Ar", "K", "Ca", "Sc", "Ti", "V", "Cr", "Mn", "Fe", "Co", "Ni", "Cu",
             "Zn", "Ga", "Ge", "As", "Se", "Br", "Kr", "Rb", "Sr", "Y", "Zr", "Nb", "Mo", "Tc",
             "Ru", "Rh", "Pd", "Ag", "Cd", "In", "Sn", "Sb", "Te", "I", "Xe"]
_LEPTONS = {"e-": (-1, 0), "e+": (1, 0), "gamma": (0, 0), "anti_nu_e": (0, 0), "nu_e": (0, 0),
            "opticalphoton": (0, 0), "mu-": (-1, 0), "mu+": (1, 0)}
_HADRONS = {"neutron": (0, 1), "proton": (1, 1), "deuteron": (1, 2), "triton": (1, 3),
            "He3": (2, 3), "alpha": (2, 4)}
_SUPERSCRIPT = str.maketrans("0123456789", "⁰¹²³⁴⁵⁶⁷⁸⁹")
NUCLIDE_RGB = {"C": (0.62, 0.62, 0.66), "N": (0.35, 0.55, 1.0), "O": (1.0, 0.3, 0.3),
               "H": (0.95, 0.95, 0.95), "Na": (0.7, 0.45, 1.0), "Cl": (0.35, 0.95, 0.4)}


def nuclide_za(name: str) -> Optional[Tuple[int, int, str]]:
    """(Z, A, symbol) of a Geant4 ion name such as ``C14`` or ``N14[0.000]``."""
    match = re.match(r"^([A-Z][a-z]?)(\d+)", name.strip())
    if not match or match.group(1) not in _ELEMENTS:
        return None
    return _ELEMENTS.index(match.group(1)), int(match.group(2)), match.group(1)


def particle_za(name: str) -> Optional[Tuple[int, int]]:
    if name in _LEPTONS:
        return _LEPTONS[name]
    if name in _HADRONS:
        return _HADRONS[name]
    nuclide = nuclide_za(name)
    return (nuclide[0], nuclide[1]) if nuclide else None


def pretty_particle(name: str) -> str:
    nuclide = nuclide_za(name)
    if nuclide:
        return f"{str(nuclide[1]).translate(_SUPERSCRIPT)}{nuclide[2]}"
    return {"neutron": "n", "proton": "p", "gamma": "γ", "e-": "e⁻", "e+": "e⁺",
            "anti_nu_e": "ν̄", "nu_e": "ν", "alpha": "α"}.get(name, name)


def target_from_conservation(projectile: str, products: Sequence[str]) -> Optional[str]:
    """Nucleus the projectile must have hit for the recorded products to conserve A and Z."""
    proj = particle_za(projectile)
    if proj is None:
        return None
    z = a = 0
    for product in products:
        za = particle_za(product)
        if za is None:
            return None
        z += za[0]
        a += za[1]
    z -= proj[0]
    a -= proj[1]
    if not (0 < z < len(_ELEMENTS)) or a <= 0:
        return None
    return f"{str(a).translate(_SUPERSCRIPT)}{_ELEMENTS[z]}"


# --------------------------------------------------------------------------- tracks


class Track:
    """One recorded trajectory plus the classifications the renderer needs."""

    def __init__(self, traj: Trajectory):
        self.event_id = traj.event_id
        self.track_id = traj.track_id
        self.particle = traj.particle
        self.primary = traj.track_id == 1
        self.points = np.asarray(traj.points, dtype=np.float64)
        times = np.asarray(traj.times_ns, dtype=np.float64)
        self.times = np.maximum.accumulate(times) if times.size else times
        self.energy = np.asarray(traj.energies_ev, dtype=np.float64)
        self.processes = list(traj.processes)
        self.interactions = list(traj.interactions)
        self.volumes = list(traj.volumes)
        self.materials = list(traj.materials)
        self.boundaries = list(traj.boundaries) if traj.boundaries else [""] * len(self.points)
        self.is_ion = species_label(traj.particle) == "ion"
        self.neutral = traj.particle in ("gamma", "neutron", "opticalphoton")
        self.first_hit: Optional[int] = None
        for index in range(1, len(self.interactions)):
            if self.interactions[index] in ("scatter", "interaction"):
                self.first_hit = index
                break
        self.color = species_color(traj.particle, float(self.energy[0]) if self.energy.size else 0)
        self.run = 0
        self.width_scale = 1.0
        self.gamma_beam = True  # history colouring applies when the primaries are photons
        self.product = False    # a reaction-product nucleus (labelled when --nuclides)

    @property
    def end_process(self) -> str:
        return self.processes[-1] if self.processes else ""

    def head(self, t_ns: float) -> Tuple[int, Optional[np.ndarray]]:
        """(number of recorded points reached, interpolated head or None when finished)."""
        if self.points.shape[0] == 0 or t_ns < self.times[0]:
            return 0, None
        k = int(np.searchsorted(self.times, t_ns, side="right"))
        if k >= self.points.shape[0]:
            return self.points.shape[0], None
        t0, t1 = self.times[k - 1], self.times[k]
        fraction = 0.0 if t1 <= t0 else (t_ns - t0) / (t1 - t0)
        return k, self.points[k - 1] + fraction * (self.points[k] - self.points[k - 1])

    def point_colors(self, color_by: str, reference_ev: float) -> np.ndarray:
        n = self.points.shape[0]
        if color_by == "energy":
            return energy_colors(self.energy, reference_ev)
        if self.particle == "opticalphoton":
            return np.asarray([visible_rgb_for_wavelength(wavelength_nm_for_energy_ev(e))
                               for e in self.energy], dtype=np.float32)
        rgb = np.tile(np.asarray(self.color, dtype=np.float32), (n, 1))
        if self.particle == "gamma" and color_by == "history" and self.gamma_beam:
            if self.primary:
                cut = self.first_hit if self.first_hit is not None else n
                rgb[:cut] = UNCOLLIDED_RGB
                rgb[cut:] = SCATTERED_RGB
            else:
                rgb[:] = SCATTERED_RGB
        return rgb


@dataclass
class Reaction:
    event_id: int
    time_ns: float
    position: np.ndarray
    label: str
    kind: str


def find_reactions(tracks: Sequence[Track]) -> List[Reaction]:
    """Nuclide-changing vertices, reconstructed from recorded parents and their products.

    A product set is the tracks of one event born at the same place and time; its parent is the
    track of that event ending there with a non-transport process. Elastic recoils (the target
    nucleus unchanged) are not reactions and are skipped.
    """
    by_event: Dict[int, List[Track]] = {}
    for track in tracks:
        by_event.setdefault(track.event_id, []).append(track)
    reactions: List[Reaction] = []
    for event_id, group in by_event.items():
        births: Dict[Tuple, List[Track]] = {}
        for track in group:
            if track.primary or track.points.shape[0] == 0:
                continue
            key = (round(float(track.times[0]), 3),) + tuple(np.round(track.points[0], 4))
            births.setdefault(key, []).append(track)
        for key, products in births.items():
            origin = products[0].points[0]
            born = float(products[0].times[0])
            parent = None
            for track in group:
                if track in products or track.points.shape[0] == 0:
                    continue
                if (np.linalg.norm(track.points[-1] - origin) < 1e-3
                        and abs(float(track.times[-1]) - born) <= max(1e-3, 1e-9 * abs(born))):
                    parent = track
                    break
            if parent is None:
                continue
            process = parent.end_process
            names = [p.particle for p in products]
            if process == "RadioactiveDecay":
                label = f"{pretty_particle(parent.particle)} → " + " + ".join(
                    pretty_particle(n) for n in _order(names))
                reactions.append(Reaction(event_id, born, origin, label, "decay"))
                continue
            if process in ("hadElastic", "neutronElastic", "compt", "phot", "Rayl", "eIoni",
                           "hIoni", "ionIoni", "msc", "eBrem", "annihil"):
                continue
            if not any(nuclide_za(n) for n in names):
                continue
            # A continuing projectile is not a product of a capture/transfer channel.
            outgoing = [n for n in names]
            target = target_from_conservation(parent.particle, outgoing)
            if target is None:
                continue
            heavy = [n for n in outgoing if nuclide_za(n)]
            if heavy and target == pretty_particle(heavy[0]) and len(heavy) == 1 and all(
                    n == parent.particle or not nuclide_za(n) for n in outgoing[1:]):
                continue
            label = (f"{pretty_particle(parent.particle)} + {target} → "
                     + " + ".join(pretty_particle(n) for n in _order(outgoing)))
            reactions.append(Reaction(event_id, born, origin, label, "reaction"))
    return sorted(reactions, key=lambda r: r.time_ns)


def _order(names: Sequence[str]) -> List[str]:
    """Heavy products first, then light particles, a stable readable order."""
    return sorted(names, key=lambda n: (0 if nuclide_za(n) else 1, n))


# --------------------------------------------------------------------------- optical bundles


def bundle_optical(tracks: Sequence[Track], bands: int = 10,
                   min_count: int = 2) -> List[Track]:
    """Merge optical photons with the same wavelength band + boundary history into mean paths.

    Only photons with an identical recorded point count and boundary-outcome sequence are merged
    (the mean of topologically identical polylines is still a physical path shape); photons with
    a unique history stay individual. Width grows with sqrt(count).
    """
    groups: Dict[Tuple, List[Track]] = {}
    passthrough: List[Track] = []
    for track in tracks:
        if track.particle != "opticalphoton" or track.energy.size == 0:
            passthrough.append(track)
            continue
        wavelength = wavelength_nm_for_energy_ev(float(track.energy[0]))
        band = int(np.clip((wavelength - 380.0) / (400.0 / bands), 0, bands - 1))
        key = (band, track.points.shape[0], tuple(track.boundaries), track.run)
        groups.setdefault(key, []).append(track)
    merged: List[Track] = list(passthrough)
    for (band, _, _, _), members in groups.items():
        if len(members) < min_count:
            merged.extend(members)
            continue
        lead = members[0]
        bundle = Track.__new__(Track)
        bundle.__dict__.update(lead.__dict__)
        bundle.points = np.mean([m.points for m in members], axis=0)
        bundle.times = np.maximum.accumulate(np.mean([m.times for m in members], axis=0))
        bundle.energy = np.mean([m.energy for m in members], axis=0)
        bundle.width_scale = min(3.2, math.sqrt(len(members)))
        bundle.count = len(members)
        merged.append(bundle)
    return merged


# --------------------------------------------------------------------------- composition glyphs

# Ball-and-stick templates in units of one glyph size: (element, offset), bonds by index.
_TEMPLATES = {
    "water": ([("O", (0, 0, 0)), ("H", (0.76, 0.59, 0)), ("H", (-0.76, 0.59, 0))], [(0, 1), (0, 2)]),
    "n2": ([("N", (-0.55, 0, 0)), ("N", (0.55, 0, 0))], [(0, 1)]),
    "na+": ([("Na", (0, 0, 0))], []),
    "cl-": ([("Cl", (0, 0, 0))], []),
    "c": ([("C", (0, 0, 0))], []),
}
_ATOM_RGB = {"O": (0.95, 0.2, 0.18), "H": (0.92, 0.92, 0.95), "N": (0.35, 0.5, 1.0),
             "Na": (0.66, 0.4, 1.0), "Cl": (0.3, 0.9, 0.35), "C": (0.45, 0.45, 0.5)}
_ATOM_R = {"O": 0.42, "H": 0.26, "N": 0.4, "Na": 0.5, "Cl": 0.62, "C": 0.42}


def material_species(scene: Scene, material: str) -> List[Tuple[str, float]]:
    """(template, relative molecule count) for a scene material, from its recorded components."""
    name = (material or "").lower()
    by_name = {str(m.get("name", "")).lower(): m for m in scene.materials or []}
    entry = by_name.get(name)
    smiles = str((entry or {}).get("smiles") or "")
    if name in ("g4_water", "water") or smiles == "O":
        return [("water", 1.0)]
    if smiles == "N#N" or name in ("g4_n", "nitrogen_gas", "g4_nitrogen"):
        return [("n2", 1.0)]
    if name in ("g4_c", "g4_graphite") or "carbon" in name:
        return [("c", 1.0)]
    if "[Na+]" in smiles and "[Cl-]" in smiles:
        components = (entry or {}).get("components") or []
        water = sum(float(c.get("fraction", 0)) for c in components
                    if "WATER" in str(c.get("material", "")).upper())
        salt = max(0.0, 1.0 - water)
        # Molecule ratio from mass fractions: NaCl 58.44 g/mol, H2O 18.015 g/mol.
        pairs = salt / 58.44
        waters = water / 18.015
        if waters <= 0:
            return [("na+", 1.0), ("cl-", 1.0)]
        return [("water", waters), ("na+", pairs), ("cl-", pairs)]
    return []


def composition_glyphs(plotter, scene: Scene, boxes: Sequence[Tuple[str, Tuple[float, ...]]],
                       max_per_volume: int = 60, seed: int = 7) -> List[Tuple[str, Tuple]]:
    """Scatter labelled molecule glyphs inside each box; returns legend entries."""
    import pyvista as pv

    rng = np.random.default_rng(seed)
    atoms_by_el: Dict[str, List[Tuple[np.ndarray, float]]] = {}
    bonds: List[Tuple[np.ndarray, np.ndarray]] = []
    legend: List[Tuple[str, Tuple]] = []
    for material, bounds in boxes:
        species = material_species(scene, material)
        if not species:
            continue
        lo = np.array(bounds[0::2], dtype=float)
        hi = np.array(bounds[1::2], dtype=float)
        span = hi - lo
        size = 0.04 * float(np.max(span))
        total = sum(weight for _, weight in species)
        is_salt = [s for s, _ in species] == ["na+", "cl-"]
        if is_salt:
            # A rock-salt lattice is what a NaCl crystal is: alternate Na/Cl on a cubic grid.
            cells = 5
            step = span / cells
            for i in range(cells):
                for j in range(cells):
                    for k in range(cells):
                        el = "Na" if (i + j + k) % 2 == 0 else "Cl"
                        pos = lo + (np.array([i, j, k]) + 0.5) * step
                        atoms_by_el.setdefault(el, []).append((pos, 0.22 * float(np.min(step))))
            legend += [("Na⁺ / Cl⁻ lattice (salt)", _ATOM_RGB["Na"])]
            continue
        count = max_per_volume
        for template, weight in species:
            n = int(round(count * weight / total))
            if weight > 0 and n == 0:
                n = 1  # a trace component is still present; say so with one glyph
            atoms, links = _TEMPLATES[template]
            for _ in range(n):
                centre = lo + rng.uniform(0.06, 0.94, 3) * span
                axis = rng.normal(size=3)
                axis /= np.linalg.norm(axis) + 1e-12
                rot = _rotation(axis, rng.uniform(0, 2 * math.pi))
                placed = []
                for el, offset in atoms:
                    pos = centre + size * (rot @ np.asarray(offset, dtype=float))
                    placed.append(pos)
                    atoms_by_el.setdefault(el, []).append((pos, size * _ATOM_R[el]))
                for a, b in links:
                    bonds.append((placed[a], placed[b]))
        labels = {"water": "H₂O", "n2": "N₂", "na+": "Na⁺", "cl-": "Cl⁻", "c": "C"}
        for template, _ in species:
            first = _TEMPLATES[template][0][0][0]
            legend.append((f"{labels[template]} ({material})", _ATOM_RGB[first]))
    for el, atoms in atoms_by_el.items():
        cloud = pv.PolyData(np.asarray([a[0] for a in atoms]))
        cloud.point_data["r"] = np.asarray([a[1] for a in atoms])
        glyphs = cloud.glyph(geom=pv.Sphere(radius=1.0, theta_resolution=10, phi_resolution=10),
                             scale="r", orient=False)
        plotter.add_mesh(glyphs, color=_ATOM_RGB[el], opacity=0.55, smooth_shading=True,
                         specular=0.3)
    if bonds:
        pts = np.asarray([p for pair in bonds for p in pair])
        cells = np.hstack([[2, 2 * i, 2 * i + 1] for i in range(len(bonds))])
        lines = pv.PolyData(pts, lines=cells)
        plotter.add_mesh(lines, color="#c8ccd6", opacity=0.45, line_width=2.0)
    return legend


def _rotation(axis: np.ndarray, angle: float) -> np.ndarray:
    x, y, z = axis
    c, s, C = math.cos(angle), math.sin(angle), 1 - math.cos(angle)
    return np.array([[c + x * x * C, x * y * C - z * s, x * z * C + y * s],
                     [y * x * C + z * s, c + y * y * C, y * z * C - x * s],
                     [z * x * C - y * s, z * y * C + x * s, c + z * z * C]])


def scene_boxes(scene: Scene) -> List[Tuple[str, Tuple[float, ...]]]:
    """World-space (material, bounds) of the medium and every box volume (innermost last)."""
    boxes: List[Tuple[str, Tuple[float, ...]]] = []
    if scene.medium_size_mm > 0:
        m = scene.medium_size_mm / 2
        boxes.append((scene.medium_material, (-m, m, -m, m, -m, m)))
    for volume in scene.volumes:
        if (volume.shape_type or "box").lower() not in ("box", "cube"):
            continue
        centre = np.asarray(volume.position_mm, dtype=float)
        half = 0.5 * np.asarray(volume.size_mm, dtype=float)
        boxes.append((volume.material, (centre[0] - half[0], centre[0] + half[0],
                                        centre[1] - half[1], centre[1] + half[1],
                                        centre[2] - half[2], centre[2] + half[2])))
    return boxes


# --------------------------------------------------------------------------- renderer


@dataclass
class RunTracks:
    tracks: List[Track]
    label: str = ""
    hud: List[str] = field(default_factory=list)
    scene: Optional[Scene] = None


def load_run(trajectories: Sequence[Trajectory], *, label: str = "", hud: Sequence[str] = (),
             scene: Optional[Scene] = None, display_events: Optional[int] = None,
             run_index: int = 0) -> RunTracks:
    tracks = [Track(traj) for traj in trajectories if traj.points]
    if display_events is not None and display_events > 0:
        keep = sorted({t.event_id for t in tracks})[:display_events]
        keep_set = set(keep)
        tracks = [t for t in tracks if t.event_id in keep_set]
    for track in tracks:
        track.run = run_index
    return RunTracks(tracks, label, list(hud), scene)


def _fade(rgb: np.ndarray, age: np.ndarray, trail: float, floor: float) -> np.ndarray:
    if trail <= 0:
        return rgb
    brightness = floor + (1.0 - floor) * np.exp(-np.maximum(age, 0.0) / trail)
    return BG_RGB + (rgb - BG_RGB) * brightness[:, None]


def render_tracks(
    runs: Sequence[RunTracks],
    *,
    gif: str,
    title: str = "",
    caption: Sequence[str] = (),
    window_size: Tuple[int, int] = (1280, 720),
    fps: int = 12,
    seconds: float = 8.0,
    orbit_deg: float = 30.0,
    elevation: float = 0.3,
    clock: str = "activity",
    hold_fraction: float = 0.18,
    color_by: str = "history",
    trail: float = 0.12,
    trail_floor: float = 0.2,
    bundle: bool = False,
    glyphs: bool = False,
    nuclides: bool = False,
    split: bool = False,
    zoom_ratio: float = 5.0,
    charts=None,
    chart_width: int = 0,
    background: str = "dark",
    screenshot: Optional[str] = None,
    focus: Optional[Sequence[float]] = None,
) -> None:
    import pyvista as pv
    from .renderer import _add_static_scene

    runs = [run for run in runs if run.tracks]
    if not runs:
        raise ValueError("no recorded trajectories to render")
    event_counts = {}
    for index, run in enumerate(runs):
        for track in run.tracks:
            track.run = index
        event_counts[index] = len({t.event_id for t in run.tracks})
        if bundle:
            run.tracks = bundle_optical(run.tracks)
    overlay_colors = [(0.3, 0.9, 1.0), (0.95, 0.35, 0.9)]
    overlay = len(runs) > 1 and not split
    if overlay and runs[0].tracks[0].particle != "opticalphoton":
        for index, run in enumerate(runs):
            for track in run.tracks:
                track.color = overlay_colors[index % 2]
    everything = [track for run in runs for track in run.tracks]
    fps = max(1, int(fps))
    total = max(2, int(round(max(seconds, 0.2) * fps)))
    hold = int(round(total * max(0.0, min(0.6, hold_fraction))))
    reveal = max(2, total - hold)
    clock_ns = activity_clock(everything, reveal, clock)
    clock_ns = np.concatenate([clock_ns, np.full(total - reveal, clock_ns[-1])])
    reference_ev = max((float(t.energy[0]) for t in everything if t.primary and t.energy.size),
                       default=1.0)
    reactions = find_reactions(everything) if nuclides else []
    gamma_beam = any(t.primary and t.particle == "gamma" for t in everything)
    for track in everything:
        track.gamma_beam = gamma_beam
    births = {(r.event_id, round(r.time_ns, 3)) for r in reactions}
    for track in everything:
        if track.is_ion and (track.event_id, round(float(track.times[0]), 3)) in births:
            track.product = True

    width, height = max(64, int(window_size[0])), max(64, int(window_size[1]))
    panel = ChartPanel(charts or [], chart_width or int(width * 0.34), height) if charts else None
    view_width = width - (panel.width if panel else 0)
    panes = runs if split else [runs[0]]
    pane_width = view_width // len(panes)

    # Shared framing: apparatus + where most recorded steps are.
    all_points = np.vstack([t.points for t in everything])
    track_lo = np.percentile(all_points, 2.0, axis=0)
    track_hi = np.percentile(all_points, 98.0, axis=0)
    if isinstance(focus, str) and focus == "scene" and runs[0].scene is not None:
        boxes = scene_boxes(runs[0].scene)
        if boxes:
            b = np.asarray([box for _, box in boxes], dtype=float)
            lo, hi = b[:, 0::2].min(axis=0), b[:, 1::2].max(axis=0)
            pad = 0.45 * (hi - lo)
            track_lo, track_hi = lo - pad, hi + pad
    elif focus is not None and not isinstance(focus, str):
        track_lo, track_hi = np.asarray(focus[0::2], float), np.asarray(focus[1::2], float)
    track_span = max(float(np.max(track_hi - track_lo)), 1e-6)
    track_lo, track_hi = track_lo - 0.08 * track_span, track_hi + 0.08 * track_span

    def frame_index(times: np.ndarray) -> np.ndarray:
        return np.searchsorted(clock_ns[:reveal], times, side="left").astype(np.float64)

    plotters = []
    pane_notes: List[str] = []
    for pane_index, pane_run in enumerate(panes):
        plotter = _new_plotter(pane_width, height, background)
        scene = pane_run.scene
        bounds: Optional[List[float]] = None
        enclosing: List[str] = []
        if scene is not None:
            _add_static_scene(plotter, scene, show_world=False, show_volumes=True,
                              show_beams=False)
            if plotter.renderer.actors:
                sb = list(float(v) for v in plotter.bounds)
                span = max(sb[1] - sb[0], sb[3] - sb[2], sb[5] - sb[4])
                if span > zoom_ratio * track_span:
                    plotter.clear_actors()
                    enclosing = _add_static_scene(
                        plotter, scene, show_world=False, show_volumes=True, show_beams=False,
                        skip_enclosing=(tuple(track_lo), tuple(track_hi))) or []
                elif focus is None or focus == "tracks":
                    bounds = sb
        bounds = _merge_bounds(bounds, track_lo, track_hi)
        legend: List[Tuple[str, Tuple]] = []
        if glyphs and scene is not None:
            boxes = [(m, b) for m, b in scene_boxes(scene)]
            clipped = []
            for material, b in boxes:
                lo = np.maximum(np.asarray(b[0::2]), np.asarray(bounds[0::2]))
                hi = np.minimum(np.asarray(b[1::2]), np.asarray(bounds[1::2]))
                if np.all(hi > lo):
                    clipped.append((material, (lo[0], hi[0], lo[1], hi[1], lo[2], hi[2])))
            legend += composition_glyphs(plotter, scene, clipped)
        view_dir = _side_view(pane_run.tracks, elevation)
        turntable = _Turntable(plotter, bounds, pane_width, height, orbit_deg,
                               elevation=elevation, ground=False, view_dir=view_dir)
        legend = _track_legend(pane_run.tracks if split else everything, color_by, runs,
                               overlay) + legend
        if nuclides:
            shown = []
            for track in (pane_run.tracks if split else everything):
                nuclide = nuclide_za(track.particle) if track.product else None
                if nuclide and pretty_particle(track.particle) not in shown:
                    shown.append(pretty_particle(track.particle))
                    legend.insert(len(shown) - 1, (f"● {shown[-1]} nucleus",
                                                   NUCLIDE_RGB.get(nuclide[2], (0.8, 0.6, 1.0))))
        if glyphs and legend:
            legend.append(("glyphs: composition, not to scale", (0.62, 0.66, 0.74)))
        if not split or pane_index == len(panes) - 1:
            _legend(plotter, legend[:10], anchor="upper_right")
        plotter.show(auto_close=False, interactive=False)
        plotters.append((plotter, turntable, pane_run, enclosing))
        pane_notes.append(", ".join(enclosing))

    line_width = max(1.6, min(4.5, 2.4 * height / 480.0))
    head_size = max(6.0, min(16.0, 10.0 * height / 480.0))
    events = {(t.run, t.event_id) for t in everything}
    t_span = float(clock_ns[-1] * 1e-9)
    images = []
    actor_sets: List[list] = [[] for _ in plotters]
    colors_cache = {id(t): t.point_colors(color_by, reference_ev) for t in everything}
    frame_cache = {id(t): frame_index(t.times) for t in everything}
    for index, t_ns in enumerate(clock_ns):
        now_frame = float(min(index, reveal - 1))
        tiles = []
        for pane_index, (plotter, turntable, pane_run, enclosing) in enumerate(plotters):
            for actor in actor_sets[pane_index]:
                plotter.remove_actor(actor)
            actors = []
            tracks = pane_run.tracks if split else everything
            buckets: Dict[float, List[Tuple[np.ndarray, np.ndarray]]] = {}
            heads, head_rgb, alive = [], [], 0
            vertices: Dict[str, List[Tuple[np.ndarray, float]]] = {}
            ion_pos, ion_rgb, ion_labels = [], [], []
            for track in tracks:
                k, head = track.head(float(t_ns))
                if k == 0:
                    continue
                rgb = colors_cache[id(track)][:k]
                age = (now_frame - frame_cache[id(track)][:k]) / max(1.0, reveal)
                rgb = _fade(rgb, age, trail, trail_floor)
                pts = track.points[:k]
                if head is not None:
                    pts = np.vstack([pts, head[None, :]])
                    rgb = np.vstack([rgb, rgb[-1:]])
                    alive += 1
                    if not track.is_ion:
                        heads.append(head)
                        head_rgb.append(colors_cache[id(track)][k - 1])
                if track.is_ion and nuclides:
                    decayed = track.end_process == "RadioactiveDecay" and head is None
                    if not decayed:
                        where = head if head is not None else track.points[-1]
                        nuclide = nuclide_za(track.particle)
                        ion_pos.append(where)
                        ion_rgb.append(NUCLIDE_RGB.get(nuclide[2] if nuclide else "", (0.8, 0.6, 1.0)))
                        ion_labels.append(pretty_particle(track.particle) if track.product else "")
                    continue
                if pts.shape[0] >= 2 and not track.is_ion:
                    width_key = round(track.width_scale * (1.0 if track.primary else 0.6), 1)
                    buckets.setdefault(width_key, []).append((pts, rgb))
                for mark in range(1, k):
                    kind = track.interactions[mark]
                    if kind not in ("scatter", "interaction") or not track.neutral:
                        continue
                    process = track.processes[mark]
                    if process in VERTEX_STYLE:
                        vertices.setdefault(process, []).append(
                            (track.points[mark], now_frame - frame_cache[id(track)][mark]))
                if track.particle == "opticalphoton" and color_by != "energy":
                    for mark in range(1, k):
                        if track.boundaries[mark] in ("reflection", "total_internal_reflection"):
                            vertices.setdefault("reflection", []).append(
                                (track.points[mark], now_frame - frame_cache[id(track)][mark]))
            for width_key, batch in sorted(buckets.items()):
                poly = _polyline_batch_rgb(batch)
                if poly is not None:
                    actors.append(plotter.add_mesh(
                        poly, scalars="rgb", rgb=True, line_width=line_width * width_key,
                        show_scalar_bar=False, render_lines_as_tubes=True))
            if heads:
                cloud = pv.PolyData(np.asarray(heads))
                cloud.point_data["rgb"] = np.asarray(head_rgb, dtype=np.float32)
                actors.append(plotter.add_points(cloud, scalars="rgb", rgb=True,
                                                 point_size=head_size, emissive=True,
                                                 render_points_as_spheres=True,
                                                 show_scalar_bar=False))
            for process, marks in vertices.items():
                colour = VERTEX_STYLE.get(process, ("#ffffff", ""))[0]
                if process == "reflection":
                    colour = "#ffe9a8"
                recent = [p for p, age in marks if age <= 2.5]
                older = [p for p, age in marks if age > 2.5]
                if older:
                    actors.append(plotter.add_points(np.asarray(older), color=colour,
                                                     point_size=head_size * 0.62, emissive=True,
                                                     render_points_as_spheres=True, opacity=0.8))
                if recent:
                    actors.append(plotter.add_points(np.asarray(recent), color=colour,
                                                     point_size=head_size * 1.9, emissive=True,
                                                     render_points_as_spheres=True))
            if ion_pos:
                cloud = pv.PolyData(np.asarray(ion_pos))
                cloud.point_data["rgb"] = np.asarray(ion_rgb, dtype=np.float32)
                actors.append(plotter.add_points(cloud, scalars="rgb", rgb=True,
                                                 point_size=head_size * 1.7,
                                                 render_points_as_spheres=True,
                                                 show_scalar_bar=False))
                unique = {}
                for pos, lab in zip(ion_pos, ion_labels):
                    if lab:
                        unique.setdefault((lab, tuple(np.round(pos, 1))), pos)
                if unique and len(unique) <= 60:
                    actors.append(plotter.add_point_labels(
                        np.asarray(list(unique.values())), [lab for lab, _ in unique],
                        font_size=max(10, int(height / 40)), text_color="#ffffff",
                        shape_opacity=0.0, show_points=False, always_visible=True,
                        name=f"ions_{pane_index}", **text_kwargs()))
            recent_reactions = [r for r in reactions
                                if r.time_ns <= t_ns and (split is False or True)
                                and now_frame - frame_index(np.array([r.time_ns]))[0]
                                <= 0.35 * reveal]
            if recent_reactions:
                seen: Dict[str, np.ndarray] = {}
                for reaction in recent_reactions[-6:]:
                    seen.setdefault(reaction.label, reaction.position)
                actors.append(plotter.add_point_labels(
                    np.asarray(list(seen.values())), list(seen.keys()),
                    font_size=max(11, int(height / 34)), text_color="#9dffb8",
                    shape_color="#0b1220", shape_opacity=0.65, show_points=False,
                    always_visible=True, name=f"reactions_{pane_index}", **text_kwargs()))
            turntable.place(index / max(1, total - 1))
            head_lines = [title] if (title and pane_index == 0) else []
            if split:
                head_lines = ([title] if pane_index == 0 and title else [""]) + [pane_run.label]
            head_lines += [
                f"Geant4 clock t = {format_clock(t_ns * 1e-9, t_span)}"
                + (f"   ({event_counts[pane_index] if split else sum(event_counts.values())} events"
                   + ("" if split else ", each from its own t=0") + ")"),
            ]
            if enclosing:
                head_lines.append(f"inside {', '.join(enclosing)} (not drawn)")
            head_lines += (pane_run.hud if split else [line for run in runs for line in run.hud])
            _hud(plotter, head_lines, height)
            actor_sets[pane_index] = actors
            tiles.append(_screenshot(plotter))
        frame = np.hstack(tiles) if len(tiles) > 1 else tiles[0]
        if caption:
            frame = draw_caption(frame, caption)
        if panel:
            frame = compose(frame, panel.render(float(t_ns)))
        images.append(frame)

    for plotter, *_ in plotters:
        plotter.close()
    write_gif(gif, images, fps)
    if screenshot:
        import imageio.v2 as imageio

        imageio.imwrite(screenshot, images[-1])


def _polyline_batch_rgb(batch):
    import pyvista as pv

    pts, cells, colors = [], [], []
    offset = 0
    for points, rgb in batch:
        n = points.shape[0]
        if n < 2:
            continue
        pts.append(points)
        cells.append(np.concatenate([[n], np.arange(offset, offset + n)]))
        colors.append(np.broadcast_to(np.asarray(rgb, dtype=np.float32), (n, 3)))
        offset += n
    if not pts:
        return None
    poly = pv.PolyData()
    poly.points = np.vstack(pts)
    poly.lines = np.concatenate(cells).astype(np.int64)
    poly.point_data["rgb"] = np.ascontiguousarray(np.clip(np.vstack(colors), 0.0, 1.0))
    return poly


def _side_view(tracks: Sequence[Track], elevation: float) -> np.ndarray:
    directions = []
    for track in tracks:
        if track.primary and track.points.shape[0] >= 2:
            step = track.points[1] - track.points[0]
            norm = float(np.linalg.norm(step))
            if norm > 0:
                directions.append(step / norm)
    up = np.array([0.0, 1.0, 0.0])
    beam = np.mean(directions, axis=0) if directions else np.array([0.0, 0.0, 1.0])
    if float(np.linalg.norm(beam)) < 0.3:
        return np.array([0.78, float(elevation), 1.0])
    beam = beam / float(np.linalg.norm(beam))
    side = np.cross(beam, up)
    if float(np.linalg.norm(side)) < 1e-3:
        side = np.array([1.0, 0.0, 0.0])
    side = side / float(np.linalg.norm(side))
    return side + float(elevation) * up - 0.3 * beam


def _track_legend(tracks: Sequence[Track], color_by: str, runs: Sequence[RunTracks],
                  overlay: bool) -> List[Tuple[str, Tuple]]:
    if color_by == "energy":
        ramp = energy_colors(np.array([1.0, 0.5, 0.15, 0.0]), 1.0)
        return [("E = primary", tuple(ramp[0])), ("E/2", tuple(ramp[1])),
                ("slowing", tuple(ramp[2])), ("stopped", tuple(ramp[3]))]
    if overlay:
        return [(run.label or f"run {i + 1}", (0.3, 0.9, 1.0) if i == 0 else (0.95, 0.35, 0.9))
                for i, run in enumerate(runs)]
    entries: List[Tuple[str, Tuple]] = []
    particles = []
    for track in tracks:
        if track.particle not in particles:
            particles.append(track.particle)
    gamma_beam = any(t.primary and t.particle == "gamma" for t in tracks)
    if "gamma" in particles and color_by == "history" and gamma_beam:
        entries += [("γ not yet interacted", UNCOLLIDED_RGB), ("γ after scattering", SCATTERED_RGB)]
    if "opticalphoton" in particles:
        entries += [("photon (colour = wavelength)", (0.4, 1.0, 0.4))]
        if any(any(b in ("reflection", "total_internal_reflection") for b in t.boundaries)
               for t in tracks if t.particle == "opticalphoton"):
            entries.append(("◦ recorded reflection", (1.0, 0.91, 0.66)))
    for particle in particles:
        if particle == "opticalphoton" or (particle == "gamma" and gamma_beam):
            continue
        label = species_label(particle)
        if label == "ion":
            continue
        entries.append((DISPLAY_NAMES.get(label, label), species_color(particle)))
    processes = {track.processes[i] for track in tracks if track.neutral
                 for i in range(1, len(track.processes))
                 if track.interactions[i] in ("scatter", "interaction")}
    for process, (colour, label) in VERTEX_STYLE.items():
        if process in processes and label not in [e[0] for e in entries]:
            rgb = tuple(int(colour[i:i + 2], 16) / 255.0 for i in (1, 3, 5))
            entries.append((f"● {label}", rgb))
    renamed = {"e-": "e⁻ (electrons)", "anti_nu_e": "ν̄ (antineutrino)", "anti-nu_e": "ν̄ (antineutrino)",
               "gamma": "γ (photons)"}
    if gamma_beam:
        renamed["e-"] = "e⁻ (knocked-out electrons)"
    entries = [(renamed.get(label, label), rgb) for label, rgb in entries]
    return entries
