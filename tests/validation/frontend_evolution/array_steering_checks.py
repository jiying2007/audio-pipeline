#!/usr/bin/env python3
"""Transition known answers extending the existing array gate, not acoustic scores."""
from __future__ import annotations
import copy
import math
from pathlib import Path
import struct
import unittest
from contracts import ROOT, load_json, require
from libfvad_reference import run_logged
from array_qualification import PLAN as STATIC_PLAN, delays, geometry_text, make_input, oracle

PLAN=ROOT/'.github/research/frontend-evolution-v1/array-steering-v1.json'


def cases(plan):
    geometries={g['id']:g for g in load_json(STATIC_PLAN)['geometries']}
    for name in plan['geometries']:
        for pattern in plan['patterns']:
            for mode in plan['interpolations']:
                for duration in plan['transition_samples']:
                    yield f'{name}-{pattern}-{mode}-{duration}',geometries[name],pattern,mode,duration


def commands(plan,duration):
    rows=['FE_STEERING_V1 2']
    for at,direction in zip(plan['command_samples'],plan['directions']):
        rows.append(' '.join(map(str,[at,duration,*direction])))
    return ('\n'.join(rows)+'\n').encode()


def blend_banks(banks,starts,duration):
    result=list(banks[0])
    for j,start in enumerate(starts):
        end=starts[j+1] if j+1<len(starts) else len(result)
        for n in range(start,end):
            a=min(1.0,(n-start)/(duration-1))
            result[n]=(1.0-a)*banks[j][n]+a*banks[j+1][n]
    return result


def expected(data,g,mode,plan,duration):
    banks=[oracle(data,g,mode)]
    for direction in plan['directions']:
        other=copy.deepcopy(g);other['direction']=direction
        require(delays(other)[0]==delays(g)[0],'direction changed common latency')
        banks.append(oracle(data,other,mode))
    return blend_banks(banks,plan['command_samples'],duration)


def read_floats(path,count):
    raw=path.read_bytes();require(len(raw)==count*4,'steering output count mismatch')
    values=[v[0] for v in struct.iter_unpack('<f',raw)]
    require(all(math.isfinite(x) for x in values),'non-finite steering output')
    return values


def error_of(values,reference):
    return max(abs(a-b) for a,b in zip(values,reference))


def run(root,targets):
    plan=load_json(PLAN);(root/'steering').mkdir()
    (root/'steering/experiment.json').write_bytes(PLAN.read_bytes())
    report={'experiment_id':plan['experiment_id'],'shipping_authority':False,
            'acoustic_improvement_proved':False,'automatic_doa':False,'aec_recovery_proved':False,'cases':[]}
    for key,g,pattern,mode,duration in cases(plan):
        d=root/'steering'/key;d.mkdir()
        data=make_input(g,pattern,plan['frames_per_case'])
        (d/'input.pcm').write_bytes(data);(d/'geometry.txt').write_bytes(geometry_text(g,mode))
        (d/'commands.txt').write_bytes(commands(plan,duration))
        boundary=plan['prefix_frames']*len(g['positions_m'])*2
        future=data[:boundary]+bytes(b^0x5a for b in data[boundary:])
        (d/'future.pcm').write_bytes(future)
        reference=expected(data,g,mode,plan,duration)
        for arch,binary,prefix in targets:
            for suffix,pcm,chunk in [('',d/'input.pcm',480),('-repeat',d/'input.pcm',480),
                                     ('-chunk',d/'input.pcm',plan['alternate_chunk_samples']),('-future',d/'future.pcm',480)]:
                dest=d/(arch+suffix)
                run_logged([*prefix,binary,d/'geometry.txt',pcm,dest.with_suffix('.f32'),dest.with_suffix('.json'),
                            d/'commands.txt',str(chunk)],dest.with_suffix('.log'))
            error=error_of(read_floats(d/f'{arch}.f32',len(reference)),reference)
            require(error<=plan['maximum_absolute_oracle_error'],'steering oracle mismatch')
            report['cases'].append({'case_id':key,'target':arch,'maximum_absolute_oracle_error':error})
    return report


