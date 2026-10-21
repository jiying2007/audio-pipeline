"""D37 past-frame signed residual model; research diagnostics only."""
from __future__ import annotations
import argparse
import csv
import json
import math
from pathlib import Path
import sys
if __package__ in (None, ''):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from tools.codex_assets import device_held_lag as previous
old = previous.old
BASE = Path('/tmp/audio-fe-device-held-lag-d36-20261011')
PLAN = old.ROOT/'docs/research/frontend-evolution-v1/DEVICE_CAUSAL_RESIDUAL_MODEL_D37_PLAN.zh-CN.md'
AMEND = PLAN.with_name('DEVICE_CAUSAL_RESIDUAL_MODEL_D37_AMENDMENT.zh-CN.md')
TEST = old.ROOT/'tests/validation/frontend_evolution/test_device_causal_residual_model.py'
FIELDS = ('frame','past_lag','model_valid','reason','normalized_valid','beta','fit_reference_energy','fit_cross_energy','residual_energy','reference_energy','prediction_energy','innovation_energy','innovation_ratio','explained_fraction','held_cos2')


def held_rows(path, count):
    with path.open(newline='') as stream:
        reader = csv.DictReader(stream)
        old.require(tuple(reader.fieldnames or ()) == previous.FIELDS, 'D36 CSV schema')
        rows = list(reader)
    old.require(len(rows) == count, 'D36 CSV shape')
    result = []
    for i, row in enumerate(rows):
        value = float(row['held_cos2'])
        old.require(row['frame'] == str(i) and math.isfinite(value) and (value == -1 or 0 <= value <= 1+1e-12), 'D36 held value')
        result.append(value)
    return result


def observe(reference, residual, prior, held):
    old.require(len(reference) == len(residual) == len(prior)*160 and len(held) == len(prior), 'trace/frame shape')
    old.require(all(math.isfinite(v) for v in reference+residual) and all(math.isfinite(v) and (v == -1 or 0 <= v <= 1+1e-12) for v in held), 'finite trace/held')
    rows = []
    for f in range(len(prior)):
        start = f*160
        rr = 0.
        for j in range(start, start+160):
            rr += residual[j]*residual[j]
        lag = prior[f-1]['chosen_lag'] if f and prior[f-1]['valid_lags'] > 0 else -1
        reason = 1 if f == 0 else 2 if lag < 0 else 0
        beta = fit_xx = fit_rx = xx = pp = ii = ratio = fraction = -1.
        normalized = 0
        if reason == 0:
            past = start-160
            old.require(type(lag) is int and 0 <= lag <= 1535 and lag <= past, 'causal fit lag')
            fit_xx = fit_rx = 0.
            for j in range(past, start):
                x = reference[j-lag]
                fit_xx += x*x
                fit_rx += residual[j]*x
            old.require(fit_xx > 0, 'positive past reference energy')
            beta = fit_rx/fit_xx
            xx = pp = ii = 0.
            for j in range(start, start+160):
                x = reference[j-lag]
                prediction = beta*x
                innovation = residual[j]-prediction
                xx += x*x
                pp += prediction*prediction
                ii += innovation*innovation
            normalized = int(rr > 0)
            if normalized:
                ratio = ii/rr
                fraction = 1-ratio
        values = (f,lag,int(reason == 0),reason,normalized,beta,fit_xx,fit_rx,rr,xx,pp,ii,ratio,fraction,held[f])
        old.require(all(math.isfinite(v) for v in values), 'nonfinite model output')
        old.require(reason == 0 or held[f] == -1, 'no-model held consistency')
        rows.append(dict(zip(FIELDS, values)))
    return rows


def selected_stats(rows, selected):
    chosen = [rows[i] for i in selected]
    result = dict(frames=len(chosen), reason_counts={str(i):sum(r['reason'] == i for r in chosen) for i in range(3)},
                  model_valid=sum(r['model_valid'] for r in chosen), normalized_valid=sum(r['normalized_valid'] for r in chosen),
                  mismatch_frames=sum(r['normalized_valid'] and r['innovation_ratio'] > 1 for r in chosen))
    for key in ('beta','prediction_energy','innovation_energy','innovation_ratio','explained_fraction','held_cos2'):
        flag = 'normalized_valid' if key in ('innovation_ratio','explained_fraction') else 'model_valid'
        result[key] = old.stats([r[key] if (r[key] >= 0 if key == 'held_cos2' else r[flag]) else None for r in chosen])
    return result


def measurement(case, member, rows):
    if case['future']:
        return None
    original = case['observation']['measurement']
    windows = []
    for window in [original['whole'], *original['windows']]:
        a,b = window['sample_range']; start,end = (a+159)//160,b//160
        old.require(0 <= start <= end <= len(rows), 'original window')
        windows.append(dict(sample_range=[a,b], complete_frame_range=[start,end], discarded_boundary_samples=b-a-(end-start)*160, statistics=selected_stats(rows,range(start,end))))
    with (old.D32/member['name']/'guard.csv').open(newline='') as stream:
        guard = list(csv.DictReader(stream))
    old.require(len(guard) == len(rows) and all(r['frame'] == str(i) for i,r in enumerate(guard)), 'guard shape')
    result = dict(original_windows=windows, monitor_guard_previous_frame=selected_stats(rows,old.guard_predecessors([int(r['guard']) for r in guard])), near=None)
    if case['kind'] == 'return':
        near = old.trace(Path(member['source_directory'])/'near.f32le',len(rows)*160)
        truth = [any(v != 0 for v in near[i:i+160]) for i in range(0,len(near),160)]
        intervals = []
        for i,present in enumerate(truth):
            if present:
                if intervals and intervals[-1][1] == i: intervals[-1][1] = i+1
                else: intervals.append([i,i+1])
        old.require(intervals in ([],[[1000,1200],[1600,1800]]), 'near intervals')
        result['near'] = dict(intervals=[dict(frame_range=[a,b],statistics=selected_stats(rows,range(a,b))) for a,b in intervals], no_near=selected_stats(rows,[i for i,v in enumerate(truth) if not v]), pure_echo=not intervals)
    return result


