"""Unit tests for the physics-derived material appearance (no Qt, no GPU).

These pin the honesty claims of ``scene/appearance.py`` + the ``scene/model`` glue:
transparency from Beer–Lambert, reflectivity from Fresnel(n), a transmission tint that only
appears when the spectrum resolves differential absorption (so a flat/clear spectrum stays
colourless), and the authored ``viz_*`` render-hint overrides.

Run: ``python tests/test_appearance.py``
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from trech_studio.scene.appearance import (  # noqa: E402
    OpticSample,
    derive_appearance,
)
from trech_studio.scene.model import (  # noqa: E402
    MaterialDef,
    RenderHint,
    SceneModel,
    Shape,
    VolumeNode,
)

_TRANSPARENT = 1.0e6


def _clear_spectrum(n: float = 1.33):
    """A visible spectrum with no attenuation (all lengths = transparent sentinel)."""
    return [
        OpticSample(wavelength_nm=wl, refractive_index=n,
                    absorption_length_mm=_TRANSPARENT, scatter_length_mm=_TRANSPARENT)
        for wl in (420.0, 480.0, 540.0, 600.0, 660.0, 720.0)
    ]


def test_clear_medium_is_transparent_and_colourless() -> None:
    ap = derive_appearance(refractive_index=1.47, absorption_length_mm=_TRANSPARENT,
                           scatter_length_mm=_TRANSPARENT, spectrum=_clear_spectrum(1.47),
                           path_mm=30.0)
    assert ap.available and ap.transparent
    assert ap.transmittance > 0.95                       # glass transmits ~all visible light
    assert ap.display_alpha < 0.2                        # rendered barely-there (see-through)
    r, g, b = ap.base_rgb
    assert max(r, g, b) - min(r, g, b) < 0.08            # flat spectrum -> neutral, not a rainbow
    assert "transparent" in ap.descriptor and "clear" in ap.descriptor


def test_fresnel_reflectance_monotonic_in_n() -> None:
    r_air = derive_appearance(refractive_index=1.0, absorption_length_mm=_TRANSPARENT,
                              scatter_length_mm=_TRANSPARENT, path_mm=10.0).reflectance
    r_water = derive_appearance(refractive_index=1.33, absorption_length_mm=_TRANSPARENT,
                                scatter_length_mm=_TRANSPARENT, path_mm=10.0).reflectance
    r_glass = derive_appearance(refractive_index=1.47, absorption_length_mm=_TRANSPARENT,
                                scatter_length_mm=_TRANSPARENT, path_mm=10.0).reflectance
    r_diamond = derive_appearance(refractive_index=2.42, absorption_length_mm=_TRANSPARENT,
                                  scatter_length_mm=_TRANSPARENT, path_mm=10.0).reflectance
    assert r_air == 0.0 < r_water < r_glass < r_diamond
    assert abs(r_water - 0.0201) < 0.002                 # ((0.33)/(2.33))^2 ~ 2%
    assert abs(r_glass - 0.0362) < 0.003                 # ~3.6% for n=1.47


def test_transmission_tint_goes_blue_when_reds_absorbed() -> None:
    # A medium that eats long wavelengths (red short abs-length) but passes blue -> blue tint.
    spectrum = [
        OpticSample(wavelength_nm=430.0, absorption_length_mm=_TRANSPARENT),   # blue: clear
        OpticSample(wavelength_nm=500.0, absorption_length_mm=400.0),
        OpticSample(wavelength_nm=580.0, absorption_length_mm=60.0),
        OpticSample(wavelength_nm=660.0, absorption_length_mm=12.0),           # red: absorbed
    ]
    ap = derive_appearance(refractive_index=1.33, absorption_length_mm=80.0,
                           scatter_length_mm=_TRANSPARENT, spectrum=spectrum, path_mm=50.0)
    r, g, b = ap.base_rgb
    assert b > r                                         # transmitted light leans blue
    assert "blue" in ap.descriptor
    assert ap.transmittance < 0.9                        # it absorbs some light


def test_opacity_scales_with_thickness_beer_lambert() -> None:
    spectrum = [OpticSample(wavelength_nm=wl, absorption_length_mm=25.0)
                for wl in (430.0, 520.0, 610.0, 700.0)]
    thin = derive_appearance(refractive_index=1.33, absorption_length_mm=25.0,
                             scatter_length_mm=_TRANSPARENT, spectrum=spectrum, path_mm=5.0)
    thick = derive_appearance(refractive_index=1.33, absorption_length_mm=25.0,
                              scatter_length_mm=_TRANSPARENT, spectrum=spectrum, path_mm=80.0)
    assert thick.transmittance < thin.transmittance      # more path -> less light through
    assert thick.display_alpha > thin.display_alpha       # thicker body renders more solid


def test_no_optics_is_unavailable_fallback() -> None:
    ap = derive_appearance(refractive_index=None, absorption_length_mm=None,
                           scatter_length_mm=None, optics_available=False)
    assert not ap.available and ap.reflectance == 0.0


def test_turbidity_from_scattering_fraction() -> None:
    ap = derive_appearance(refractive_index=1.33, absorption_length_mm=1000.0,
                           scatter_length_mm=50.0, path_mm=20.0)
    assert ap.turbidity > 0.9                             # scattering dominates extinction (milky)


# --- render-hint parsing + model glue -----------------------------------------------------

def test_render_hint_parsing() -> None:
    h = RenderHint.from_tags(["fluid", "viz_opacity=0.4", "viz_tint=#3366ff", "viz_solid"])
    assert abs(h.opacity - 0.4) < 1e-9 and h.solid and not h.hidden
    assert h.tint is not None and h.tint[2] > h.tint[0]  # blue-dominant tint
    assert RenderHint.from_tags(["viz_hidden"]).hidden
    assert RenderHint.from_tags(["viz_glow"]).emissive
    assert RenderHint.from_tags(["viz_shell"]).shell and RenderHint.from_tags(["viz_wireframe"]).shell
    c = RenderHint.from_tags(["viz_color=0.2,0.8,0.3"]).color
    assert c is not None and abs(c[1] - 0.8) < 1e-6      # r,g,b float form
    assert RenderHint.from_tags(["fluid"]).is_empty


def test_viz_shell_forces_clear_glass_shell() -> None:
    # The forced-parameter lever: an authored viz_shell makes a volume a near-invisible shell so a
    # beam/contents inside read through it — and it's disabled just by dropping the tag.
    scene = SceneModel()
    scene.materials.append(MaterialDef(name="glass", mean_refractive_index=1.47,
                                       mean_absorption_length_mm=_TRANSPARENT,
                                       mean_scatter_length_mm=_TRANSPARENT,
                                       spectrum=_clear_spectrum(1.47), optics_available=True))
    plain = VolumeNode(name="g", material="glass", shape=Shape(type="box", size_mm=(40.0,) * 3))
    shell = VolumeNode(name="g2", material="glass", shape=Shape(type="box", size_mm=(40.0,) * 3),
                       tags=["viz_shell"])
    assert scene.volume_color(shell)[3] <= 0.05          # shell fill is near-invisible
    assert scene.volume_color(shell)[3] < scene.volume_color(plain)[3]
    # An explicit opacity still overrides the shell default (author stays in control).
    shell.tags = ["viz_shell", "viz_opacity=0.5"]
    assert abs(scene.volume_color(shell)[3] - 0.5) < 1e-6


def test_path_length_from_shape() -> None:
    box = VolumeNode(name="b", material="m", shape=Shape(type="box", size_mm=(20.0, 40.0, 60.0)))
    assert abs(box.path_length_mm() - 40.0) < 1e-6       # mean extent
    sphere = VolumeNode(name="s", material="m", shape=Shape(type="sphere", outer_radius_mm=15.0))
    assert abs(sphere.path_length_mm() - 30.0) < 1e-6    # diameter


def test_scene_volume_color_prefers_hint_over_physics() -> None:
    scene = SceneModel()
    scene.materials.append(MaterialDef(name="glass", mean_refractive_index=1.47,
                                       mean_absorption_length_mm=_TRANSPARENT,
                                       mean_scatter_length_mm=_TRANSPARENT,
                                       spectrum=_clear_spectrum(1.47), optics_available=True))
    vol = VolumeNode(name="pane", material="glass",
                     shape=Shape(type="box", size_mm=(30.0, 30.0, 30.0)),
                     tags=["viz_opacity=0.9", "viz_color=#ff0000"])
    r, g, b, a = scene.volume_color(vol)
    assert (r, g, b) == (1.0, 0.0, 0.0)                  # authored colour wins
    assert abs(a - 0.9) < 1e-6                            # authored opacity wins
    # And the surface params still carry the physics-derived reflectance (glass is glossy).
    _rgba, params = scene.volume_surface(vol)
    assert params[0] > 0.03                               # Fresnel R0 for n=1.47


def test_bounds_fit_volumes_not_world() -> None:
    # Camera framing must fit the *placed volumes*, not the whole world box — otherwise the
    # subject renders tiny in a sea of grid (the framing bug this fixes).
    scene = SceneModel(world_size_mm=200.0)
    scene.volumes.append(VolumeNode(name="slab", material="glass",
                                    shape=Shape(type="box", size_mm=(80.0, 80.0, 40.0))))
    scene.volumes.append(VolumeNode(name="src", material="air", position_mm=(-50.0, 0.0, -70.0),
                                    shape=Shape(type="box", size_mm=(20.0, 20.0, 10.0))))
    lo, hi = scene.bounds_mm()
    # Union of the two boxes, far tighter than the ±100 world half-extent.
    assert lo == (-60.0, -40.0, -75.0)
    assert hi == (40.0, 40.0, 20.0)
    # A hidden volume is excluded; an empty scene falls back to the world box.
    scene.volumes.append(VolumeNode(name="ghost", material="air", position_mm=(500.0, 0.0, 0.0),
                                    shape=Shape(type="box", size_mm=(10.0, 10.0, 10.0)),
                                    tags=["viz_hidden"]))
    assert scene.bounds_mm()[1][0] == 40.0                # ghost did not stretch the bounds
    empty = SceneModel(world_size_mm=120.0)
    assert empty.bounds_mm() == ((-60.0, -60.0, -60.0), (60.0, 60.0, 60.0))


def test_scene_volume_color_physics_when_no_hint() -> None:
    scene = SceneModel()
    scene.materials.append(MaterialDef(name="water", mean_refractive_index=1.33,
                                       mean_absorption_length_mm=_TRANSPARENT,
                                       mean_scatter_length_mm=_TRANSPARENT,
                                       spectrum=_clear_spectrum(1.33), optics_available=True))
    vol = VolumeNode(name="cup", material="water",
                     shape=Shape(type="box", size_mm=(40.0, 40.0, 40.0)), tags=["fluid"])
    r, g, b, a = scene.volume_color(vol)
    assert a < 0.2                                        # transparent water renders see-through
    assert max(r, g, b) - min(r, g, b) < 0.1             # colourless (honest for the EM base)


def _run_all() -> int:
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    failures = 0
    for t in tests:
        try:
            t()
            print(f"PASS {t.__name__}")
        except Exception as exc:  # noqa: BLE001
            failures += 1
            print(f"FAIL {t.__name__}: {exc}")
    print(f"\n{len(tests) - failures}/{len(tests)} passed")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(_run_all())
