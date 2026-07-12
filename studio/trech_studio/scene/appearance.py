"""Derive a material's *look* from the engine's optical physics — honestly.

Studio is a client, never a second physics engine (studio/AGENTS.md). So the colour, the
transparency and the glossiness of a material are **not invented here**: they are read off the
run's ``derived_optics`` — the same Geant4-derived quantities the engine already emits
(``mean_refractive_index`` with visible-band dispersion, per-wavelength ``absorption_length_mm``
/ ``scatter_length_mm``) — and turned into RGBA + surface parameters by textbook optics:

* **Reflectivity** ("how does it reflect photons?") ← the Fresnel reflectance at normal
  incidence ``R0 = ((n-1)/(n+1))**2``. Water (n≈1.33) reflects ~2%, glass (n≈1.47) ~3.6%; the
  renderer turns ``R0`` into a specular highlight so glass reads glassy.
* **Transparency** ("is the glass transparent?") ← Beer–Lambert transmittance through the
  volume's *own thickness*: ``T = exp(-path / attenuation_length)``. A clear medium
  (attenuation length ≫ thickness) transmits ~everything → we render it barely-there, visible
  mostly by its Fresnel edges, exactly like real glass.
* **Colour** ("does water tend to be blue?") ← integrate the per-wavelength transmittance
  against the CIE 1931 colour-matching functions, **normalised against a flat spectrum** so a
  non-absorbing medium comes out neutral and a medium that eats long wavelengths comes out
  blue. The tint therefore emerges only when the physics resolves differential absorption.

Honest scope: Geant4's EM optical base models refraction and photoelectric/Compton/Rayleigh
attenuation, **not** the molecular vibrational overtones that give bulk water its faint blue.
So for the shipped pure-water/glass runs the honest result is a *colourless clear* medium
distinguished only by refractive index — and this module says so (``note``). A scenario that
*wants* a more legible look (a tinted dielectric, a highlighted collector) declares it as an
authored render hint (see ``scene.model.RenderHint``), never as physics.

Pure module: numpy only, no Qt/wgpu/engine imports, so it is unit-testable in isolation.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional, Sequence, Tuple

import numpy as np

Vec3 = Tuple[float, float, float]

# Sentinel the engine writes for "effectively transparent at this band" (1/mu -> huge).
_TRANSPARENT_MM = 1.0e6

# Display-alpha envelope. Physically-clear media get MIN_ALPHA (a faint body) so the viewport
# still shows a silhouette; the Fresnel specular does the rest. Fully-absorbing media approach
# MAX_ALPHA. Both are labelled rendering choices, not physics (see ``note``).
_MIN_ALPHA = 0.08
_MAX_ALPHA = 0.97


# --- CIE 1931 colour matching (Wyman et al. 2013 multi-lobe analytic fit) -----------------

def _g(x: np.ndarray, mu: float, s1: float, s2: float) -> np.ndarray:
    """Asymmetric Gaussian: sigma s1 below the peak, s2 above (Wyman's ``g`` lobe)."""
    s = np.where(x < mu, s1, s2)
    t = (x - mu) / s
    return np.exp(-0.5 * t * t)


def _cie_xyz(nm: np.ndarray) -> np.ndarray:
    """Approximate CIE 1931 2° x̄/ȳ/z̄ at wavelengths ``nm`` -> array shape (len, 3)."""
    xbar = 1.056 * _g(nm, 599.8, 37.9, 31.0) + 0.362 * _g(nm, 442.0, 16.0, 26.7) \
        - 0.065 * _g(nm, 501.1, 20.4, 26.2)
    ybar = 0.821 * _g(nm, 568.8, 46.9, 40.5) + 0.286 * _g(nm, 530.9, 16.3, 31.1)
    zbar = 1.217 * _g(nm, 437.0, 11.8, 36.0) + 0.681 * _g(nm, 459.0, 26.0, 13.8)
    return np.stack([xbar, ybar, zbar], axis=1)


# XYZ -> linear sRGB (D65). We only ever use it on *ratios* (transmitted / reference) so the
# absolute white point is unimportant; normalisation makes a flat spectrum land on neutral.
_XYZ_TO_RGB = np.array([
    [3.2406, -1.5372, -0.4986],
    [-0.9689, 1.8758, 0.0415],
    [0.0557, -0.2040, 1.0570],
], dtype=np.float64)

# Fixed visible sampling grid + precomputed CMFs and the flat-spectrum reference integral.
_GRID_NM = np.arange(390.0, 731.0, 5.0)
_CMF = _cie_xyz(_GRID_NM)                       # (N, 3)
_REF_XYZ = _CMF.sum(axis=0)                     # ∫ 1·cmf  (equal-energy illuminant)
_REF_RGB = _XYZ_TO_RGB @ _REF_XYZ


# --- spectrum → attenuation ---------------------------------------------------------------

@dataclass
class OpticSample:
    """One visible-band optics sample from ``derived_optics.samples`` (engine-emitted)."""

    wavelength_nm: float
    refractive_index: float = 1.0
    absorption_length_mm: float = _TRANSPARENT_MM
    scatter_length_mm: float = _TRANSPARENT_MM
    extinction_k: float = 0.0


def _mu_per_mm(abs_len_mm: float, scat_len_mm: float) -> float:
    """Total attenuation coefficient 1/mm from absorption + scattering lengths."""
    mu = 0.0
    if 0.0 < abs_len_mm < _TRANSPARENT_MM:
        mu += 1.0 / abs_len_mm
    if 0.0 < scat_len_mm < _TRANSPARENT_MM:
        mu += 1.0 / scat_len_mm
    return mu


def _transmittance_grid(spectrum: Sequence[OpticSample], path_mm: float) -> Optional[np.ndarray]:
    """Beer–Lambert transmittance T(λ) on ``_GRID_NM`` from the sampled spectrum, or None.

    ``None`` means the spectrum carried no wavelength-resolved attenuation (all transparent);
    the caller then falls back to the scalar means. Returns values in [0, 1].
    """
    usable = [s for s in spectrum if s.wavelength_nm > 0.0]
    if not usable:
        return None
    usable.sort(key=lambda s: s.wavelength_nm)
    wl = np.array([s.wavelength_nm for s in usable], dtype=np.float64)
    mu = np.array([_mu_per_mm(s.absorption_length_mm, s.scatter_length_mm) for s in usable])
    if not np.any(mu > 0.0):
        return None
    mu_grid = np.interp(_GRID_NM, wl, mu, left=mu[0], right=mu[-1])
    return np.exp(-np.clip(mu_grid * path_mm, 0.0, 60.0))


# --- result -------------------------------------------------------------------------------

@dataclass
class MaterialAppearance:
    """A material's derived look: an RGBA to draw plus surface params for the shader.

    Every field traces to engine optics (or is an explicit, labelled rendering choice).
    """

    base_rgb: Vec3 = (0.72, 0.74, 0.78)   # transmission tint (neutral when clear)
    display_alpha: float = 0.85           # rendering-choice alpha from luminous transmittance
    reflectance: float = 0.0              # Fresnel R0 at normal incidence (specular strength)
    gloss: float = 0.0                    # 0..1 tightness of the highlight (from n)
    transmittance: float = 1.0            # luminous transmittance through the volume (0..1)
    turbidity: float = 0.0                # 0..1 haze from scattering vs absorption
    refractive_index: float = 1.0
    transparent: bool = True
    available: bool = False               # were derived optics present at all?
    descriptor: str = "no derived optics"
    note: str = ""

    def rgba(self) -> Tuple[float, float, float, float]:
        r, g, b = self.base_rgb
        return (float(r), float(g), float(b), float(self.display_alpha))


def _fresnel_r0(n: float) -> float:
    if n <= 0.0:
        return 0.0
    r = (n - 1.0) / (n + 1.0)
    return float(r * r)


def _hue_word(rgb: Vec3) -> str:
    r, g, b = rgb
    mx, mn = max(rgb), min(rgb)
    if mx - mn < 0.06:
        return "clear"
    if b >= r and b >= g:
        return "blue-tinted"
    if r >= g and r >= b:
        return "amber" if g > b else "red-tinted"
    return "green-tinted"


def derive_appearance(
    *,
    refractive_index: Optional[float],
    absorption_length_mm: Optional[float],
    scatter_length_mm: Optional[float],
    spectrum: Sequence[OpticSample] = (),
    path_mm: float = 10.0,
    optics_available: bool = True,
    fallback_rgb: Vec3 = (0.72, 0.74, 0.78),
) -> MaterialAppearance:
    """Turn engine-emitted optics into a :class:`MaterialAppearance`.

    ``path_mm`` is the volume's own characteristic thickness (see ``scene.model``), so the same
    material renders more opaque in a thick body than a thin one — Beer–Lambert, honestly.
    """
    if not optics_available:
        return MaterialAppearance(base_rgb=fallback_rgb, available=False,
                                  descriptor="no derived optics for this run")

    n = float(refractive_index or 1.0)
    path = max(float(path_mm), 1e-3)
    reflectance = _fresnel_r0(n)
    gloss = float(np.clip((n - 1.0) / 0.6, 0.0, 1.0))

    # Colour + luminous transmittance from the spectrum when it resolves attenuation, else the
    # scalar means. A flat spectrum divides out to neutral, so clear media stay colourless.
    grid_t = _transmittance_grid(spectrum, path)
    if grid_t is not None:
        trans_xyz = (grid_t[:, None] * _CMF).sum(axis=0)
        trans_rgb = _XYZ_TO_RGB @ trans_xyz
        ratio = np.clip(trans_rgb / np.where(_REF_RGB != 0.0, _REF_RGB, 1.0), 0.0, 1.0)
        # Luminous transmittance = ratio of the Y (luminance) integrals.
        lum_t = float(np.clip(trans_xyz[1] / _REF_XYZ[1], 0.0, 1.0))
        # Keep the brightest channel near the transmittance so a clear medium reads white, not
        # a dim grey; the *hue* (channel balance) is what carries the physics.
        mx = float(max(ratio)) or 1.0
        base_rgb = tuple(float(c / mx) for c in ratio)  # normalized hue
    else:
        mu = _mu_per_mm(float(absorption_length_mm or _TRANSPARENT_MM),
                        float(scatter_length_mm or _TRANSPARENT_MM))
        lum_t = float(np.exp(-min(mu * path, 60.0)))
        base_rgb = (1.0, 1.0, 1.0)

    # Turbidity: fraction of extinction that is scattering rather than absorption (milkiness).
    abs_mu = 0.0 if not absorption_length_mm or absorption_length_mm >= _TRANSPARENT_MM \
        else 1.0 / absorption_length_mm
    scat_mu = 0.0 if not scatter_length_mm or scatter_length_mm >= _TRANSPARENT_MM \
        else 1.0 / scatter_length_mm
    turbidity = float(scat_mu / (abs_mu + scat_mu)) if (abs_mu + scat_mu) > 0.0 else 0.0

    opacity_phys = 1.0 - lum_t
    display_alpha = _MIN_ALPHA + (_MAX_ALPHA - _MIN_ALPHA) * opacity_phys
    transparent = lum_t > 0.6

    clarity = "transparent" if lum_t > 0.85 else "translucent" if lum_t > 0.4 else "opaque"
    hue = _hue_word(base_rgb)
    finish = f"glossy (n={n:.3g})" if reflectance > 0.03 else f"matte (n={n:.3g})"
    descriptor = f"{clarity} · {hue} · {finish}"

    note = (
        "Look derived from Geant4 EM optics (refractive index + absorption/scatter spectra); "
        "opacity is Beer–Lambert over the volume thickness, reflectivity is Fresnel(n). "
        "On-screen alpha is floored for visibility. The EM base does not model molecular "
        "vibrational bands, so a colourless clear medium is the honest result unless the "
        "spectrum resolves a tint."
    )

    return MaterialAppearance(
        base_rgb=base_rgb,
        display_alpha=float(np.clip(display_alpha, _MIN_ALPHA, _MAX_ALPHA)),
        reflectance=reflectance,
        gloss=gloss,
        transmittance=lum_t,
        turbidity=turbidity,
        refractive_index=n,
        transparent=transparent,
        available=True,
        descriptor=descriptor,
        note=note,
    )
