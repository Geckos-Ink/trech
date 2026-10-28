#!/usr/bin/env python3
"""Electronic reference service shared by CLI and Studio; optional PySCF, never Geant4 truth."""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import numpy as np
import pyscf
from pyscf import gto, scf, dft, lib

ROOT = Path(__file__).resolve().parents[2]


def default_scene():
    water = {'atoms': [{'element': 'O', 'massNumber': 16, 'position': [0, 0, 0]},
                       {'element': 'H', 'massNumber': 1, 'position': [.95, 0, 0]},
                       {'element': 'H', 'massNumber': 1, 'position': [-.24, .92, 0]}],
             'bonds': [[0, 1, 1], [0, 2, 1]], 'charge': 0}
    d2 = {'atoms': [{'element': 'H', 'massNumber': 2, 'position': [-.37, 0, 0]},
                    {'element': 'H', 'massNumber': 2, 'position': [.37, 0, 0]}],
          'bonds': [[0, 1, 1]], 'charge': 0}
    frames = [{'parameter_value': float(i), 'molecules': [
        {'id': 'water', 'structure': water, 'position': [0, 0, 0]},
        {'id': 'deuterium', 'structure': d2, 'position': [distance, 0, 0]}]}
        for i, distance in enumerate([4., 3., 2.])]
    return {'schema': 'trech_chemistry_scene_v1', 'length_unit': 'angstrom', 'time_kind': 'parameter_scan',
            'molecules': frames[0]['molecules'], 'frames': frames,
            'note': 'Authored water and D2 approach scan (4/3/2 Å); independent quantum reference, no predicted reaction.'}


def placed(molecules):
    """Same declared x/y/z rotation then translation contract as the scenario."""
    atoms = []
    for m in molecules:
        angles = np.radians(m.get('rotation_deg', [0, 0, 0]))
        c, s = np.cos(angles), np.sin(angles)
        for a in m['structure']['atoms']:
            x, y, z = a['position']
            y, z = c[0]*y-s[0]*z, s[0]*y+c[0]*z
            x, z = c[1]*x+s[1]*z, -s[1]*x+c[1]*z
            x, y = c[2]*x-s[2]*y, s[2]*x+c[2]*y
            atoms.append(dict(a, position=(np.array([x, y, z])+m.get('position', [0, 0, 0])).tolist()))
    return atoms


def grid_points(shape, origin, spacing):
    indices = np.stack(np.meshgrid(*(np.arange(n) for n in shape), indexing='ij'), -1)
    return origin + indices.reshape(-1, 3)*spacing


