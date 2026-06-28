"""TRECH PubChem helper: fetch + cache substance properties and 2D structures.

PubChem is queried *once* and the result is committed under ``data/pubchem/`` so
that scenarios, validation references and visualization stay reproducible and
offline. Nothing here runs inside the deterministic Geant4/hook path; it is an
authoring/validation/visualization helper only.
"""

from .client import (
    CACHE_DIR,
    Compound,
    fetch_compound,
    load_compound,
    cache_path,
)

__all__ = [
    "CACHE_DIR",
    "Compound",
    "fetch_compound",
    "load_compound",
    "cache_path",
]
