"""PySide6 panels — the editor shell. Glue only: no physics, no direct engine file IO.

Every panel talks to the rest of Studio through the ``scene``/``engine``/``render`` layers,
never around them. Only ``app.py`` imports ``ui``.
"""

from .main_window import StudioWindow

__all__ = ["StudioWindow"]
