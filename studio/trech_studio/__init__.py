"""TRECH Studio — real-time 3D scenario editor, simulation viewer, and code editor.

Studio is a *client* of the TRECH engine, never a second physics engine: everything it
draws comes from a real `trech run` output directory or a live `trech lab` session, parsed
from the documented JSONL/JSON outputs (see `docs/output_schema.md` at the repo root).

Package layers (import only downward: ui -> scene/engine/render):

- ``trech_studio.engine`` : the only code that talks to the engine binary.
- ``trech_studio.scene``  : the editable scenario model + loader.
- ``trech_studio.render`` : the wgpu real-time viewport (pure rendering).
- ``trech_studio.ui``     : PySide6 panels (glue only).
"""

__version__ = "0.1.0"
__all__ = ["__version__"]
