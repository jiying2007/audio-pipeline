"""D35 causal historical-reference observer; no protection candidate or AEC run."""
from __future__ import annotations
import argparse
import array
import csv
import hashlib
import json
import math
from pathlib import Path
import shutil
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
BASE = Path('/tmp/audio-fe-device-guard-feedback-d34-20261011')
D30 = Path('/tmp/audio-fe-device-activity-d30-20261011')
D32 = Path('/tmp/audio-fe-device-causal-guard-d32-20261011')
D31 = Path('/tmp/audio-fe-device-observability-d31-attempt1-20261011')
PLAN = ROOT / 'docs/research/frontend-evolution-v1/DEVICE_REFERENCE_COHERENCE_D35_PLAN.zh-CN.md'
AMEND = ROOT / 'docs/research/frontend-evolution-v1/DEVICE_REFERENCE_COHERENCE_D35_AMENDMENT.zh-CN.md'
C = ROOT / 'tests/validation/frontend_evolution/device_reference_coherence_d35.c'
TEST = C.parent / 'test_device_reference_coherence.py'
HASHES = {'result.json':'902de3247ac3179082481f28c07b471b8dd2eabd0834562da7416b3a657b9acd', 'binding.json':'edf842ff61d6d9fd0ac4ccdb05bc408c8f2500f692db00b5edf64eabb2df0d09'}
REVIEW = ROOT / 'docs/research/frontend-evolution-v1/DEVICE_GUARD_FEEDBACK_D34_REVIEW.zh-CN.md'
REVIEW_SHA = '329de75f38d4000fedf0784ceed63c862b589f8e95abfbd80c3026bf18c65dfb'
FIELDS = ('frame','tested_lags','valid_lags','residual_energy','max_cos2','chosen_lag','chosen_cos2','zero_lag_cos2')
FLOATS = ('residual_energy','max_cos2','chosen_cos2','zero_lag_cos2')
FLAGS = ('-std=c11','-O2','-Wall','-Wextra','-Werror','-Wconversion','-Wshadow','-pedantic','-ffp-contract=off')


def require(condition, message):
    if not condition:
        raise ValueError(message)


def sha(path):
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for b in iter(lambda: stream.read(1048576), b''):
            h.update(b)
    return h.hexdigest()


def read_json(path):
    def pairs(items):
        result = {}
        for k,v in items:
            require(k not in result, 'duplicate JSON key')
            result[k] = v
        return result
    def invalid(v):
        raise ValueError('nonfinite JSON ' + v)
    return json.loads(path.read_text(), object_pairs_hook=pairs, parse_constant=invalid)


