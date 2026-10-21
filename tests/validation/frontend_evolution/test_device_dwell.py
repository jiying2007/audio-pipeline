"""D27 contract tests; real bank replays are checked separately."""
import math
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[3]))
from tools.codex_assets.device_dwell import recurrence
from tools.codex_assets.device_shadow import step

class DwellContract(unittest.TestCase):
    def test_legacy_exact_recurrence(self):
        bank=streak=0;last=None;old_bank=old_streak=0
        for frame in range(240):
            active=frame>=4;eligible=frame%13!=0;pe,se=((1,.1) if frame%8<4 else (.1,1))
            old_bank,old_streak,change=step(old_bank,old_streak,active,eligible,pe,se)
            bank,streak,last,new,hold=recurrence(bank,streak,last,frame,0,active,eligible,pe,se)
            self.assertEqual((bank,streak,new,hold),(old_bank,old_streak,change,0))
    def test_exact_hold_and_release(self):
        bank=streak=0;last=None;events=[]
        for frame in range(56):
            pe,se=((1,.1) if frame<3 else (.1,1))
            bank,streak,last,change,hold=recurrence(bank,streak,last,frame,50,True,True,pe,se)
            if change:events.append(frame)
            if 3<=frame<52:self.assertEqual((bank,streak,hold),(1,0,52-frame))
            if frame==52:self.assertEqual((streak,hold),(1,0))
            if frame==53:self.assertEqual((streak,hold),(2,0))
        self.assertEqual(events,[2,54])
    def test_clock_continues_and_ineligible_clears(self):
        self.assertEqual(recurrence(1,2,2,51,50,True,False,.1,1),(1,0,2,0,1))
        self.assertEqual(recurrence(1,0,2,52,50,True,True,.1,1),(1,1,2,0,0))
        self.assertEqual(recurrence(1,1,2,53,50,True,False,.1,1),(1,0,2,0,0))
    def test_inactive_resets_history(self):
        self.assertEqual(recurrence(1,2,10,11,50,False,True,1,.1),(0,0,None,0,0))
        self.assertEqual(recurrence(0,0,None,12,50,True,True,1,.1),(0,1,None,0,0))
    def test_strict_energy_boundary(self):
        self.assertEqual(recurrence(0,2,None,2,50,True,True,1,.8),(0,0,None,0,0))
        self.assertEqual(recurrence(0,2,None,2,50,True,True,1e-20,0),(0,0,None,0,0))
        self.assertEqual(recurrence(0,2,None,2,50,True,True,1,.79),(1,0,2,1,50))
    def test_invalid_during_hold_rejected(self):
        for pe,se in ((math.nan,1),(1,math.inf),(-1,1)):
            with self.assertRaises(ValueError):recurrence(1,0,2,3,50,True,True,pe,se)

if __name__=='__main__':unittest.main()
