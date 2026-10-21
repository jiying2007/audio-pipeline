"""D36 previous-frame held-lag diagnostic; no DSP or protection execution."""
from __future__ import annotations
import argparse
import csv
import json
import math
from pathlib import Path
import sys
if __package__ in (None, ''):
    sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from tools.codex_assets import device_reference_coherence as old

BASE = Path('/tmp/audio-fe-device-reference-coherence-d35-20261011')
PLAN = old.ROOT / 'docs/research/frontend-evolution-v1/DEVICE_HELD_LAG_D36_PLAN.zh-CN.md'
TEST = old.ROOT / 'tests/validation/frontend_evolution/test_device_held_lag.py'
FIELDS = ('frame','past_lag','held_valid','reason','residual_energy','reference_energy','held_cos2','current_max_cos2','max_minus_held','lag_changed')


def observe(reference, residual, prior):
    old.require(len(reference)==len(residual)==len(prior)*160, 'trace/frame shape')
    old.require(all(math.isfinite(v) for v in reference) and all(math.isfinite(v) for v in residual), 'finite trace')
    rows=[]
    for f,current in enumerate(prior):
        start=f*160; rr=0.
        for j in range(start,start+160): rr+=residual[j]*residual[j]
        lag=prior[f-1]['chosen_lag'] if f and prior[f-1]['valid_lags'] else -1
        xx=-1.; held=-1.; gap=-1.; changed=-1
        reason=1 if not f else 2 if lag<0 else 0
        if lag>=0:
            old.require(0<=lag<=1535 and lag<=start, 'causal past lag')
            xx=0.; rx=0.
            for j in range(start,start+160):
                x=reference[j-lag]; r=residual[j]; xx+=x*x; rx+=r*x
            reason=3 if rr==0 else 4 if xx==0 else 0
            if not reason:
                held=rx*rx/(rr*xx)
                old.require(current['valid_lags']>0, 'valid current maximum')
                gap=current['max_cos2']-held
                old.require(0<=held<=1+1e-12 and gap>=-1e-12, 'held bounds')
                changed=int(lag!=current['chosen_lag'])
        rows.append(dict(zip(FIELDS,(f,lag,int(reason==0),reason,rr,xx,held,current['max_cos2'],gap,changed))))
    return rows


def selected_stats(rows, selected):
    chosen=[rows[i] for i in selected]
    result=dict(frames=len(chosen),reason_counts={str(i):sum(r['reason']==i for r in chosen) for i in range(5)},
                lag_comparable=sum(r['held_valid'] for r in chosen),lag_changed=sum(r['lag_changed']==1 for r in chosen))
    for key in ('held_cos2','current_max_cos2','max_minus_held','past_lag'):
        # D35 maximum retains its own validity independently of held validity.
        result[key]=old.stats([r[key] if (r[key]>=0 if key in ('current_max_cos2','past_lag') else r['held_valid']) else None for r in chosen])
    return result


def measurement(case,member,rows):
    if case['future']: return None
    original=case['observation']['measurement']; windows=[]
    for window in [original['whole'],*original['windows']]:
        a,b=window['sample_range']; start,end=(a+159)//160,b//160
        old.require(0<=start<=end<=len(rows),'original window')
        windows.append(dict(sample_range=[a,b],complete_frame_range=[start,end],discarded_boundary_samples=b-a-(end-start)*160,statistics=selected_stats(rows,range(start,end))))
    with (old.D32/member['name']/'guard.csv').open(newline='') as stream: guard=list(csv.DictReader(stream))
    old.require(len(guard)==len(rows) and all(r['frame']==str(i) for i,r in enumerate(guard)), 'guard shape')
    result=dict(original_windows=windows,monitor_guard_previous_frame=selected_stats(rows,old.guard_predecessors([int(r['guard']) for r in guard])),near=None)
    if case['kind']=='return':
        near=old.trace(Path(member['source_directory'])/'near.f32le',len(rows)*160)
        truth=[any(v!=0 for v in near[i:i+160]) for i in range(0,len(near),160)]; intervals=[]
        for i,present in enumerate(truth):
            if present:
                if intervals and intervals[-1][1]==i: intervals[-1][1]=i+1
                else: intervals.append([i,i+1])
        old.require(intervals in ([],[[1000,1200],[1600,1800]]),'near intervals')
        result['near']=dict(intervals=[dict(frame_range=[a,b],statistics=selected_stats(rows,range(a,b))) for a,b in intervals],no_near=selected_stats(rows,[i for i,v in enumerate(truth) if not v]),pure_echo=not intervals)
    return result


