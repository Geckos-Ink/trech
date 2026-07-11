"""Orbit camera + view/projection matrices (numpy, no external math dep).

Matrices are built for WebGPU's clip space: right-handed view, NDC depth in [0, 1] (unlike
OpenGL's [-1, 1]). Returned matrices are row-major and used column-vector style in the WGSL
shader as ``view_proj * vec4(pos, 1.0)``; we upload the transpose so the shader's
column-major ``mat4x4`` sees the right layout.
"""

from __future__ import annotations

import math
from typing import Tuple

import numpy as np

Vec3 = Tuple[float, float, float]


def _normalize(v: np.ndarray) -> np.ndarray:
    n = np.linalg.norm(v)
    return v / n if n > 1e-12 else v


def look_at(eye: np.ndarray, target: np.ndarray, up: np.ndarray) -> np.ndarray:
    """Right-handed view matrix (row-major)."""
    f = _normalize(target - eye)          # forward
    s = _normalize(np.cross(f, up))       # right
    u = np.cross(s, f)                    # true up
    m = np.eye(4, dtype=np.float32)
    m[0, :3] = s
    m[1, :3] = u
    m[2, :3] = -f
    m[0, 3] = -np.dot(s, eye)
    m[1, 3] = -np.dot(u, eye)
    m[2, 3] = np.dot(f, eye)
    return m


def perspective_wgpu(fov_y_rad: float, aspect: float, near: float, far: float) -> np.ndarray:
    """Perspective projection for WebGPU clip space (z in [0, 1]), row-major."""
    f = 1.0 / math.tan(fov_y_rad * 0.5)
    aspect = max(aspect, 1e-6)
    m = np.zeros((4, 4), dtype=np.float32)
    m[0, 0] = f / aspect
    m[1, 1] = f
    m[2, 2] = far / (near - far)
    m[2, 3] = (far * near) / (near - far)
    m[3, 2] = -1.0
    return m


class Camera:
    """Turntable/orbit camera around a target point."""

    def __init__(self) -> None:
        self.target = np.zeros(3, dtype=np.float32)
        self.distance = 300.0
        self.yaw = math.radians(45.0)      # around world up (+Y)
        self.pitch = math.radians(25.0)    # elevation
        self.fov_y = math.radians(45.0)
        self.near = 0.5
        self.far = 100000.0
        self._up = np.array([0.0, 1.0, 0.0], dtype=np.float32)

    # --- interaction --------------------------------------------------------------------

    def orbit(self, dyaw: float, dpitch: float) -> None:
        self.yaw += dyaw
        limit = math.radians(89.0)
        self.pitch = max(-limit, min(limit, self.pitch + dpitch))

    def dolly(self, factor: float) -> None:
        """Multiplicative zoom (wheel). factor < 1 moves closer."""
        self.distance = max(1e-2, self.distance * factor)

    def pan(self, dx: float, dy: float) -> None:
        """Pan the target in the camera's screen plane; dx/dy are in world units."""
        right, up, _ = self._basis()
        self.target = self.target + right * dx + up * dy

    def fit_bounds(self, lo: Vec3, hi: Vec3) -> None:
        lo_a = np.asarray(lo, dtype=np.float32)
        hi_a = np.asarray(hi, dtype=np.float32)
        self.target = (lo_a + hi_a) * 0.5
        radius = float(np.linalg.norm(hi_a - lo_a) * 0.5) or 1.0
        # Distance so the bounding sphere fits the vertical FOV, with margin.
        self.distance = radius / math.tan(self.fov_y * 0.5) * 1.4

    # --- matrices -----------------------------------------------------------------------

    def eye(self) -> np.ndarray:
        cp = math.cos(self.pitch)
        offset = np.array(
            [
                math.cos(self.yaw) * cp,
                math.sin(self.pitch),
                math.sin(self.yaw) * cp,
            ],
            dtype=np.float32,
        )
        return self.target + offset * self.distance

    def _basis(self) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
        eye = self.eye()
        forward = _normalize(self.target - eye)
        right = _normalize(np.cross(forward, self._up))
        up = np.cross(right, forward)
        return right, up, forward

    def view_matrix(self) -> np.ndarray:
        return look_at(self.eye(), self.target, self._up)

    def view_proj(self, aspect: float) -> np.ndarray:
        proj = perspective_wgpu(self.fov_y, aspect, self.near, self.far)
        return (proj @ self.view_matrix()).astype(np.float32)
