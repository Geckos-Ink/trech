"""The wgpu real-time viewport (pure rendering).

Receives a ``SceneModel`` (+ trajectories, planned) and draws it with WebGPU/WGSL — Vulkan on
Linux/Windows, Metal on macOS, chosen by wgpu-native automatically. This layer never reads
engine files and never computes physics: it only turns a scene into pixels. Anything it draws
that the engine did not emit (the ground grid, placeholder meshes) is a labelled rendering
choice, per studio/AGENTS.md.

``WGPU_AVAILABLE`` reflects whether the wgpu import succeeded so the UI can fall back to a
message widget instead of failing to launch on a machine without a working GPU stack.
"""

from .camera import Camera
from .viewport import WGPU_AVAILABLE, create_viewport

__all__ = ["Camera", "WGPU_AVAILABLE", "create_viewport"]
