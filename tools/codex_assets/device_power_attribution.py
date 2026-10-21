"""D43 measurement contracts; no candidate selection or shipping authority."""
from __future__ import annotations
import argparse
import csv
import io
import json
import math
from pathlib import Path
import shutil
import sys
import time
if __package__ in (None, ''):
    sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from tools.codex_assets.device_capture import ROOT,bounded,require,sha,strict_json
from tools.codex_assets.device_exact_reference import read_json,dump
from tools.codex_assets import device_noise_conditioned_protection as d42

D42=Path('/tmp/audio-fe-device-noise-conditioned-protection-d42-20261011')
D42_HASHES={'result.json':'a2b839fbc635d1f1664d4c98d0406186e481b52aaef0a2a4fd4f4285902f31e2',
    'binding.json':'291d91f48162fa5fcab3f7deff25ec8c9baff77cbe7e39cd78004108f52883f0'}
PLAN=ROOT/'docs/research/frontend-evolution-v1/DEVICE_POWER_ATTRIBUTION_D43_PLAN.zh-CN.md'
AMEND=PLAN.with_name('DEVICE_POWER_ATTRIBUTION_D43_AMENDMENT.zh-CN.md')
REVIEW=PLAN.with_name('DEVICE_POWER_ATTRIBUTION_D43_PLAN_REVIEW.zh-CN.md')
C=ROOT/'tests/validation/frontend_evolution/device_power_attribution_d43.c'
NS=C.with_name('device_power_ns_d43.c')
HEADER=C.with_suffix('.h')
TEST=C.with_name('test_device_power_attribution.py')
OUTPUTS=d42.OUTPUTS+('power.csv','bins.csv')
POWER_FIELDS='frame far dt count_before valid_bins noise_dominant_bins positive_floor_bins would_raise_bins raised_bins q_mean echo_sum residual_sum innovation_sum noise_sum excess_sum floor_mean floor2_residual_sum'.split()
BIN_FIELDS='frame bin far dt count_before valid E R Cr Ci N er ei rr ri power echo_power original_target old_gain floor applied_target res_gain'.split()
EXTRA_FRAMES=frozenset((1,9,10,11,999,1001,1199,1200,1201,1599,1600,1601,1799,1800,1801))
DECISION='POWER_ATTRIBUTION_DIAGNOSTIC_NO_PROMOTION'

def snapshot_frames(frames):
    require(type(frames) is int and 0<frames<=10000,'frame count')
    return sorted(set(range(0,frames,100)) | {f for f in EXTRA_FRAMES if f<frames} | {frames-1})

def records(path,fields):
    reader=csv.DictReader(io.StringIO(bounded(path,4*1024*1024).decode('ascii')))
    require(reader.fieldnames==fields,'diagnostic schema '+path.name)
    for row in reader:
        require(None not in row and all(v is not None for v in row.values()),'diagnostic row width')
        yield row

def integer(row,key,maximum):
    value=row[key]
    require(value.isascii() and value.isdecimal() and (value=='0' or not value.startswith('0')),'integer encoding '+key)
    number=int(value);require(number<=maximum,'integer range '+key)
    return number

def finite(row,key,low=None,high=None):
    value=float(row[key]);require(math.isfinite(value),'nonfinite '+key)
    require((low is None or value>=low) and (high is None or value<=high),'numeric range '+key)
    return value