def preflight(output):
    old.require(output.is_absolute() and output == output.resolve() and output.parent == Path('/tmp') and not output.exists(), 'fresh direct /tmp output required')
    locked = {}
    for name,h in (('result.json','8b1123301e08caa8e695188e8005a1022e0f023500e5151046454bb90f28c8b9'),('binding.json','800b73b466054e606eeb6a70210d0027e01fde3eb1d225738ea84ff4bf09820e')):
        p = BASE/name; old.require(old.sha(p) == h, 'D36 identity'); locked[str(p)] = h
    binding = old.read_json(BASE/'binding.json')
    for group in ('input_files','source_files','artifacts'):
        for name,h in binding[group].items():
            p = BASE/name if group == 'artifacts' else Path(name)
            old.require(p.is_file() and old.sha(p) == h, 'D36 dependency drift '+str(p)); locked[str(p)] = h
    extras = {
        old.ROOT/'docs/research/frontend-evolution-v1/DEVICE_HELD_LAG_D36_REVIEW.zh-CN.md':'4af6a9db121ea7c70bd727a3993d8e95ff55e9d6bf6886f9ea1803440a38eea3',
        Path('/tmp/audio-device-d36-independent-audit.py'):'3f6eae447150c25726a8084963ba0bd1c871195ee798688dfe9fe84b48852b23',
        Path('/tmp/audio-device-d36-independent-audit.json'):'d4729fe1f725e4e7d5913d1f8b8da7a9bcfa17fc41261cb1da83851cfbd3aed4',
        PLAN:'ab15bccb2657bfc6dc010dac2f26d0d34820125b1bc7e2fb8843a3f993aaf8be',
        AMEND:'9b68b12f72c8d522beab3abedd4cd8042ce41fd13522d293ffeb9a09c0d7a5e7'}
    for p,h in extras.items():
        old.require(old.sha(p) == h, 'plan/audit/review identity'); locked[str(p)] = h
    sources = {str(p):old.sha(p) for p in (Path(__file__).resolve(),Path(previous.__file__).resolve(),Path(old.__file__).resolve(),PLAN,AMEND,TEST)}
    cases = old.read_json(old.D30/'result.json')['cases']
    old.require(len(cases) == 46 and len({c['name'] for c in cases}) == 46 and sum(c['execution_summary']['frames'] for c in cases) == 126486, 'case identity')
    monitor = {c['name'][8:]:c for c in old.read_json(old.D32/'result.json')['cases'] if c['mode'] == 'monitor'}
    old.require(set(monitor) == {c['name'] for c in cases}, 'monitor identity')
    return cases,monitor,locked,sources


def run(output,cases,monitor,locked,sources):
    output.mkdir(); records = []
    for case in cases:
        name = case['name']; n = case['execution_summary']['frames']
        rows = observe(old.trace(old.D30/name/'reference.f32le',n*160),old.trace(old.D30/name/'primary_residual.f32le',n*160),old.rows_from(previous.BASE/(name+'.csv'),n),held_rows(BASE/(name+'.csv'),n))
        with (output/(name+'.csv')).open('x',newline='') as stream:
            writer = csv.DictWriter(stream,fieldnames=FIELDS); writer.writeheader(); writer.writerows(rows)
        records.append(dict(name=name,kind=case['kind'],future=case['future'],frames=n,measurement=measurement(case,monitor[name],rows)))
        print(name,n,flush=True)
    normal = (output/'field-case-07-used0-shadow.csv').read_bytes()
    old.require(normal == (output/'repeat.csv').read_bytes(), 'repeat exact')
    old.require(normal.splitlines()[:1248] == (output/'future.csv').read_bytes().splitlines()[:1248], 'future prefix exact')
    old.require(all(old.sha(Path(p)) == h for p,h in {**locked,**sources}.items()), 'end identity drift')
    old.dump(output/'result.json',dict(experiment='FE_DEVICE_CAUSAL_RESIDUAL_MODEL_D37',decision='CAUSAL_RESIDUAL_MODEL_DIAGNOSTIC_NO_PROMOTION',promotion_allowed=False,shipping_approved=False,aec_executions=0,lag_search_executions=0,cases=records,frames=126486,data_role='inspected development and synthetic engineering; adaptive reuse',source_input_start_end_equal=True))
    old.dump(output/'binding.json',dict(input_files=locked,source_files=sources,artifacts={str(p.relative_to(output)):old.sha(p) for p in output.rglob('*') if p.is_file()}))
    print('RESULT_SHA256',old.sha(output/'result.json'),flush=True); print('BINDING_SHA256',old.sha(output/'binding.json'),flush=True)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-root',type=Path,required=True); parser.add_argument('--dry-run',action='store_true')
    args = parser.parse_args(argv)
    try:
        values = preflight(args.output_root)
        if args.dry_run: print(json.dumps(dict(cases=46,frames=126486,writes=False,aec_executions=0,lag_search_executions=0)))
        else: run(args.output_root,*values)
    except (ValueError,OSError,KeyError,TypeError,OverflowError) as error:
        print('MEASUREMENT_INVALID:',error,file=sys.stderr); return 2
    return 0


if __name__ == '__main__': raise SystemExit(main())
