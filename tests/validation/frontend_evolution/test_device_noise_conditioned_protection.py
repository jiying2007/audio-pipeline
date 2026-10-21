import unittest
import json
import subprocess
import tempfile
from pathlib import Path
from unittest.mock import patch
from tools.codex_assets.device_noise_conditioned_protection import aligned_range,f32,encode,logged,matrix_budget,development_admission

class NoiseConditionedProtectionContract(unittest.TestCase):
    def test_matrix_clock_at_frozen_budget(self):
        with patch('tools.codex_assets.device_noise_conditioned_protection.time.monotonic',return_value=1900):
            matrix_budget(100)
    def test_matrix_clock_after_frozen_budget_rejects(self):
        with patch('tools.codex_assets.device_noise_conditioned_protection.time.monotonic',return_value=1900.0001):
            with self.assertRaises(ValueError):matrix_budget(100)
    def test_ola_whole_tail_is_explicit(self):
        self.assertEqual(aligned_range(0,3200,3200),dict(input_range=[0,3040],output_range=[160,3200],tail_truncated_samples=160))
    def test_fixed_window_shift(self):
        self.assertEqual(aligned_range(1600,1920,3200),dict(input_range=[1600,1920],output_range=[1760,2080],tail_truncated_samples=0))
    def test_tail_only_is_null(self):
        self.assertIsNone(aligned_range(3040,3200,3200))
    def test_invalid_range_rejected(self):
        for args in ((-1,10,320),(10,10,320),(0,400,320)):
            with self.assertRaises(ValueError):aligned_range(*args)
    def test_binary32_output_clamp_coordinate(self):
        limit=f32(10**(-2/20));gain=f32(.5)
        self.assertEqual(encode([max(-limit,min(limit,f32(v*gain))) for v in [-2,0,2]]),encode([-limit,0,limit]))
    def test_timeout_preserves_command_and_partial_output(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);error=subprocess.TimeoutExpired(['fixture'],120,output=b'partial',stderr=b'err')
            with patch('tools.codex_assets.device_noise_conditioned_protection.subprocess.run',side_effect=error):
                with self.assertRaises(subprocess.TimeoutExpired):logged(root,'timeout',['fixture'],root)
            value=json.loads((root/'command-timeout.json').read_text())
            self.assertIsNone(value['exit_code']);self.assertEqual(value['stdout'],'partial');self.assertEqual(value['stderr'],'err')
            self.assertEqual(value['command'],['fixture']);self.assertEqual(value['error_type'],'TimeoutExpired')
            with patch('tools.codex_assets.device_noise_conditioned_protection.subprocess.run') as run:
                with self.assertRaises(ValueError):logged(root,'timeout',['fixture'],root)
                run.assert_not_called()
    def test_start_failure_preserves_null_exit(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            with patch('tools.codex_assets.device_noise_conditioned_protection.subprocess.run',side_effect=FileNotFoundError('fixture')):
                with self.assertRaises(FileNotFoundError):logged(root,'missing',['fixture'],root)
            value=json.loads((root/'command-missing.json').read_text())
            self.assertIsNone(value['exit_code']);self.assertEqual(value['error_type'],'FileNotFoundError')
            self.assertEqual(value['cwd'],str(root));self.assertGreaterEqual(value['elapsed_seconds'],0)

class AdmissionContract(unittest.TestCase):
    def fixture(self):
        cases=[];records=[]
        for path in ('A','ABA'):
            for ratio in ('r16','r20'):
                for kind in ('echo','dt','unguarded'):
                    name='return-'+path+'-'+ratio+'-'+kind+'-shadow'
                    labels=[dict(sample_range=[i*160,(i+1)*160],near_present=kind!='echo' and i<3) for i in range(8)]
                    cases.append(dict(name=name,observation=dict(measurement=dict(windows=labels))))
                    for arm in ('primary','selected'):
                        def delta(i,label=None):
                            return dict(original_sample_range=[i*160,(i+1)*160],stages=dict(final=dict(signal_rms_db_delta=1.0,known_near_error_rms_db_delta=-3.0)))
                        ds=[delta(0)]+[delta(i,l) for i,l in enumerate(labels)]
                        if kind!='echo':ds[0]['stages']['final']['signal_rms_db_delta']=99.0
                        records.append(dict(mode='candidate',arm=arm,kind='return',future=False,source_case=name,observation=dict(baseline_differences=ds)))
        return records,cases
    def test_exact_admission_edges_and_pure_echo_whole_set(self):
        records,cases=self.fixture();value=development_admission(records,cases)
        self.assertTrue(value['accepted'])
        for arm in value['arms'].values():
            self.assertEqual((arm['near_count'],arm['no_near_count'],arm['echo_whole_count']),(24,72,4))
    def test_one_arm_echo_whole_failure_rejects(self):
        records,cases=self.fixture()
        records[0]['observation']['baseline_differences'][0]['stages']['final']['signal_rms_db_delta']=1.000001
        value=development_admission(records,cases)
        self.assertFalse(value['accepted']);self.assertTrue(value['arms']['selected']['accepted'])
    def test_near_median_failure_rejects(self):
        records,cases=self.fixture()
        for r in records:
            for d in r['observation']['baseline_differences']:
                d['stages']['final']['known_near_error_rms_db_delta']=-2.999
        self.assertFalse(development_admission(records,cases)['accepted'])
    def test_no_near_fixed_failure_rejects(self):
        records,cases=self.fixture()
        records[0]['observation']['baseline_differences'][1]['stages']['final']['signal_rms_db_delta']=1.000001
        self.assertFalse(development_admission(records,cases)['accepted'])
    def test_missing_fixed_set_rejects(self):
        records,cases=self.fixture()
        with self.assertRaises(ValueError):development_admission(records[2:],cases)

if __name__=='__main__':unittest.main()
