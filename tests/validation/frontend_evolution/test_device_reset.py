"""D23 actual-event attestation and paired difference contracts."""
import contextlib
import io
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[3]))
from tools.codex_assets import device_reset as d23


def summary(reset=False):
    fields=('reset_frame','reset_pre_weight_l2','reset_post_weight_l2','reset_post_x_power_total','reset_post_steady_frames','reset_post_x_head')
    s=dict(frames=2000,samples=320000,sync_calls=0,reset_calls=int(reset),**{k:None for k in fields})
    if reset: s.update(reset_frame=1000,reset_pre_weight_l2=1.0,reset_post_weight_l2=0,
                       reset_post_x_power_total=0,reset_post_steady_frames=0,reset_post_x_head=47)
    return s


class ResetTests(unittest.TestCase):
    def test_actual_event_and_absence_contract(self):
        d23.verify_summary(summary(),'keep','normal')
        d23.verify_summary(summary(True),'reset','normal')
        for key,bad in [('reset_calls',True),('reset_frame',999),('reset_post_weight_l2',0.01),
                        ('reset_post_x_head',0),('reset_pre_weight_l2',float('nan')),('reset_post_x_power_total',False)]:
            value=summary(True); value[key]=bad
            with self.assertRaises(ValueError): d23.verify_summary(value,'reset','normal')
        value=summary(); value['reset_frame']=0
        with self.assertRaises(ValueError): d23.verify_summary(value,'keep','normal')

    def test_negative_preweight_and_missing_summary(self):
        value=summary(True); value['reset_pre_weight_l2']=0
        d23.verify_summary(value,'reset','zero')
        with self.assertRaises(ValueError): d23.verify_summary(value,'reset','normal')
        value.pop('reset_frame')
        with self.assertRaises(ValueError): d23.verify_summary(value,'reset','zero')

    def test_paired_difference_direction_known_answer(self):
        self.assertEqual(d23.difference(dict(residual_rms_dbfs=-20,known_echo_erle_db=10),
                                       dict(residual_rms_dbfs=-26,known_echo_erle_db=16)),
                         dict(residual_rms_dbfs=-6,known_echo_erle_db=6))

    def test_output_owned_failure_only(self):
        with tempfile.TemporaryDirectory(prefix='d23-negative-') as directory:
            existing=Path(directory)
            with patch.object(d23,'preflight'),contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(d23.main(['--root',str(existing),'--output',str(existing)]),2)
                self.assertFalse((existing/'measurement-invalid.json').exists())
                target=existing/'new'
                with patch.object(d23,'logged',side_effect=ValueError('controlled compilation failure')):
                    self.assertEqual(d23.main(['--root',str(existing),'--output',str(target)]),2)
                self.assertTrue((target/'measurement-invalid.json').exists())


if __name__ == '__main__': unittest.main()
