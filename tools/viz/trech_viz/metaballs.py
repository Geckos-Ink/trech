"""Gaussian scalar fields for classic-viewer material-frame surfaces."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass
class DensityGrid:
    values: np.ndarray
    origin_mm: np.ndarray
    spacing_mm: float


def gaussian_density_grid(positions_mm: np.ndarray, surface) -> DensityGrid:
    """Reconstruct the scenario-declared density field without changing parcel centres."""
    points = np.asarray(positions_mm, dtype=np.float32)
    spacing = max(float(surface.grid_spacing_mm), 0.05)
    sigma = max(float(surface.sigma_mm), 0.05)
    if points.ndim != 2 or points.shape[0] == 0:
        return DensityGrid(np.empty((0, 0, 0), np.float32), np.zeros(3, np.float32), spacing)
    points = np.ascontiguousarray(points[:, :3], dtype=np.float32)
    support = 3.25 * sigma
    lo = np.floor((points.min(axis=0) - support) / spacing) * spacing
    hi = np.ceil((points.max(axis=0) + support) / spacing) * spacing
    axis = {"x": 0, "y": 1, "z": 2}.get(surface.clip_axis, 1)
    radial_axes = [index for index in range(3) if index != axis]
    if surface.clip_radius_mm is not None and surface.clip_radius_mm > 0.0:
        for radial_axis in radial_axes:
            lo[radial_axis] = max(lo[radial_axis], -surface.clip_radius_mm)
            hi[radial_axis] = min(hi[radial_axis], surface.clip_radius_mm)
    if surface.clip_min_mm is not None:
        lo[axis] = max(lo[axis], surface.clip_min_mm)
    if surface.clip_max_mm is not None:
        hi[axis] = min(hi[axis], surface.clip_max_mm)
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
    if surface.clip_radius_mm is not None and surface.clip_radius_mm > 0.0:
        coords = [lo[dim] + np.arange(shape[dim], dtype=np.float32) * spacing for dim in range(3)]
        radial2 = (
            coords[radial_axes[0]].reshape(
                tuple(shape[radial_axes[0]] if dim == radial_axes[0] else 1 for dim in range(3))
            ) ** 2 +
            coords[radial_axes[1]].reshape(
                tuple(shape[radial_axes[1]] if dim == radial_axes[1] else 1 for dim in range(3))
            ) ** 2
        )
        values *= radial2 <= surface.clip_radius_mm ** 2
    return DensityGrid(values=values, origin_mm=np.asarray(lo, np.float32), spacing_mm=spacing)
