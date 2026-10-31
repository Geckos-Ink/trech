"""Typed particle controls resolve through the real engine, with honest axis roles."""
import json
import os
from pathlib import Path
import subprocess

import pytest


ROOT = Path(__file__).resolve().parents[2]


def inspect(name, *options):
    engine = ROOT / 'build/rel/trech'
    if not engine.is_file():
        pytest.skip('No local engine for typed control inspection')
    env = dict(os.environ, TRECH_PUBCHEM_CACHE_DIR=str(ROOT / 'build/pubchem_cache'))
    result = subprocess.run([str(engine), 'inspect', str(ROOT / 'examples/scenarios' / name / (name+'.js')),
        *options], text=True, capture_output=True, env=env)
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


def test_shaken_count_and_surface_grid_are_independent_axes():
    name = 'glass_of_water_shaken'
    a = inspect(name)['config']['precision']['axes']
    b = inspect(name, '--param', 'particle_count_factor=2')['config']['precision']['axes']
    c = inspect(name, '--param', 'render_grid_mm=1')['config']['precision']['axes']
    assert a[0]['value'] == 4301 and b[0]['value'] > 2 * a[0]['value'] * .95
    assert a[0]['role'] == 'spatial' and not a[0]['representationOnly']
    assert c[0]['value'] == a[0]['value'] and c[1]['value'] == 1
    assert c[1]['representationOnly']


def test_beaker_samples_are_explicitly_representation_only():
    name = 'beaker_water_n_pentane'
    a = inspect(name)['config']
    b = inspect(name, '--param', 'particle_count_factor=2')['config']
    assert a['run']['nEvents'] == b['run']['nEvents'] == 60
    assert a['precision']['axes'][0]['value'] == 440
    assert b['precision']['axes'][0]['value'] == 880
    assert b['precision']['axes'][0]['role'] == 'representation'
    assert b['precision']['axes'][0]['representationOnly']
