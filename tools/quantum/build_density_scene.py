#!/usr/bin/env python3
"""Build a bounded independent QM density comparison; no Geant4-training/dynamics claim."""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import numpy as np
import pyscf
from pyscf import gto, scf, dft, lib

ROOT = Path(__file__).resolve().parents[2]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, default=ROOT / 'data/chemistry_probability/water_deuterium.json')
    args = parser.parse_args()
    lib.num_threads(1)
    water = {'atoms': [{'element': 'O', 'massNumber': 16, 'position': [0, 0, 0]},
                       {'element': 'H', 'massNumber': 1, 'position': [.95, 0, 0]},
                       {'element': 'H', 'massNumber': 1, 'position': [-.24, .92, 0]}],
             'bonds': [[0, 1, 1], [0, 2, 1]], 'charge': 0}
    d2 = {'atoms': [{'element': 'H', 'massNumber': 2, 'position': [-.37, 0, 0]},
                    {'element': 'H', 'massNumber': 2, 'position': [.37, 0, 0]}],
          'bonds': [[0, 1, 1]], 'charge': 0}
    shape, spacing, origin = (69, 37, 37), .16, np.array([-2.88, -2.88, -2.88])
    indices = np.stack(np.meshgrid(*(np.arange(n) for n in shape), indexing='ij'), -1)
    coordinates = origin + indices.reshape(-1, 3) * spacing
    frames, reports = [], []
    for index, distance in enumerate([4., 3., 2.]):
        molecules = [{'id': 'water', 'structure': water, 'position': [0, 0, 0]},
                     {'id': 'deuterium', 'structure': d2, 'position': [distance, 0, 0]}]
        atoms = [(a['element'], (np.array(a['position']) + m['position']).tolist())
                 for m in molecules for a in m['structure']['atoms']]
        mol = gto.M(atom=atoms, unit='Angstrom', basis='6-31g', charge=0, spin=0, verbose=0)
        method = scf.RHF(mol)
        method.conv_tol = 1e-10
        energy = float(method.kernel())
        if not method.converged:
            raise RuntimeError('SCF did not converge')
        dm = method.make_rdm1()
        def cell_average(points, order):
            # Numerical quadrature, not a physical density law. Point sampling
            # under-resolves O's core and badly over-counts electrons at this grid.
            nodes, weights = np.polynomial.legendre.leggauss(order)
            averaged = np.zeros(len(points))
            for i in range(order):
                for j in range(order):
                    for k in range(order):
                        sample = points + spacing / 2 * np.array([nodes[i], nodes[j], nodes[k]])
                        ao = dft.numint.eval_ao(mol, sample / lib.param.BOHR)
                        rho = dft.numint.eval_rho(mol, ao, dm) / lib.param.BOHR**3
                        averaged += rho * weights[i] * weights[j] * weights[k] / 8
            return averaged
        values = cell_average(coordinates, 2)
        nuclei = np.asarray([a[1] for a in atoms])
        near = np.min(np.sum((coordinates[:, None, :] - nuclei[None, :, :])**2, axis=2), axis=1) < .6**2
        values[near] = cell_average(coordinates[near], 6)
        if not np.all(np.isfinite(values)) or values.min() < -1e-12:
            raise RuntimeError('invalid electronic density')
        values = np.maximum(values, 0).reshape(shape)
        integral = float(np.sum(values) * spacing**3)
        if abs(integral / mol.nelectron - 1) > .01:
            raise RuntimeError(f'Cell quadrature electron-count gap exceeds 1%: {integral}/{mol.nelectron}')
        # Samples from a disclosed piecewise-constant voxel quadrature of the
        # emitted grid, not labelled electron identities or classical orbits.
        rng = np.random.default_rng(20261027 + index)
        chosen = rng.choice(values.size, size=1600, p=values.ravel() / values.sum())
        xyz = np.stack(np.unravel_index(chosen, values.shape), -1)
        samples = origin + (xyz + rng.random(xyz.shape) - .5) * spacing
        source = {'kind': 'quantum_reference', 'method': 'PySCF RHF/6-31g joint-system density',
                  'pyscf_version': pyscf.__version__, 'geant4_trained': False, 'measured': False,
                  'scope': 'Clamped authored nuclei, neutral isolated joint system. Isotopic nuclear dynamics, electron correlation and physical reaction time are not predicted.',
                  'scf_converged': True, 'energy_hartree': energy, 'electron_count': mol.nelectron,
                  'grid_integral_electrons': integral, 'grid_integral_relative_gap': abs(integral / mol.nelectron - 1),
                  'grid_semantics': 'cell-average density, 2-point/axis Gauss quadrature, 6-point/axis within 0.6 angstrom of nuclei; no renormalization',
                  'geometry_sha256': hashlib.sha256(json.dumps(atoms, sort_keys=True).encode()).hexdigest()}
        field = {'id': 'joint_electrons', 'particle': 'electron', 'owner_ids': ['water', 'deuterium'],
                 'geometry': {'charge': 0, 'atoms': [dict(a, position=(np.array(a['position']) + m['position']).tolist())
                    for m in molecules for a in m['structure']['atoms']]},
                 'length_unit': 'angstrom', 'density_unit': 'electrons/angstrom^3', 'source': source,
                 'grid': {'shape': list(shape), 'origin': origin.tolist(), 'spacing': spacing,
                          'values': [float(f'{x:.6g}') for x in values.ravel()]},
                 'isovalue': .035, 'samples': np.round(samples, 6).tolist(),
                 'sampling_note': '1600 independent voxel-quadrature visualization samples, not 1600 electrons or persistent electron identities; no physical trajectories'}
        frames.append({'parameter_value': float(index), 'molecules': molecules, 'fields': [field]})
        reports.append(source)
        print(f'distance={distance:g} Å: {energy:.9f} hartree, grid integral {integral:.6f}/{mol.nelectron} electrons', flush=True)
    scene = {'schema': 'trech_chemistry_scene_v1', 'length_unit': 'angstrom', 'time_kind': 'parameter_scan',
             'molecules': frames[0]['molecules'], 'frames': frames,
             'note': 'Authored water and D2 approach scan (4/3/2 Å); joint independent quantum reference. No inferred approach dynamics or predicted reaction.'}
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(scene, separators=(',', ':'), allow_nan=False) + '\n')
    manifest = {'schema': 'trech_density_scene_manifest_v1', 'scene_sha256': hashlib.sha256(args.out.read_bytes()).hexdigest(),
                'generator': 'tools/quantum/build_density_scene.py', 'references': reports,
                'density_note': 'Number density, not a single-electron orbital or hard molecular boundary. Finite-grid quadrature gap is retained.',
                'source': 'https://pyscf.org/contributor/dft_developer.html'}
    args.out.with_suffix('.manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')


if __name__ == '__main__':
    main()