def stats(values):
    valid = sorted(v for v in values if v is not None)
    require(all(math.isfinite(v) for v in valid), 'finite stats')
    result = dict(valid=len(valid), null=len(values)-len(valid), min=None, max=None, p10=None, p50=None, p90=None)
    if valid:
        result.update(min=valid[0],max=valid[-1])
        for key,p in (('p10',10),('p50',50),('p90',90)):
            result[key] = valid[(len(valid)*p+99)//100-1]
    return result


def selected_stats(rows, selected):
    chosen = [rows[i] for i in selected]
    return dict(frames=len(chosen), max_cos2=stats([r['max_cos2'] if r['valid_lags'] else None for r in chosen]),
                chosen_lag=stats([r['chosen_lag'] if r['valid_lags'] else None for r in chosen]),
                zero_lag_cos2=stats([r['zero_lag_cos2'] if r['zero_lag_cos2']>=0 else None for r in chosen]))


def guard_predecessors(flags):
    require(all(v in (0,1) for v in flags), 'guard binary')
    require(not flags or not flags[0], 'no fabricated guard predecessor')
    return [i-1 for i,v in enumerate(flags) if v]


def trace(path, count):
    require(path.stat().st_size == count*4, 'trace size')
    values = array.array('f');require(values.itemsize==4,'Float32 array');values.frombytes(path.read_bytes())
    if sys.byteorder!='little':
        values.byteswap()
    require(all(math.isfinite(v) for v in values),'finite trace')
    return values


def rows_from(path, frames):
    with path.open(newline='') as stream:
        reader = csv.DictReader(stream);require(reader.fieldnames==list(FIELDS),'observer schema');rows=[]
        for frame,row in enumerate(reader):
            require(set(row)==set(FIELDS) and None not in row.values(),'observer row')
            r = {k:float(row[k]) if k in FLOATS else int(row[k]) for k in FIELDS}
            require(r['frame']==frame and all(math.isfinite(v) for v in r.values()),'finite frame')
            require(r['tested_lags']==min(1536,frame*160+1) and 0<=r['valid_lags']<=r['tested_lags'] and r['residual_energy']>=0,'startup/valid/energy')
            require(-1<=r['zero_lag_cos2']<=1+1e-12,'zero-lag bounds')
            if r['valid_lags']:
                require(0<=r['chosen_lag']<r['tested_lags'] and 0<=r['max_cos2']<=1+1e-12 and r['max_cos2']-1e-12<=r['chosen_cos2']<=r['max_cos2'],'max/chosen bounds')
            else:
                require(r['max_cos2']==r['chosen_cos2']==r['zero_lag_cos2']==-1 and r['chosen_lag']==-1,'all invalid sentinel')
            rows.append(r)
    require(len(rows)==frames,'observer frame count')
    return rows


def preflight(output):
    require(output.is_absolute() and output==output.resolve() and output.parent==Path('/tmp') and not output.exists(),'fresh direct /tmp output required')
    locked = {}
    for name,expected in HASHES.items():
        p=BASE/name;require(sha(p)==expected,'D34 identity');locked[str(p)]=expected
    b=read_json(BASE/'binding.json')
    for group in ('input_files','source_files','artifacts'):
        for name,expected in b[group].items():
            p=BASE/name if group=='artifacts' else Path(name)
            require(p.is_file() and sha(p)==expected,'D34 dependency drift '+str(p));locked[str(p)]=expected
    require(sha(REVIEW)==REVIEW_SHA,'D34 REVIEW identity');locked[str(REVIEW)]=REVIEW_SHA
    for name,expected in (('result.json','d1465d24fb2b26d378dd2e6590c661f2a67d5e23ca1255ab7f6bd5970961aee2'),('binding.json','04990be63adfb174d37f6483fa6e1d3e0679276ee6581577eba59baf30cdc506')):
        p=D31/name;require(sha(p)==expected,'D31 anchor identity');locked[str(p)]=expected
    anchor=read_json(D31/'binding.json')
    for group in ('source_files','input_files','artifacts'):
        for name,expected in anchor[group].items():
            p=D31/name if group=='artifacts' else Path(name)
            require(p.is_file() and sha(p)==expected,'D31 anchor drift '+str(p));locked[str(p)]=expected
    cases=read_json(D30/'result.json')['cases'];require(len(cases)==46 and len({c['name'] for c in cases})==46 and sum(c['execution_summary']['frames'] for c in cases)==126486,'exact sources/frames')
    monitor={c['name'][len('monitor-'):]:c for c in read_json(D32/'result.json')['cases'] if c['mode']=='monitor'}
    require(set(monitor)=={c['name'] for c in cases},'monitor source set')
    for c in cases:
        require(Path(c['name']).name==c['name'] and c['name'] not in ('.','..'),'safe case')
        require(str(D31/(c['name']+'.csv')) in locked,'D31 zero-lag anchor locked')
        if c['kind']=='return':
            p=Path(monitor[c['name']]['source_directory'])/'near.f32le';require(str(p) in locked,'near source locked')
    compiler=Path(shutil.which('cc') or '/nonexistent').resolve();require(compiler.is_file(),'actual C compiler')
    sources={str(p):sha(p) for p in (Path(__file__).resolve(),PLAN,AMEND,C,TEST,compiler)}
    return cases,monitor,locked,sources,compiler


def dump(path,value):
    with path.open('x') as stream:
        stream.write(json.dumps(value,sort_keys=True,indent=2,allow_nan=False)+'\n')


def logged(output,name,command,expected=0):
    path=output/(name+'.json');require(not path.exists(),'no receipt overwrite');start=time.time()
    try:
        r=subprocess.run(command,cwd='/tmp',capture_output=True,text=True,timeout=120)
    except (subprocess.TimeoutExpired,OSError) as error:
        def decoded(value):
            return value.decode('utf-8',errors='replace') if isinstance(value,bytes) else value or ''
        dump(path,dict(command=command,exit_code=None,error_type=type(error).__name__,error=str(error),
                       stdout=decoded(getattr(error,'stdout',None)),stderr=decoded(getattr(error,'stderr',None)),elapsed_seconds=time.time()-start))
        raise
    dump(path,dict(command=command,exit_code=r.returncode,stdout=r.stdout,stderr=r.stderr,elapsed_seconds=time.time()-start))
    require(r.returncode==expected,'command exit '+name)
    return r.stdout


def measurement(case,member,rows):
    if case['future']:
        return None
    original=case['observation']['measurement'];windows=[]
    for window in [original['whole'],*original['windows']]:
        a,b=window['sample_range'];start,end=(a+159)//160,b//160
        require(0<=start<=end<=len(rows),'original window')
        windows.append(dict(sample_range=[a,b],complete_frame_range=[start,end],discarded_boundary_samples=b-a-(end-start)*160,statistics=selected_stats(rows,range(start,end))))
    with (D32/member['name']/'guard.csv').open(newline='') as stream:
        guard=list(csv.DictReader(stream))
    require(len(guard)==len(rows) and all(r['frame']==str(i) for i,r in enumerate(guard)),'guard source count')
    preceding=guard_predecessors([int(r['guard']) for r in guard])
    result=dict(original_windows=windows,monitor_guard_previous_frame=selected_stats(rows,preceding),near=None)
    if case['kind']=='return':
        v=trace(Path(member['source_directory'])/'near.f32le',len(rows)*160)
        truth=[int(any(x!=0 for x in v[i:i+160])) for i in range(0,len(v),160)]
        intervals=[]
        for i,present in enumerate(truth):
            if present:
                if intervals and intervals[-1][1]==i:intervals[-1][1]=i+1
                else:intervals.append([i,i+1])
        require(intervals in ([],[[1000,1200],[1600,1800]]),'near role intervals')
        result['near']=dict(intervals=[dict(frame_range=[a,b],statistics=selected_stats(rows,range(a,b))) for a,b in intervals],
                            no_near=selected_stats(rows,[i for i,present in enumerate(truth) if not present]),pure_echo=not intervals)
    return result


def run(output,cases,monitor,locked,sources,compiler):
    output.mkdir();runner=output/'observer'
    logged(output,'compiler-version',['rtk',str(compiler),'--version'])
    logged(output,'compile',['rtk',str(compiler),*FLAGS,str(C),'-lm','-o',str(runner)])
    runner_sha=sha(runner);logged(output,'self-test',['rtk',str(runner),'--self-test'])
    sentinel=output/'invalid-output.csv';sentinel.write_bytes(b'D35-SENTINEL')
    for i,value in enumerate(('0','-1','nan','10001','')):
        logged(output,'invalid-'+str(i),['rtk',str(runner),'/nonexistent-reference','/nonexistent-residual',value,str(sentinel)],2)
        require(sentinel.read_bytes()==b'D35-SENTINEL','invalid output preserved')
    logged(output,'invalid-argc',['rtk',str(runner)],2)
    records=[];anchors=0;lag_candidates=0
    for case in cases:
        name=case['name'];frames=case['execution_summary']['frames']
        execution=json.loads(logged(output,'case-'+name,['rtk',str(runner),str(D30/name/'reference.f32le'),str(D30/name/'primary_residual.f32le'),str(frames),str(output/(name+'.csv'))]))
        require(execution['frames']==execution['observer_calls']==frames and execution['aec_calls']==0,'actual observer counts')
        rows=rows_from(output/(name+'.csv'),frames)
        require(execution['lag_candidates']==sum(r['tested_lags'] for r in rows),'lag candidate count');lag_candidates+=execution['lag_candidates']
        with (D31/(name+'.csv')).open(newline='') as stream:
            old=list(csv.DictReader(stream))
        require(len(old)==frames,'D31 anchor rows')
        for row,prior in zip(rows,old):
            v=prior['primary_residual_reference_cos2'];expected=float(v) if v else -1.
            require(abs(row['zero_lag_cos2']-expected)<=1e-12,'D31 zero-lag equivalence');anchors+=1
        records.append(dict(name=name,kind=case['kind'],future=case['future'],frames=frames,execution_summary=execution,measurement=measurement(case,monitor[name],rows)))
        print(name,frames,flush=True)
    normal=(output/'field-case-07-used0-shadow.csv').read_bytes()
    require(normal==(output/'repeat.csv').read_bytes(),'repeat exact observer')
    require(normal.splitlines()[:1248]==(output/'future.csv').read_bytes().splitlines()[:1248],'future prefix exact observer')
    require(all(sha(Path(p))==h for p,h in {**locked,**sources}.items()) and sha(runner)==runner_sha,'end identity drift')
    result=dict(experiment='FE_DEVICE_REFERENCE_COHERENCE_D35',decision='REFERENCE_COHERENCE_DIAGNOSTIC_NO_PROMOTION',promotion_allowed=False,shipping_approved=False,
                aec_executions=0,observer_executions=46,frames=126486,lag_candidates=lag_candidates,zero_lag_anchor_frames=anchors,cases=records,
                data_role='inspected development and synthetic engineering; adaptive reuse',source_input_runner_start_end_equal=True)
    dump(output/'result.json',result)
    dump(output/'binding.json',dict(input_files=locked,source_files=sources,runner_sha256=runner_sha,artifacts={str(p.relative_to(output)):sha(p) for p in output.rglob('*') if p.is_file()}))
    print('RESULT_SHA256',sha(output/'result.json'),flush=True);print('BINDING_SHA256',sha(output/'binding.json'),flush=True)


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output-root',type=Path,required=True);parser.add_argument('--dry-run',action='store_true');args=parser.parse_args(argv)
    try:
        cases,monitor,locked,sources,compiler=preflight(args.output_root)
        if args.dry_run:
            print(json.dumps(dict(cases=46,frames=126486,writes=False,aec_executions=0)))
        else:
            run(args.output_root,cases,monitor,locked,sources,compiler)
    except (ValueError,OSError,KeyError,TypeError,OverflowError,subprocess.TimeoutExpired) as error:
        print('MEASUREMENT_INVALID:',error,file=sys.stderr);return 2
    return 0


if __name__=='__main__':
    raise SystemExit(main())
