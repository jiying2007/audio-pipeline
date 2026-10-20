"""D25 mixed target/scoring scope, truth labels and owned failure behavior."""
import contextlib
import io
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[3]))
from tools.codex_assets import device_return as d25

class ReturnTests(unittest.TestCase):
    def test_mixed_target_is_not_erle(self):
        values={'true_echo':[1.0,1.0],'near':[0.5,0.5], 'residual':[0.75,0.75], 'primary_residual':[0.75,0.75]}
        result=d25.window(values,0,2,'keep')
        self.assertIsNone(result['channels']['shadow'])
        self.assertIsNone(result['channels']['selected']['known_echo_erle_db'])
        self.assertAlmostEqual(result['channels']['selected']['error']['rms_dbfs'],-12.041199826559248)
    def test_inactive_shadow_and_echo_known_answer(self):
        values={'true_echo':[1.0,1.0],'near':[0.0,0.0], 'residual':[0.5,0.5], 'primary_residual':[0.5,0.5]}
        result=d25.window(values,0,2,'shadow')
        self.assertIsNone(result['channels']['shadow'])
        self.assertAlmostEqual(result['channels']['selected']['known_echo_erle_db'],6.020599913279624)
    def test_gate_boundaries_and_case_accounting(self):
        self.assertEqual([d25.near_active(n) for n in (999,1000,1199,1200,1599,1600,1799,1800)],
                         [False,True,True,False,False,True,True,False])
        self.assertEqual(len(d25.CASES),26)
        self.assertEqual(len({c[0] for c in d25.CASES}),26)
    def test_owned_failure_path(self):
        with tempfile.TemporaryDirectory(prefix='d25-negative-') as directory:
            existing=Path(directory)
            with patch.object(d25,'preflight'),contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(d25.main(['--root',str(existing),'--output',str(existing)]),2)
                self.assertFalse((existing/'measurement-invalid.json').exists())
                target=existing/'new'
                with patch.object(d25,'logged',side_effect=ValueError('controlled compilation failure')):
                    self.assertEqual(d25.main(['--root',str(existing),'--output',str(target)]),2)
                self.assertTrue((target/'measurement-invalid.json').exists())

if __name__=='__main__': unittest.main()
