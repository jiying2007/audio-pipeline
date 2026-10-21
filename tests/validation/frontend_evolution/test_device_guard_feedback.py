import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

PATH = Path(__file__).resolve().parents[3] / 'tools/codex_assets/device_guard_feedback.py'
spec = importlib.util.spec_from_file_location('d34', PATH)
d34 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(d34)


class GuardFeedbackTests(unittest.TestCase):
    def test_real_mapping_python38(self):
        members = [dict(name='monitor-field-case-01'), dict(name='monitor-repeat')]
        self.assertEqual(set(d34.case_mapping(members, 'monitor')), {'field-case-01', 'repeat'})
        with self.assertRaises(ValueError):
            d34.case_mapping(members, 'feedback')
        with self.assertRaises(ValueError):
            d34.case_mapping([members[0], members[0]], 'monitor')

    def test_intervals_and_null(self):
        self.assertEqual(d34.intervals([0, 1, 1, 0, 1]), [[1, 3], [4, 5]])
        self.assertIsNone(d34.summary([0, 0])['first_delay'])
        self.assertEqual(d34.summary([0, 1, 1, 0], 1, 4)['first_delay'], 0)
        with self.assertRaises(ValueError):
            d34.summary([0], 0, 2)

    def test_monitor_actual_vs_potential(self):
        rows = [dict(guard=1, used_dt=0, potential_dt=1)] * 2
        s = d34.arm_summary(rows, [{'sample_range': [1, 319]}], None)
        self.assertEqual(s['whole']['used_dt']['count'], 0)
        self.assertEqual(s['whole']['potential_dt']['count'], 2)
        self.assertEqual(s['original_windows'][0]['discarded_boundary_samples'], 318)
        self.assertIsNone(s['near_intervals'])

    def test_gate_recurrence_and_notify(self):
        def make(frame, before=0, after=0):
            return dict(frame=frame, mode=1, detected_dt=0, guard=0, used_dt=0, armed_before=0, stable_before=before, hold_after_gate=0,
                        cme=1., cre=0., ratio=0., valid_me=1, valid_re=1, armed_after=0, stable_after=after)
        rows = [make(0, 0, 1), make(1, 0, 1)]
        d34.recurrence(rows, [(1, 0)] * 2, True, 1, True)
        self.assertEqual(rows[1]['potential_dt'], 0)
        with self.assertRaises(ValueError):
            d34.recurrence(rows, [(1, 0)] * 2, True, 1, False)

    def test_differences_full_runs(self):
        a = [{k: 0 for k in d34.OUTPUT_FIELDS} for _ in range(4)]
        b = [dict(r) for r in a]
        b[1]['guard'] = b[2]['guard'] = 1
        self.assertEqual(d34.differences(a, b)['guard']['intervals'], [[1, 3]])
        self.assertEqual(d34.differences(a, b)['used_dt']['count'], 0)

    def test_invalid_json_output_csv(self):
        with tempfile.TemporaryDirectory() as temp:
            p = Path(temp) / 'input.json'
            for text in ('{"x":1,"x":2}', '{"x":NaN}'):
                p.write_text(text)
                with self.assertRaises(ValueError):
                    d34.read_json(p)
            with self.assertRaises(ValueError):
                d34.preflight(Path(temp))
            p.write_text('frame,mode\n0,0\n')
            with self.assertRaises(ValueError):
                d34.parsed_rows(p, 1)


if __name__ == '__main__':
    unittest.main()
