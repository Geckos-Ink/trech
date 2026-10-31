"""Validate and display recorded regular scalar grids; no field solver or extrapolation."""
import math
import numpy as np


def scalar_grid(raw, up_axis):
    from .probability import ScalarDensity
    from .density import DensityDisplay
    if not isinstance(raw, dict) or raw.get('schema') != 'trech_scalar_grid_v1':
        raise ValueError('Unsupported scalar grid')
    shape = raw['shape']
    if (len(shape) != 3 or any(type(n) is not int or n < 2 for n in shape)
            or math.prod(shape) > 1000000 or raw.get('order') != 'x_fastest'):
        raise ValueError('Invalid scalar grid shape/order')
    values = np.asarray(raw['values'], dtype=np.float64)
    origin = np.asarray(raw['origin'], dtype=np.float64)
    spacing = float(raw['spacing'])
    mask = np.asarray(raw['active_mask'])
    if (values.shape != (math.prod(shape),) or not np.all(np.isfinite(values))
            or origin.shape != (3,) or not np.all(np.isfinite(origin))
            or not math.isfinite(spacing) or spacing <= 0 or mask.dtype != np.bool_
            or mask.shape != values.shape or not np.any(mask)):
        raise ValueError('Invalid scalar grid data/calibration')
    if not all(isinstance(raw.get(k), str) and raw[k].strip() for k in ('unit', 'source')):
        raise ValueError('Scalar unit and source must be explicit')
    display = raw['display']
    mode = display['mode']
    low, high, opacity, iso, fraction = [float(display[k]) for k in ('low','high','opacity','isovalue','fraction')]
    axis = 'xyz'.index(display['axis'])
    if (mode not in ('volume','slice','surface') or not all(map(math.isfinite,(low,high,opacity,iso,fraction)))
            or high <= low or not 0 <= opacity <= 1 or not 0 <= fraction <= 1):
        raise ValueError('Invalid scalar display declaration')
    if mode == 'surface' and iso <= 0:
        raise ValueError('Surface isovalue must be positive')
    values = np.where(mask, values, 0).reshape(shape, order='F')
    mask = mask.reshape(shape, order='F')
    if up_axis == 'z':
        # Existing material-frame mapping is (x,z,-y).
        values = values.transpose(0,2,1)[:,:,::-1]
        mask = mask.transpose(0,2,1)[:,:,::-1]
        origin = np.array([origin[0],origin[2],-origin[1]-(shape[1]-1)*spacing])
        axis = [0,2,1][axis]
        if display['axis'] == 'y': fraction = 1-fraction
    elif up_axis != 'y':
        raise ValueError('Scalar grids currently support y/z up axes')
    density = ScalarDensity(values, origin, spacing, iso, raw['unit'], raw['source'])
    density.quantity = 'scalar'
    density.scalar_range = (low, high)
    density.active_mask = mask
    density.rgba = (.25,.65,.95,opacity)
    return density, DensityDisplay(mode=mode,opacity=opacity,axis=axis,slice_fraction=fraction)


def recorded_camera(raw):
    if raw is None: return None
    recorded_projection(raw)
    yaw, pitch = float(raw['yaw_deg']), float(raw['pitch_deg'])
    if not math.isfinite(yaw) or not math.isfinite(pitch) or not -89 <= pitch <= 89:
        raise ValueError('Invalid recorded camera')
    return yaw, pitch


def recorded_projection(raw):
    projection = 'perspective' if raw is None else raw.get('projection', 'perspective')
    if projection not in ('perspective', 'orthographic'):
        raise ValueError('Invalid recorded camera projection')
    return projection
