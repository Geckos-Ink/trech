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
            label = f'{f["particle"]}: {f["id"]} [{f["source"]["kind"]}]'
            views.append(("density:" + f["id"], label + " density isosurface"))
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
                views.append((key + ":" + component, f'{ensemble["element"]}-{data["a"]}: {component} [Geant4 initial-state ensemble, fm]'))
    return views


def _background(structure):
    palette = {"H": [.9, .94, 1, 1], "C": [.32, .39, .48, 1], "N": [.37, .48, 1, 1], "O": [1, .34, .28, 1]}
    atoms = structure.get("atoms", [])
    return (np.asarray([a["position"] for a in atoms], np.float32).reshape(-1, 3),
            np.asarray([palette.get(a["element"], [.65, .8, .6, 1]) for a in atoms], np.float32).reshape(-1, 4),
            np.asarray([.16 if a["element"] == "H" else .25 for a in atoms], np.float32),
            np.asarray([b[:2] for b in structure.get("bonds", [])], np.int32).reshape(-1, 2))


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
                    frames.append(ParticleFrame(time=float(i), positions=positions, colors=colors,
                        radii=np.full(len(positions), .18, np.float32), tag=emit.tag,
                        phase="Independent nuclear initial state; index is not physical time"))
                note = data["source"]["method"] + ": " + data["source"]["scope"]
                unit, clock, source_tag = "fm", "ensemble_index", emit.tag
                break
            if frames:
                break
    else:
        for payload in quantum:
            clock = payload["time_kind"]
            positions, colors, radii, bonds = _background(payload["structure"])
            density = None
            if view != "structure":
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
                if unit != "angstrom":
                    positions, colors, radii, bonds = _background({}) # nuclear and molecular scales stay separate
                note = field["source"]["kind"] + ": " + field["source"]["method"] + "; owners: " + ", ".join(field["owner_ids"])
                if kind == "density":
                    g = field["grid"]
                    values = np.asarray(g["values"], np.float32).reshape(g["shape"])
                    if np.any(~np.isfinite(values)) or np.any(values < 0):
                        raise ValueError("invalid recorded density field")
                    density = ScalarDensity(values, np.asarray(g["origin"], np.float32), float(g["spacing"]),
                        float(field["isovalue"]), field["density_unit"], note)
                else:
                    points = np.asarray(field["samples"], np.float32).reshape(-1, 3)
                    positions = np.concatenate((positions, points))
                    colors = np.concatenate((colors, np.tile([.3, .68, 1, .25], (len(points), 1)).astype(np.float32)))
                    radii = np.concatenate((radii, np.full(len(points), .025 if unit == "angstrom" else .12, np.float32)))
                    note += "; " + field["sampling_note"]
            frames.append(ParticleFrame(time=float(payload["cursor"]), positions=positions, colors=colors,
                radii=radii, bonds=bonds, density=density, tag="quantum_frame",
                physical_time_s=payload.get("physical_time_s"), phase=note or "Authored molecular structures"))
    if not frames:
        return Playback()
    times = np.asarray([f.time for f in frames], np.float64)
    physical = [f.physical_time_s for f in frames if f.physical_time_s is not None]
    return Playback(kind="particles", unit="s" if clock == "physical" else "parameter" if clock == "parameter_scan" else "ensemble sample" if clock == "ensemble_index" else "snapshot",
        t_min=float(times[0]), t_max=float(times[-1]), frames=frames, frame_times=times,
        source_tag=source_tag, length_unit=unit, label=view + " · " + note,
        physical_t_min=min(physical) if physical else None, physical_t_max=max(physical) if physical else None)
