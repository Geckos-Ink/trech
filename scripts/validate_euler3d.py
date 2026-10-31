#!/usr/bin/env python3
"""Exact periodic Euler verification and common-time obstacle refinement; no training labels."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--trech', type=Path, default=Path('build/rel/trech'))
    parser.add_argument('--output', type=Path, default=Path('build/euler3d_validation'))
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    binary = args.trech.resolve()
    args.output.mkdir(parents=True, exist_ok=True)
    output = Path(tempfile.mkdtemp(prefix='validation_', dir=args.output.resolve()))
    fixture = 'tests/fixtures/js/euler3d_accuracy.js'
    scenario = 'examples/scenarios/aerodynamics_reference/aerodynamics_reference.js'
    sources = [fixture, 'js/trech_euler3d_reference.js', 'include/trech/core/ScalarField.hpp',
               'js/trech_helpers.js', 'js/trech_math.js', 'js/trech_random.js', 'js/trech_material_facts.js',
               'src/core/ScalarField.cpp', 'src/js/JsRuntime.cpp', scenario,
               scenario.replace('.js', '.ui.js'), scenario.replace('.js', '.view.js'),
               scenario.replace('.js', '.validation.js'), 'scripts/validate_euler3d.py']
    def identities():
        return {s: hashlib.sha256((root / s).read_bytes()).hexdigest() for s in sources}
    source_hashes = identities()
    binary_hash = hashlib.sha256(binary.read_bytes()).hexdigest()

    def run(name, source, **parameters):
        target = output / name
        command = [str(binary), 'run', str(root / source), '--output', str(target)]
        for key, value in parameters.items():
            command += ['--param', key + '=' + json.dumps(value)]
        with (output / (name + '.log')).open('w') as log:
            subprocess.run(command, cwd=root, stdout=log, stderr=subprocess.STDOUT, check=True, timeout=300)
        scores = json.loads((target / 'trech_scores.jsonl').read_text().splitlines()[-1])
        assert scores['hook_predict_count'] == 0 and scores['hook_emit_dropped_count'] == 0, name
        emits = [json.loads(line) for line in (target / 'trech_hook_emits.jsonl').read_text().splitlines()]
        return target, emits

    original, emits = run('exact', fixture)
    replay, _ = run('exact_replay', fixture)
    for filename in ('trech_scores.jsonl', 'trech_hook_emits.jsonl'):
        assert (original / filename).read_bytes() == (replay / filename).read_bytes(), filename
    assert len(emits) == 1 and emits[0]['tag'] == 'euler3d_accuracy'
    exact = emits[0]['payload']
    assert exact['schema'] == 'trech_euler3d_verification_v1' and len(exact['anchors']) == 3
    assert not exact['physical_accuracy_verified'] and not exact['particle_training_data']
    obstacles = []
    for n, cfl in ((20, .3), (30, .3), (40, .3), (30, .15), (30, .075)):
        _, records = run(f'obstacle_{n}_{cfl}', scenario, grid_x=n, cfl=cfl, ticks=5, duration_s=.0001)
        frames = [r['payload'] for r in records if r['tag'] == 'aerodynamics_reference']
        assert len(frames) == 6
        for i, frame in enumerate(frames):
            assert abs(frame['time_s'] - .0001 * i / 5) < 1e-18
            assert all(abs(v) < 1e-10 * max(1, abs(t))
                       for v, t in zip(frame['balance_residual'], frame['integral']))
            assert all(row[3] > 0 and row[7] > 0 for row in frame['cells'])
        final = frames[-1]
        obstacles.append(dict(grid_x=n, cfl=cfl, time_s=final['time_s'], steps=final['steps'],
                              integral=final['integral'], balance_residual=final['balance_residual'],
                              temperature_range_k=[min(c[8] for c in final['cells']), max(c[8] for c in final['cells'])]))
    assert identities() == source_hashes, 'Source changed during verification; rerun against a stable snapshot'
    assert hashlib.sha256(binary.read_bytes()).hexdigest() == binary_hash, 'Engine changed during verification'
    report = dict(scope='Numerical verification only; obstacle diagnostics have no independent accuracy anchor',
                  exact=exact, exact_replay=True, obstacle_common_time=obstacles,
                  source_sha256=source_hashes, binary_sha256=binary_hash, output=str(output))
    (output / 'report.json').write_text(json.dumps(report, indent=2) + '\n')
    print(output / 'report.json')
    for anchor in exact['anchors']:
        print(anchor['kind'], 'grid orders', anchor['spatial_orders'], 'time orders', anchor['temporal_orders'])


if __name__ == '__main__':
    main()
