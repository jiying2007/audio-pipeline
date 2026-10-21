"""D20 timing known answers and rejected measurement inputs."""
from array import array
import contextlib
import io
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from tools.codex_assets import device_timing as d20


class TimingTests(unittest.TestCase):
    def test_ranges_and_missing_events(self):
        self.assertEqual(d20.differing_ranges([0, 0, 0, 0, 0], [0, 1, 1, 0, 1]),
                         dict(count=3, first=1, last=4, ranges_half_open=[[1, 3], [4, 5]]))
        self.assertEqual(d20.differing_ranges([], [])['first'], None)
        with self.assertRaises(ValueError):
            d20.differing_ranges([0], [])
        for output, gate, expected in ((None, None, 'no-output-difference'), (2, None, 'no-gate-difference'),
                                       (2, 1, 'before'), (2, 2, 'same-frame'), (2, 3, 'after')):
            self.assertEqual(d20.relationship(output, gate), expected)

    def test_bitwise_first_signed_zero_and_negative_latency_coordinate(self):
        with tempfile.TemporaryDirectory(prefix='d20-known-') as directory:
            paths = [Path(directory) / name for name in ('a', 'b')]
            for path, values in zip(paths, ([0.0, 0.0, 1.0, -0.0], [0.0, 2.0, 1.0, 0.0])):
                data = array('f', values)
                if sys.byteorder != 'little':
                    data.byteswap()
                path.write_bytes(data.tobytes())
            actual = d20.trace_difference(*paths, 4, 160)
            self.assertEqual(actual['mismatched_samples'], 2)
            self.assertEqual(actual['first']['sample'], 1)
            self.assertEqual(actual['first']['latency_paired_input_sample'], -159)
            self.assertTrue(d20.trace_difference(paths[0], paths[0], 4)['byte_equal'])

    def test_bad_float_and_length(self):
        with tempfile.TemporaryDirectory(prefix='d20-negative-') as directory:
            path = Path(directory) / 'a'
            for value in (float('nan'), float('inf')):
                path.write_bytes(array('f', [value]).tobytes())
                with self.assertRaises(ValueError):
                    d20.trace_difference(path, path, 1)
            path.write_bytes(b'\x00' * 4)
            with self.assertRaises(ValueError):
                d20.trace_difference(path, path, 2)

    def test_control_policy_and_schema(self):
        with tempfile.TemporaryDirectory(prefix='d20-negative-') as directory:
            path = Path(directory) / 'control.csv'
            header = ','.join(d20.FIELDS) + '\n'
            metrics = [dict(far_end_active=1, double_talk_active=0)]
            path.write_text(header + '0,1,0,1,1,0.5,0,1,1\n')
            self.assertEqual(d20.controls(path, metrics)[0]['agc_allow'], 0)
            for row in ('1,1,0,1,1,0.5,0,1,1', '0,1,0,1,1,0.5,1,1,1',
                        '0,1,0,1,1,nan,0,1,1', '0,2,0,1,1,0.5,0,1,1'):
                path.write_text(header + row + '\n')
                with self.assertRaises(ValueError):
                    d20.controls(path, metrics)

    def test_output_ownership(self):
        with tempfile.TemporaryDirectory(prefix='d20-negative-') as directory:
            existing = Path(directory)
            with patch.object(d20, 'preflight', return_value=[]), contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(d20.main(['--root', str(existing), '--output', str(existing)]), 2)
                self.assertFalse((existing / 'measurement-invalid.json').exists())
                target = existing / 'new'
                with patch.object(d20, 'analyze', side_effect=ValueError('controlled analysis failure')):
                    self.assertEqual(d20.main(['--root', str(existing), '--output', str(target)]), 2)
                self.assertTrue((target / 'measurement-invalid.json').exists())


if __name__ == '__main__':
    unittest.main()
