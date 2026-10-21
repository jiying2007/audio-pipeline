"""D44 baseline exclusions must preserve waveform and past-state contracts."""
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from tools.codex_assets import device_innovation_noise_gate as gate

class InnovationNoiseGateTests(unittest.TestCase):
    def test_baseline_projection_only_allows_declared_gain_fields(self):
        a={'power':[{'noise_sum':'1','floor_mean':'.2','raised_bins':'0'}],
           'bins':[{'N':'1','valid':'1','floor':'.2','old_gain':'.5'}]}
        b={'power':[{'noise_sum':'1','floor_mean':'.4','raised_bins':'1'}],
           'bins':[{'N':'1','valid':'1','floor':'.4','old_gain':'.6'}]}
        gate.baseline_trace(a,b)
        for section,key in (('power','noise_sum'),('bins','N'),('bins','valid')):
            with self.subTest(section=section,key=key):
                original=b[section][0][key];b[section][0][key]='2'
                with self.assertRaises(ValueError):gate.baseline_trace(a,b)
                b[section][0][key]=original

    def test_projection_rejects_missing_and_extra_rows(self):
        for a,b in (([],[{}]),([{}],[]),([{},{}],[{}])):
            with self.assertRaises(ValueError):gate.project_equal(a,b,set(),'test')

    def test_monitor_only_excludes_floor_mean(self):
        a=[{key:'0' for key in gate.PROTECTION_FIELDS}]
        b=[dict(a[0],floor_mean='.5')]
        gate.project_equal(a,b,{'floor_mean'},'monitor')
        for key in gate.PROTECTION_FIELDS[:-1]:
            with self.subTest(key=key):
                b[0][key]='1'
                with self.assertRaises(ValueError):gate.project_equal(a,b,{'floor_mean'},'monitor')
                b[0][key]='0'

    def test_existing_root_and_symlink_rejected_without_preflight(self):
        with tempfile.TemporaryDirectory(prefix='audio-d44-unit-') as name:
            root=Path(name)
            with patch.object(gate,'preflight',side_effect=AssertionError('must not read')):
                with self.assertRaises(ValueError):gate.run(root)
                link=root/'alias';link.symlink_to(root)
                with self.assertRaises(ValueError):gate.run(link)

    def test_monitor_audio_and_control_never_excluded(self):
        with tempfile.TemporaryDirectory(prefix='audio-d44-unit-') as name:
            root=Path(name);a=root/'a';b=root/'b';a.mkdir();b.mkdir()
            for directory in (a,b):
                for filename in gate.OUTPUTS[:4]:(directory/filename).write_bytes(b'original')
                (directory/'protection.csv').write_text(','.join(gate.PROTECTION_FIELDS)+'\n'+','.join(['0']*8)+'\n')
            gate.baseline_outputs(a,b,'monitor')
            for filename in gate.OUTPUTS[:4]:
                with self.subTest(filename=filename):
                    (a/filename).write_bytes(b'changed')
                    with self.assertRaises(ValueError):gate.baseline_outputs(a,b,'monitor')
                    (a/filename).write_bytes(b'original')
            (a/'ns.f32le').write_bytes(b'candidate-change')
            gate.baseline_outputs(a,b,'candidate')
            (a/'bypass.f32le').write_bytes(b'changed')
            with self.assertRaises(ValueError):gate.baseline_outputs(a,b,'candidate')

if __name__=='__main__':unittest.main()

