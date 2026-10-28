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
 field=frame['fields'][0];source=field['source'];grid=field['grid']
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
 assert len(electronic['dipole_debye'])==3 and len(frame['fields'])==8
 for orbital in frame['fields'][1:]:
  row=orbital['orbital'];grid=orbital['grid']
  integral=sum(grid['values'])*grid['spacing']**3
  assert abs(integral-row['grid_integral_probability'])<5e-6
  if row['occupation']: assert abs(integral-1)<.015
  assert orbital['density_unit']=='probability/angstrom^3'
  assert orbital['geometry']==field['geometry']
 assert len(json.dumps(frame).encode()) < 4194304
print('Independent joint-density fixture hash, geometry binding and <0.1% electron-count gap pass')
