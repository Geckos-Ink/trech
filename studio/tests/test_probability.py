"""Faithful replay of recorded joint densities and nuclear ensembles (no GPU)."""
from __future__ import annotations
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import numpy as np
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from trech_studio.render.probability import probability_views, build_probability_playback
from trech_studio.render.playback import build_playback
from trech_studio.render.metaballs import DensityGrid, density_surface_mesh
from trech_studio.engine.chemistry import read_scene, write_scene, stage_scene_parameters


def emit(tag, payload): return SimpleNamespace(tag=tag, payload=payload)


def quantum(time=0, kind='physical'):
    return emit('quantum_frame', {'schema': 'trech_quantum_frame_v1', 'time_kind': kind, 'cursor': time,
        'physical_time_s': time if kind == 'physical' else None,
        'structure': {'atoms': [{'element': 'H', 'position': [0, 0, 0]}, {'element': 'O', 'position': [2, 0, 0]}], 'bonds': [[0, 1]], 'molecule_ids': ['a', 'b']},
        'fields': [{'id': 'joint', 'particle': 'electron', 'owner_ids': ['a', 'b'], 'length_unit': 'angstrom',
            'density_unit': 'electrons/angstrom^3', 'source': {'kind': 'quantum_reference', 'method': 'recorded test grid'},
            'grid': {'shape': [2, 2, 2], 'origin': [-1, -1, -1], 'spacing': 1, 'values': [0, 0, 0, 0, 1, 1, 1, 1]},
            'isovalue': .5, 'samples': [[.1, .2, .3]], 'sampling_note': 'independent samples, no identities'}]})


def test_joint_density_preserves_values_and_shared_owners():
    raw = quantum()
    pb = build_playback([], [raw])
    field = raw.payload['fields'][0]
    assert pb.length_unit == 'angstrom' and pb.unit == 's'
    assert pb.frames[0].density.values.ravel().tolist() == field['grid']['values']
    assert pb.frames[0].positions.tolist() == [[0, 0, 0], [2, 0, 0]]
    assert pb.frames[0].bonds.tolist() == [[0, 1]]
    assert field['owner_ids'] == ['a', 'b']
    mesh = density_surface_mesh(DensityGrid(pb.frames[0].density.values, np.zeros(3), 1), .5)
    assert len(mesh.vertices) and np.allclose(mesh.vertices[:, 0], .5)


def test_density_surface_does_not_clamp_small_recorded_values():
    grid = np.zeros((2, 2, 2), np.float32)
    grid[1] = 1e-12
    mesh = density_surface_mesh(DensityGrid(grid, np.zeros(3), 1), 5e-13)
    assert len(mesh.vertices) and np.allclose(mesh.vertices[:, 0], .5)


def test_missing_field_clears_previous_density_at_exact_recorded_clock():
    first, missing, last = quantum(0), quantum(.5), quantum(1)
    missing.payload['fields'] = []
    pb = build_probability_playback([first, missing, last], 'density:joint')
    assert len(pb.frames) == 3
    assert pb.frames[pb.frame_index_at(.5)].density is None
    assert pb.frames[pb.frame_index_at(.499)].density is not None
    assert pb.frames[-1].physical_time_s == 1


def test_probability_samples_are_held_points_without_particle_identity():
    first, last = quantum(0, 'parameter_scan'), quantum(1, 'parameter_scan')
    last.payload['fields'][0]['samples'] = [[.5, .6, .7]]
    pb = build_probability_playback([first, last], 'samples:joint')
    assert pb.unit == 'parameter' and pb.physical_t_max is None
    assert np.allclose(pb.frames[pb.frame_index_at(.9)].positions[-1], [.1, .2, .3])
    assert 'no identities' in pb.label


def test_nuclear_views_keep_fm_and_no_physical_clock():
    raw = emit('chemistry_nuclear_ensemble', {'ensembles': [{'element': 'H', 'data': {'a': 2, 'z': 1, 'available': True,
        'source': {'method': 'G4Fancy3DNucleus', 'scope': 'initial states, not time evolution'},
        'configurations': [{'protons': [[1, 0, 0]], 'neutrons': [[-1, 0, 0]]},
                           {'protons': [[0, 1, 0]], 'neutrons': [[0, -1, 0]]}]}}]})
    assert len(probability_views([raw])) == 4
    pb = build_probability_playback([raw], 'nuclear:H:2:both')
    assert pb.length_unit == 'fm' and pb.unit == 'ensemble sample'
    assert pb.frames[0].positions.tolist() == [[1, 0, 0], [-1, 0, 0]]
    assert pb.physical_t_max is None
    assert len(build_probability_playback([raw], 'nuclear:H:2:neutrons').frames[0].positions) == 1


def test_scene_files_and_large_parameter_staging_round_trip():
    scene = {'schema': 'trech_chemistry_scene_v1', 'molecules': [], 'note': 'x' * 40000}
    with tempfile.TemporaryDirectory() as tmp:
        directory = Path(tmp)
        write_scene(directory / 'source.json', scene)
        assert read_scene(directory / 'source.json') == scene
        args = ['--param', 'scene_json=' + json.dumps(json.dumps(scene)), '--param', 'scene_file=""']
        staged = stage_scene_parameters(args, directory / 'drafts')
        assert len(staged) == 4 and 'scene_json=""' in staged
        path = Path(json.loads(staged[-1].split('=', 1)[1]))
        assert read_scene(path) == scene
        assert stage_scene_parameters(args, directory / 'drafts') == staged
        assert len(list((directory / 'drafts').glob('*.json'))) == 1


if __name__ == '__main__':
    tests = [v for k, v in list(globals().items()) if k.startswith('test_')]
    for test in tests:
        test(); print('PASS', test.__name__)
    print(f'{len(tests)}/{len(tests)} passed')
