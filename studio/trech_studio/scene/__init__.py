"""The editable scenario model + loaders.

``SceneModel`` is Studio's in-memory truth for a scenario's geometry, materials, beams, and
run parameters. It is built from a ``trech_viz_scene.json`` today (``loader.py``); writing a
``SceneModel`` back out to a runnable scenario ``.js`` is the standing goal in ROADMAP M2.

Pure data + numpy — no Qt, no wgpu, no engine imports — so both the renderer and the UI can
depend on it without cycles.
"""

from .model import Beam, MaterialDef, RunParams, SceneModel, Shape, Vec3, VolumeNode
from .loader import scene_from_viz_json, scene_from_output_dir

__all__ = [
    "Vec3",
    "Shape",
    "VolumeNode",
    "MaterialDef",
    "Beam",
    "RunParams",
    "SceneModel",
    "scene_from_viz_json",
    "scene_from_output_dir",
]
