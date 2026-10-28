"""Recorded density/ensemble playback. No wavefunction, sampling or dynamics is computed here."""
from __future__ import annotations
from dataclasses import dataclass
from typing import Any, Sequence
import numpy as np
from .playback import ParticleFrame, Playback


@dataclass
class ScalarDensity:
    values: np.ndarray
    origin: np.ndarray
    spacing: float
    isovalue: float
    density_unit: str
    source_note: str
    rgba: tuple = (0.28, 0.64, 1.0, 0.30)
    amplitude: Any = None
    statistics: Any = None
    quantity: str = "number_density"
    comparison: Any = None
    atom_labels: Any = None
    overlays: Any = None
    energy_components: Any = None


def _quantum(emits):
    return [e.payload for e in emits if getattr(e, "tag", "") == "quantum_frame" and isinstance(e.payload, dict)]


def probability_views(emits: Sequence[Any]) -> list[tuple[str, str]]:
    views = [("structure", "Molecular structures")]
    seen = set()
    for payload in _quantum(emits):
        for f in payload.get("fields", []):
            if f["id"] in seen:
                continue
            seen.add(f["id"])
            orbital = f.get("orbital")
            label = (f'MO {orbital["index"]} · {orbital["occupation"]:g} e [{f["source"]["kind"]}]'
                     if orbital else f'{f["particle"]}: {f["id"]} [{f["source"]["kind"]}]')
            if f.get("energy_components"): label = "Occupied energy contributions · electron density"
            if f.get("quantity") == "density_difference": label = "Redistribution: joint − isolated fragments"
            views.append(("density:" + f["id"], label + " · explore field"))
            if f.get("samples"):
                views.append(("samples:" + f["id"], label + " probability samples"))
    for emit in emits:
        if getattr(emit, "tag", "") != "chemistry_nuclear_ensemble":
            continue
        for ensemble in emit.payload.get("ensembles", []):
            data = ensemble["data"]
            if not data.get("available"):
                continue
            key = f'nuclear:{ensemble["element"]}:{data["a"]}'
            if key in seen:
                continue
            seen.add(key)
            for component in ("both", "protons", "neutrons"):
                if component == "neutrons" and data["a"] == data["z"]:
                    continue
                views.append((key + ":" + component, f'{ensemble["element"]}-{data["a"]}: one nucleus · {data["z"]} p + {data["a"]-data["z"]} n · {component} (fm)'))
    return views


def _background(structure):
    palette = {"H": [.9, .94, 1, 1], "C": [.32, .39, .48, 1], "N": [.37, .48, 1, 1], "O": [1, .34, .28, 1]}
    atoms = structure.get("atoms", [])
    return (np.asarray([a["position"] for a in atoms], np.float32).reshape(-1, 3),
            np.asarray([palette.get(a["element"], [.65, .8, .6, 1]) for a in atoms], np.float32).reshape(-1, 4),
            np.asarray([.16 if a["element"] == "H" else .25 for a in atoms], np.float32),
            np.asarray([b[:2] for b in structure.get("bonds", [])], np.int32).reshape(-1, 2))


def _nuclear_guides(statistics):
    """Three circles mark the recorded sample's extent; these are not physical shells."""
    if not statistics:
        return None
    centre = np.asarray(statistics["centre_fm"], np.float32)
    radius = max(statistics[s]["max_radius_fm"] for s in ("protons", "neutrons"))
    angles = np.linspace(0, 2*np.pi, 97)
    segments = []
    for x, y in ((0, 1), (1, 2), (0, 2)):
        points = np.tile(centre, (len(angles), 1))
        points[:, x] += radius*np.cos(angles)
        points[:, y] += radius*np.sin(angles)
        segments.extend(np.stack((points[:-1], points[1:]), axis=1).reshape(-1, 3))
    return np.asarray(segments, np.float32)


