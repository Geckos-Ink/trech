import numpy as np

from trech_studio.render.mesh import cylinder, for_shape
from trech_studio.scene.model import Shape


def test_hollow_tube_preserves_inner_wall_and_annular_opening():
    mesh = for_shape(Shape(type="tube", outer_radius_mm=20.0,
                           inner_radius_mm=15.0, length_mm=40.0))

    radii = np.linalg.norm(mesh.vertices[:, :2], axis=1)
    assert np.isclose(radii, 15.0).any()
    assert np.isclose(radii, 20.0).any()
    assert not np.isclose(radii, 0.0).any()
    inner = np.isclose(radii, 15.0) & np.isclose(mesh.vertices[:, 5], 0.0)
    radial_dot = np.sum(mesh.vertices[inner, :2] * mesh.vertices[inner, 3:5], axis=1)
    assert np.all(radial_dot < 0.0)


def test_solid_cylinder_has_end_cap_centres():
    mesh = cylinder(10.0, 20.0, sectors=12)
    radii = np.linalg.norm(mesh.vertices[:, :2], axis=1)
    assert np.isclose(radii, 0.0).any()
    assert mesh.index_count == 12 * 12