def preflight(output):
    old.require(output.is_absolute() and output==output.resolve() and output.parent==Path('/tmp') and not output.exists(),'fresh direct /tmp output required')
    locked={}
    for name,expected in (('result.json','a18f8b4e678410a043dcbb4b5e2d8ebb68df70156f52ec6f18fad02d09cf58dc'),('binding.json','a913b140255a0a84b75e3604517536d0644c4895093d071f359fe25b5b76a6ca')):
        p=BASE/name;old.require(old.sha(p)==expected,'D35 identity');locked[str(p)]=expected
    binding=old.read_json(BASE/'binding.json')
    for group in ('input_files','source_files','artifacts'):
        for name,expected in binding[group].items():
            p=BASE/name if group=='artifacts' else Path(name)
            old.require(p.is_file() and old.sha(p)==expected,'D35 dependency drift '+str(p));locked[str(p)]=expected
    extras={old.ROOT/'docs/research/frontend-evolution-v1/DEVICE_REFERENCE_COHERENCE_D35_REVIEW.zh-CN.md':'3d4e172f2d9b5531f54a415a26d982c05cda3358d3d51f8c48ecea3b93b54e23',
            Path('/tmp/audio-device-d35-independent-audit.py'):'30401a830c76b8b049486e1539f703fc12f0828feb117af4cf70a6bbf2cbfef0',
            Path('/tmp/audio-device-d35-independent-audit.c'):'7e0db41c5dc859169de1aa971bf1e28dc62928427e8ac83774810cabbebc287c',
            Path('/tmp/audio-device-d35-independent-audit.json'):'f33b4ce15d1030f9b035e42d92c194fdd37490fc5c7eb1c86cc21a69dc920d3c',
            Path('/tmp/audio-device-d35-exact-zero-audit.json'):'13192eb784710cf591aade0b3bed6c605f00b06295b70657c75f83612d52bb63',
            Path('/tmp/audio-device-d35-exact-zero-audit.py'):'789345d33d5befcaabaa271150ebfd9ce2fa7032e2f867ae19f7d8c6f1a0c5fb'}
    for p,h in extras.items(): old.require(old.sha(p)==h,'audit/review identity');locked[str(p)]=h
    old.require(old.sha(PLAN)=='244bd87cde99c336e3fc791de0a49eb3ada5cb66159a522d74851586781ca501','PLAN identity')
    sources={str(p):old.sha(p) for p in (Path(__file__).resolve(),Path(old.__file__).resolve(),PLAN,TEST)}
    cases=old.read_json(old.D30/'result.json')['cases']
    old.require(len(cases)==46 and len({c['name'] for c in cases})==46 and sum(c['execution_summary']['frames'] for c in cases)==126486,'case identity')
    monitor={c['name'][8:]:c for c in old.read_json(old.D32/'result.json')['cases'] if c['mode']=='monitor'}
    old.require(set(monitor)=={c['name'] for c in cases},'monitor identity')
    return cases,monitor,locked,sources


def run(output,cases,monitor,locked,sources):
    output.mkdir();records=[]
    for case in cases:
        name=case['name']; n=case['execution_summary']['frames']
        prior=old.rows_from(BASE/(name+'.csv'),n)
        rows=observe(old.trace(old.D30/name/'reference.f32le',n*160),old.trace(old.D30/name/'primary_residual.f32le',n*160),prior)
        with (output/(name+'.csv')).open('x',newline='') as stream:
            writer=csv.DictWriter(stream,fieldnames=FIELDS);writer.writeheader();writer.writerows(rows)
        records.append(dict(name=name,kind=case['kind'],future=case['future'],frames=n,measurement=measurement(case,monitor[name],rows)))
        print(name,n,flush=True)
    normal=(output/'field-case-07-used0-shadow.csv').read_bytes()
    old.require(normal==(output/'repeat.csv').read_bytes(),'repeat exact')
    old.require(normal.splitlines()[:1248]==(output/'future.csv').read_bytes().splitlines()[:1248],'future prefix exact')
    old.require(all(old.sha(Path(p))==h for p,h in {**locked,**sources}.items()),'end identity drift')
    old.dump(output/'result.json',dict(experiment='FE_DEVICE_HELD_LAG_D36',decision='HELD_LAG_DIAGNOSTIC_NO_PROMOTION',promotion_allowed=False,shipping_approved=False,aec_executions=0,lag_search_executions=0,cases=records,frames=126486,data_role='inspected development and synthetic engineering; adaptive reuse',source_input_start_end_equal=True))
    old.dump(output/'binding.json',dict(input_files=locked,source_files=sources,artifacts={str(p.relative_to(output)):old.sha(p) for p in output.rglob('*') if p.is_file()}))
    print('RESULT_SHA256',old.sha(output/'result.json'),flush=True);print('BINDING_SHA256',old.sha(output/'binding.json'),flush=True)


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output-root',type=Path,required=True);parser.add_argument('--dry-run',action='store_true');args=parser.parse_args(argv)
    try:
        cases,monitor,locked,sources=preflight(args.output_root)
        if args.dry_run: print(json.dumps(dict(cases=46,frames=126486,writes=False,aec_executions=0,lag_search_executions=0)))
        else: run(args.output_root,cases,monitor,locked,sources)
    except (ValueError,OSError,KeyError,TypeError,OverflowError) as error:
        print('MEASUREMENT_INVALID:',error,file=sys.stderr);return 2
    return 0


if __name__=='__main__': raise SystemExit(main())
