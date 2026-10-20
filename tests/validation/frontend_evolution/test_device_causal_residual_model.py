import math
import tempfile
import unittest
from pathlib import Path
from tools.codex_assets import device_causal_residual_model as d


class CausalResidualModelTests(unittest.TestCase):
    def prior(self, lags):
        return [dict(chosen_lag=v,valid_lags=int(v >= 0),max_cos2=1. if v >= 0 else -1.) for v in lags]

    def observe(self,x,r,lags,held=None):
        return d.observe(x,r,self.prior(lags),held if held is not None else [-1.]+[1.]*(len(lags)-1))

    def test_signed_fit_and_first_frame(self):
        for beta in (2.,-1.):
            rows=self.observe([1.]*320,[beta]*320,[0,0])
            self.assertEqual(rows[0]['reason'],1)
            self.assertEqual(rows[0]['residual_energy'],160*beta*beta)
            self.assertEqual(rows[1]['beta'],beta)
            self.assertEqual(rows[1]['fit_cross_energy'],160*beta)
            self.assertEqual(rows[1]['innovation_energy'],0.)
            self.assertEqual(rows[1]['explained_fraction'],1.)
        self.assertEqual(d.selected_stats(rows,[1])['beta']['valid'],1)

    def test_nonzero_lag_crosses_frame_boundary(self):
        x=[float(i%11+1) for i in range(480)]
        r=[x[j] if j<160 else -2*x[j-7] for j in range(480)]
        rows=self.observe(x,r,[0,7,7])
        self.assertEqual(rows[2]['past_lag'],7)
        self.assertEqual(rows[2]['beta'],-2.)
        self.assertEqual(rows[2]['innovation_energy'],0.)

    def test_path_change_is_not_clamped(self):
        rows=self.observe([1.]*320,[3.]*160+[1.]*160,[0,0])
        self.assertEqual(rows[1]['innovation_ratio'],4.)
        self.assertEqual(rows[1]['explained_fraction'],-3.)
        self.assertEqual(d.selected_stats(rows,[1])['mismatch_frames'],1)

    def test_near_innovation(self):
        r=[1.]*160+[1.+(-1 if i%2 else 1) for i in range(160)]
        row=self.observe([1.]*320,r,[0,0])[1]
        self.assertEqual(row['beta'],1.)
        self.assertEqual(row['innovation_energy'],160.)
        self.assertEqual(row['innovation_ratio'],0.5)

    def test_current_zero_residual_retains_model(self):
        row=self.observe([1.]*320,[1.]*160+[0.]*160,[0,-1],[-1.,-1.])[1]
        self.assertEqual(row['model_valid'],1)
        self.assertEqual(row['normalized_valid'],0)
        self.assertEqual(row['innovation_ratio'],-1.)
        self.assertEqual(row['explained_fraction'],-1.)
        self.assertEqual(row['prediction_energy'],160.)
        self.assertEqual(row['innovation_energy'],160.)
        self.assertEqual(row['held_cos2'],-1.)

    def test_current_zero_reference_and_invalid_no_hold(self):
        rows=self.observe([1.]*160+[0.]*160+[1.]*160,[1.]*480,[0,-1,0],[-1.,-1.,-1.])
        self.assertEqual(rows[1]['model_valid'],1)
        self.assertEqual(rows[1]['reference_energy'],0.)
        self.assertEqual(rows[1]['innovation_ratio'],1.)
        self.assertEqual(rows[2]['reason'],2)
        self.assertEqual(rows[2]['past_lag'],-1)
        self.assertEqual(rows[2]['beta'],-1.)

    def test_shape_nan_causality_and_nonfinite_fail(self):
        for x,r,lags,h in [([1.],[],[],[]),([math.nan]*160,[1.]*160,[0],[-1.]),([1.]*320,[1.]*320,[1,0],[-1.,1.]),([1e308]*320,[1.]*320,[0,0],[-1.,1.])]:
            with self.assertRaises(ValueError):self.observe(x,r,lags,h)

    def test_missing_csv_schema(self):
        with tempfile.TemporaryDirectory() as root:
            p=Path(root)/'bad.csv';p.write_text('frame,held_cos2\n0,-1\n')
            with self.assertRaises(ValueError):d.held_rows(p,1)
            with self.assertRaises(ValueError):d.old.rows_from(p,1)

    def test_future_samples_do_not_change_prefix(self):
        x=[1.]*640; r=[2.]*640
        before=self.observe(x,r,[0]*4)
        x[480:]=[9.]*160; r[480:]=[-7.]*160
        after=self.observe(x,r,[0]*4)
        self.assertEqual(before[:3],after[:3])


if __name__=='__main__':unittest.main()
