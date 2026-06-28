"""TRECH PubChem helper: fetch + cache substance properties and 2D structures.

PubChem data is fetched into a build-local cache by default
(``build/pubchem_cache``), or into ``--cache-dir`` / ``TRECH_PUBCHEM_CACHE_DIR``
when set, so validation/runtime scenarios can use current records without
committing new blobs. ``data/pubchem`` remains a read-only legacy fallback.
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
