#!/usr/bin/env python3
"""Offline contracts and explicit re-sealed evidence failures; no speech tuning."""
import argparse
import copy
import json
import math
from pathlib import Path
import shutil
import struct
import tempfile
import unittest
from contracts import load_json
from libfvad_reference import write_json, seal_output
from speech_source import select_members, flac_info
from speech_spatial import N, RATE, geometry, delays, gains, sinc_taps, values, encode, metrics, verify


class Contracts(unittest.TestCase):
    def names(self):
        return [f'LibriSpeech/dev-clean/{s}/20/{s}-20-{u:04}.flac' for s in (123,2,10,4,8,6,7,5,99) for u in range(4)]
    def test_numeric_selection(self):
        self.assertEqual([s for s,_ in select_members(self.names())],[2,4,5,6,7,8,10,99])
    def test_selection_order_independent(self):
        self.assertEqual(select_members(self.names()),select_members(list(reversed(self.names()))))
    def test_no_duplicate(self):
        with self.assertRaises(ValueError):select_members(self.names()+self.names()[:1])
    def test_path_traversal(self):
        for name in ('../file','/tmp/file','dir\\file'):
            with self.assertRaises(ValueError):select_members(self.names()+[name])
    def test_source_identity(self):
        with self.assertRaises(ValueError):select_members(self.names()+['LibriSpeech/dev-clean/2/20/3-20-0040.flac'])
    def test_source_count(self):
        with self.assertRaises(ValueError):select_members(self.names()[:4])
    def test_flac_format(self):
        b=bytearray(42);b[:4]=b'fLaC';b[7]=34;b[18:26]=((16000<<44)|(15<<36)|64000).to_bytes(8,'big')
        self.assertEqual(flac_info(bytes(b)),(16000,1,16,64000))
        b[18:26]=((48000<<44)|(15<<36)|64000).to_bytes(8,'big')
        with self.assertRaises(ValueError):flac_info(bytes(b))
    def test_common_aperture_delay(self):
        for name in ('dual70','ula4-70','uca4-70'):
            for az in (0,60,90,150):self.assertEqual(delays(geometry(name,az))[0],5)
    def test_sinc_dc_and_identity(self):
        for a in (0,.1,.5,1.1,-.3,3.265306):self.assertAlmostEqual(sum(w for _,w in sinc_taps(a)),1,places=12)
        self.assertAlmostEqual(dict(sinc_taps(0))[0],1,places=12)
    def test_equal_rms(self):
        t=[.1,-.2,.3,-.4];i=[.9,-.3,.2,-.1];a,b=gains(t,i)
        self.assertAlmostEqual(sum((a*x)**2 for x in t),sum((b*x)**2 for x in i))
        self.assertLessEqual(a*max(map(abs,t))+b*max(map(abs,i)),.25000000001)
    def test_zero_speech_rejected(self):
        with self.assertRaises(ValueError):gains([0,0],[1,1])
    def test_pcm_roundtrip(self):
        self.assertEqual(values(encode([-32768,0,32767],'h'),'h',3),[-32768,0,32767])
        with self.assertRaises(ValueError):values(b'\x00','h',1)
        with self.assertRaises(ValueError):values(struct.pack('<f',float('nan')),'f',1)
    def test_metric_fixed_delay(self):
        t=[.1*math.sin(2*math.pi*731*k/RATE) for k in range(N)]
        i=[.1*math.sin(2*math.pi*1709*k/RATE) for k in range(N)]
        yt=[0]*5+t[:-5];yi=[0]*5+i[:-5];ym=[a+b for a,b in zip(yt,yi)]
        result=metrics(t,i,yt,yi,ym,5)
        self.assertAlmostEqual(result['component_sir_gain_db'],0,places=12)
        self.assertEqual(result['target_relative_error_energy'],0)
        self.assertLess(metrics(t,i,yt,yi,ym,0)['canonical_si_sdr_db'],result['canonical_si_sdr_db'])
    def test_metric_rejects_missing_and_nonlinear(self):
        t=[.1]*N;i=[.2]*N
        with self.assertRaises(ValueError):metrics(t,i,t,i,[.3]*(N-1),0)
        with self.assertRaises(ValueError):metrics(t,i,t,i,[0.0]*N,0)


def negative_evidence(path:Path):
    """Mutate a scratch copy; preserve the original evidence and re-seal each fault."""
    base=load_json(path/'result.json');case=base['cases'][0]['case_id'];answers={}
    changes={
      'missing-case': lambda r:r['cases'].pop(),
      'duplicate-case':lambda r:r['cases'].append(copy.deepcopy(r['cases'][0])),
      'wrong-role':lambda r:r['cases'][0].update(role='blind'),
      'false-promotion':lambda r:r.update(shipping_authority=True),
      'false-real-array':lambda r:r.update(real_array_recording=True),
      'false-doa':lambda r:r.update(oracle_directions=False),
      'missing-arm':lambda r:r['cases'][0]['arms'].pop('linear'),
      'wrong-score':lambda r:r['cases'][0]['arms']['linear'].update(canonical_si_sdr_db=999.0),
      'changed-summary':lambda r:r['summary'][0].update(speaker_pairs=999),
      'wrong-execution':lambda r:r.update(execution_source_revision='f'*40),
      'changed-gain':lambda r:r['cases'][0]['gains'].__setitem__(0,99.0),
    }
    with tempfile.TemporaryDirectory(prefix='fe-speech-negative-') as tmp:
        scratch=Path(tmp)/'evidence';shutil.copytree(path,scratch)
        for name,change in changes.items():
            report=copy.deepcopy(base);change(report);write_json(scratch/'result.json',report);seal_output(scratch,report)
            try:verify(scratch,base['execution_source_revision'])
            except ValueError:answers[name]='REJECTED'
            else:raise AssertionError('false evidence passed: '+name)
        write_json(scratch/'result.json',base)
        target=scratch/'cases'/case/'linear/mixture.f32';original=target.read_bytes();target.write_bytes(original[:-4]);seal_output(scratch,base)
        try:verify(scratch,base['execution_source_revision'])
        except ValueError:answers['truncated-output']='REJECTED'
        else:raise AssertionError('truncated output passed')
    return answers


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--evidence',type=Path);args=parser.parse_args()
    if args.evidence:print(json.dumps(negative_evidence(args.evidence),sort_keys=True))
    else:unittest.main(argv=['test_speech_spatial'])
