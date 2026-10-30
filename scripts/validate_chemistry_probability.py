#!/usr/bin/env python3
"""Geant4 nuclear probe isolation and recorded electronic comparison gates."""
from __future__ import annotations
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
ROOT=Path(__file__).resolve().parents[1]

def rows(path): return [json.loads(s) for s in path.read_text().splitlines() if s.strip()]

def main():
    output=ROOT/'build/chemistry_probability_validation';output.mkdir(parents=True,exist_ok=True)
    source=ROOT/'data/chemistry_probability/water_deuterium.json'
    manifest=json.loads(source.with_suffix('.manifest.json').read_text())
    assert hashlib.sha256(source.read_bytes()).hexdigest()==manifest['scene_sha256']
    assert all(r['scf_converged'] and not r['geant4_trained'] and r['grid_integral_relative_gap']<.01 for r in manifest['references'])
    reports=[]; physics={}
    for mode in ('predictive','strict'):
        for count in (0,8):
            label=f'{mode}_{count}';out=output/label
            command=[str(ROOT/'build/rel/trech'),'run',str(ROOT/'examples/scenarios/chemistry_probability_reference/chemistry_probability_reference.js'),
                     '--output',str(out),'--param',f'mode="{mode}"','--param','events=3','--param',f'nuclear_samples={count}']
            previous=None
            for repeat in range(2):
                if out.exists(): shutil.rmtree(out)
                result=subprocess.run(command,cwd=ROOT,capture_output=True,text=True)
                (output/f'{label}_{repeat}.log').write_text(result.stdout+result.stderr)
                assert result.returncode==0,label
                snapshot={name:(out/name).read_bytes() for name in ('trech_scores.jsonl','trech_provenance.jsonl','trech_hook_emits.jsonl')}
                if previous is not None: assert snapshot==previous,label+' replay changed'
                previous=snapshot
            score=rows(out/'trech_scores.jsonl')[-1]
            assert score['hook_predict_count']==0 and score['hook_emit_dropped_count']==0
            events=rows(out/'trech_hook_emits.jsonl')
            frames=[e['payload'] for e in events if e['tag']=='quantum_frame']
            assert len(frames)==3 and all(f['time_kind']=='parameter_scan' and f['physical_time_s'] is None for f in frames)
            for frame in frames:
                assert len(frame['fields'])==10 and not frame['omitted_fields']
                difference=frame['fields'][-1]
                assert difference['quantity']=='density_difference'
                assert difference['statistics']['negative_integral']>0 and difference['statistics']['positive_integral']>0
                assert next(f for f in frame['fields'] if f.get('orbital'))['amplitude']['values']
                assert len(frame['fields'][0]['statistics']['mass_levels'])==99
                electronic=frame['electronic_structure']
                assert sum(o['occupation'] for o in electronic['orbitals'])==12
                assert frame['particle_inventory']=={'protons':12,'neutrons':10,'electrons':12}
                field=next(f for f in frame['fields'] if f['id']=='joint_electrons')
                assert field['owner_ids']==['water','deuterium'] and field['source']['kind']=='quantum_reference'
                assert len(field['samples'])==1600 and field['source']['grid_integral_relative_gap']<.01
            ensembles=[e['payload'] for e in events if e['tag']=='chemistry_nuclear_ensemble']
            assert bool(ensembles)==bool(count)
            if count:
                for item in ensembles[0]['ensembles']:
                    data=item['data']
                    if not data['available']: continue
                    assert len(data['configurations'])==count
                    assert data['time_kind']=='ensemble_index' and data['length_unit']=='fm'
                    for sample in data['configurations']:
                        assert len(sample['protons'])==data['z'] and len(sample['neutrons'])==data['a']-data['z']
                        assert sample['statistics']['protons']['count']==data['z']
                    assert sum(data['radial_distribution']['proton_counts'])==data['z']*count
                    assert sum(data['radial_distribution']['neutron_counts'])==(data['a']-data['z'])*count
            physical={k:v for k,v in score.items() if k.startswith('primaries_') or k in ('total_edep_mev','event_feature_stats')}
            if mode in physics: assert physical==physics[mode], 'nuclear diagnostic changed Geant4 transport'
            physics[mode]=physical
            reports.append({'mode':mode,'nuclear_samples':count,'byte_identical':True,'transport_unchanged':True,'density_frames':3})
            print('PASS',label,flush=True)
    (output/'report.json').write_text(json.dumps(reports,indent=2)+'\n')
    print('8 real Geant4 runs pass; QM density remains independent comparison and nuclei remain initial-state samples.')
if __name__=='__main__': main()