def trace(directory,frames,mode,gates):
    """Validate all rows; independent snapshot arithmetic belongs to separate audit."""
    require(mode in ('monitor','candidate'),'mode')
    require(len(gates)==frames*2 and all(x in (0,1) for x in gates),'gate count/value')
    power=[];previous_count=0
    for index,row in enumerate(records(directory/'power.csv',POWER_FIELDS)):
        require(index<frames and integer(row,'frame',frames-1)==index,'power frame sequence')
        far=integer(row,'far',1);dt=integer(row,'dt',1)
        require((far,dt)==tuple(gates[index*2:index*2+2]),'power gate identity')
        count=integer(row,'count_before',10)
        counts={k:integer(row,k,257) for k in POWER_FIELDS[4:9]}
        valid=counts['valid_bins'];active=bool(far and not dt)
        require(count==previous_count,'past count continuity')
        previous_count=min(10,count+1) if active else 0
        require((active and count==10) or valid==0,'warmup valid count')
        require(all(v<=valid for v in counts.values()),'bin count relation')
        require(mode!='monitor' or counts['raised_bins']==0,'monitor raised')
        require(mode!='candidate' or counts['raised_bins']==counts['would_raise_bins'],'candidate raised')
        nums={k:finite(row,k,0.0,1.0 if k in ('q_mean','floor_mean') else None) for k in POWER_FIELDS[9:]}
        require(nums['innovation_sum']<=nums['residual_sum']+1e-12*nums['residual_sum'],'innovation bound')
        require(nums['excess_sum']<=nums['innovation_sum']+1e-12*nums['innovation_sum'],'excess bound')
        if not valid:require(all(v==0.0 for v in nums.values()),'empty aggregate')
        power.append(dict(row))
    require(len(power)==frames,'power frame count')
    snapshots=snapshot_frames(frames);rows=0;selected=[];valid_in_snapshot=0
    for row in records(directory/'bins.csv',BIN_FIELDS):
        require(rows<len(snapshots)*257,'extra bin row')
        frame=snapshots[rows//257];k=rows%257
        require(integer(row,'frame',frames-1)==frame and integer(row,'bin',256)==k,'snapshot/bin sequence')
        p=power[frame]
        for name in ('far','dt','count_before'):require(row[name]==p[name],'snapshot state identity')
        valid=integer(row,'valid',1)
        valid_in_snapshot+=valid
        if valid:require(p['far']=='1' and p['dt']=='0' and p['count_before']=='10','snapshot valid state')
        for key in ('E','R','N','power','echo_power'):finite(row,key,0.0)
        for key in ('Cr','Ci','er','ei','rr','ri'):finite(row,key)
        for key in ('original_target','old_gain','floor','applied_target','res_gain'):finite(row,key,0.0,1.0)
        if not valid:require(float(row['floor'])==0.0,'invalid floor')
        if p['far']!='1' or p['dt']!='0':
            require(all(float(row[key])==0.0 for key in ('E','R','Cr','Ci','er','ei','echo_power','original_target','old_gain','floor','applied_target','res_gain')) and valid==0,'inactive snapshot')
        selected.append(dict(row));rows+=1
        if k==256:
            require(valid_in_snapshot==int(p['valid_bins']),'snapshot valid aggregate')
            valid_in_snapshot=0
    require(rows==len(snapshots)*257,'snapshot bin count')
    return dict(power=power,bins=selected,snapshot_frames=snapshots,bin_rows=rows)

def preflight():
    cases,locks=d42.preflight()
    for name,h in D42_HASHES.items():
        p=D42/name;require(sha(bounded(p,4*1024*1024))==h,'D42 identity');locks[str(p)]=h
    binding=read_json(D42/'binding.json')
    require(set(binding)>= {'locked_files','artifacts'},'D42 binding schema')
    for group in ('locked_files','artifacts'):
        for name,h in binding[group].items():
            p=D42/name if group=='artifacts' else Path(name)
            require(sha(bounded(p,4*1024*1024))==h,'D42 locked drift '+str(p));locks[str(p)]=h
    result=read_json(D42/'result.json')
    require(result.get('decision')=='NOISE_CONDITIONED_PROTECTION_DEVELOPMENT_REJECTED','D42 rejection identity')
    snapshot=Path('/tmp/audio-device-d42-review-snapshot.json')
    require(sha(bounded(snapshot,4*1024*1024))=='3faf06d95b908ea2debe20fb3048cfe06c8d4bf991a7c855dece1e50a144a892','historical D42 snapshot identity')
    locks[str(snapshot)]=sha(snapshot.read_bytes())
    for p,h in ((PLAN,'67cc799ccfc9d012694c717a1e96b66643d457be90840ecbb70b89b47b0288e1'),
        (AMEND,'cf9f9a8af23cddeee5c1d9f7909c55b2173d4a6355b536c89f4e800f6228a664'),
        (REVIEW,'e835035bd67edc6d4c55064719570cd2702bc3ebbe77a962a42ec9ffb4c268bb')):
        require(sha(bounded(p,4*1024*1024))==h,'frozen plan identity')
    for p in (PLAN,AMEND,REVIEW,C,NS,HEADER,TEST,Path(__file__).resolve()):
        locks[str(p)]=sha(bounded(p,4*1024*1024))
    return cases,locks

def size_budget(output):
    paths=[p for p in output.rglob('*') if p.is_file()]
    require(all(p.stat().st_size<=4*1024*1024 for p in paths),'artifact size budget')
    require(sum(p.stat().st_size for p in paths)<=1536*1024*1024,'root size budget')

def paired_traces(a,b):
    for key,excluded in (('power',{'raised_bins'}),('bins',{'old_gain','applied_target','res_gain'})):
        require(len(a[key])==len(b[key]),'mode diagnostic length')
        require(all({k:v for k,v in x.items() if k not in excluded}==
            {k:v for k,v in y.items() if k not in excluded} for x,y in zip(a[key],b[key])),
            'mode past-state diagnostic exact')

def repeat_future(output):
    for mode in ('monitor','candidate'):
        for arm in ('primary','selected'):
            original=output/(mode+'-'+arm+'-field-case-07-used0-shadow')
            for name in OUTPUTS:
                a=bounded(original/name,4*1024*1024)
                require(a==bounded(output/(mode+'-'+arm+'-repeat')/name,4*1024*1024),'repeat diagnostic exact')
                b=bounded(output/(mode+'-'+arm+'-future')/name,4*1024*1024)
                if name.endswith('.f32le'):equal=a[:1247*640]==b[:1247*640]
                elif name=='bins.csv':
                    select=lambda data:[line for line in data.splitlines()[1:] if int(line.split(b',',1)[0])<1247]
                    equal=a.splitlines()[0]==b.splitlines()[0] and select(a)==select(b)
                else:equal=a.splitlines()[:1248]==b.splitlines()[:1248]
                require(equal,'future prefix exact '+name)

def run(output):
    require(not output.exists() and not output.is_symlink() and Path('/tmp') in output.resolve().parents,'new /tmp root required')
    cases,locks=preflight()
    require(shutil.disk_usage('/tmp').free>=3*1024**3,'startup disk budget')
    previous={r['name']:r for r in read_json(D42/'result.json')['cases']}
    require(len(previous)==184,'D42 execution set')
    output.mkdir();completed=[];matrix_started=None
    try:
        flags=(d42.D18/'build/CMakeFiles/audio_pipeline.dir/flags.make').read_text()
        defs=[s.split('=',1)[1].split() for s in flags.splitlines() if s.startswith('C_DEFINES =')]
        require(len(defs)==1 and all(x.startswith('-DAP_BUILD_') for x in defs[0]),'original build defines')
        d42.logged(output,'compile',['rtk','cc',*d42.FLAGS,'-ffp-contract=off',*defs[0],'-I',str(d42.D18/'source/src'),'-I',str(d42.D18/'source/include'),'-I',str(d42.D18/'build/generated'),str(C),str(NS),str(d42.D18/'build/libaudio_pipeline.a'),'-lm','-lpthread','-o',str(output/'runner')],ROOT)
        d42.logged(output,'self-test',['rtk',str(output/'runner'),'--self-test'],ROOT)
        d42.logged(output,'invalid-argc',['rtk',str(output/'runner'),'invalid'],ROOT,expected=2)
        for label,frame_text,mode,bad_gate in [('frames','bad','monitor',False),('mode','1','bad',False),('gates','1','monitor',True)]:
            directory=output/('invalid-preserve-'+label);directory.mkdir()
            for name in OUTPUTS:(directory/name).write_bytes(b'D43_SENTINEL '+name.encode())
            source=d42.BASE/cases[0]['name']
            for name in ('residual','echo'):(directory/(name+'.f32le')).write_bytes(bounded(source/(name+'.f32le'),4*1024*1024)[:640])
            (directory/'gates.bin').write_bytes(bytes((2,0)) if bad_gate else bytes((0,0)))
            before={p.name:p.read_bytes() for p in directory.iterdir()}
            d42.logged(output,'invalid-preserve-'+label,['rtk',str(output/'runner'),str(directory/'residual.f32le'),str(directory/'echo.f32le'),str(directory/'gates.bin'),frame_text,str(directory),mode],ROOT,expected=4 if bad_gate else 2)
            require({p.name:p.read_bytes() for p in directory.iterdir()}==before,'seven-output sentinel preservation')
        matrix_started=time.monotonic()
        for case in cases:
            source=d42.BASE/case['name'];frames=case['execution_summary']['frames'];gates=d42.gate_bytes(source,frames)
            for arm in ('primary','selected'):
                pair=[]
                for mode in ('monitor','candidate'):
                    d42.matrix_budget(matrix_started)
                    name=mode+'-'+arm+'-'+case['name'];directory=output/name;directory.mkdir()
                    (directory/'gates.bin').write_bytes(gates);prefix='primary_' if arm=='primary' else ''
                    command=['rtk',str(output/'runner'),str(source/(prefix+'residual.f32le')),str(source/(prefix+'echo.f32le')),str(directory/'gates.bin'),str(frames),str(directory),mode]
                    summary=strict_json(d42.logged(output,name,command,ROOT).encode())
                    require(set(summary)==set(previous[name]['execution_summary'])|{'observer_state_bytes','measurement_scoped_bytes'},'summary schema')
                    original_summary={k:v for k,v in summary.items() if k not in ('observer_state_bytes','measurement_scoped_bytes')}
                    require(original_summary==previous[name]['execution_summary'],'D42 resource/call identity')
                    require(type(summary['observer_state_bytes']) is int and summary['observer_state_bytes']>0 and
                        summary['measurement_scoped_bytes']==summary['scoped_bytes']+summary['observer_state_bytes'] and
                        summary['measurement_scoped_bytes']<=65536 and summary['measurement_scoped_bytes']+71224<=131072,'measurement resource budget')
                    require(all(bounded(directory/n,4*1024*1024)==bounded(D42/name/n,4*1024*1024) for n in d42.OUTPUTS),'five D42 outputs byte exact')
                    observation=d42.observe(directory,case,arm,original_summary,mode)
                    require(observation==previous[name]['observation'],'D42 frozen measurement identity')
                    diagnostic=trace(directory,frames,mode,gates);pair.append(diagnostic)
                    completed.append(dict(name=name,source_case=case['name'],kind=case['kind'],future=case['future'],arm=arm,mode=mode,
                        execution_summary=summary,observation=observation,
                        diagnostic=dict(snapshot_frames=diagnostic['snapshot_frames'],bin_rows=diagnostic['bin_rows'],power_rows=len(diagnostic['power']))))
                    size_budget(output);d42.matrix_budget(matrix_started)
                    print('D43_CASE_PASS '+name,flush=True)
                paired_traces(*pair)
        repeat_future(output)
        require(len(completed)==184 and sum(r['execution_summary']['frames'] for r in completed)==505944,'matrix coverage')
        require(all(sha(bounded(Path(p),4*1024*1024))==h for p,h in locks.items()),'source/input end drift')
        size_budget(output);d42.matrix_budget(matrix_started)
        dump(output/'result.json',dict(experiment='FE_DEVICE_POWER_ATTRIBUTION_D43',executions=184,frames=505944,
            data_role='development-and-synthetic-engineering',decision=DECISION,measurement_only=True,
            promotion_allowed=False,shipping_approved=False,baseline_hashes=D42_HASHES,
            preserved_d42_development_admission=read_json(D42/'result.json')['development_admission'],
            cases=completed,matrix_elapsed_seconds=time.monotonic()-matrix_started))
        dump(output/'binding.json',dict(locked_files=locks,baseline_hashes=D42_HASHES,source_input_start_end_equal=True,
            runner_sha256=sha((output/'runner').read_bytes()),artifacts={str(p.relative_to(output)):sha(p.read_bytes()) for p in sorted(output.rglob('*')) if p.is_file()}))
        size_budget(output)
        print('D43_MEASUREMENT_PASS 184 actual diagnostic NO_PROMOTION',flush=True)
    except Exception as error:
        dump(output/'measurement-invalid.json',dict(decision='MEASUREMENT_INVALID_REPLAN',error=str(error),completed_executions=len(completed)))
        raise

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dry-run',action='store_true',help='Read and validate frozen inputs without writing or executing DSP')
    parser.add_argument('--output-root',type=Path,help='New /tmp root; execute only after independent implementation review')
    args=parser.parse_args()
    if not args.dry_run:
        require(args.output_root is not None,'output root required for execution')
        run(args.output_root);return 0
    cases,locks=preflight()
    print(json.dumps(dict(experiment='FE_DEVICE_POWER_ATTRIBUTION_D43',cases=len(cases),
        locked_files=len(locks),writes=False,dsp_executed=False,decision=DECISION,
        promotion_allowed=False,shipping_approved=False,formal_matrix_implemented=True)))
    return 0

if __name__=='__main__':
    try:raise SystemExit(main())
    except (ValueError,OSError,UnicodeError,KeyError,TypeError) as error:
        print(str(error),file=sys.stderr);raise SystemExit(2)
