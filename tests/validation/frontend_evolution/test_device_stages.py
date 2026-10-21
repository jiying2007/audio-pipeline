"""D19 measurement negative contracts; no acoustic or product authority."""
from array import array
import contextlib
import io
import math
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from tools.codex_assets import device_stages as d19


class StageTests(unittest.TestCase):
    def test_rms_peak_known_answers(self):
        self.assertEqual(d19.energy([0.0] * 4, 0, 4), dict(samples=4, rms_dbfs=-240.0, peak=0.0))
        actual = d19.energy([0.5, -0.5, 0.5, -0.5], 1, 3)
        self.assertAlmostEqual(actual['rms_dbfs'], 20 * math.log10(0.5), places=12)
        self.assertEqual(actual['peak'], 0.5)
        with self.assertRaises(ValueError):
            d19.energy([0.0], 0, 2)

    def test_nonfinite_and_short_trace_rejected(self):
        with tempfile.TemporaryDirectory(prefix='d19-negative-') as directory:
            path = Path(directory) / 'trace.f32le'
            for samples, count in (([0.0], 2), ([float('nan')], 1), ([float('inf')], 1)):
                values = array('f', samples)
                if sys.byteorder != 'little':
                    values.byteswap()
                path.write_bytes(values.tobytes())
                with self.assertRaises(ValueError):
                    d19.floats(path, count)

    def test_creation_boundary_and_owned_failure(self):
        with tempfile.TemporaryDirectory(prefix='d19-negative-') as directory:
            existing = Path(directory)
            for target in (existing, existing / 'new'):
                def fail(root, output, created):
                    if output == existing:
                        raise ValueError('existing output rejected')
                    output.mkdir()
                    created.append(output)
                    raise ValueError('controlled post-create failure')
                with patch.object(d19, 'run', side_effect=fail), contextlib.redirect_stderr(io.StringIO()):
                    self.assertEqual(d19.main(['--root', str(existing), '--output', str(target)]), 2)
                self.assertEqual((target / 'measurement-invalid.json').exists(), target != existing)


if __name__ == '__main__':
    unittest.main()
