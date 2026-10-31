"""Recorded bulk material grouping, axis/phase isolation, transparency and replay."""
from copy import deepcopy
import json
from types import SimpleNamespace

import numpy as np
import pytest

from trech_studio.render.materials import phase_grid, material_meshes, sorted_triangles
from trech_studio.render.playback import build_material_frame_playback


def grid():
    values = np.zeros((4, 3, 2), dtype=int)
    values[2:] = 1
    return dict(origin=[1, 2, 3], spacing=[2, 3, 4], shape=list(values.shape),
        values=values.ravel(order='F').tolist(), replaces_points=True,
        classes=[dict(id=0, label='sand', style='solid', color_rgba=[.8, .7, .4, .35]),
                 dict(id=1, label='melt', style='liquid', color_rgba=[1, .4, .1, .45])])


def playback(payloads):
    return build_material_frame_playback([SimpleNamespace(tag='material_frame', payload=dict(
        positions_mm=[[0, 0, 0], [2, 0, 0], [0, 2, 0]],
        colors_rgba=[[1, 0, 0, 1]] * 3, up_axis='y', **p)) for p in payloads])


def group(indices, phase='liquid'):
    return dict(label=phase, phase=phase, point_indices=indices, color_rgba=[.3, .6, 1, .25],
        render_surface=dict(mode='metaball', kernel='gaussian', sigma_mm=1.4,
                            grid_spacing_mm=.5, iso_level=.42, positions_unmodified=True))


def test_calibrated_grid_axes_and_full_outer_boundary():
    raw = grid()
    z = phase_grid(raw, 'z')
    assert z.values.shape == (4, 2, 3)
    assert np.array_equal(z.origin, [1, 3, 2])
    assert np.array_equal(z.spacing, [2, 4, 3])
    assert z.values[3, 1, 2] == 1
    frame = playback([dict(grid=raw)]).frames[0]
    original = deepcopy(frame)
    layers, notes, keep = material_meshes(frame)
    assert len(layers) == 2 and not np.any(keep)
    assert all(mesh.index_count > 0 for mesh, _ in layers)
    # Adjacent phases meet at their cell midpoint, not one Gaussian pooled by colour.
    assert layers[0][0].vertices[:, 0].max() == pytest.approx(4)
    assert layers[1][0].vertices[:, 0].min() == pytest.approx(4)
    assert [n['cells'] for n in notes] == [12, 12]
    assert notes[0]['opacity'] == pytest.approx(.35)
    assert np.array_equal(frame.positions, original.positions)
    assert np.array_equal(frame.material_grid.values, original.material_grid.values)
    empty_points = build_material_frame_playback([SimpleNamespace(tag='material_frame',payload=dict(
        positions_mm=[], colors_rgba=[], up_axis='y', grid=raw))])
    lo, hi = empty_points.particle_bounds()
    assert np.allclose(lo, [0, .5, 1]) and np.allclose(hi, [8, 9.5, 9])


@pytest.mark.parametrize('change', [
    lambda g:g.update(values=[0]), lambda g:g.update(spacing=[2, 0, 1]),
    lambda g:g.update(shape=[4, True, 2]), lambda g:g['values'].__setitem__(0, 5),
    lambda g:g['values'].__setitem__(0, .5), lambda g:g.update(origin=[0, float('nan'), 0]),
    lambda g:g['classes'][0].update(color_rgba=[1, 1, 1, 2]),
])
def test_malformed_grid_rejected(change):
    raw = grid(); change(raw)
    with pytest.raises(ValueError, match='Invalid material grid'):
        phase_grid(raw, 'y')


def test_grouped_liquid_gas_and_unassigned_points_are_isolated():
    frame = playback([dict(material_groups=[group([0], 'liquid'), group([1], 'gas')])]).frames[0]
    layers, descriptions, keep = material_meshes(frame)
    assert keep.tolist() == [False, False, True]
    assert [d['phase'] for d in descriptions] == ['liquid', 'gas']
    assert layers[0][0].vertices[:, 0].mean() == pytest.approx(0, abs=.15)
    assert layers[1][0].vertices[:, 0].mean() == pytest.approx(2, abs=.15)
    fine, _, _ = material_meshes(frame, detail=2)
    assert fine[0][0].index_count > layers[0][0].index_count
    assert np.array_equal(frame.positions, [[0, 0, 0], [2, 0, 0], [0, 2, 0]])
    _, bounded_notes, _ = material_meshes(frame, detail=8, max_cells=1000)
    json.dumps(bounded_notes)  # numpy budget arithmetic must not leak into capture JSON