def build_probability_playback(emits: Sequence[Any], view: str | None = None) -> Playback:
    quantum = _quantum(emits)
    if view is None:
        view = next((key for key, _ in probability_views(emits) if key.startswith("density:")), "structure")
    frames = []
    unit = "angstrom"
    note = ""
    clock = "snapshot"
    source_tag = "quantum_frame"
    if view.startswith("nuclear:"):
        _, element, mass, component = view.split(":")
        for emit in emits:
            if getattr(emit, "tag", "") != "chemistry_nuclear_ensemble":
                continue
            for ensemble in emit.payload.get("ensembles", []):
                data = ensemble["data"]
                if ensemble["element"] != element or data["a"] != int(mass) or not data.get("available"):
                    continue
                for i, sample in enumerate(data["configurations"]):
                    protons = sample["protons"] if component != "neutrons" else []
                    neutrons = sample["neutrons"] if component != "protons" else []
                    positions = np.asarray(protons + neutrons, np.float32).reshape(-1, 3)
                    colors = np.asarray([[1, .3, .24, 1]] * len(protons) + [[.3, .65, 1, 1]] * len(neutrons), np.float32).reshape(-1, 4)
                    statistics = sample.get("statistics")
                    detail = {"kind": "nuclear", "element": element, "a": data["a"], "z": data["z"],
                        "statistics": statistics, "radial_distribution": data.get("radial_distribution"),
                        "configuration": i+1, "configuration_count": len(data["configurations"]), "component": component}
                    frames.append(ParticleFrame(time=float(i), positions=positions, colors=colors,
                        radii=np.full(len(positions), .48, np.float32), tag=emit.tag, guides=_nuclear_guides(statistics), details=detail,
                        phase=f'ONE {element}-{mass} nucleus · {data["z"]} protons (red) + {data["a"]-data["z"]} neutrons (blue) · configuration {i+1}/{len(data["configurations"])}; no physical time'))
                note = f'ONE {element}-{mass} nucleus · {data["z"]} protons (red) + {data["a"]-data["z"]} neutrons (blue). Glyph radii and extent guides are display choices. ' + data["source"]["scope"]
                unit, clock, source_tag = "fm", "ensemble_index", emit.tag
                break
            if frames:
                break
    else:
        for payload in quantum:
            clock = payload["time_kind"]
            positions, colors, radii, bonds = _background(payload["structure"])
            density = None
            details = {"kind": "electronic", "particle_inventory": payload.get("particle_inventory"),
                       "electronic_structure": payload.get("electronic_structure"), "selected_field": None}
            if view != "structure":
                # Tiny centre markers leave the core density visible; these are
                # screen-context glyphs, not physical nuclear/atomic radii.
                radii = np.full(len(positions), .04, np.float32)
                kind, field_id = view.split(":", 1)
                field = next((f for f in payload["fields"] if f["id"] == field_id), None)
                if field is None:
                    # Explicit missing frame clears the previous surface/cloud.
                    # Skipping it would hold stale probability as if still recorded.
                    frames.append(ParticleFrame(time=float(payload["cursor"]), positions=positions, colors=colors,
                        radii=radii, bonds=bonds, tag="quantum_frame", physical_time_s=payload.get("physical_time_s"),
                        phase="Probability field unavailable at this recorded frame"))
                    continue
                unit = field["length_unit"]
                details["selected_field"] = {k: field[k] for k in ("id", "orbital", "sampling_note", "isovalue", "density_unit") if k in field}
                if unit != "angstrom":
                    positions, colors, radii, bonds = _background({}) # nuclear and molecular scales stay separate
                note = field["source"]["kind"] + ": " + field["source"]["method"] + "; owners: " + ", ".join(field["owner_ids"])
                if kind == "density":
                    g = field["grid"]
                    values = np.asarray(g["values"], np.float32).reshape(g["shape"])
                    if np.any(~np.isfinite(values)) or (np.any(values < 0) and field.get("quantity") != "density_difference"):
                        raise ValueError("invalid recorded density field")
                    density = ScalarDensity(values, np.asarray(g["origin"], np.float32), float(g["spacing"]),
                        float(field["isovalue"]), field["density_unit"], note)
                    density.statistics = field.get("statistics")
                    density.energy_components = field.get("energy_components")
                    density.quantity = field.get("quantity", "orbital_probability" if field.get("orbital") else "number_density")
                    density.comparison = field.get("comparison")
                    density.atom_labels = [(a["element"], a["position"], owner) for a, owner in
                        zip(payload["structure"].get("atoms", []), payload["structure"].get("molecule_ids", []))]
                    density.overlays = {}
                    if not field.get("orbital"):
                        for other in payload["fields"]:
                            if not other.get("amplitude") or not other.get("orbital"): continue
                            og = other["grid"]
                            density.overlays[other["id"]] = {
                                "orbital": other["orbital"], "amplitude": np.asarray(other["amplitude"]["values"], np.float32).reshape(og["shape"]),
                                "origin": np.asarray(og["origin"],np.float32), "spacing": float(og["spacing"]), "statistics": other.get("statistics")}
                    if field.get("amplitude"):
                        density.amplitude = np.asarray(field["amplitude"]["values"], np.float32).reshape(g["shape"])
                    if field.get("orbital"):
                        density.rgba = (.72, .46, 1., .48) if field["orbital"]["occupation"] else (1., .68, .25, .48)
                else:
                    points = np.asarray(field["samples"], np.float32).reshape(-1, 3)
                    positions = np.concatenate((positions, points))
                    colors = np.concatenate((colors, np.tile([.3, .68, 1, .25], (len(points), 1)).astype(np.float32)))
                    radii = np.concatenate((radii, np.full(len(points), .025 if unit == "angstrom" else .12, np.float32)))
                    note += "; " + field["sampling_note"]
            frames.append(ParticleFrame(time=float(payload["cursor"]), positions=positions, colors=colors,
                radii=radii, bonds=bonds, density=density, tag="quantum_frame",
                physical_time_s=payload.get("physical_time_s"), phase=note or "Authored molecular structures", details=details))
    if not frames:
        return Playback()
    times = np.asarray([f.time for f in frames], np.float64)
    physical = [f.physical_time_s for f in frames if f.physical_time_s is not None]
    return Playback(kind="particles", unit="s" if clock == "physical" else "parameter" if clock == "parameter_scan" else "ensemble sample" if clock == "ensemble_index" else "snapshot",
        t_min=float(times[0]), t_max=float(times[-1]), frames=frames, frame_times=times,
        source_tag=source_tag, length_unit=unit, label=view + " · " + note,
        physical_t_min=min(physical) if physical else None, physical_t_max=max(physical) if physical else None)
