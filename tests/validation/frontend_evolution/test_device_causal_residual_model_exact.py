import csv
from decimal import Decimal,localcontext,Inexact,Rounded
import math
import sys
from pathlib import Path
import unittest
from tools.codex_assets import device_causal_residual_model_exact as d
import test_device_causal_residual_model as baseline_tests


def exact(values):
    with localcontext() as ctx:
        ctx.prec=2200; ctx.traps[Inexact]=True; ctx.traps[Rounded]=True
        total=Decimal(0)
        for value in reversed(list(values)):total+=Decimal.from_float(value)
        return float(total)


class ExactModelTests(baseline_tests.CausalResidualModelTests):
    def observe(self,x,r,lags,held=None):
        return d.observe(x,r,self.prior(lags),held if held is not None else [-1.]+[1.]*(len(lags)-1))

    def test_signed_cancellation_and_order(self):
        values=([1e16,1.,-1e16,0.]*40)
        expected=exact(values)
        self.assertEqual(expected,40.)
        for terms in (values,list(reversed(values)),sorted(values)):
            self.assertEqual(d.accurate_sum(terms),expected)

    def test_decimal_precision_extremes(self):
        smallest=float.fromhex('0x0.0000000000001p-1022')
        values=[sys.float_info.max,smallest,-sys.float_info.max]+[0.]*157
        self.assertEqual(exact(values),smallest)
        self.assertEqual(d.accurate_sum(values),smallest)

    def test_large_ratio_not_clamped(self):
        row=self.observe([1.]*320,[200.]*160+[1.]*160,[0,0])[1]
        self.assertEqual(row['innovation_ratio'],39601.)
        self.assertEqual(row['explained_fraction'],-39600.)

    def test_actual_d37_failed_frame_against_decimal(self):
        name='field-case-03-fixed1-shadow'; n=3008; count=1832
        x=d.old.trace(d.old.D30/name/'reference.f32le',n*160)[:count*160]
        r=d.old.trace(d.old.D30/name/'primary_residual.f32le',n*160)[:count*160]
        prior=d.old.rows_from(d.previous.previous.BASE/(name+'.csv'),n)[:count]
        held=d.previous.held_rows(d.previous.BASE/(name+'.csv'),n)[:count]
        row=d.observe(x,r,prior,held)[1831]; start=1831*160; lag=1516
        xx=exact(x[j-lag]*x[j-lag] for j in range(start-160,start))
        rx=exact(r[j]*x[j-lag] for j in range(start-160,start)); beta=rx/xx
        rr=exact(r[j]*r[j] for j in range(start,start+160))
        ii=exact((r[j]-beta*x[j-lag])*(r[j]-beta*x[j-lag]) for j in range(start,start+160))
        self.assertEqual(row['past_lag'],lag)
        self.assertEqual(row['beta'],beta)
        self.assertEqual(row['residual_energy'],rr)
        self.assertEqual(row['innovation_energy'],ii)
        self.assertEqual(row['innovation_ratio'],ii/rr)
        self.assertGreater(row['innovation_ratio'],21693.)


if __name__=='__main__':unittest.main()
