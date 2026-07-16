"""Pure Gaussian-density surface tests (no Qt/GPU)."""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from trech_studio.render.metaballs import density_surface_mesh, gaussian_density_grid  # noqa: E402


def test_nearby_parcels_merge_into_one_density_bridge() -> None:
    points = np.asarray([[-1.0, 0.0, 0.0], [1.0, 0.0, 0.0]], dtype=np.float32)
    original = points.copy()
    grid = gaussian_density_grid(
        points, grid_spacing_mm=0.5, sigma_mm=1.2,
        clip_axis="y", clip_radius_mm=10.0,
    )
    midpoint = np.rint((np.zeros(3) - grid.origin_mm) / grid.spacing_mm).astype(int)
    assert grid.values[tuple(midpoint)] > 0.52
    mesh = density_surface_mesh(grid, 0.52)
    assert mesh.index_count > 0 and mesh.vertices.shape[1] == 6
    assert np.array_equal(points, original)  # representation never moves emitted centres


def test_surface_grid_precision_is_independent_of_particle_state() -> None:
    points = np.asarray([[0.0, 0.0, 0.0], [2.0, 0.0, 0.0]], dtype=np.float32)
    coarse = density_surface_mesh(gaussian_density_grid(
        points, grid_spacing_mm=1.0, sigma_mm=1.5,
    ), 0.52)
    fine = density_surface_mesh(gaussian_density_grid(
        points, grid_spacing_mm=0.5, sigma_mm=1.5,
    ), 0.52)
    assert fine.index_count > coarse.index_count > 0
    assert np.array_equal(points, [[0.0, 0.0, 0.0], [2.0, 0.0, 0.0]])


def test_cylindrical_clip_bounds_density() -> None:
    points = np.asarray([[4.8, 0.0, 0.0]], dtype=np.float32)
    grid = gaussian_density_grid(
        points, grid_spacing_mm=0.5, sigma_mm=1.2,
        clip_axis="y", clip_radius_mm=5.0, clip_min_mm=-2.0, clip_max_mm=2.0,
    )
    coords = [grid.origin_mm[i] + np.arange(grid.values.shape[i]) * grid.spacing_mm
              for i in range(3)]
    radial2 = coords[0][:, None, None] ** 2 + coords[2][None, None, :] ** 2
    assert np.all(grid.values[np.broadcast_to(radial2 > 25.0, grid.values.shape)] == 0.0)
