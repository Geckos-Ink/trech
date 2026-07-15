"""CPU mesh generation for scene primitives.

Returns interleaved ``[px, py, pz, nx, ny, nz]`` float32 vertex buffers + uint32 index
buffers, ready to upload to wgpu. Tube meshes preserve both radii, including the inner wall
and annular end faces, so open vessels do not turn into solid cylinders in Studio.

All sizes are millimetres, matching the scene model.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Tuple

import numpy as np

from ..scene.model import Shape


@dataclass
class MeshData:
    vertices: np.ndarray  # (N, 6) float32: position(3) + normal(3)
    indices: np.ndarray   # (M,)   uint32

    @property
    def index_count(self) -> int:
        return int(self.indices.shape[0])


def box(size_mm: Tuple[float, float, float]) -> MeshData:
    """Axis-aligned box centred at origin with flat per-face normals."""
    hx, hy, hz = (max(s, 1e-6) * 0.5 for s in size_mm)
    # 6 faces * 4 verts. Each face: 4 corners with the face normal.
    faces = [
        # (+X)                                        normal
        ([(hx, -hy, -hz), (hx, hy, -hz), (hx, hy, hz), (hx, -hy, hz)], (1, 0, 0)),
        # (-X)
        ([(-hx, -hy, hz), (-hx, hy, hz), (-hx, hy, -hz), (-hx, -hy, -hz)], (-1, 0, 0)),
        # (+Y)
        ([(-hx, hy, -hz), (-hx, hy, hz), (hx, hy, hz), (hx, hy, -hz)], (0, 1, 0)),
        # (-Y)
        ([(-hx, -hy, hz), (-hx, -hy, -hz), (hx, -hy, -hz), (hx, -hy, hz)], (0, -1, 0)),
        # (+Z)
        ([(hx, -hy, hz), (hx, hy, hz), (-hx, hy, hz), (-hx, -hy, hz)], (0, 0, 1)),
        # (-Z)
        ([(-hx, -hy, -hz), (-hx, hy, -hz), (hx, hy, -hz), (hx, -hy, -hz)], (0, 0, -1)),
    ]
    verts = []
    idx = []
    for corners, normal in faces:
        base = len(verts)
        for c in corners:
            verts.append([*c, *normal])
        idx += [base, base + 1, base + 2, base, base + 2, base + 3]
    return MeshData(
        vertices=np.asarray(verts, dtype=np.float32),
        indices=np.asarray(idx, dtype=np.uint32),
    )


def sphere(radius_mm: float, rings: int = 12, sectors: int = 16) -> MeshData:
    """UV sphere (smooth normals). Placeholder resolution; refine in M1."""
    r = max(radius_mm, 1e-6)
    verts = []
    for i in range(rings + 1):
        v = i / rings
        theta = v * math.pi
        st, ct = math.sin(theta), math.cos(theta)
        for j in range(sectors + 1):
            u = j / sectors
            phi = u * 2.0 * math.pi
            sp, cp = math.sin(phi), math.cos(phi)
            n = (st * cp, ct, st * sp)
            verts.append([r * n[0], r * n[1], r * n[2], *n])
    idx = []
    row = sectors + 1
    for i in range(rings):
        for j in range(sectors):
            a = i * row + j
            b = a + row
            idx += [a, b, a + 1, a + 1, b, b + 1]
    return MeshData(
        vertices=np.asarray(verts, dtype=np.float32),
        indices=np.asarray(idx, dtype=np.uint32),
    )


def cylinder(
    radius_mm: float,
    length_mm: float,
    sectors: int = 32,
    inner_radius_mm: float = 0.0,
) -> MeshData:
    """Closed cylinder or annular tube along +Z with truthful inner geometry."""
    r = max(radius_mm, 1e-6)
    inner = max(0.0, min(float(inner_radius_mm), r - 1e-6))
    hz = max(length_mm, 1e-6) * 0.5
    sectors = max(int(sectors), 3)
    verts: list[list[float]] = []
    idx: list[int] = []

    def add_quad(corners, normals) -> None:
        base = len(verts)
        for corner, normal in zip(corners, normals):
            verts.append([*corner, *normal])
        idx.extend([base, base + 1, base + 2, base, base + 2, base + 3])

    def add_triangle(corners, normal) -> None:
        base = len(verts)
        for corner in corners:
            verts.append([*corner, *normal])
        idx.extend([base, base + 1, base + 2])

    for j in range(sectors):
        a0 = (j / sectors) * 2.0 * math.pi
        a1 = ((j + 1) / sectors) * 2.0 * math.pi
        c0, s0 = math.cos(a0), math.sin(a0)
        c1, s1 = math.cos(a1), math.sin(a1)

        # Outer wall, smooth radial normals.
        add_quad(
            [(r * c0, r * s0, -hz), (r * c0, r * s0, hz),
             (r * c1, r * s1, hz), (r * c1, r * s1, -hz)],
            [(c0, s0, 0.0), (c0, s0, 0.0),
             (c1, s1, 0.0), (c1, s1, 0.0)],
        )

        if inner > 0.0:
            # Inner wall faces the void. Separate vertices keep the opposite normals exact.
            add_quad(
                [(inner * c1, inner * s1, -hz), (inner * c1, inner * s1, hz),
                 (inner * c0, inner * s0, hz), (inner * c0, inner * s0, -hz)],
                [(-c1, -s1, 0.0), (-c1, -s1, 0.0),
                 (-c0, -s0, 0.0), (-c0, -s0, 0.0)],
            )
            add_quad(
                [(inner * c0, inner * s0, hz), (r * c0, r * s0, hz),
                 (r * c1, r * s1, hz), (inner * c1, inner * s1, hz)],
                [(0.0, 0.0, 1.0)] * 4,
            )
            add_quad(
                [(inner * c1, inner * s1, -hz), (r * c1, r * s1, -hz),
                 (r * c0, r * s0, -hz), (inner * c0, inner * s0, -hz)],
                [(0.0, 0.0, -1.0)] * 4,
            )
        else:
            add_triangle(
                [(0.0, 0.0, hz), (r * c0, r * s0, hz), (r * c1, r * s1, hz)],
                (0.0, 0.0, 1.0),
            )
            add_triangle(
                [(0.0, 0.0, -hz), (r * c1, r * s1, -hz), (r * c0, r * s0, -hz)],
                (0.0, 0.0, -1.0),
            )
    return MeshData(
        vertices=np.asarray(verts, dtype=np.float32),
        indices=np.asarray(idx, dtype=np.uint32),
    )


def for_shape(shape: Shape) -> MeshData:
    """Dispatch on a scene ``Shape`` to the right primitive."""
    t = (shape.type or "box").lower()
    if t == "sphere":
        return sphere(shape.outer_radius_mm or max(shape.size_mm) * 0.5 or 1.0)
    if t in ("tube", "cylinder"):
        radius = shape.outer_radius_mm or 1.0
        length = shape.length_mm or max(shape.size_mm) or 1.0
        return cylinder(radius, length, inner_radius_mm=shape.inner_radius_mm)
    # Default: box. Fall back to a small cube if extents are unset.
    size = shape.size_mm if any(shape.size_mm) else (10.0, 10.0, 10.0)
    return box(size)


def grid_lines(half_extent_mm: float, spacing_mm: float, y: float = 0.0) -> np.ndarray:
    """Ground grid as a flat (N, 3) float32 array of line-list endpoints (a rendering aid)."""
    half = max(half_extent_mm, spacing_mm)
    n = int(half / spacing_mm)
    pts = []
    for i in range(-n, n + 1):
        x = i * spacing_mm
        pts.append([x, y, -half])
        pts.append([x, y, half])
        pts.append([-half, y, x])
        pts.append([half, y, x])
    return np.asarray(pts, dtype=np.float32)
