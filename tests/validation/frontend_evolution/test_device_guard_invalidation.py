import math
import csv
import struct
import tempfile
import shutil
from pathlib import Path
import sys
import unittest
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from tools.codex_assets.device_guard_invalidation import initial_guard, gate, observe_guard, invalidate
from tools.codex_assets import device_guard_invalidation as candidate


class GuardTests(unittest.TestCase):
    def test_notification_invalidation_and_rearming(self):
        s=dict(initial_guard(),cme=.5,cre=.01,ratio=.5,stable=100,armed=1,hold=3,valid_me=1,valid_re=1)
        self.assertEqual(invalidate(s,'monitor',True),s)
        self.assertEqual(invalidate(s,'feedback',False),s)
        reset=invalidate(s,'feedback',True)
        self.assertEqual(reset,initial_guard());self.assertEqual(gate(reset,1)[1],0)
        for frame in range(100):
            reset=observe_guard(reset,[1.]*160,[1.]*160,[0.]*160,1,0)
            self.assertEqual(reset['armed'],int(frame==99))
        self.assertEqual(s['hold'],3)

    def test_arming_next_frame_and_release(self):
        s = initial_guard(); e = [1.] * 160; zero = [0.] * 160
        for f in range(100):
            s, flag = gate(s, 1); self.assertEqual(flag, 0)
            s = observe_guard(s, e, e, zero, 1, 0); self.assertEqual(s['armed'], int(f == 99))
        s, flag = gate(s, 1); self.assertEqual(flag, 0)
        r = [1., -1.] * 80; m = [a + b for a, b in zip(e, r)]
        s = observe_guard(s, m, e, r, 1, 0)
        s, flag = gate(s, 1); self.assertEqual((flag, s['hold']), (1, 3))
        s = observe_guard(s, e, e, zero, 1, 0)
        for expected in (2, 1, 0):
            s, flag = gate(s, 1); self.assertEqual((flag, s['hold']), (int(expected > 0), expected))
        s, flag = gate(s, 0); self.assertEqual(s, initial_guard()); self.assertEqual(flag, 0)

    def test_strict_boundaries_and_invalid_energy(self):
        s = dict(initial_guard(), armed=1, valid_me=1, valid_re=1, cme=.5, cre=.01, ratio=.5)
        self.assertEqual(gate(s, 1)[1], 1)
        for key, value in [('cme', .2), ('cme', .9), ('cre', .1), ('ratio', .2), ('valid_re', 0), ('valid_me', 0)]:
            self.assertEqual(gate(dict(s, **{key: value}), 1)[1], 0)
        zero = [0.] * 160
        invalid = observe_guard(initial_guard(), zero, zero, zero, 1, 0)
        self.assertEqual((invalid['cme'], invalid['cre'], invalid['ratio']), (-1., -1., -1.))
        self.assertEqual(gate(invalid, 1)[1], 0)

    def test_counter_resets_and_nonfinite_rejected(self):
        e = [1.] * 160; zero = [0.] * 160
        s = observe_guard(dict(initial_guard(), stable=99), e, e, zero, 1, 1)
        self.assertEqual((s['stable'], s['armed']), (0, 0))
        for bad in ([math.nan] * 160, [math.inf] * 160, [1.] * 159):
            with self.assertRaises(ValueError):
                observe_guard(initial_guard(), bad, e, zero, 1, 0)

    def test_complete_observe_activity_csv_path(self):
        # Parser/recurrence fixture, with no DSP execution or acoustic score claim.
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary); output = root / 'actual'; baseline = root / 'baseline' / 'fixture'
            output.mkdir(); baseline.mkdir(parents=True)
            values = {k: [.25 if k in ('mic', 'residual', 'primary_residual') else 0.] * 160 for k in candidate.TRACES}
            for key, v in values.items():
                (output / (key + '.f32le')).write_bytes(struct.pack('<160f', *v))
            me, re = candidate.frame_energy(values['mic']), candidate.frame_energy(values['reference'])
            _, flags = candidate.activity_step((0., 0., 0, 0), me, re)
            self.assertEqual(flags, (0, 0))
            tables = [('state.csv', candidate.STATE_FIELDS, [0, 2, 0, 0, 0, 0, 0., 0.]),
                      ('selector.csv', candidate.SELECT_FIELDS, [0, 0, 0, 0, 0, 0, 0, 10., 0., 0]),
                      ('transition.csv', candidate.TRANS_FIELDS, [0, 0, 0, 0, 0, 0, 0, 1., 1.]),
                      ('activity.csv', candidate.ACT_FIELDS, [0, me, re, me, re, 0, 0, 0, 0]),
                      ('guard.csv', candidate.GUARD_FIELDS, [0, 0, 0, 0, 0, 0, 0, 0, -1., -1., 1., 0, 0, 0, 0])]
            for name, fields, row in tables:
                with (output / name).open('w', newline='') as stream:
                    writer = csv.writer(stream); writer.writerow(fields); writer.writerow(row)
            for name in candidate.OUTPUTS[:-1]:
                shutil.copyfile(output / name, baseline / name)
            measurement = dict(whole=dict(sample_range=[0, 160], channels=dict(selected=dict(residual=dict(rms_dbfs=-12.041199826559248)))), windows=[])
            source = dict(kind='field', actual=dict(name='fixture', observation=dict(measurement=measurement)),d32={'monitor':dict(observation=dict(measurement=measurement))})
            d32_directory=root/'monitor-fixture';d32_directory.mkdir()
            for name in candidate.OUTPUTS:shutil.copyfile(output/name,d32_directory/name)
            execution = dict(frames=1, samples=160, primary_calls=1, shadow_calls=0, shadow_reset_calls=0, selector_calls=1,
                             transition_calls=1, mixed_samples=0, remaining=0, switch_count=0, sync_calls=0, aec_state_bytes=33020,
                             two_aec_state_bytes=66040, selector_state_bytes=20, transition_state_bytes=16, frame_buffer_bytes=5120,
                             scoped_bytes=71264, activity_calls=1, activity_state_bytes=28, observer_calls=1, guard_state_bytes=40)
            with patch.object(candidate, 'D32', root), patch.object(candidate, 'BASE', baseline.parent), patch.object(candidate, 'input_info', return_value=(root, output / 'mic.f32le', output / 'reference.f32le', bytes([0, 0]), 160, None)), patch.object(candidate, 'score', return_value=measurement):
                result = candidate.observe(output, source, False, execution, 'monitor')
            self.assertEqual(result['used_dt_frames'], 0)
            self.assertTrue(all(result['baseline_file_equivalence'].values()))


if __name__ == '__main__':
    unittest.main()

