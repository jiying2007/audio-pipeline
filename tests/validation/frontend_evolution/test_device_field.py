"""D26 rejected-alert counters, unavailable scores, gates and failure ownership."""
import contextlib
import io
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[3]))
from tools.codex_assets import device_field as d26

class FieldTests(unittest.TestCase):
    def test_state_schema_is_not_activity_control(self):
        with tempfile.TemporaryDirectory(prefix='d26-state-') as directory:
            path=Path(directory)/'state.csv'
            path.write_text('frame,runtime_stride,steady_frames,adapt_phase,constrain_partition,x_head,x_power_total,weight_l2\n0,2,0,0,0,0,0,0\n')
            self.assertEqual(d26.read_state(path,1)[0]['runtime_stride'],'2')
            path.write_text('frame,far,dt,frequency_enabled,frequency_active,res_gain,agc_allow,gain_before,gain_after\n0,1,0,1,0,1,0,1,1\n')
            with self.assertRaisesRegex(ValueError,'state schema'):d26.read_state(path,1)
    def test_alert_first_and_all(self):
        rows=[dict(aec_resets=a,delay_jumps=a) for a in (0,1,1,2)]
        self.assertEqual(d26.alert_frames(rows),[1,3])
        for bad in [[dict(aec_resets=2,delay_jumps=2)],[dict(aec_resets=1,delay_jumps=0)],
                    [dict(aec_resets=1,delay_jumps=1),dict(aec_resets=0,delay_jumps=0)]]:
            with self.assertRaises(ValueError):d26.alert_frames(bad)
    def test_null_shadow_scope(self):
        values={name:[0.5]*2 for name in d26.TRACES}
        self.assertIsNone(d26.measure_window(values,0,2,None,'shadow')['channels']['shadow'])
        self.assertIsNone(d26.measure_window(values,0,2,1,'shadow')['channels']['shadow'])
        self.assertIsNone(d26.measure_window(values,0,2,0,'keep')['channels']['shadow'])
        self.assertIsNotNone(d26.measure_window(values,0,2,0,'shadow')['channels']['shadow'])
    def test_gate_streak_clears(self):
        self.assertEqual(d26.step(0,2,True,False,1.0,0.1),(0,0,0))
        self.assertEqual(d26.step(1,2,True,True,0.1,1.0),(0,0,1))
    def test_owned_failure(self):
        with tempfile.TemporaryDirectory(prefix='d26-negative-') as directory:
            existing=Path(directory)
            with patch.object(d26,'preflight',return_value=({},[],[])),contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(d26.main(['--root',str(existing),'--output',str(existing)]),2)
                self.assertFalse((existing/'measurement-invalid.json').exists())

if __name__=='__main__':unittest.main()
