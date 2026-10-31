"""Grouped observer material geometry. No phase inference, motion or state updates.

Classes come from a recorded cell grid; parcel groups name explicit point indices and
Gaussian display kernels. Neighbouring classes are never pooled by colour or proximity.
"""
from dataclasses import dataclass
from typing import Any

import numpy as np

from .metaballs import DensityGrid, density_surface_mesh, gaussian_surface_mesh


@dataclass
class PhaseGrid:
    origin: np.ndarray
    spacing: np.ndarray
    values: np.ndarray
    classes: tuple
    replaces_points: bool


@dataclass
class MaterialGroup:
    label: str
    phase: str
    indices: np.ndarray
    rgba: np.ndarray
    surface: Any


def phase_grid(raw, up_axis):
    if raw is None:
        return None
    try:
        shape = raw['shape']
        if (len(shape) != 3 or any(type(n) is not int or n < 1 for n in shape)
                or np.prod(shape, dtype=np.float64) > 1000000):
            raise ValueError('invalid shape')
        values = np.asarray(raw['values'], dtype=np.float64)
        origin = np.asarray(raw['origin'], dtype=np.float32)
        spacing = np.broadcast_to(np.asarray(raw['spacing'], dtype=np.float32), (3,)).copy()
        if (values.shape != (int(np.prod(shape)),) or not np.all(np.isfinite(values))
                or not np.all(values == np.floor(values)) or origin.shape != (3,)
                or not np.all(np.isfinite(origin)) or not np.all(np.isfinite(spacing))
                or np.any(spacing <= 0)):
            raise ValueError('invalid cell data/calibration')
        classes, ids = [], set()
        for entry in raw['classes']:
            cid = entry['id']
            rgba = np.asarray(entry['color_rgba'], dtype=np.float32)
            style = entry.get('style', 'solid')
            if (type(cid) is not int or cid in ids or rgba.shape != (4,)
                    or not np.all(np.isfinite(rgba)) or np.any((rgba < 0) | (rgba > 1))
                    or style not in ('solid', 'liquid', 'gas', 'grains')):
                raise ValueError('invalid class')
            ids.add(cid)
            classes.append(dict(id=cid, label=str(entry.get('label', cid)), rgba=rgba, style=style))
        if not classes or not set(values).issubset(ids):
            raise ValueError('undeclared class')
        values = values.reshape(shape, order='F').copy()
        order = {'y': (0, 1, 2), 'z': (0, 2, 1), 'x': (1, 0, 2)}[up_axis]
        return PhaseGrid(origin[list(order)].copy(), spacing[list(order)].copy(),
                         values.transpose(order).copy(), tuple(classes),
                         raw.get('replaces_points') is True)
    except (KeyError, TypeError, ValueError, OverflowError) as exc:
        raise ValueError(f'Invalid material grid: {exc}') from exc


def _refine(values, factor):
    """Trilinear display sampling; cell identities and calibrated extents are unchanged."""
    result = values
    for axis in range(3):
        old = np.arange(result.shape[axis])
        new = np.linspace(0, len(old) - 1, (len(old) - 1) * factor + 1)
        result = np.apply_along_axis(lambda row: np.interp(new, old, row), axis, result)
    return result.astype(np.float32)


def material_meshes(frame, detail=1.0, max_cells=500000, merge_radius_scale=1.0):
    """(mesh, RGBA) layers, limited display sampling, and the retained point mask."""
    layers, descriptions = [], []
    keep = np.ones(len(frame.positions), dtype=bool)
    grid = frame.material_grid
    if grid is not None:
        factor = max(1, min(16, int(round(2 * detail))))
        while factor > 1 and np.prod((np.asarray(grid.values.shape) + 1) * factor + 1) > max_cells:
            factor -= 1
        for cls in grid.classes:
            indicator = grid.values == cls['id']
            if not np.any(indicator):
                continue
            # Zero padding closes outer boundaries, including a completely full grid.
            values = _refine(np.pad(indicator.astype(np.float32), 1), factor)
            mesh = density_surface_mesh(DensityGrid(values, grid.origin - grid.spacing,
                                                    grid.spacing / factor), 0.5)
            layers.append((mesh, cls['rgba']))
            descriptions.append(dict(label=cls['label'], phase=cls['style'],
                                     cells=int(indicator.sum()), opacity=float(cls['rgba'][3]),
                                     display_spacing_native=(grid.spacing / factor).tolist()))
        if grid.replaces_points:
            keep[:] = False
    for group in frame.material_groups:
        keep[group.indices] = False
        if not len(group.indices):
            continue
        from dataclasses import replace
        surface = replace(group.surface, sigma_mm=group.surface.sigma_mm * merge_radius_scale)
        # The original neck samples describe the authored observer topology. Do not extend
        # those links when a user overrides Gaussian width for inspection.
        if merge_radius_scale != 1:
            surface = replace(surface, neck_mode='none')
        points = frame.positions[group.indices]
        spacing = max(0.05, surface.grid_spacing_mm / detail)
        span = np.ptp(points, axis=0) + 6.5 * surface.sigma_mm
        for _ in range(16):
            cells = np.prod(np.ceil(span / spacing) + 3)
            if cells <= max_cells:
                break
            spacing *= max(1.05, (cells / max_cells) ** (1 / 3))
        mesh = gaussian_surface_mesh(points, replace(surface, grid_spacing_mm=spacing))
        layers.append((mesh, group.rgba))
        descriptions.append(dict(label=group.label, phase=group.phase, points=len(points),
                                 opacity=float(group.rgba[3]), grid_spacing_mm=float(spacing),
                                 sigma_mm=float(surface.sigma_mm)))
    return layers, descriptions, keep


def colored_material_mesh(layers):
    """Pack separate material boundaries together for global triangle alpha sorting."""
    vertices, indices, offset = [], [], 0
    for mesh, rgba in layers:
        if not mesh.index_count:
            continue
        vertices.append(np.column_stack((mesh.vertices, np.tile(rgba, (len(mesh.vertices), 1)))))
        indices.append(mesh.indices + offset)
        offset += len(mesh.vertices)
    return (np.ascontiguousarray(np.concatenate(vertices), dtype=np.float32),
            np.ascontiguousarray(np.concatenate(indices), dtype=np.uint32)) if vertices else (
                np.empty((0, 10), np.float32), np.empty(0, np.uint32))


def sorted_triangles(vertices, indices, eye, target):
    """Stable far-to-near triangle order in view depth, recomputed when the camera moves."""
    triangles = indices.reshape(-1, 3)
    centres = vertices[triangles, :3].mean(axis=1)
    forward = np.asarray(target) - np.asarray(eye)
    return np.ascontiguousarray(triangles[np.argsort(-(centres @ forward), kind='stable')].ravel())