def verify(root,report,targets):
    plan=load_json(root/'steering/experiment.json');require(plan==load_json(PLAN),'steering policy changed')
    require(report['experiment_id']==plan['experiment_id'] and report['shipping_authority'] is False and
            report['acoustic_improvement_proved'] is False and report['automatic_doa'] is False and
            report['aec_recovery_proved'] is False,'steering authority mismatch')
    required={(key,arch) for key,*_ in cases(plan) for arch in targets}
    rows={(r['case_id'],r['target']):r for r in report['cases']}
    require(len(rows)==len(report['cases']) and set(rows)==required,'missing/duplicate steering cases')
    for arch in [*targets,'sanitized']:
        unit=load_json(root/f'steering-unit-{arch}.json')
        require(unit['status']=='PASS' and unit['blend_configurations']==120 and unit['assertions']>=300000 and
                unit['stress_frames']==32000 and unit['lifecycles']==64 and
                unit['maximum_blend_error']<=plan['maximum_absolute_oracle_error'] and
                0<unit['controller_state_bytes']<=plan['maximum_controller_bytes'] and
                0<unit['array_state_bytes']<=plan['maximum_state_bytes'],'steering unit evidence incomplete')
    for key,g,pattern,mode,duration in cases(plan):
        d=root/'steering'/key;data=(d/'input.pcm').read_bytes()
        require(data==make_input(g,pattern,plan['frames_per_case']),'steering fixture changed')
        require((d/'geometry.txt').read_bytes()==geometry_text(g,mode),'steering geometry changed')
        require((d/'commands.txt').read_bytes()==commands(plan,duration),'steering commands changed')
        boundary=plan['prefix_frames']*len(g['positions_m'])*2
        future=data[:boundary]+bytes(b^0x5a for b in data[boundary:])
        require((d/'future.pcm').read_bytes()==future,'steering future input changed')
        reference=expected(data,g,mode,plan,duration)
        last=copy.deepcopy(g);last['direction']=plan['directions'][-1];latency,ds=delays(last)
        for arch in targets:
            values=read_floats(d/f'{arch}.f32',len(reference));raw=(d/f'{arch}.f32').read_bytes()
            error=error_of(values,reference)
            require(error==rows[key,arch]['maximum_absolute_oracle_error'] and error<=plan['maximum_absolute_oracle_error'],
                    'steering score or PCM mismatch')
            for suffix in ('','-repeat','-chunk','-future'):
                meta=load_json(d/f'{arch}{suffix}.json')
                actual=read_floats(d/f'{arch}{suffix}.f32',len(reference))
                require(meta['status']=='PASS' and meta['samples_processed']==plan['frames_per_case'] and
                        meta['mic_count']==len(g['positions_m']) and meta['sample_rate_hz']==g['sample_rate_hz'] and
                        meta['active_mask']==g['active_mask'] and meta['common_delay_samples']==latency and
                        meta['interpolation']==plan['interpolations'].index(mode) and
                        meta['steering_accepted']==meta['steering_completed']==2 and
                        meta['steering_cancelled']==meta['transition_remaining_samples']==0 and
                        meta['direction']==plan['directions'][-1] and meta['shipping_authority'] is False and
                        meta['output_encoding']=='f32le-unclipped','steering transport receipt mismatch')
                require(meta['state_bytes']==load_json(root/f'steering-unit-{arch}.json')['array_state_bytes']-
                        (4-len(g['positions_m']))*128*4,'steering state accounting')
                require(len(meta['compensation_samples'])==len(ds) and
                        max(abs(a-b) for a,b in zip(meta['compensation_samples'],ds))<1e-10,'wrong target compensation')
                other=(d/f'{arch}{suffix}.f32').read_bytes()
                if suffix in ('-repeat','-chunk'):require(other==raw,'steering repeat/chunk drift')
                if suffix=='-future':
                    require(other[:plan['prefix_frames']*4]==raw[:plan['prefix_frames']*4],'steering future leak')
                    require(error_of(actual,expected(future,g,mode,plan,duration))<=plan['maximum_absolute_oracle_error'],
                            'future output not processed correctly')
    return len(rows)


class SteeringOracleTests(unittest.TestCase):
    def test_endpoints_and_repeated_commands(self):
        b=[[1.]*20,[3.]*20,[-2.]*20];v=blend_banks(b,[2,10],4)
        self.assertEqual(v[:3],[1.]*3);self.assertEqual(v[5:11],[3.]*6);self.assertEqual(v[13:],[-2.]*7)
        self.assertAlmostEqual(v[3],1.+2./3.)
    def test_two_sample_transition(self):
        self.assertEqual(blend_banks([[1.]*6,[2.]*6],[2],2),[1.,1.,1.,2.,2.,2.])
    def test_exact_matrix_and_boundaries(self):
        p=load_json(PLAN);self.assertEqual(len(list(cases(p))),48)
        for t in p['transition_samples']:
            self.assertLess(p['command_samples'][0]+t,p['command_samples'][1])
            self.assertLess(p['command_samples'][1]+t,p['frames_per_case'])
        self.assertFalse(p['shipping_authority']);self.assertFalse(p['automatic_doa'])
    def test_policy_contract(self):
        self.assertEqual(load_json(PLAN)['policy'],{'minimum_confidence':.8,'minimum_coherent_observations':3,
            'minimum_stable_ms':20,'maximum_coherence_angle_degrees':5,'minimum_change_degrees':15,'cooldown_ms':200,
            'maximum_observation_age_ms':20,'maximum_observation_gap_ms':20,'transition_ms':20,
            'speech_required':True,'render_playback_holds':True})


if __name__=='__main__':unittest.main()
