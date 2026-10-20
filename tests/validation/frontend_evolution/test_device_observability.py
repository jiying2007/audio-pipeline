"""Known-answer and rejection tests for D31 observation, not speech quality."""
import math
import array
import tempfile
import weakref
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from tools.codex_assets.device_observability import CHANNELS, FEATURES, frame_features, summary, window_summary
from tools.codex_assets.device_observability import run


class ObservationTests(unittest.TestCase):
    def values(self, value):
        return {k: list(value) for k in CHANNELS}

    def test_parallel_antiparallel_scaling(self):
        values = self.values([1., -2.] * 80)
        values['reference'] = [-3 * x for x in values['mic']]
        result = frame_features(values)
        self.assertTrue(all(abs(result[k] - 1) < 1e-12 for k in FEATURES))
        scaled = {k: [x * .125 for x in v] for k, v in values.items()}
        self.assertEqual(result, frame_features(scaled))

    def test_orthogonal_and_zero_null(self):
        values = self.values([1., -1.] * 80)
        values['reference'] = [1.] * 160
        self.assertEqual(frame_features(values)['mic_reference_cos2'], 0.)
        self.assertTrue(all(v is None for v in frame_features(self.values([0.] * 160)).values()))

    def test_rejection(self):
        for bad in ([1.] * 159, [math.nan] * 160, [math.inf] * 160):
            with self.assertRaises(ValueError):
                frame_features(self.values(bad))
        with self.assertRaises(ValueError):
            frame_features({})

    def test_window_rounding_quantiles_and_causality(self):
        first = frame_features(self.values([1.] * 160))
        changed = frame_features(self.values([0.] * 160))
        rows = [first, first, changed]
        result = window_summary(rows, {'sample_range': [1, 479]})
        self.assertEqual(result['complete_frame_range'], [1, 2])
        self.assertEqual(result['discarded_boundary_samples'], 318)
        self.assertEqual(result['features'][FEATURES[0]]['p50'], 1.)
        self.assertEqual(rows[:2], [first, first])
        self.assertEqual(summary([None, 3., 1., 2.])['p50'], 2.)
        self.assertEqual(summary([None])['null'], 1)

    def test_single_case_trace_lifetime(self):
        references = []
        peak = [0]
        def load(path, count):
            value = array.array('f', [1.] * count)
            references.append(weakref.ref(value))
            peak[0] = max(peak[0], sum(ref() is not None for ref in references))
            return value
        cases = [dict(name=name, kind='field', future=name == 'future',
                      execution_summary=dict(samples=160, frames=1),
                      observation=dict(measurement=dict(whole=dict(sample_range=[0, 160]), windows=[])))
                 for name in ('field-case-07-used0-shadow', 'repeat', 'future')]
        with tempfile.TemporaryDirectory() as temporary:
            with patch('tools.codex_assets.device_observability.floats', side_effect=load), patch('builtins.print'):
                run(Path(temporary) / 'out', cases, {}, {})
        self.assertEqual(peak[0], 6)
        self.assertTrue(all(ref() is None for ref in references))


if __name__ == '__main__':
    unittest.main()
