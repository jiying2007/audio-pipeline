"""D38 accurately summed causal residual model; diagnostics only."""
from __future__ import annotations
import argparse
import csv
import json
import math
from pathlib import Path
import sys
if __package__ in (None, ''):
    sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from tools.codex_assets import device_causal_residual_model as previous
old = previous.old
BASE = Path('/tmp/audio-fe-device-causal-residual-model-d37-20261011')
PLAN = old.ROOT/'docs/research/frontend-evolution-v1/DEVICE_CAUSAL_RESIDUAL_MODEL_D38_PLAN.zh-CN.md'
TEST = old.ROOT/'tests/validation/frontend_evolution/test_device_causal_residual_model_exact.py'
FIELDS = previous.FIELDS


def accurate_sum(values):
    try:
        value = math.fsum(values)
    except OverflowError as error:
        raise ValueError('nonfinite accurate sum') from error
    old.require(math.isfinite(value), 'finite accurate sum')
    return value


def observe(reference,residual,prior,held):
    old.require(sys.float_info.radix == 2 and sys.float_info.mant_dig == 53 and sys.float_info.max_exp == 1024, 'binary64 environment')
    old.require(len(reference) == len(residual) == len(prior)*160 and len(held) == len(prior), 'trace/frame shape')
    old.require(all(math.isfinite(v) for seq in (reference,residual) for v in seq) and all(math.isfinite(v) and (v == -1 or 0 <= v <= 1+1e-12) for v in held), 'finite trace/held')
    rows = []
    for f in range(len(prior)):
        start = f*160
        rr = accurate_sum(residual[j]*residual[j] for j in range(start,start+160))
        lag = prior[f-1]['chosen_lag'] if f and prior[f-1]['valid_lags'] > 0 else -1
        reason = 1 if f == 0 else 2 if lag < 0 else 0
        beta = fit_xx = fit_rx = xx = pp = ii = ratio = fraction = -1.
        normalized = 0
        if reason == 0:
            past = start-160
            old.require(type(lag) is int and 0 <= lag <= 1535 and lag <= past, 'causal fit lag')
            fit_xx = accurate_sum(reference[j-lag]*reference[j-lag] for j in range(past,start))
            fit_rx = accurate_sum(residual[j]*reference[j-lag] for j in range(past,start))
            old.require(fit_xx > 0, 'positive past reference energy')
            beta = fit_rx/fit_xx
            xx_terms = []; pp_terms = []; ii_terms = []
            for j in range(start,start+160):
                x = reference[j-lag]; prediction = beta*x; innovation = residual[j]-prediction
                xx_terms.append(x*x); pp_terms.append(prediction*prediction); ii_terms.append(innovation*innovation)
            xx = accurate_sum(xx_terms); pp = accurate_sum(pp_terms); ii = accurate_sum(ii_terms)
            normalized = int(rr > 0)
            if normalized:
                ratio = ii/rr; fraction = 1-ratio
        values = (f,lag,int(reason == 0),reason,normalized,beta,fit_xx,fit_rx,rr,xx,pp,ii,ratio,fraction,held[f])
        old.require(all(math.isfinite(v) for v in values), 'nonfinite model output')
        old.require(reason == 0 or held[f] == -1, 'no-model held consistency')
        rows.append(dict(zip(FIELDS,values)))
    return rows


