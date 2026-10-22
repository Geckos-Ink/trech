"""PubChem 3D comparison records, with explicit atom-ID joins (never a 2D fallback)."""
from __future__ import annotations

import datetime
import hashlib
import json
import math
import urllib.parse

from .client import PUG, _get, cache_dir, slugify


def parse_conformer(payload: dict) -> dict:
    compound = payload["PC_Compounds"][0]
    atoms = compound["atoms"]
    ids = atoms["aid"]
    if len(set(ids)) != len(ids) or len(ids) != len(atoms["element"]):
        raise ValueError("invalid atom IDs")
    index = {aid: i for i, aid in enumerate(ids)}
    coords = next((c for c in compound.get("coords", []) if 2 in c.get("type", [])), None)
    if coords is None:
        raise ValueError("PubChem record has no 3D conformer")
    conf = coords["conformers"][0]
    coord_ids = coords["aid"]
    if set(coord_ids) != set(ids) or len(coord_ids) != len(ids):
        raise ValueError("3D atom IDs do not match the compound")
    if any(len(conf[axis]) != len(ids) for axis in ("x", "y", "z")):
        raise ValueError("incomplete 3D coordinates")
    by_id = {aid: [float(conf[axis][i]) for axis in ("x", "y", "z")]
             for i, aid in enumerate(coord_ids)}
    positions = [by_id[aid] for aid in ids]
    if not all(math.isfinite(v) for row in positions for v in row):
        raise ValueError("non-finite 3D coordinates")
    bonds = compound.get("bonds", {})
    columns = [bonds.get(key, []) for key in ("aid1", "aid2", "order")]
    if len({len(c) for c in columns}) != 1:
        raise ValueError("incomplete bond table")
    edges = [[index[a], index[b], order] for a, b, order in zip(*columns)]
    # PubChem stores a sparse MMFF94 list: unlisted atoms have zero charge
    # ONLY when that property is present and its entry count is complete.
    charges = None
    for prop in compound.get("props", []):
        urn = prop.get("urn", {})
        if (urn.get("label"), urn.get("name")) == ("Charge", "MMFF94 Partial"):
            entries = prop["value"]["slist"]
            if int(entries[0]) != len(entries) - 1:
                raise ValueError("incomplete MMFF94 charge list")
            charges = [0.0] * len(ids)
            seen = set()
            for entry in entries[1:]:
                aid, value = entry.split()
                aid, value = int(aid), float(value)
                if aid in seen or not math.isfinite(value):
                    raise ValueError("invalid MMFF94 charge entry")
                seen.add(aid)
                charges[index[aid]] = value
    return {"cid": compound["id"]["id"]["cid"], "atom_ids": ids,
            "atomic_numbers": atoms["element"], "positions_angstrom": positions,
            "bonds": edges, "mmff94_charges_e": charges,
            "geometry_scope": "PubChem theoretical default conformer; not experimental truth",
            "charge_scope": "MMFF94 partial charges; not electron density or QM charges"}


def fetch_conformer(name: str, *, cache_root=None, timeout: float = 30) -> dict:
    root = cache_dir(cache_root)
    root.mkdir(parents=True, exist_ok=True)
    url = f"{PUG}/compound/name/{urllib.parse.quote(name, safe='')}/JSON?record_type=3d"
    raw = _get(url, timeout)
    result = parse_conformer(json.loads(raw))
    result["provenance"] = {
        "url": url, "sha256": hashlib.sha256(raw).hexdigest(),
        "fetched_at_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "policy": "comparison_only; excluded from model fitting and geometry construction"}
    (root / f"{slugify(name)}-3d.raw.json").write_bytes(raw)
    (root / f"{slugify(name)}-3d.json").write_text(json.dumps(result, indent=2) + "\n")
    return result
