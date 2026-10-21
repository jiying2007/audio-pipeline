"""D22 known construction and failure contracts, not acoustic qualification."""
import contextlib
import io
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[3]))
from tools.codex_assets import device_multipath as d22


class MultipathTests(unittest.TestCase):
    def test_impulse_kernels_known_answers(self):
        raw = [0.0]*600; raw[0] = 1.0
        for shape, expected in [('A',{48:0.5,176:-0.25,400:0.125}),('B',{80:0.375,240:-0.125,560:0.25})]:
            self.assertEqual({n:d22.mic_sample(raw,n,shape) for n in range(600) if d22.mic_sample(raw,n,shape)},expected)

    def test_switch_boundary_uses_past_and_prescribed_kernel(self):
        raw = [0.0]*160001
        raw[159999-48] = 0.25
        raw[160000-80] = 0.5
        raw[160000-240] = -0.25
        raw[160000-560] = 0.125
        self.assertEqual(d22.mic_sample(raw,159999,'switch'),0.125)
        self.assertEqual(d22.mic_sample(raw,160000,'switch'),0.25)
        raw[160000] = 100.0
        self.assertEqual(d22.mic_sample(raw,160000,'switch'),0.25)

    def test_float32_order_is_observable(self):
        raw = [0.0]*600
        raw[600-1-48] = 33554432.0
        raw[600-1-176] = -4.0
        raw[600-1-400] = -134217728.0
        self.assertEqual(d22.mic_sample(raw,599,'A'),0.0)
        self.assertEqual(sum(g*raw[599-d] for d,g in d22.KERNELS['A']),1.0)

    def test_owned_output_failure_only(self):
        with tempfile.TemporaryDirectory(prefix='d22-negative-') as directory:
            existing = Path(directory)
            with patch.object(d22,'preflight'),contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(d22.main(['--root',str(existing),'--output',str(existing)]),2)
                self.assertFalse((existing/'measurement-invalid.json').exists())
                target = existing/'new'
                with patch.object(d22,'logged',side_effect=ValueError('controlled compilation failure')):
                    self.assertEqual(d22.main(['--root',str(existing),'--output',str(target)]),2)
                self.assertTrue((target/'measurement-invalid.json').exists())


if __name__ == '__main__':
    unittest.main()
