"""D21 fixture measurement contracts, not product qualification."""
import contextlib
import io
import math
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from tools.codex_assets import device_path as d21


class PathTests(unittest.TestCase):
    def test_prng_known_vector_and_future_boundary(self):
        normal, future = d21.raw_signal(), d21.raw_signal(True)
        self.assertEqual([int(v * 262144) for v in normal[:8]], [-9563, -23389, 29892, 11416, -30840, 25165, -12515, -4567])
        self.assertEqual(normal[:160000], future[:160000])
        self.assertTrue(all(a == -b for a, b in zip(normal[160000:], future[160000:])))

    def test_echo_attenuation_known_answer(self):
        actual = d21.stats([0.5, -0.5], [0.25, -0.25], 0, 2)
        self.assertAlmostEqual(actual['known_echo_erle_db'], 10 * math.log10(4), places=12)
        self.assertEqual(actual['residual_peak'], 0.25)
        with self.assertRaises(ValueError):
            d21.stats([0.0], [0.0], 0, 1)

    def test_trace_length_and_finite(self):
        with tempfile.TemporaryDirectory(prefix='d21-negative-') as directory:
            path = Path(directory) / 'trace'
            path.write_bytes(b'\x00' * 4)
            with self.assertRaises(ValueError):
                d21.signal(path)
            for bad in (float('nan'), float('inf')):
                path.write_bytes(d21.encoded([bad] + [0.0] * 319999))
                with self.assertRaises(ValueError):
                    d21.signal(path)

    def test_output_ownership(self):
        with tempfile.TemporaryDirectory(prefix='d21-negative-') as directory:
            existing = Path(directory)
            with patch.object(d21, 'preflight'), contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(d21.main(['--root', str(existing), '--output', str(existing)]), 2)
                self.assertFalse((existing / 'measurement-invalid.json').exists())
                target = existing / 'new'
                with patch.object(d21, 'logged', side_effect=ValueError('controlled compilation failure')):
                    self.assertEqual(d21.main(['--root', str(existing), '--output', str(target)]), 2)
                self.assertTrue((target / 'measurement-invalid.json').exists())


if __name__ == '__main__':
    unittest.main()
