"""D39 frozen saved AEC outputs -> CALL/FULL downstream; research only."""
from __future__ import annotations
import argparse
import csv
import io
import json
import math
from pathlib import Path
import struct
import subprocess
import sys
import time
if __package__ in (None, ''):
    sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from tools.codex_assets.device_capture import ROOT,bounded,require,sha,strict_json
from tools.codex_assets.device_exact_reference import dump,read_json
from tools.codex_assets.device_stages import D18,floats
from tools.codex_assets.device_return import rms_peak
from tools.codex_assets.device_replay import FLAGS

BASE=Path('/tmp/audio-fe-device-activity-d30-20261011')
HASHES={'result.json':'e0b74142093d4579615be9ffe047335b4618f46aa1116f0b24941bb921de470d','binding.json':'2558d74e0e8377087bcb1a44fc3e13d890c4da9b641b579db9d670e207083956'}
LIB_SHA='eb5b0c784c316e71d6ed9f58db6cb66f190b631daa00c55a94032168d5a47aa4'
PLAN=ROOT/'docs/research/frontend-evolution-v1/DEVICE_DOWNSTREAM_D39_PLAN.zh-CN.md'
AMEND=PLAN.with_name('DEVICE_DOWNSTREAM_D39_AMENDMENT.zh-CN.md')
C=ROOT/'tests/validation/frontend_evolution/device_downstream_d39.c'
TEST=C.with_name('test_device_downstream.py')
OUTPUTS=('bypass.f32le','ns.f32le','final.f32le','control.csv')
FIELDS=['frame','far','dt','frequency_active','speech_probability','noise_rms_dbfs','residual_gain','agc_allow','gain_before','gain_after','effective_gain','vad_probability','vad_active','vad_noise_rms','vad_hangover']
def logged(output,label,command,cwd,expected=0):
    receipt=output/('command-'+label+'.json');intent=output/('intent-'+label+'.json')
    require(not receipt.exists() and not intent.exists(),'existing command: reconcile, never replay')
    with intent.open('x') as f:
        json.dump(dict(command=command,cwd=str(cwd),requested_at_ns=time.time_ns()),f,indent=2)
    start=time.monotonic()
    try:
        r=subprocess.run(command,cwd=cwd,capture_output=True,text=True,timeout=120)
        value=dict(command=command,cwd=str(cwd),exit_code=r.returncode,stdout=r.stdout,stderr=r.stderr,elapsed_seconds=time.monotonic()-start,intent_sha256=sha(intent.read_bytes()))
    except (subprocess.TimeoutExpired,OSError) as error:
        decode=lambda v:v.decode(errors='replace') if isinstance(v,bytes) else v or ''
        value=dict(command=command,cwd=str(cwd),exit_code=None,error_type=type(error).__name__,stdout=decode(getattr(error,'stdout',None)),stderr=decode(getattr(error,'stderr',None)),elapsed_seconds=time.monotonic()-start,intent_sha256=sha(intent.read_bytes()))
        with receipt.open('x') as f:json.dump(value,f,indent=2)
        raise
    with receipt.open('x') as f:json.dump(value,f,indent=2)
    require(r.returncode==expected,'command failed '+label)
    return r.stdout
def f32(v):return struct.unpack('<f',struct.pack('<f',v))[0]
def encode(values):return struct.pack('<'+str(len(values))+'f',*values)
def aligned_range(a,b,n):
    require(0<=a<b<=n and n>=320,'window bounds')
    end=min(b,n-160)
    return None if a>=end else dict(input_range=[a,end],output_range=[a+160,end+160],tail_truncated_samples=b-end)
def gate_bytes(directory,frames):
    rows=list(csv.DictReader(io.StringIO(bounded(directory/'activity.csv',1024*1024).decode('ascii'))))
    require(len(rows)==frames,'gate count')
    result=[]
    for i,r in enumerate(rows):
        require(r['frame']==str(i) and r['far'] in ('0','1') and r['dt'] in ('0','1'),'gate identity')
        result.extend((int(r['far']),int(r['dt'])))
    return bytes(result)
