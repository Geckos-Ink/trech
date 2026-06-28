"""Fetch + cache PubChem compound properties and 2D structure images.

The cache defaults to ``build/pubchem_cache/`` so new fetched records stay out
of git. Callers can set ``TRECH_PUBCHEM_CACHE_DIR`` or pass ``--cache-dir`` to
choose another build-local cache:

* ``<cache>/<slug>.json`` -- properties (CID, MW, XLogP, SMILES, ...) plus
  provenance (source URLs, UTC fetch time, PubChem build comment).
* ``<cache>/<slug>.png`` -- the PubChem 2D structure depiction.

``fetch_compound`` performs the network calls (PUG-REST) and writes the cache;
``load_compound`` reads the selected cache first, then the legacy
``data/pubchem`` cache only as a fallback (no network).
"""

from __future__ import annotations

import dataclasses
import datetime as _dt
import json
import os
import re
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Dict, Optional

# Repo root (this file is tools/pubchem/trech_pubchem/client.py). Default writes
# go under build/ so fetched PubChem data does not need to be committed.
REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_CACHE_DIR = REPO_ROOT / "build" / "pubchem_cache"
LEGACY_CACHE_DIR = REPO_ROOT / "data" / "pubchem"


def cache_dir(override: Optional[Path | str] = None) -> Path:
    if override is not None:
        return Path(override).expanduser()
    env = os.environ.get("TRECH_PUBCHEM_CACHE_DIR")
    if env:
        return Path(env).expanduser()
    return DEFAULT_CACHE_DIR


CACHE_DIR = cache_dir()

PUG = "https://pubchem.ncbi.nlm.nih.gov/rest/pug"
# Properties to request. PubChem renamed CanonicalSMILES -> ConnectivitySMILES;
# we request both spellings and normalize on read.
_PROPERTIES = [
    "MolecularWeight", "XLogP", "TPSA", "IUPACName",
    "ConnectivitySMILES", "CanonicalSMILES", "SMILES",
    "HBondDonorCount", "HBondAcceptorCount", "Complexity",
    "MolecularFormula",
]


def slugify(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.strip().lower()).strip("-")


def cache_path(name: str, cache_root: Optional[Path | str] = None) -> Path:
    return cache_dir(cache_root) / f"{slugify(name)}.json"


@dataclasses.dataclass
class Compound:
    """A cached PubChem compound (a thin view over the JSON cache)."""

    name: str
    cid: int
    molecular_weight: Optional[float]
    xlogp: Optional[float]
    tpsa: Optional[float]
    iupac_name: Optional[str]
    smiles: Optional[str]
    molecular_formula: Optional[str]
    hbond_donors: Optional[int]
    hbond_acceptors: Optional[int]
    raw: Dict
    png_path: Optional[Path]

    @property
    def lipophilic(self) -> Optional[bool]:
        """Overton's rule heuristic: XLogP > 0 partitions into the lipid core."""
        return None if self.xlogp is None else self.xlogp > 0.0

    @classmethod
    def from_cache(cls, data: Dict, png_path: Optional[Path]) -> "Compound":
        return cls(
            name=data.get("name"),
            cid=int(data.get("cid")),
            molecular_weight=_as_float(data.get("molecular_weight")),
            xlogp=_as_float(data.get("xlogp")),
            tpsa=_as_float(data.get("tpsa")),
            iupac_name=data.get("iupac_name"),
            smiles=data.get("smiles"),
            molecular_formula=data.get("molecular_formula"),
            hbond_donors=_as_int(data.get("hbond_donors")),
            hbond_acceptors=_as_int(data.get("hbond_acceptors")),
            raw=data,
            png_path=png_path if png_path and png_path.exists() else None,
        )


def _as_float(v) -> Optional[float]:
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _as_int(v) -> Optional[int]:
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


def _get(url: str, timeout: float = 30.0) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": "trech-pubchem/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310 (trusted host)
        return resp.read()


def fetch_compound(name: str, *, png: bool = True, timeout: float = 30.0,
                   cache_root: Optional[Path | str] = None) -> Compound:
    """Query PubChem for ``name`` and write the selected cache. Network call."""
    root = cache_dir(cache_root)
    root.mkdir(parents=True, exist_ok=True)
    enc = urllib.parse.quote(name)
    prop_url = f"{PUG}/compound/name/{enc}/property/{','.join(_PROPERTIES)}/JSON"
    payload = json.loads(_get(prop_url, timeout))
    props = payload["PropertyTable"]["Properties"][0]
    cid = int(props["CID"])

    smiles = (props.get("ConnectivitySMILES") or props.get("CanonicalSMILES")
              or props.get("SMILES"))
    record = {
        "name": name,
        "slug": slugify(name),
        "cid": cid,
        "molecular_weight": props.get("MolecularWeight"),
        "molecular_formula": props.get("MolecularFormula"),
        "xlogp": props.get("XLogP"),
        "tpsa": props.get("TPSA"),
        "iupac_name": props.get("IUPACName"),
        "smiles": smiles,
        "hbond_donors": props.get("HBondDonorCount"),
        "hbond_acceptors": props.get("HBondAcceptorCount"),
        "complexity": props.get("Complexity"),
        "provenance": {
            "source": "PubChem PUG-REST",
            "property_url": prop_url,
            "structure_png_url": f"{PUG}/compound/cid/{cid}/PNG",
            "fetched_at_utc": _dt.datetime.now(_dt.timezone.utc)
            .replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        },
    }

    png_path = root / f"{slugify(name)}.png"
    if png:
        png_bytes = _get(f"{PUG}/compound/cid/{cid}/PNG", timeout)
        png_path.write_bytes(png_bytes)
        record["structure_png"] = png_path.name

    cache_path(name, root).write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    return Compound.from_cache(record, png_path if png else None)


def load_compound(name: str, cache_root: Optional[Path | str] = None) -> Optional[Compound]:
    """Read a compound from the selected cache, then legacy cache (no network)."""
    root = cache_dir(cache_root)
    roots = [root]
    if root.resolve() != LEGACY_CACHE_DIR.resolve():
        roots.append(LEGACY_CACHE_DIR)
    path = None
    for candidate_root in roots:
        candidate = cache_path(name, candidate_root)
        if candidate.exists():
            root = candidate_root
            path = candidate
            break
    if path is None:
        return None
    data = json.loads(path.read_text(encoding="utf-8"))
    png = root / f"{slugify(name)}.png"
    return Compound.from_cache(data, png if png.exists() else None)
