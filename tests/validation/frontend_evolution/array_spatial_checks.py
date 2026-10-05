#!/usr/bin/env python3
"""Fixed spatial bank known answers integrated into existing array evidence."""
from __future__ import annotations
import math
from pathlib import Path
import struct
import unittest
from contracts import ROOT, load_json, require, sha256
from libfvad_reference import run_logged, write_json
from spatial_weights import design, response, config_text, solve, LOADS
from array_qualification import FLAGS
from speech_spatial import geometry

HERE=Path(__file__).resolve().parent
PLAN=ROOT/'.github/research/frontend-evolution-v1/spatial-weights-v1.json'


def cases():
    for name in ('dual70','ula4-70','uca4-70'):
        for angle in (0,30,60,90):
            for load in LOADS:
                yield f'{name}-{angle}-{load}',geometry(name,angle),load


def signal(n):
    return struct.pack('<'+'h'*(480*n),*[((t*7+i*13)%101-50)*64 for t in range(480) for i in range(n)])


def direct_oracle(pcm,g,bank):
    n=len(g['positions_m']);x=[v[0]/32768 for v in struct.iter_unpack('<h',pcm)];start=bank['tap_start_samples']
    return [sum(float(v)*x[(t-start-k)*n+g['channel_map'][i]]
                for i,row in enumerate(bank['coefficients']) for k,v in enumerate(row) if t>=start+k)
            for t in range(len(x)//n)]


def run(root,targets):
    d=root/'spatial';d.mkdir();p=load_json(PLAN);write_json(d/'experiment.json',p)
    record={'experiment_id':p['experiment_id'],'shipping_authority':False,'cases':[],'unit_binaries':{}}
    for arch,_,prefix in targets+[('sanitized',None,[])]:
        dest=d/('unit-'+arch);compiler='arm-linux-gnueabihf-gcc' if arch=='arm' else 'cc'
        flags=FLAGS+(['-mcpu=cortex-a32','-mfpu=neon-fp-armv8','-mfloat-abi=hard'] if arch=='arm' else [])
        if arch=='sanitized':flags=flags+['-O1','-g','-fsanitize=address,undefined','-fno-omit-frame-pointer']
        command=[compiler,*flags,HERE/'array_native.c',HERE/'array_spatial_test.c','-lm','-o',dest]
        write_json(d/('build-'+arch+'.json'),{'command':list(map(str,command))});run_logged(command,d/('build-'+arch+'.log'))
        run_logged([*prefix,dest],d/('unit-'+arch+'.json'),timeout=180)
        record['unit_binaries'][arch]=sha256(dest.read_bytes())
    for key,g,load in cases():
        sub=d/key;sub.mkdir();bank=design(g,load);cfg=config_text(g,bank);data=signal(len(g['positions_m']))
        write_json(sub/'bank.json',bank);write_json(sub/'response.json',{'realized_fir':response(bank)})
        (sub/'geometry.txt').write_bytes(cfg);(sub/'input.pcm').write_bytes(data)
        cut=240*len(g['positions_m'])*2;(sub/'future.pcm').write_bytes(data[:cut]+bytes(b^0x55 for b in data[cut:]))
        expected=direct_oracle(data,g,bank)
        for arch,binary,prefix in targets:
            for kind in ('main','repeat','future'):
                run_logged([*prefix,binary,sub/'geometry.txt',sub/('future.pcm' if kind=='future' else 'input.pcm'),
                           sub/f'{arch}-{kind}.f32',sub/f'{arch}-{kind}.json'],sub/f'{arch}-{kind}.log')
            actual=[v[0] for v in struct.iter_unpack('<f',(sub/f'{arch}-main.f32').read_bytes())]
            require(len(actual)==480,'spatial PCM cardinality')
            error=max(abs(a-b) for a,b in zip(actual,expected));require(error<=p['oracle_error_bound'],'spatial C/oracle mismatch')
            record['cases'].append({'case_id':key,'target':arch,'bank_sha256':sha256((sub/'bank.json').read_bytes()),'max_absolute_error':error})
    return record


def verify(root,record,targets):
    d=root/'spatial';p=load_json(PLAN)
    require(load_json(d/'experiment.json')==p and record['experiment_id']==p['experiment_id'] and record['shipping_authority'] is False,'spatial identity/authority')
    require(set(record['unit_binaries'])==set([*targets,'sanitized']),'spatial unit targets')
    for arch in [*targets,'sanitized']:
        binary=(d/('unit-'+arch)).read_bytes();u=load_json(d/('unit-'+arch+'.json'))
        require(binary[:4]==b'\x7fELF' and sha256(binary)==record['unit_binaries'][arch],'spatial unit identity')
        require(u['status']=='PASS' and u['configurations']==15 and u['stress_frames']==7680 and u['state_bytes_4']==3704 and u['assertions']>=100000,'spatial unit coverage')
    rows={(r['case_id'],r['target']):r for r in record['cases']}
    expected_keys={(key,a) for key,*_ in cases() for a in targets}
    require(set(rows)==expected_keys and len(rows)==len(record['cases']),'spatial missing/duplicate cases')
    for key,g,load in cases():
        sub=d/key;bank=design(g,load);data=signal(len(g['positions_m']));cut=240*len(g['positions_m'])*2
        require(load_json(sub/'bank.json')==bank and (sub/'geometry.txt').read_bytes()==config_text(g,bank),'spatial bank/geometry changed')
        require(load_json(sub/'response.json')=={'realized_fir':response(bank)},'ideal-versus-realized response drift')
        require((sub/'input.pcm').read_bytes()==data and (sub/'future.pcm').read_bytes()==data[:cut]+bytes(b^0x55 for b in data[cut:]),'spatial input mutation')
        expected=direct_oracle(data,g,bank)
        for arch in targets:
            pcm=(sub/f'{arch}-main.f32').read_bytes();require(len(pcm)==480*4,'spatial PCM count')
            actual=[v[0] for v in struct.iter_unpack('<f',pcm)];require(all(math.isfinite(v) for v in actual),'spatial non-finite output')
            error=max(abs(a-b) for a,b in zip(actual,expected));row=rows[key,arch]
            require(row['bank_sha256']==sha256((sub/'bank.json').read_bytes()) and row['max_absolute_error']==error and error<=p['oracle_error_bound'],'spatial oracle changed')
            require(pcm==(sub/f'{arch}-repeat.f32').read_bytes() and pcm[:240*4]==(sub/f'{arch}-future.f32').read_bytes()[:240*4],'spatial repeat/causality')
            for kind in ('main','repeat','future'):
                meta=load_json(sub/f'{arch}-{kind}.json')
                require(meta['status']=='PASS' and meta['mic_count']==len(g['positions_m']) and meta['sample_rate_hz']==16000 and meta['active_mask']==(1<<len(g['positions_m']))-1 and meta['interpolation']==4 and meta['common_delay_samples']==21 and meta['samples_processed']==480 and meta['shipping_authority'] is False and meta['steering_accepted']==0,'spatial metadata')
    return len(rows)


class SpatialTests(unittest.TestCase):
    def test_solve_known(self):
        self.assertEqual(solve([[2,1],[1,2]],[3,0]),[2+0j,-1+0j])
    def test_singular_rejected(self):
        with self.assertRaises(ValueError):solve([[1,1],[1,1]],[1,0])
    def test_scope_rejects_mask(self):
        g=geometry('uca4-70',0);g['active_mask']=7
        with self.assertRaises(ValueError):design(g,.1)
    def test_no_load_sweep(self):
        with self.assertRaises(ValueError):design(geometry('dual70',0),.01)
    def test_mono_identity(self):
        g=geometry('dual70',0);g.update(positions_m=[[0,0,0]],active_mask=1,gains=[1],latency_samples=[0],channel_map=[0])
        b=design(g,.1);self.assertAlmostEqual(b['coefficients'][0][16],1)
        self.assertLess(sum(abs(v) for i,v in enumerate(b['coefficients'][0]) if i!=16),1e-10)
    def test_dc_and_distinct_weights(self):
        b=design(geometry('ula4-70',60),.1)
        self.assertAlmostEqual(sum(sum(r) for r in b['coefficients']),1,places=6)
        self.assertNotEqual(b['coefficients'][0],b['coefficients'][1])
    def test_next_source_disjoint(self):
        from speech_source import select_members
        names=[f'LibriSpeech/dev-clean/{s}/1/{s}-1-{u}.flac' for s in range(1,17) for u in range(4)]
        self.assertEqual([s for s,_ in select_members(names,8)],list(range(9,17)))
        for offset in (-1,1,True,16):
            with self.assertRaises(ValueError):select_members(names,offset)
    def test_frozen_matrix(self):
        p=load_json(PLAN);self.assertEqual(p['diagonal_loads'],[.1,1.0]);self.assertEqual(p['taps'],33)
        self.assertEqual(len(list(cases())),24)