def preflight():
    for name,h in HASHES.items():require(sha(bounded(BASE/name,4*1024*1024))==h,'D30 identity')
    binding=read_json(BASE/'binding.json');locks={str(BASE/n):h for n,h in HASHES.items()}
    for group in ('source_files','input_files','artifacts'):
        for name,h in binding[group].items():
            p=BASE/name if group=='artifacts' else Path(name)
            require(sha(bounded(p,4*1024*1024))==h,'D30 file drift '+str(p));locks[str(p)]=h
    require(sha(bounded(D18/'build/libaudio_pipeline.a',4*1024*1024))==LIB_SHA,'original library')
    d18_binding=D18/'binding.json'
    require(sha(bounded(d18_binding,4*1024*1024))=='ab41fbe3d970b11ff4a001cfdcf4bd2c2f1d6a4032c36a1da0511526943c2da2','D18 binding identity')
    locks[str(d18_binding)]=sha(d18_binding.read_bytes())
    for name,h in read_json(d18_binding)['artifacts'].items():
        if name.startswith('source/') or name.startswith('build/generated/') or name=='build/CMakeFiles/audio_pipeline.dir/flags.make':
            p=D18/name;require(sha(bounded(p,4*1024*1024))==h,'D18 source/header drift');locks[str(p)]=h
    for rel in ('src/core/ap_pipeline.c','src/enhance/ap_enhance.h','src/enhance/ap_ns.c','src/enhance/ap_agc.c','src/enhance/ap_vad.c','src/enhance/ap_res.c','src/enhance/ap_noise_tracker.c','src/enhance/ap_window.c'):
        p=D18/'source'/rel;locks[str(p)]=sha(bounded(p,4*1024*1024))
    for p in (PLAN,AMEND,C,TEST,Path(__file__).resolve(),D18/'build/CMakeFiles/audio_pipeline.dir/flags.make',D18/'build/libaudio_pipeline.a',ROOT/'tools/codex_assets/device_return.py',ROOT/'tools/codex_assets/device_stages.py',ROOT/'tools/codex_assets/device_capture.py',ROOT/'tools/codex_assets/device_exact_reference.py',ROOT/'tools/codex_assets/device_replay.py'):
        locks[str(p)]=sha(bounded(p,4*1024*1024))
    result=read_json(BASE/'result.json');cases=result['cases']
    require(result['data_role']=='development-and-synthetic-engineering' and len(cases)==46 and len({c['name'] for c in cases})==46,'D30 case set/data role')
    for case in cases:
        d=BASE/case['name'];n=case['execution_summary']['frames']*160
        require(n>=320 and n<=1600000,'sample budget');gate_bytes(d,n//160)
        for name in ('echo','residual','primary_echo','primary_residual'):floats(d/(name+'.f32le'),n)
        if case['kind']=='return' and not case['future']:
            p=Path(case['source_directory'])/'near.f32le';floats(p,n);locks[str(p)]=sha(bounded(p,4*1024*1024))
    return cases,locks
def observe(directory,case,arm,summary):
    source=BASE/case['name'];n=case['execution_summary']['samples'];frames=n//160
    residual=source/(('primary_' if arm=='primary' else '')+'residual.f32le')
    require((directory/'bypass.f32le').read_bytes()==bounded(residual,4*1024*1024),'bypass exact')
    require(all(type(v) is int for v in summary.values()),'integer actual summary')
    expected=dict(frames=frames,samples=n,ns_calls=frames,agc_calls=frames,vad_calls=frames,res_calls=0,aec_calls=0)
    require(all(summary[k]==v for k,v in expected.items()) and set(summary)==set(expected)|{'ns_state_bytes','agc_state_bytes','vad_state_bytes','frame_buffer_bytes','scoped_bytes'},'actual counts')
    require(summary['frame_buffer_bytes']==2560 and summary['agc_state_bytes']==12 and summary['vad_state_bytes']==8 and
        summary['scoped_bytes']==sum(summary[k] for k in ('ns_state_bytes','agc_state_bytes','vad_state_bytes','frame_buffer_bytes')) and
        summary['ns_state_bytes']>0 and summary['scoped_bytes']<=65536 and 71224+summary['scoped_bytes']<=131072,'scoped resource contract')
    reader=csv.DictReader(io.StringIO(bounded(directory/'control.csv',2*1024*1024).decode('ascii')))
    require(reader.fieldnames==FIELDS,'control schema');rows=list(reader);require(len(rows)==frames,'control count')
    gates=gate_bytes(source,frames);signals={name:floats(directory/(name+'.f32le'),n) for name in ('bypass','ns','final')}
    limit=f32(10**(-2/20));active=0;frequency=0
    for i,r in enumerate(rows):
        require(all(math.isfinite(float(v)) for v in r.values()),'finite control')
        far,dt=gates[2*i:2*i+2];allow=int(not(far and not dt));freq=int(far and not dt)
        require([r[k] for k in ('frame','far','dt','frequency_active','agc_allow')]==list(map(str,(i,far,dt,freq,allow))),'gate and branch')
        for k in ('speech_probability','residual_gain','vad_probability'):require(0<=float(r[k])<=1,'probability/gain range')
        require(r['vad_active'] in ('0','1') and 0<=int(r['vad_hangover'])<=8 and float(r['vad_noise_rms'])>0,'VAD state range')
        gain=f32(float(r['effective_gain']));require(gain>=0 and (allow or gain<=1),'effective controlled gain')
        a,b=i*160,(i+1)*160
        expected_values=[max(-limit,min(limit,f32(v*gain))) for v in signals['ns'][a:b]]
        require(encode(expected_values)==encode(signals['final'][a:b]),'effective gain/limiter output')
        active+=int(r['vad_active']);frequency+=freq
    measured=None
    if not case['future']:
        near=floats(Path(case['source_directory'])/'near.f32le',n) if case['kind']=='return' else None
        old=case['observation']['measurement'];windows=[]
        for w in [old['whole'],*old['windows']]:
            a,b=w['sample_range'];coords=aligned_range(a,b,n);item=dict(original_sample_range=[a,b],alignment=coords,stages=None)
            if coords:
                ia,ib=coords['input_range'];oa,ob=coords['output_range'];stages={}
                for stage in ('bypass','ns','final'):
                    values=signals[stage][ia:ib] if stage=='bypass' else signals[stage][oa:ob]
                    metric=dict(signal=rms_peak(values),known_near_error=None)
                    if near is not None:metric['known_near_error']=rms_peak([v-q for v,q in zip(values,near[ia:ib])])
                    stages[stage]=metric
                item['stages']=stages
            windows.append(item)
        measured=dict(whole=windows[0],windows=windows[1:],alignment_samples=160,no_tail_flush=True)
    return dict(vad_active_frames=active,frequency_res_frames=frequency,measurement=measured)
def run(output):
    require(not output.exists() and not output.is_symlink() and Path('/tmp') in output.resolve().parents,'new /tmp root required')
    cases,locks=preflight();output.mkdir()
    try:
        flags=(D18/'build/CMakeFiles/audio_pipeline.dir/flags.make').read_text()
        defs=[s.split('=',1)[1].split() for s in flags.splitlines() if s.startswith('C_DEFINES =')]
        require(len(defs)==1 and all(x.startswith('-DAP_BUILD_') for x in defs[0]),'original build defines')
        logged(output,'compile',['cc',*FLAGS,'-ffp-contract=off',*defs[0],'-I',str(D18/'source/src'),'-I',str(D18/'source/include'),'-I',str(D18/'build/generated'),str(C),str(D18/'build/libaudio_pipeline.a'),'-lm','-lpthread','-o',str(output/'runner')],ROOT)
        logged(output,'self-test',[str(output/'runner'),'--self-test'],ROOT)
        logged(output,'invalid-argc',[str(output/'runner'),'invalid'],ROOT,expected=2)
        for label,frame_text,mode,bad_gate in [('frames','bad','full',False),('mode','1','bad',False),('gates','1','full',True)]:
            d=output/('invalid-preserve-'+label);d.mkdir()
            sentinels={name:b'D39_SENTINEL '+name.encode() for name in OUTPUTS}
            for name,data in sentinels.items():(d/name).write_bytes(data)
            residual=BASE/cases[0]['name']/'residual.f32le';echo=BASE/cases[0]['name']/'echo.f32le'
            (d/'input.f32le').write_bytes(residual.read_bytes()[:640]);(d/'echo.f32le').write_bytes(echo.read_bytes()[:640]);(d/'gates.bin').write_bytes(bytes((2,0)) if bad_gate else bytes((0,0)))
            before={p.name:p.read_bytes() for p in d.iterdir()}
            logged(output,'invalid-preserve-'+label,[str(output/'runner'),str(d/'input.f32le'),str(d/'echo.f32le'),str(d/'gates.bin'),frame_text,str(d),mode],ROOT,expected=4 if bad_gate else 2)
            require({p.name:p.read_bytes() for p in d.iterdir()}==before,'invalid sentinel preservation')
        records=[];matrix_started=time.monotonic()
        for case in cases:
            require(time.monotonic()-matrix_started<=1800,'matrix time budget')
            source=BASE/case['name'];frames=case['execution_summary']['frames']
            for arm in ('primary','selected'):
                name=arm+'-'+case['name'];d=output/name;d.mkdir();(d/'gates.bin').write_bytes(gate_bytes(source,frames))
                prefix='primary_' if arm=='primary' else ''
                command=[str(output/'runner'),str(source/(prefix+'residual.f32le')),str(source/(prefix+'echo.f32le')),str(d/'gates.bin'),str(frames),str(d),'full']
                summary=strict_json(logged(output,name,command,ROOT).encode());observation=observe(d,case,arm,summary)
                records.append(dict(name=name,source_case=case['name'],kind=case['kind'],future=case['future'],arm=arm,execution_summary=summary,observation=observation));print('D39_CASE_PASS '+name,flush=True)
        for arm in ('primary','selected'):
            original=output/(arm+'-field-case-07-used0-shadow')
            for name in OUTPUTS:
                a=(original/name).read_bytes();require(a==(output/(arm+'-repeat')/name).read_bytes(),'repeat exact')
                b=(output/(arm+'-future')/name).read_bytes()
                require(a[:1247*640]==b[:1247*640] if name.endswith('.f32le') else a.splitlines()[:1248]==b.splitlines()[:1248],'future prefix exact')
        require(all(sha(bounded(Path(p),4*1024*1024))==h for p,h in locks.items()),'source/input end drift')
        dump(output/'result.json',dict(experiment='FE_DEVICE_DOWNSTREAM_D39',executions=92,data_role='development-and-synthetic-engineering',decision='DOWNSTREAM_INTEGRATION_DIAGNOSTIC_NO_PROMOTION',integration_changed=True,shipping_algorithm_changed=False,promotion_allowed=False,shipping_approved=False,cases=records))
        dump(output/'binding.json',dict(locked_files=locks,baseline_hashes=HASHES,library_sha256=LIB_SHA,source_input_start_end_equal=True,runner_sha256=sha((output/'runner').read_bytes()),artifacts={str(p.relative_to(output)):sha(p.read_bytes()) for p in sorted(output.rglob('*')) if p.is_file()}))
        print('D39_MEASUREMENT_PASS 92 actual downstream NO_PROMOTION',flush=True)
    except Exception as error:
        dump(output/'measurement-invalid.json',dict(decision='MEASUREMENT_INVALID',error=str(error)));raise
def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output-root',type=Path,required=True);parser.add_argument('--dry-run',action='store_true');args=parser.parse_args(argv)
    try:
        if args.dry_run:cases,locks=preflight();print('D39_PREFLIGHT_PASS',len(cases),'cases',len(locks),'locks writes=False')
        else:run(args.output_root)
        return 0
    except (ValueError,OSError,KeyError,TypeError,OverflowError,subprocess.TimeoutExpired) as error:
        print('device_downstream: '+str(error),file=sys.stderr);return 2
if __name__=='__main__':raise SystemExit(main())
