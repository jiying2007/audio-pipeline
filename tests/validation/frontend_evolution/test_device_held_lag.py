import math
import tempfile
import unittest
from pathlib import Path
from tools.codex_assets import device_held_lag as d


class HeldLagTests(unittest.TestCase):
    def prior(self,lags):
        return [dict(chosen_lag=v,valid_lags=int(v>=0),max_cos2=1. if v>=0 else -1.) for v in lags]

    def test_antiphase_continuation(self):
        x=[float(i%7-3) for i in range(480)]; r=[-v for v in x]
        rows=d.observe(x,r,self.prior([0,0,0]))
        self.assertEqual(rows[0]['reason'],1)
        self.assertEqual(rows[1]['past_lag'],0)
        self.assertEqual(rows[1]['held_cos2'],1.)
        self.assertEqual(rows[1]['lag_changed'],0)

    def test_true_current_optimum_changes_but_past_is_fixed(self):
        x=[float(i%7-3) for i in range(480)]
        r=[-x[j] if j<160 else -x[j-1] for j in range(480)]
        rows=d.observe(x,r,self.prior([0,1,1]))
        self.assertEqual(rows[1]['past_lag'],0)
        self.assertEqual(rows[1]['lag_changed'],1)
        self.assertLess(rows[1]['held_cos2'],rows[1]['current_max_cos2'])
        self.assertEqual(rows[2]['past_lag'],1)
        self.assertEqual(rows[2]['held_cos2'],1.)
        self.assertEqual(rows[2]['lag_changed'],0)

    def test_invalid_does_not_hold(self):
        rows=d.observe([1.]*480,[1.]*160+[0.]*160+[1.]*160,self.prior([0,-1,0]))
        self.assertEqual(rows[2]['reason'],2)
        self.assertEqual(rows[2]['past_lag'],-1)
        self.assertEqual(rows[2]['reference_energy'],-1.)
        self.assertEqual(rows[2]['held_cos2'],-1.)

    def test_zero_denominators_and_priority(self):
        p=self.prior([0,0]);r=d.observe([1.]*320,[1.]*160+[0.]*160,p)
        self.assertEqual(r[1]['reason'],3)
        r=d.observe([1.]*160+[0.]*160,[1.]*320,p)
        self.assertEqual(r[1]['reason'],4)
        self.assertEqual(r[1]['reference_energy'],0.)
        r=d.observe([0.]*320,[0.]*320,self.prior([-1,-1]))
        self.assertEqual([v['reason'] for v in r],[1,2])

    def test_shape_nonfinite_and_causality(self):
        for x,r,p in [([1.],[],[]),([math.nan]*160,[1.]*160,self.prior([0])),([1.]*320,[1.]*320,self.prior([200,0]))]:
            with self.assertRaises(ValueError):d.observe(x,r,p)

    def test_current_max_own_validity(self):
        rows=d.observe([1.]*320,[1.]*320,self.prior([0,0]))
        s=d.selected_stats(rows,range(2))
        self.assertEqual(s['current_max_cos2']['valid'],2)
        self.assertEqual(s['held_cos2']['valid'],1)
        self.assertEqual(s['past_lag']['null'],1)

    def test_missing_csv_schema(self):
        with tempfile.TemporaryDirectory() as root:
            p=Path(root)/'bad.csv';p.write_text('frame,chosen_lag\n0,0\n')
            with self.assertRaises(ValueError):d.old.rows_from(p,1)


if __name__=='__main__':unittest.main()
