"""D46 measurement known answers and refusal contracts; no DSP."""
import contextlib
import csv
import io
import math
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from tools.codex_assets import device_release_path_attribution as d46


class AttributionTests(unittest.TestCase):
    def test_alignment_partition_and_tail(self):
        segments = [d46.alignment(a, b) for a, b in d46.PHASES]
        self.assertEqual(segments[0]['output_range'], [160, 160160])
        self.assertEqual(segments[-1]['original_input_range'], [289600, 320000])
        self.assertEqual(segments[-1]['effective_input_range'], [289600, 319840])
        self.assertEqual(segments[-1]['output_range'], [289760, 320000])
        self.assertEqual(segments[-1]['tail_truncated_samples'], 160)
        self.assertEqual(sum(s['samples'] for s in segments), 319840)
        self.assertEqual([s['tail_truncated_samples'] for s in segments[:-1]], [0] * 6)
        for left, right in zip(segments, segments[1:]):
            self.assertEqual(left['output_range'][1], right['output_range'][0])
        for a, b in ((0, 0), (-1, 1), (0, 2001), (2, 1)):
            with self.assertRaises(ValueError):
                d46.alignment(a, b)

    def test_energy_known_answer_and_zero(self):
        value = d46.energies([1.0, -2.0, 3.0], [0.0, 1.0, 1.0], 0, 3)
        self.assertEqual((value['candidate_energy'], value['monitor_energy'],
                          value['difference_energy'], value['energy_delta']), (14.0, 2.0, 14.0, 12.0))
        self.assertEqual((value['candidate_peak'], value['monitor_peak']), (3.0, 1.0))
        self.assertAlmostEqual(value['signal_energy_delta_db'], 10 * math.log10(7))
        zero = d46.energies([0.0, -0.0], [0.0, 0.0], 0, 2)
        self.assertTrue(zero['candidate_zero'] and zero['monitor_zero'])
        self.assertIsNone(zero['signal_energy_delta_db'])
        self.assertEqual(zero['difference_energy'], 0)
        one_zero = d46.energies([1.0], [0.0], 0, 1)
        self.assertFalse(one_zero['candidate_zero'])
        self.assertTrue(one_zero['monitor_zero'])
        self.assertIsNone(one_zero['signal_energy_delta_db'])

    def test_nonfinite_and_energy_bounds(self):
        for invalid in (float('nan'), float('inf'), float('-inf')):
            with self.assertRaises(ValueError):
                d46.energies([invalid], [0], 0, 1)
        for args in (([1], [0], 0, 2), ([1], [0, 1], 0, 1), ([1], [0], 0, 0)):
            with self.assertRaises(ValueError):
                d46.energies(*args)

    def test_strict_zero_and_partition(self):
        self.assertFalse(d46.close_number(1e-30, 0))
        self.assertTrue(d46.close_number(0, 0))
        self.assertTrue(d46.close_number(2.0 + 1e-13, 2.0))
        self.assertFalse(d46.close_number(2.0 + 1e-8, 2.0))
        a = d46.energies([1, 2], [0, 0], 0, 1)
        b = d46.energies([1, 2], [0, 0], 1, 2)
        whole = d46.energies([1, 2], [0, 0], 0, 2)
        segments = [{'stages': {stage: v for stage in ('ns', 'final')}} for v in (a, b)]
        d46.check_partition(segments, {stage: whole for stage in ('ns', 'final')})
        segments[0]['stages']['ns'] = dict(a, difference_energy=2)
        with self.assertRaises(ValueError):
            d46.check_partition(segments, {stage: whole for stage in ('ns', 'final')})

    def test_float32le_length_finite(self):
        import struct
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'samples.f32le'
            with mock.patch.object(d46, 'SAMPLES', 2):
                path.write_bytes(struct.pack('<ff', 1.25, -2.5))
                self.assertEqual(list(d46.pcm(path)), [1.25, -2.5])
                path.write_bytes(struct.pack('<f', 1.25))
                with self.assertRaises(ValueError):
                    d46.pcm(path)
                path.write_bytes(struct.pack('<ff', 1.25, float('nan')))
                with self.assertRaises(ValueError):
                    d46.pcm(path)

    def test_complete_pair_identity(self):
        rows = []
        for mode in ('candidate', 'monitor'):
            for arm in ('primary', 'selected'):
                for source in d46.case_names():
                    rows.append(dict(mode=mode, arm=arm, source_case=source, kind='return', future=False,
                                     name='-'.join((mode, arm, source)),
                                     execution_summary=dict(frames=2000, samples=320000)))
        self.assertEqual(len(d46.select_pairs({'cases': rows})), 24)
        for invalid in (rows[:-1], rows + [rows[0]], rows[:-1] + [rows[0]]):
            with self.assertRaises(ValueError):
                d46.select_pairs({'cases': invalid})
        altered = [dict(r) for r in rows]
        altered[0]['name'] = 'wrong-case'
        with self.assertRaises(ValueError):
            d46.select_pairs({'cases': altered})

    def test_power_actual_projection_and_segments(self):
        monitor = [dict.fromkeys(d46.POWER_FIELDS, '0') for _ in range(2000)]
        for index, row in enumerate(monitor):
            row['frame'] = str(index)
            row['positive_floor_bins'] = '3'
            row['post_would_raise_bins'] = '2'
        candidate = [dict(r, raised_bins='2') for r in monitor]
        d46.paired_power(candidate, monitor)
        value = d46.power_segment(candidate, 1000, 1200)
        self.assertEqual((value['raised_frames'], value['raised_bins'], value['positive_floor_bins']),
                         (200, 400, 600))
        candidate[0]['q_mean'] = '0.5'
        with self.assertRaises(ValueError):
            d46.paired_power(candidate, monitor)
        candidate[0] = dict(monitor[0], raised_bins='1')
        with self.assertRaises(ValueError):
            d46.paired_power(candidate, monitor)

    def test_power_schema_finite_order(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'power.csv'
            rows = [dict.fromkeys(d46.POWER_FIELDS, '0') for _ in range(2)]
            rows[1]['frame'] = '1'

            def save(fields=d46.POWER_FIELDS):
                with path.open('w', newline='') as stream:
                    writer = csv.DictWriter(stream, fieldnames=fields, extrasaction='ignore')
                    writer.writeheader()
                    writer.writerows(rows)

            with mock.patch.object(d46, 'FRAMES', 2):
                save()
                self.assertEqual(len(d46.power(path)), 2)
                save(d46.POWER_FIELDS[:-1])
                with self.assertRaises(ValueError):
                    d46.power(path)
                rows[1]['frame'] = '0'
                save()
                with self.assertRaises(ValueError):
                    d46.power(path)
                rows[1]['frame'] = '1'
                rows[0]['q_mean'] = 'nan'
                save()
                with self.assertRaises(ValueError):
                    d46.power(path)

    def test_root_refusal_before_preflight_and_preservation(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            sentinel = root / 'sentinel'
            sentinel.write_bytes(b'preserve')
            before = sorted(p.name for p in root.iterdir())
            with mock.patch.object(d46, 'OUTPUT', root), mock.patch.object(d46, 'preflight') as preflight:
                with mock.patch.object(sys_module(), 'argv', ['d46', '--run', '--output-root', str(root)]):
                    with contextlib.redirect_stderr(io.StringIO()):
                        self.assertEqual(d46.main(), 2)
                preflight.assert_not_called()
            self.assertEqual(sentinel.read_bytes(), b'preserve')
            self.assertEqual(sorted(p.name for p in root.iterdir()), before)
            with self.assertRaises(ValueError):
                d46.validate_output(Path('/vsdata/unsafe-output'))

    def test_finite_invalid_power_ranges_and_lifecycle(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'power.csv'
            rows = [dict.fromkeys(d46.POWER_FIELDS, '0') for _ in range(11)]
            for index, row in enumerate(rows):
                row.update(frame=str(index), far='1', count_before=str(min(index, 10)))
            rows[-1].update(valid_bins='2', positive_floor_bins='2', post_would_raise_bins='2',
                            q_mean='.5', floor_mean='.1', echo_sum='1', residual_sum='2',
                            innovation_sum='1', noise_sum='.1', excess_sum='.5', floor2_residual_sum='.25')

            def save(values):
                with path.open('w', newline='') as stream:
                    writer = csv.DictWriter(stream, fieldnames=d46.POWER_FIELDS)
                    writer.writeheader()
                    writer.writerows(values)

            with mock.patch.object(d46, 'FRAMES', 11):
                save(rows)
                self.assertEqual(len(d46.power(path)), 11)
                for change in ({'q_mean': '1.5'}, {'floor_mean': '-.2'}, {'echo_sum': '-1'},
                               {'positive_floor_bins': '3'}, {'post_would_raise_bins': '3'},
                               {'innovation_sum': '3'}, {'excess_sum': '2'},
                               {'count_before': '9'}, {'far': '0'}, {'valid_bins': '0'}):
                    invalid = [dict(row) for row in rows]
                    invalid[-1].update(change)
                    save(invalid)
                    with self.subTest(change=change), self.assertRaises(ValueError):
                        d46.power(path)
                invalid = [dict(row) for row in rows]
                invalid[-1].update({key: '0' for key in d46.POWER_FIELDS[4:]})
                invalid[-1]['q_mean'] = '1e-30'
                save(invalid)
                with self.assertRaises(ValueError):
                    d46.power(path)

    def test_own_and_parent_symlink_refusal(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            target = base / 'target'
            target.mkdir()
            own = base / 'own'
            own.symlink_to(target, target_is_directory=True)
            parent = base / 'parent'
            parent.symlink_to(target, target_is_directory=True)
            for output in (own, parent / 'new-output'):
                with mock.patch.object(d46, 'OUTPUT', output):
                    with self.assertRaises(ValueError):
                        d46.validate_output(output)
            self.assertEqual(list(target.iterdir()), [])

    def test_deadline_boundary(self):
        with mock.patch.object(d46.time, 'monotonic', return_value=180):
            d46.deadline(0)
        with mock.patch.object(d46.time, 'monotonic', return_value=180.0001):
            with self.assertRaises(ValueError):
                d46.deadline(0)


def sys_module():
    import sys
    return sys


if __name__ == '__main__':
    unittest.main()
