#!/usr/bin/env python3
"""D9 engineering negatives; synthetic one-frame controls, not acoustic evidence."""
import json
from pathlib import Path
import struct
import subprocess
import tempfile
import unittest
import dualmic_gated_rise_d9 as d9

class D9Controls(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=tempfile.TemporaryDirectory();cls.root=Path(cls.tmp.name)
        src=(d9.ROOT/'src/enhance/ap_agc.c').read_text()
        assert src.count(d9.BEFORE)==1
        candidate=src.replace(d9.BEFORE,d9.AFTER).replace('ap_agc_','d9_agc_').replace('d9_agc_state_t','ap_agc_state_t')
        assert candidate.replace('d9_agc_','ap_agc_').replace(d9.AFTER,d9.BEFORE)==src
        (cls.root/'base.c').write_text(src);(cls.root/'candidate.c').write_text(candidate)
        subprocess.run(['cc','-std=c11','-O2','-ffp-contract=off','-DAP_BUILD_STAGE_AGC=1','-I'+str(d9.ROOT/'src'),str(cls.root/'base.c'),str(cls.root/'candidate.c'),str(Path(d9.__file__).with_suffix('.c')),'-lm','-o',str(cls.root/'replay')],check=True,timeout=30)
    @classmethod
    def tearDownClass(cls):cls.tmp.cleanup()
    def run_case(self, inp=None, reference=None, control=None, profile='call', frames='1'):
        folder=self.root/self._testMethodName;folder.mkdir()
        (folder/'input').write_bytes(inp if inp is not None else b'\0'*640)
        (folder/'ref').write_bytes(reference if reference is not None else b'\0'*640)
        (folder/'ctl').write_bytes(control if control is not None else struct.pack('<IIff',0,0,1.,1.))
        return subprocess.run([str(self.root/'replay'),str(folder/'input'),str(folder/'ref'),str(folder/'ctl'),str(folder/'b'),str(folder/'c'),str(folder/'trace'),profile,frames],stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=5).returncode
    def test_closed_result_archive(self):
        raw=(d9.ROOT/'docs/research/frontend-evolution-v1/dualmic-gated-rise-d9-result.json').read_bytes()
        self.assertEqual(d9.sha(raw),'7116683c183971bd9d6df6b58f96056d9de1c36fef1a157afd36031f921fe68a')
        r=json.loads(raw);self.assertEqual(r['decision'],'NO_ADVANCE');self.assertFalse(r['promotion_allowed'])
        cases=r['cases'];self.assertEqual(len(cases),60)
        scores=[c['delta']['common']['near_si_sdr_change_db'] for c in cases if c['delta']['common']['near_si_sdr_change_db'] is not None]
        self.assertEqual(scores,[0.]*32)
        self.assertEqual(sum(len(c['delta']['one_second_windows']) for c in cases),362)
        self.assertFalse(r['screen']['doubletalk_1db'])
        self.assertEqual(sum(c['runtime']['baseline_gated_rise_frames'] for c in cases),532)
        self.assertEqual(sum(c['changed_samples'] for c in cases),52612)
        self.assertTrue(all(c['actual_clamp_sample_counts']==[0,0] for c in cases))
        self.assertEqual(sum(c['delta']['common']['near_si_sdr_change_db'] is None for c in cases),28)
    def test_pristine(self):self.assertEqual(self.run_case(),0)
    def test_selftest(self):
        r=subprocess.run([str(self.root/'replay'),'--self-test'],stdout=subprocess.PIPE,check=True,timeout=5)
        self.assertEqual(json.loads(r.stdout)['selftest_cases'],120)
    def test_nan(self):self.assertEqual(self.run_case(inp=struct.pack('<f',float('nan'))+b'\0'*636),3)
    def test_short(self):self.assertEqual(self.run_case(inp=b'\0'*636),3)
    def test_extra(self):self.assertEqual(self.run_case(inp=b'\0'*644),3)
    def test_invalid_allow(self):self.assertEqual(self.run_case(control=struct.pack('<IIff',2,0,1.,1.)),3)
    def test_invalid_reset(self):self.assertEqual(self.run_case(control=struct.pack('<IIff',0,2,1.,1.)),3)
    def test_baseline_state(self):self.assertEqual(self.run_case(control=struct.pack('<IIff',0,0,.5,1.)),4)
    def test_baseline_pcm(self):self.assertEqual(self.run_case(reference=struct.pack('<f',.01)+b'\0'*636),4)
    def test_invalid_profile(self):self.assertEqual(self.run_case(profile='bogus'),2)
    def test_invalid_frames(self):self.assertEqual(self.run_case(frames='0'),2)
if __name__=='__main__':unittest.main()
