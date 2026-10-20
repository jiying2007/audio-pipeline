"""D24 selector causal/confirmation contracts and owned failure paths."""
import contextlib
import io
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[3]))
from tools.codex_assets import device_shadow as d24

class ShadowTests(unittest.TestCase):
    def test_strict_ratio_and_consecutive_confirmation(self):
        self.assertEqual(d24.step(0,0,True,True,1.0,0.8),(0,0,0))
        self.assertEqual(d24.step(0,0,True,True,1.0,0.5),(0,1,0))
        self.assertEqual(d24.step(0,1,True,False,1.0,0.5),(0,0,0))
        self.assertEqual(d24.step(0,2,True,True,1.0,0.5),(1,0,1))
    def test_reverse_and_absence(self):
        self.assertEqual(d24.step(1,2,True,True,0.1,1.0),(0,0,1))
        self.assertEqual(d24.step(0,2,False,True,1.0,0.0),(0,0,0))
        self.assertEqual(d24.step(0,0,True,True,0.0,0.0),(0,0,0))
    def test_summary_rejection(self):
        with self.assertRaises(ValueError): d24.observe(Path('/nonexistent'),'A',16,'normal','keep',{'frames':True})
    def test_owned_output_failure(self):
        with tempfile.TemporaryDirectory(prefix='d24-negative-') as directory:
            existing=Path(directory)
            with patch.object(d24,'preflight'),contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(d24.main(['--root',str(existing),'--output',str(existing)]),2)
                self.assertFalse((existing/'measurement-invalid.json').exists())
                target=existing/'new'
                with patch.object(d24,'logged',side_effect=ValueError('controlled compilation failure')):
                    self.assertEqual(d24.main(['--root',str(existing),'--output',str(target)]),2)
                self.assertTrue((target/'measurement-invalid.json').exists())

if __name__=='__main__': unittest.main()
