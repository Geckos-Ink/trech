"""TRECH PubChem helper: fetch + cache substance properties and 2D structures.

PubChem data can be fetched into a build-local cache with ``--cache-dir`` or
``TRECH_PUBCHEM_CACHE_DIR`` so validation/runtime scenarios can use current
records without committing new blobs. ``data/pubchem`` remains a legacy fallback.
"""

from .client import (
    CACHE_DIR,
    Compound,
    fetch_compound,
    load_compound,
    cache_path,
    cache_dir,
)

__all__ = [
    "CACHE_DIR",
    "Compound",
    "fetch_compound",
    "load_compound",
    "cache_path",
    "cache_dir",
]
