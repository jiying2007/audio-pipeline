"""D28 numerical contract tests, independent of physical qualification."""
from pathlib import Path
import struct
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[3]))
from tools.codex_assets.device_transition import mix
class TransitionContract(unittest.TestCase):
    def test_endpoints_preserve_signed_zero(self):
        self.assertEqual(struct.pack('<f',mix(-0.0,1.0,0)),struct.pack('<f',-0.0))
        self.assertEqual(struct.pack('<f',mix(1.0,-0.0,319)),struct.pack('<f',-0.0))
    def test_midpoint_and_continuity(self):
        y=[mix(-.25,.75,i) for i in range(320)]
        self.assertEqual(y[0],-.25);self.assertEqual(y[-1],.75)
        self.assertTrue(all(a<b for a,b in zip(y,y[1:])))
    def test_common_alpha_algebra(self):
        for i in range(320):self.assertLessEqual(abs(mix(.125,.25,i)+mix(.375,.25,i)-.5),1e-6)
    def test_positions_rejected(self):
        for i in (-1,320):
            with self.assertRaises(ValueError):mix(0.,1.,i)
if __name__=='__main__':unittest.main()
