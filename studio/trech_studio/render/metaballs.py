"""CPU Gaussian-density surface reconstruction for particle playback.

This is a representation layer only: emitted particle centres are neither moved nor
interpolated.  A compact scalar field is reconstructed around them and its threshold boundary
is converted to a depth-tested mesh for Studio's existing WGSL surface shader.  The grid and
kernel parameters come from the scenario's ``render_surface`` hint.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import numpy as np

from .mesh import MeshData


@dataclass
class DensityGrid:
    values: np.ndarray
    origin_mm: np.ndarray
    spacing_mm: float


def gaussian_density_grid(
    positions_mm: np.ndarray,
    *,
    grid_spacing_mm: float,
    sigma_mm: float,
    clip_axis: str = "y",
    clip_radius_mm: Optional[float] = None,
    clip_min_mm: Optional[float] = None,
    clip_max_mm: Optional[float] = None,
) -> DensityGrid:
    """Splat unit Gaussian kernels onto a bounded regular grid."""
    points = np.asarray(positions_mm, dtype=np.float32)
    spacing = max(float(grid_spacing_mm), 0.05)
    sigma = max(float(sigma_mm), 0.05)
    if points.ndim != 2 or points.shape[1] < 3 or points.shape[0] == 0:
        return DensityGrid(
            values=np.empty((0, 0, 0), dtype=np.float32),
            origin_mm=np.zeros(3, dtype=np.float32), spacing_mm=spacing,
        )
    points = np.ascontiguousarray(points[:, :3], dtype=np.float32)
    support = 3.25 * sigma
    lo = np.floor((points.min(axis=0) - support) / spacing) * spacing
    hi = np.ceil((points.max(axis=0) + support) / spacing) * spacing

    axis = {"x": 0, "y": 1, "z": 2}.get((clip_axis or "y").lower(), 1)
    radial_axes = [index for index in range(3) if index != axis]
    if clip_radius_mm is not None and float(clip_radius_mm) > 0.0:
        radius = float(clip_radius_mm)
        for radial_axis in radial_axes:
            lo[radial_axis] = max(lo[radial_axis], -radius)
            hi[radial_axis] = min(hi[radial_axis], radius)
    if clip_min_mm is not None:
        lo[axis] = max(lo[axis], float(clip_min_mm))
    if clip_max_mm is not None:
        hi[axis] = min(hi[axis], float(clip_max_mm))
    shape = np.maximum(np.rint((hi - lo) / spacing).astype(np.int32) + 1, 2)
    values = np.zeros(tuple(int(value) for value in shape), dtype=np.float32)

    radius_cells = max(1, int(np.ceil(support / spacing)))
    inv_two_sigma2 = 0.5 / (sigma * sigma)
    for point in points:
        centre = np.rint((point - lo) / spacing).astype(np.int32)
        starts = np.maximum(centre - radius_cells, 0)
        stops = np.minimum(centre + radius_cells + 1, shape)
        coords = [
            lo[dim] + np.arange(starts[dim], stops[dim], dtype=np.float32) * spacing
            for dim in range(3)
        ]
        kernels = [np.exp(-((coord - point[dim]) ** 2) * inv_two_sigma2) for dim, coord in enumerate(coords)]
        values[
            starts[0]:stops[0], starts[1]:stops[1], starts[2]:stops[2]
        ] += (kernels[0][:, None, None] * kernels[1][None, :, None] *
              kernels[2][None, None, :]).astype(np.float32)

    if clip_radius_mm is not None and float(clip_radius_mm) > 0.0:
        coords = [lo[dim] + np.arange(shape[dim], dtype=np.float32) * spacing for dim in range(3)]
        radial2 = (
            coords[radial_axes[0]].reshape(
                tuple(shape[radial_axes[0]] if dim == radial_axes[0] else 1 for dim in range(3))
            ) ** 2 +
            coords[radial_axes[1]].reshape(
                tuple(shape[radial_axes[1]] if dim == radial_axes[1] else 1 for dim in range(3))
            ) ** 2
        )
        values *= (radial2 <= float(clip_radius_mm) ** 2)
    return DensityGrid(values=values, origin_mm=np.asarray(lo, dtype=np.float32), spacing_mm=spacing)


def density_surface_mesh(grid: DensityGrid, iso_level: float) -> MeshData:
    """Extract a smooth dependency-free marching-tetrahedra isosurface.

    Only cubes crossed by the threshold are expanded. Vertices and density-gradient normals are
    linearly interpolated on tetrahedral edges, avoiding the block silhouette of voxel faces.
    """
    density = np.asarray(grid.values, dtype=np.float32)
    if density.size == 0 or density.ndim != 3 or min(density.shape) < 2:
        return MeshData(np.empty((0, 6), np.float32), np.empty((0,), np.uint32))
    iso = max(float(iso_level), 1e-6)
    corner_offsets = np.asarray([
        [0, 0, 0], [1, 0, 0], [0, 1, 0], [1, 1, 0],
        [0, 0, 1], [1, 0, 1], [0, 1, 1], [1, 1, 1],
    ], dtype=np.float32)
    corner_slices = [
        tuple(slice(int(offset[dim]), density.shape[dim] - 1 + int(offset[dim]))
              for dim in range(3))
        for offset in corner_offsets
    ]
    corner_fields = [density[slices] for slices in corner_slices]
    active = np.minimum.reduce(corner_fields) < iso
    active &= np.maximum.reduce(corner_fields) >= iso
    cube_indices = np.argwhere(active)
    if cube_indices.shape[0] == 0:
        return MeshData(np.empty((0, 6), np.float32), np.empty((0,), np.uint32))
    spacing = float(grid.spacing_mm)
    bases = grid.origin_mm[None, :] + cube_indices.astype(np.float32) * spacing
    corner_values = np.stack([field[active] for field in corner_fields], axis=1)
    gradient_fields = np.gradient(density, spacing, edge_order=1)
    corner_gradients = np.stack([
        np.stack([gradient[slices][active] for gradient in gradient_fields], axis=1)
        for slices in corner_slices
    ], axis=1)
    tetrahedra = (
        (0, 1, 3, 7), (0, 3, 2, 7), (0, 2, 6, 7),
        (0, 6, 4, 7), (0, 4, 5, 7), (0, 5, 1, 7),
    )
    vertex_chunks = []
    index_chunks = []
    vertex_count = 0

    def edge(row_ids: np.ndarray, corner_a: int, corner_b: int):
        va = corner_values[row_ids, corner_a]
        vb = corner_values[row_ids, corner_b]
        fraction = np.clip((iso - va) / np.where(np.abs(vb - va) > 1e-8, vb - va, 1.0), 0.0, 1.0)
        offset = (corner_offsets[corner_a][None, :] + fraction[:, None] *
                  (corner_offsets[corner_b] - corner_offsets[corner_a])[None, :])
        points = bases[row_ids] + offset * spacing
        ga = corner_gradients[row_ids, corner_a]
        gb = corner_gradients[row_ids, corner_b]
        normals = -(ga + fraction[:, None] * (gb - ga))
        lengths = np.linalg.norm(normals, axis=1, keepdims=True)
        normals /= np.maximum(lengths, 1e-8)
        return points.astype(np.float32), normals.astype(np.float32)

    def add_triangles(points: np.ndarray, normals: np.ndarray) -> None:
        nonlocal vertex_count
        if points.shape[0] == 0:
            return
        packed = np.concatenate([points, normals], axis=2).reshape(-1, 6)
        count = packed.shape[0]
        vertex_chunks.append(np.ascontiguousarray(packed, dtype=np.float32))
        index_chunks.append(np.arange(vertex_count, vertex_count + count, dtype=np.uint32))
        vertex_count += count

    for tetra in tetrahedra:
        tetra_values = corner_values[:, tetra]
        tetra_inside = tetra_values >= iso
        counts = tetra_inside.sum(axis=1)
        # One vertex on one side of the surface: its three incident edges form a triangle.
        for singular_count in (1, 3):
            for singular in range(4):
                selector = (counts == singular_count) & (
                    tetra_inside[:, singular] if singular_count == 1 else ~tetra_inside[:, singular]
                )
                rows = np.flatnonzero(selector)
                if rows.size == 0:
                    continue
                others = [index for index in range(4) if index != singular]
                samples = [edge(rows, tetra[singular], tetra[other]) for other in others]
                points = np.stack([sample[0] for sample in samples], axis=1)
                normals = np.stack([sample[1] for sample in samples], axis=1)
                if singular_count == 3:
                    points = points[:, [0, 2, 1], :]
                    normals = normals[:, [0, 2, 1], :]
                add_triangles(points, normals)
        # Two inside/two outside produces a quadrilateral; split it without a bow-tie.
        for inside_a, inside_b in ((0, 1), (0, 2), (0, 3), (1, 2), (1, 3), (2, 3)):
            selector = (counts == 2) & tetra_inside[:, inside_a] & tetra_inside[:, inside_b]
            rows = np.flatnonzero(selector)
            if rows.size == 0:
                continue
            outside = [index for index in range(4) if index not in (inside_a, inside_b)]
            pairs = (
                (inside_a, outside[0]), (inside_a, outside[1]),
                (inside_b, outside[1]), (inside_b, outside[0]),
            )
            samples = [edge(rows, tetra[a], tetra[b]) for a, b in pairs]
            quad_points = np.stack([sample[0] for sample in samples], axis=1)
            quad_normals = np.stack([sample[1] for sample in samples], axis=1)
            add_triangles(quad_points[:, [0, 1, 2], :], quad_normals[:, [0, 1, 2], :])
            add_triangles(quad_points[:, [0, 2, 3], :], quad_normals[:, [0, 2, 3], :])

    if not vertex_chunks:
        return MeshData(np.empty((0, 6), np.float32), np.empty((0,), np.uint32))
    return MeshData(
        vertices=np.concatenate(vertex_chunks, axis=0),
        indices=np.concatenate(index_chunks, axis=0),
    )


def gaussian_surface_mesh(positions_mm: np.ndarray, surface) -> MeshData:
    """Convenience bridge from a playback ``ParticleSurface`` to a GPU-ready mesh."""
    grid = gaussian_density_grid(
        positions_mm,
        grid_spacing_mm=surface.grid_spacing_mm,
        sigma_mm=surface.sigma_mm,
        clip_axis=surface.clip_axis,
        clip_radius_mm=surface.clip_radius_mm,
        clip_min_mm=surface.clip_min_mm,
        clip_max_mm=surface.clip_max_mm,
    )
    return density_surface_mesh(grid, surface.iso_level)