@pytest.mark.parametrize('groups', [
    [group([0, 0])], [group([3])], [group([0.5])], [group([True])],
    [group([0]), group([0], 'gas')], [group([0], 'unknown')],
    [dict(group([0]), render_surface=dict(mode='metaball', sigma_mm=float('nan')))],
])
def test_invalid_membership_never_silently_fuses_other_materials(groups):
    with pytest.raises(ValueError, match='Invalid material group'):
        playback([dict(material_groups=groups)])


def test_triangle_sort_changes_with_camera_and_is_stable():
    vertices = np.array([[x, y, z] for z in (-2, 2) for x, y in ((0, 0), (1, 0), (0, 1))])
    indices = np.arange(6, dtype=np.uint32)
    assert sorted_triangles(vertices, indices, [0, 0, 10], [0, 0, 0]).tolist() == list(range(6))
    assert sorted_triangles(vertices, indices, [0, 0, -10], [0, 0, 0]).tolist() == [3, 4, 5, 0, 1, 2]


def test_liquid_clip_closes_the_surface_without_moving_centres():
    g = group([0, 1, 2])
    g['render_surface']['clip_cylinder'] = dict(axis='y', radius_mm=2, min_mm=0, max_mm=2)
    frame = playback([dict(material_groups=[g])]).frames[0]
    mesh = material_meshes(frame)[0][0][0]
    triangles = mesh.vertices[mesh.indices.reshape(-1, 3), :3]
    # A closed oriented boundary has zero total area vector, including the clipped floor.
    area = np.cross(triangles[:, 1] - triangles[:, 0], triangles[:, 2] - triangles[:, 0])
    assert np.allclose(area.sum(axis=0), 0, atol=2e-4)
    assert mesh.vertices[:, 1].min() > -.5
    assert np.array_equal(frame.positions, [[0, 0, 0], [2, 0, 0], [0, 2, 0]])


def test_merge_radius_override_is_separate_from_sampling_and_recorded_membership():
    frame = playback([dict(material_groups=[group([0, 1])])]).frames[0]
    a, an, ak = material_meshes(frame, detail=1, merge_radius_scale=.5)
    b, bn, bk = material_meshes(frame, detail=1, merge_radius_scale=1.5)
    assert an[0]['sigma_mm'] == pytest.approx(.7)
    assert bn[0]['sigma_mm'] == pytest.approx(2.1)
    assert b[0][0].vertices[:, 0].max() > a[0][0].vertices[:, 0].max()
    assert np.array_equal(ak, bk) and frame.material_groups[0].indices.tolist() == [0, 1]
    assert frame.material_groups[0].surface.sigma_mm == 1.4


def test_gpu_grouped_grid_replaces_points_and_reverse_scrubs():
    from trech_studio.capture import _offscreen_renderer
    from trech_studio.scene.model import SceneModel
    a, b = grid(), grid()
    b['values'] = [1] * len(b['values'])
    pb = playback([dict(time_s=0, grid=a), dict(time_s=1, grid=b)])
    canvas, renderer, reason = _offscreen_renderer(240, 160, 'dark')
    if renderer is None:
        pytest.skip(reason)
    renderer.set_scene(SceneModel(world_size_mm=20))
    renderer.set_playback(pb)
    renderer.fit_view(*pb.particle_bounds())
    renderer.set_playback_time(0)
    first = np.asarray(canvas.draw()).copy()
    info = renderer.precision_info()
    assert info['particle_representation'] == 'grouped_material_surfaces'
    assert info['material_points_drawn'] == 0 and info['material_triangles'] > 0
    renderer.set_playback_time(1)
    last = np.asarray(canvas.draw()).copy()
    assert not np.array_equal(first, last)
    renderer.set_playback_time(0)
    assert np.array_equal(first, np.asarray(canvas.draw()))
    renderer.camera.orbit(.5, .1)
    assert not np.array_equal(first, np.asarray(canvas.draw()))