def calculate(scene):
    if scene.get('schema') != 'trech_chemistry_scene_v1' or scene.get('length_unit', 'angstrom') != 'angstrom':
        raise ValueError('Expected a chemistry scene in angstrom')
    raw_frames = scene.get('frames') or [{}]
    if len(raw_frames) > 16:
        raise ValueError('QM service is bounded to 16 frames per job')
    prepared = [(f, f.get('molecules', scene['molecules'])) for f in raw_frames]
    geometries = [placed(m) for _, m in prepared]
    if any(not atoms or len(atoms) > 32 for atoms in geometries):
        raise ValueError('QM reference is bounded to 1–32 atoms per joint system')
    all_positions = np.asarray([a['position'] for atoms in geometries for a in atoms])
    if not np.isfinite(all_positions).all():
        raise ValueError('Non-finite geometry')
    # Cell-centre convention. Keep the original example's domain; expand for edited scenes.
    spacing = .16
    while True:
        origin = np.floor((all_positions.min(axis=0)-2.88)/spacing)*spacing
        shape = np.ceil((all_positions.max(axis=0)+2.88-origin)/spacing).astype(int)+1
        shape += (shape+1) % 2  # odd dimensions give a common nested coarse orbital grid
        if np.prod(shape) <= 131072 and np.max(shape) <= 128:
            break
        spacing = round(spacing+.02, 2)
        if spacing > .32:
            break
    if spacing > .32:
        raise ValueError('Geometry exceeds the bounded density grid; reduce the spatial extent')
    coordinates = grid_points(shape, origin, spacing)
    orbital_shape, orbital_spacing = (shape+1)//2, spacing*2
    orbital_coordinates = grid_points(orbital_shape, origin, orbital_spacing)
    frames, reports = [], []
    for index, ((raw, molecules), atoms) in enumerate(zip(prepared, geometries)):
        charge = sum(m['structure'].get('charge', 0) for m in molecules)
        mol = gto.M(atom=[(a['element'], a['position']) for a in atoms], unit='Angstrom',
                    basis='6-31g', charge=charge, spin=0, verbose=0)
        if mol.nelectron % 2 or not 2 <= mol.nelectron <= 64:
            raise ValueError('This RHF reference supports 2–64 electrons in closed-shell even-electron systems only')
        method = scf.RHF(mol)
        method.conv_tol = 1e-10
        energy = float(method.kernel())
        if not method.converged:
            raise RuntimeError('SCF did not converge; no reference published')
        occupied = np.flatnonzero(method.mo_occ > 0)
        # Full spectrum, bounded spatial records: core + five frontier occupied
        # orbitals, plus LUMO. Small systems retain every occupied state.
        selected = sorted(set([occupied[0], *occupied[-5:]])) + list(np.flatnonzero(method.mo_occ == 0)[:1])
        coefficients = method.mo_coeff[:, selected]
        dm = method.make_rdm1()
        nuclei = np.asarray([a['position'] for a in atoms])

        def average(points, cell_spacing, order, orbitals=False):
            nodes, weights = np.polynomial.legendre.leggauss(order)
            averaged = np.zeros((len(points), len(selected))) if orbitals else np.zeros(len(points))
            for i in range(order):
                for j in range(order):
                    for k in range(order):
                        sample = points + cell_spacing/2*np.array([nodes[i], nodes[j], nodes[k]])
                        ao = dft.numint.eval_ao(mol, sample/lib.param.BOHR)
                        rho = (ao @ coefficients)**2 if orbitals else dft.numint.eval_rho(mol, ao, dm)
                        averaged += rho / lib.param.BOHR**3 * weights[i]*weights[j]*weights[k]/8
            return averaged

        def cell_grid(points, cell_spacing, orbitals=False):
            values = average(points, cell_spacing, 2, orbitals)
            near = np.min(np.sum((points[:, None, :]-nuclei[None, :, :])**2, axis=2), axis=1) < .8**2
            values[near] = average(points[near], cell_spacing, 12 if orbitals else 6, orbitals)
            if not np.isfinite(values).all() or values.min() < -1e-12:
                raise RuntimeError('Invalid electronic density')
            return np.maximum(values, 0)

        values = cell_grid(coordinates, spacing).reshape(shape)
        orbital_values = cell_grid(orbital_coordinates, orbital_spacing, True)
        integral = float(values.sum()*spacing**3)
        if abs(integral/mol.nelectron-1) > .01:
            raise RuntimeError(f'Electron-count quadrature gap exceeds 1%: {integral}/{mol.nelectron}')
        source = {'kind': 'quantum_reference', 'method': 'PySCF RHF/6-31g joint-system density',
                  'pyscf_version': pyscf.__version__, 'geant4_trained': False, 'measured': False,
                  'scope': 'Clamped authored nuclei; independent mean-field reference. No correlated electronic dynamics, isotope motion, stability or reaction prediction.',
                  'scf_converged': True, 'energy_hartree': energy, 'electron_count': mol.nelectron,
                  'grid_integral_electrons': integral, 'grid_integral_relative_gap': abs(integral/mol.nelectron-1),
                  'grid_semantics': 'cell-average Gauss quadrature; core refinement; no renormalization',
                  'geometry_sha256': hashlib.sha256(json.dumps(atoms, sort_keys=True).encode()).hexdigest()}
        geometry = {'charge': charge, 'atoms': atoms}
        rng = np.random.default_rng(20261027+index)

        def field(field_id, grid_values, grid_shape, step, count, orbital=None):
            chosen = rng.choice(grid_values.size, size=count, p=grid_values.ravel()/grid_values.sum())
            xyz = np.stack(np.unravel_index(chosen, grid_shape), -1)
            samples = origin + (xyz+rng.random(xyz.shape)-.5)*step
            f = {'id': field_id, 'particle': 'electron', 'owner_ids': [m['id'] for m in molecules],
                 'geometry': geometry, 'length_unit': 'angstrom',
                 'density_unit': 'probability/angstrom^3' if orbital else 'electrons/angstrom^3',
                 'source': source, 'grid': {'shape': grid_shape.tolist(), 'origin': origin.tolist(),
                     'spacing': step, 'values': [float(f'{x:.6g}') for x in grid_values.ravel()]},
                 'isovalue': .035 if orbital is None else .02,
                 'samples': np.round(samples, 6).tolist(),
                 'sampling_note': f'{count} independent visualization samples, not {count} electrons or persistent identities; spatial probability is continuous, energy states are discrete'}
            if orbital:
                f['orbital'] = orbital
            return f

        fields = [field('joint_electrons', values, shape, spacing, 1600)]
        orbitals = []
        for i in range(len(method.mo_energy)):
            occupation = float(method.mo_occ[i])
            row = {'index': i+1, 'energy_hartree': float(method.mo_energy[i]), 'occupation': occupation}
            if i in selected:
                grid = orbital_values[:, selected.index(i)].reshape(orbital_shape)
                row['field_id'] = 'mo_'+str(i+1)
                row['grid_integral_probability'] = float(grid.sum()*orbital_spacing**3)
                if occupation and abs(row['grid_integral_probability']-1) > .015:
                    raise RuntimeError(f'Occupied orbital {i+1} integral {row["grid_integral_probability"]}: quadrature gap exceeds 1.5%')
                fields.append(field(row['field_id'], grid, orbital_shape, orbital_spacing, 500, dict(row)))
            orbitals.append(row)
        electronic = {'source': source, 'geometry': geometry, 'electron_count': mol.nelectron, 'orbitals': orbitals,
                      'total_energy_hartree': energy, 'dipole_debye': method.dip_moment(unit='Debye', verbose=0).tolist(),
                      'scope': 'Canonical RHF orbital energies/occupations and dipole for this geometry. Orbital eigenvalues are not excitation energies; no classical paths or discrete allowed radii.'}
        frame = {'molecules': molecules, 'fields': fields, 'electronic_structure': electronic}
        clock = scene.get('time_kind', 'snapshot')
        if clock != 'snapshot':
            key = 'time_s' if clock == 'physical' else 'parameter_value'
            frame[key] = raw.get(key, raw.get('cursor'))
        frames.append(frame)
        reports.append(source)
        print(f'frame={index}: {energy:.9f} hartree, {mol.nelectron} electrons, {len(occupied)} occupied orbitals; grid integral {integral:.6f}', flush=True)
    return dict(scene, frames=frames), reports


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--scene', type=Path, help='Calculate the placed molecules/frames in this JSON scene')
    parser.add_argument('--out', type=Path, default=ROOT/'data/chemistry_probability/water_deuterium.json')
    args = parser.parse_args()
    lib.num_threads(1)
    scene = json.loads(args.scene.read_text()) if args.scene else default_scene()
    result, reports = calculate(scene)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    # Atomic publish: failure never replaces a previously valid scene.
    temporary = args.out.with_suffix('.tmp')
    temporary.write_text(json.dumps(result, separators=(',', ':'), allow_nan=False)+'\n')
    temporary.replace(args.out)
    manifest = {'schema': 'trech_density_scene_manifest_v1', 'scene_sha256': hashlib.sha256(args.out.read_bytes()).hexdigest(),
                'generator': 'tools/quantum/build_density_scene.py', 'references': reports,
                'density_note': 'Total number density and individual |orbital|² grids; finite quadrature gaps retained, no renormalization.',
                'source': 'https://pyscf.org/pyscf_api_docs/pyscf.scf.html'}
    args.out.with_suffix('.manifest.json').write_text(json.dumps(manifest, indent=2)+'\n')


if __name__ == '__main__':
    main()