def preflight(output):
    old.require(output.is_absolute() and output == output.resolve() and output.parent == Path('/tmp') and not output.exists(), 'fresh direct /tmp output required')
    locked = {}
    for name,h in (('result.json','2b65812dbb88db0765846c3f15adb54b8bb0df10104593df086ba4b6bfe212ec'),('binding.json','644e2197afb7b46f7b68026b2a671d3e1c8f41342603b9288332e071abfc901e')):
        p = BASE/name; old.require(old.sha(p) == h,'D37 identity'); locked[str(p)] = h
    binding = old.read_json(BASE/'binding.json')
    for group in ('input_files','source_files','artifacts'):
        for name,h in binding[group].items():
            p = BASE/name if group == 'artifacts' else Path(name)
            old.require(p.is_file() and old.sha(p) == h,'D37 dependency drift '+str(p)); locked[str(p)] = h
    extras = {
        old.ROOT/'docs/research/frontend-evolution-v1/DEVICE_CAUSAL_RESIDUAL_MODEL_D37_REVIEW.zh-CN.md':'bd952fb008e876d5605c387287930e38911afcb5512abe34aa3462dafa1972a2',
        Path('/tmp/audio-device-d37-independent-audit.py'):'d7246244c320dbcc5a4043290370d3036c027638c180f65ce0582e16d3ba0dd7',
        Path('/tmp/audio-device-d37-independent-audit.json'):'038df36983b0e08fbda73022430f807d147ef328f5b7578836cd3b5e467a4e53',
        PLAN:'9e4927fefd2cc8b207b2e026b4ada38aefa12423f3d2912869e48edf5171df08'}
    for p,h in extras.items():
        old.require(old.sha(p) == h,'plan/audit/review identity'); locked[str(p)] = h
    sources = {str(p):old.sha(p) for p in (Path(__file__).resolve(),Path(previous.__file__).resolve(),Path(old.__file__).resolve(),PLAN,TEST)}
    cases = old.read_json(old.D30/'result.json')['cases']
    old.require(len(cases) == 46 and len({c['name'] for c in cases}) == 46 and sum(c['execution_summary']['frames'] for c in cases) == 126486,'case identity')
    monitor = {c['name'][8:]:c for c in old.read_json(old.D32/'result.json')['cases'] if c['mode'] == 'monitor'}
    old.require(set(monitor) == {c['name'] for c in cases},'monitor identity')
    return cases,monitor,locked,sources


def run(output,cases,monitor,locked,sources):
    output.mkdir(); records = []
    for case in cases:
        name = case['name']; n = case['execution_summary']['frames']
        rows = observe(old.trace(old.D30/name/'reference.f32le',n*160),old.trace(old.D30/name/'primary_residual.f32le',n*160),old.rows_from(previous.previous.BASE/(name+'.csv'),n),previous.held_rows(previous.BASE/(name+'.csv'),n))
        with (output/(name+'.csv')).open('x',newline='') as stream:
            writer = csv.DictWriter(stream,fieldnames=FIELDS); writer.writeheader(); writer.writerows(rows)
        records.append(dict(name=name,kind=case['kind'],future=case['future'],frames=n,measurement=previous.measurement(case,monitor[name],rows)))
        print(name,n,flush=True)
    normal = (output/'field-case-07-used0-shadow.csv').read_bytes()
    old.require(normal == (output/'repeat.csv').read_bytes(),'repeat exact')
    old.require(normal.splitlines()[:1248] == (output/'future.csv').read_bytes().splitlines()[:1248],'future prefix exact')
    old.require(all(old.sha(Path(p)) == h for p,h in {**locked,**sources}.items()),'end identity drift')
    old.dump(output/'result.json',dict(experiment='FE_DEVICE_CAUSAL_RESIDUAL_MODEL_D38',decision='CAUSAL_RESIDUAL_MODEL_DIAGNOSTIC_NO_PROMOTION',promotion_allowed=False,shipping_approved=False,aec_executions=0,lag_search_executions=0,cases=records,frames=126486,data_role='inspected development and synthetic engineering; adaptive reuse',source_input_start_end_equal=True,summation='math.fsum of binary64 terms'))
    old.dump(output/'binding.json',dict(input_files=locked,source_files=sources,artifacts={str(p.relative_to(output)):old.sha(p) for p in output.rglob('*') if p.is_file()}))
    print('RESULT_SHA256',old.sha(output/'result.json'),flush=True); print('BINDING_SHA256',old.sha(output/'binding.json'),flush=True)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-root',type=Path,required=True); parser.add_argument('--dry-run',action='store_true'); args = parser.parse_args(argv)
    try:
        values = preflight(args.output_root)
        if args.dry_run: print(json.dumps(dict(cases=46,frames=126486,writes=False,aec_executions=0,lag_search_executions=0)))
        else: run(args.output_root,*values)
    except (ValueError,OSError,KeyError,TypeError,OverflowError) as error:
        print('MEASUREMENT_INVALID:',error,file=sys.stderr); return 2
    return 0


if __name__ == '__main__': raise SystemExit(main())
