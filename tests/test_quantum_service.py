#!/usr/bin/env python3
"""Optional actual solver gate for an edited/rotated JSON scene, outside Studio."""
import json
from pathlib import Path
import subprocess
import tempfile
ROOT = Path(__file__).resolve().parents[1]
python = ROOT/'build/render-venv/bin/python'
if not python.exists():
    print('SKIP optional QM service: build/render-venv is unavailable')
    raise SystemExit(0)
with tempfile.TemporaryDirectory() as directory:
    directory = Path(directory)
    molecule = {'id': 'hydrogen', 'position': [1, 0, 0], 'rotation_deg': [0, 0, 90],
                'structure': {'atoms': [{'element': 'H', 'position': [-.37, 0, 0]},
                                        {'element': 'H', 'position': [.37, 0, 0]}], 'charge': 0, 'bonds': [[0, 1]]}}
    scene = {'schema': 'trech_chemistry_scene_v1', 'length_unit': 'angstrom', 'molecules': [molecule]}
    request, result = directory/'request.json', directory/'result.json'
    request.write_text(json.dumps(scene))
    completed = subprocess.run([str(python), str(ROOT/'tools/quantum/build_density_scene.py'), '--scene', str(request), '--out', str(result)], capture_output=True, text=True)
    assert completed.returncode == 0, completed.stdout+completed.stderr
    output = json.loads(result.read_text())
    frame = output['frames'][0]
    electronic = frame['electronic_structure']
    assert electronic['electron_count'] == 2 and sum(o['occupation'] for o in electronic['orbitals']) == 2
    assert electronic['total_energy_hartree'] < 0
    assert len(frame['fields']) == 4  # energy decomposition, total, occupied, LUMO
    assert abs(frame['fields'][0]['geometry']['atoms'][0]['position'][1]+.37) < 1e-12
    inspected = subprocess.run([str(ROOT/'build/rel/trech'), 'inspect', str(ROOT/'examples/experiments/chemistry_mode.js'), '--param', 'scene_file='+json.dumps(str(result))], capture_output=True, text=True)
    assert inspected.returncode == 0, inspected.stderr
    # An unsupported odd-electron input fails without replacing a valid result.
    snapshot = result.read_bytes()
    scene['molecules'][0]['structure']['charge'] = 1
    request.write_text(json.dumps(scene))
    completed = subprocess.run([str(python), str(ROOT/'tools/quantum/build_density_scene.py'), '--scene', str(request), '--out', str(result)], capture_output=True, text=True)
    assert completed.returncode != 0 and result.read_bytes() == snapshot
print('PASS rotated edited scene → independent solver → TRECH; electron counts and atomic failure publication')
