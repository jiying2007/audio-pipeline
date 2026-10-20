import sys
from pathlib import Path
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[3]))
from tools.codex_assets.device_activity import activity_step,frame_energy,f32,runner_command

class ActivityContract(unittest.TestCase):
    def test_actual_runner_has_no_external_gate_or_truth_arguments(self):
        source=object()
        with patch('tools.codex_assets.device_activity.input_info',return_value=(Path('/old'),Path('/mic'),Path('/ref'),b'\1\0',160,0)):
            self.assertEqual(runner_command(Path('/runner'),source,Path('/out'),False),['/runner','/mic','/ref','1','0','/out','normal'])
    def test_current_near_onset_and_hangover_expiry(self):
        state,gate=activity_step((0.,0.,0,0),f32(1e-8),f32(1e-4));self.assertEqual(gate,(1,0))
        state,gate=activity_step(state,f32(1e-2),f32(1e-4));self.assertEqual(gate,(1,1))
        for expected in ((1,1),(1,1),(1,0)):
            state,gate=activity_step(state,f32(1e-8),f32(1e-4));self.assertEqual(gate,expected)
    def test_float32_energy_is_sign_invariant_and_seeded(self):
        values=[f32((i-80)/512) for i in range(160)]
        self.assertEqual(frame_energy(values),frame_energy([-v for v in values]))
        self.assertEqual(frame_energy([0.]*160),f32(f32(1e-12)/160))
    def test_invalid_inputs_rejected(self):
        for values in ([0.]*159,[float('nan')]*160):
            with self.assertRaises(ValueError):frame_energy(values)
        for energy in (-1.,float('inf')):
            with self.assertRaises(ValueError):activity_step((0.,0.,0,0),energy,0.)

if __name__=='__main__':unittest.main()
