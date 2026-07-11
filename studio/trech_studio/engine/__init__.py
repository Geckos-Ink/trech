"""Engine bridge — the ONLY layer in Studio that talks to the TRECH engine binary.

Nothing outside this package should shell out to `trech` or read engine output files
directly. Keeping that boundary means the rest of Studio depends on typed Python objects
(`RunResult`, snapshots, `SceneModel`) instead of on the on-disk JSONL layout.
"""

from .locator import EngineLocation, locate_engine
from .outputs import RunResult, load_run_result

__all__ = [
    "EngineLocation",
    "locate_engine",
    "RunResult",
    "load_run_result",
]
