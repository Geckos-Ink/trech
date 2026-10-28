"""Probability-field display transforms only. No solver, new samples or normalization."""
from dataclasses import dataclass
import numpy as np


@dataclass(frozen=True)
class DensityDisplay:
    mode: str = 'volume'
    mass_percent: int = 90
    decades: float = 4.0
    opacity: float = 0.6
    axis: int = 2
    slice_fraction: float = 0.5
    overlay_id: str = ""
    cutaway: bool = False


def mass_level(density, percent):
    levels = (density.statistics or {}).get('mass_levels', [])
    return levels[max(0, min(len(levels)-1, int(percent)-1))] if levels else None


def transfer_range(density, display):
    maximum = float(np.max(np.abs(density.values)))
    maximum = max(maximum, 1e-30)
    high = np.log10(maximum)
    return high-float(display.decades), high


def density_colors(values, low, high, signed=False):
    """Same explicit log transfer palette as volume.wgsl (display, not material optics)."""
    values = np.asarray(values)
    t = np.clip((np.log10(np.maximum(np.abs(values), 1e-30))-low)/(high-low), 0, 1)
    if signed:
        positive = np.array([1., .43, .16])
        negative = np.array([.18, .66, 1.])
        colors = np.where((values >= 0)[..., None], positive, negative)*t[..., None]**.55
    else:
        stops = np.array([[.03,.025,.13],[.22,.08,.45],[.11,.52,.67],[.39,.84,.49],[1.,.91,.35]])
        x = t*4
        a = np.minimum(x.astype(int), 3)
        f = (x-a)[..., None]
        colors = stops[a]*(1-f)+stops[a+1]*f
    return np.asarray(colors, np.float32), t


def slice_data(density, display):
    axis = display.axis
    index = int(round(display.slice_fraction*(density.values.shape[axis]-1)))
    values = np.take(density.values, index, axis=axis)
    axes = [a for a in range(3) if a != axis]
    return values, axes, index, float(density.origin[axis]+index*density.spacing)
