"""The editable scenario model + loaders.

``SceneModel`` is Studio's in-memory truth for a scenario's geometry, materials, beams, and
run parameters. It is built from ``trech_viz_scene.json`` (``loader.py``). ``writer.py``
exports standalone transport-scene JS while preserving the full recorded config; callback
source and external model dependencies still require the original scenario.

Pure data + numpy — no Qt, no wgpu, no engine imports — so both the renderer and the UI can
depend on it without cycles.
"""

from .model import Beam, MaterialDef, RunParams, SceneModel, Shape, Vec3, VolumeNode
from .loader import scene_from_viz_json, scene_from_output_dir
from .writer import scene_to_config, scene_to_js

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
    "scene_to_config",
    "scene_to_js",
]
