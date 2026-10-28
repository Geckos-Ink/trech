#!/usr/bin/env python3
"""Offline integrity and electron-count gap of the independent joint-density fixture."""
import hashlib
import json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
p=ROOT/'data/chemistry_probability/water_deuterium.json'
manifest=json.loads(p.with_suffix('.manifest.json').read_text())
assert hashlib.sha256(p.read_bytes()).hexdigest()==manifest['scene_sha256']
scene=json.loads(p.read_text())
assert scene['schema']=='trech_chemistry_scene_v1' and scene['time_kind']=='parameter_scan'
assert len(scene['molecules'])==2 and len(scene['frames'])==3
for frame in scene['frames']:
 field=next(f for f in frame['fields'] if f['id']=='joint_electrons');source=field['source'];grid=field['grid']
 assert field['particle']=='electron' and field['owner_ids']==['water','deuterium']
 assert source['kind']=='quantum_reference' and not source['geant4_trained'] and source['scf_converged']
 assert len(grid['values'])==grid['shape'][0]*grid['shape'][1]*grid['shape'][2]
 integral=sum(grid['values'])*grid['spacing']**3
 assert abs(integral/source['electron_count']-1)<.001
 assert abs(integral-source['grid_integral_electrons'])<1e-5
 atoms=[dict(a,position=[x+y for x,y in zip(a['position'],m['position'])]) for m in frame['molecules'] for a in m['structure']['atoms']]
 assert field['geometry']=={'charge':0,'atoms':atoms}
 assert len(field['samples'])==1600 and 'not 1600 electrons' in field['sampling_note']
 electronic=frame['electronic_structure']
 assert sum(o['occupation'] for o in electronic['orbitals'])==electronic['electron_count']==12
 assert len(electronic['dipole_debye'])==3 and len(frame['fields'])==10
 for orbital in [f for f in frame['fields'] if 'orbital' in f]:
  row=orbital['orbital'];grid=orbital['grid']
  integral=sum(grid['values'])*grid['spacing']**3
  assert abs(integral-row['grid_integral_probability'])<5e-6
  if row['occupation']: assert abs(integral-1)<.015
  assert orbital['density_unit']=='probability/angstrom^3'
  assert orbital['geometry']==field['geometry']
  assert len(orbital['amplitude']['values'])==len(grid['values'])
  assert orbital['amplitude']['unit']=='angstrom^-3/2'
 assert len(json.dumps(frame).encode()) < 8388608
print('Independent joint-density fixture hash, geometry binding and <0.1% electron-count gap pass')

# An independently calculated closed-shell atom must resolve core/valence radial
# structure, preserve the electron inventory and include the spherical measure.
p=ROOT/'data/chemistry_probability/neon_atom.json'
manifest=json.loads(p.with_suffix('.manifest.json').read_text())
assert hashlib.sha256(p.read_bytes()).hexdigest()==manifest['scene_sha256']
neon=json.loads(p.read_text())['frames'][0]
profiles=neon['electronic_structure']['radial_profiles']
assert neon['electronic_structure']['electron_count']==10 and len(profiles)==1
profile=profiles[0];levels=profile['levels'];r=profile['radii_angstrom']
assert [g['occupation'] for g in levels]==[2,2,6]
peaks=[r[max(range(len(r)),key=lambda i:g['radial_probability_per_angstrom'][i])] for g in levels]
assert peaks[0]<.1 and min(peaks[1:])>.2
for g in levels:
 assert abs(g['finite_radius_integral_electrons']/g['occupation']-1)<.005
 for radius,density,probability in zip(r,g['density_average_per_angstrom3'],g['radial_probability_per_angstrom']):
  assert abs(probability-4*3.141592653589793*radius**2*density)<1e-10
assert len(neon['fields'][0]['energy_components'])==3
print('Neon computed core/valence radial separation, spherical measure and occupied-state counts pass')
