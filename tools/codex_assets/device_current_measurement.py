"""D48 measurement contract repair; frozen D47 algorithm is unchanged.

The old D42 monotone floor property is reported as historical diagnostics.
All waveform scoring, control validation and six-state projections remain.
Measurement verification never grants algorithm promotion or shipping authority.
"""
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
if __package__ in (None,''):
    sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from tools.codex_assets.device_capture import ROOT,sha,strict_json
from tools.codex_assets.device_exact_reference import dump
from tools.codex_assets import device_current_innovation as d47
from tools.codex_assets import device_noise_conditioned_protection as d42
from tools.codex_assets.device_noise_conditioned_protection import (
    BASE,D39,D41,FIELDS,ORIGINAL_OUTPUTS,f32,encode,floats,aligned_range,
    rms_peak,gate_bytes,read_json,bounded,require,
)

FROZEN_OBSERVE_SOURCE_SHA256='a6c5b230836bd2e9cd2a14562b7eeffed4abb3c849318a0540364f325239001e'
COMMON_OBSERVATION_FIELDS=frozenset(('vad_active_frames','frequency_res_frames',
    'measurement','baseline_differences','ordinary_ns_statistics_exact',
    'inactive_baseline_control'))
PLAN=ROOT/'docs/research/frontend-evolution-v1/DEVICE_CURRENT_MEASUREMENT_D48_PLAN.zh-CN.md'
REVIEW=PLAN.with_name('DEVICE_CURRENT_MEASUREMENT_D48_PLAN_REVIEW.zh-CN.md')
TEST=ROOT/'tests/validation/frontend_evolution/test_device_current_measurement.py'
C=d47.C;NS=d47.NS;HEADER=d47.HEADER;D45=d47.D45
OUTPUTS=d47.OUTPUTS;D45_HASHES=d47.D45_HASHES

FROZEN_D47_SOURCES={
    C:'ca1ba081b344e6554473328510fbaf15c56d9b2657dee06b9ce9b5d7f328b733',
    NS:'8dd2db9027d972aac3f6ea7f75a8bbd84c9e8c2eef6b0ab09b24aa9f7234916a',
    HEADER:'28c0520df7a9c3932fff32e0c9a8f4a0bb6eba08bdbcecd404f05103ae031d59',
    Path(d47.__file__).resolve():'71b5e2eb0cd0626179b1b459bb02977913f43b11dcd4ba293fff9908af72cd44',
    d47.TEST:'cb76c720e43fc8503e3c961ee91b5d29ea8e296ef789847f5aecab11198b788b',
}

def common_observation(value):
    """Project only the explicitly declared shared contract, reject field drift."""
    extra=set(value)-COMMON_OBSERVATION_FIELDS
    require(extra in ({'noise_conditioned_floor_monotone'},
                       {'historical_floor_diagnostic'}),'observation diagnostic schema')
    require(COMMON_OBSERVATION_FIELDS<=set(value),'missing common observation field')
    return {key:value[key] for key in sorted(COMMON_OBSERVATION_FIELDS)}

def observe(directory,case,arm,summary,mode):
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
    baseline=next(c for c in read_json(D39/'result.json')['cases'] if c['name']==arm+'-'+case['name'])
    baseline_directory=D39/(arm+'-'+case['name'])
    baseline_rows=list(csv.DictReader(io.StringIO(bounded(baseline_directory/'control.csv',2*1024*1024).decode('ascii'))))
    require(len(baseline_rows)==frames,'D39 baseline control count')
    require((directory/'bypass.f32le').read_bytes()==(baseline_directory/'bypass.f32le').read_bytes(),'D39 bypass exact')
    gates=gate_bytes(source,frames);signals={name:floats(directory/(name+'.f32le'),n) for name in ('bypass','ns','final')}
    limit=f32(10**(-2/20));active=0;frequency=0
    for i,r in enumerate(rows):
        require(all(math.isfinite(float(v)) for v in r.values()),'finite control')
        far,dt=gates[2*i:2*i+2];allow=int(not(far and not dt));freq=1-allow
        require([r[k] for k in ('frame','far','dt','frequency_active','agc_allow')]==list(map(str,(i,far,dt,freq,allow))),'gate and branch')
        for k in ('speech_probability','residual_gain','vad_probability'):require(0<=float(r[k])<=1,'probability/gain range')
        require(r['vad_active'] in ('0','1') and 0<=int(r['vad_hangover'])<=8 and float(r['vad_noise_rms'])>0,'VAD state range')
        require(all(r[k]==baseline_rows[i][k] for k in ('frame','far','dt','agc_allow')),'D39 gate/allow exact')
        require(all(f32(float(r[k]))==f32(float(baseline_rows[i][k])) for k in ('speech_probability','noise_rms_dbfs')),'D39 ordinary NS statistics exact')
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
    differences=None
    if measured is not None:
        old=baseline['observation']['measurement'];differences=[]
        for w,b in zip([measured['whole'],*measured['windows']],[old['whole'],*old['windows']]):
            require(w['original_sample_range']==b['original_sample_range'] and w['alignment']==b['alignment'],'D39 measurement coordinates')
            delta=None
            if w['stages'] is not None:
                require(w['stages']['bypass']==b['stages']['bypass'],'D39 aligned bypass statistics')
                delta={}
                for stage in ('bypass','ns','final'):
                    x=w['stages'][stage];y=b['stages'][stage]
                    delta[stage]=dict(signal_rms_db_delta=x['signal']['rms_dbfs']-y['signal']['rms_dbfs'],
                        known_near_error_rms_db_delta=None if x['known_near_error'] is None else x['known_near_error']['rms_dbfs']-y['known_near_error']['rms_dbfs'])
            differences.append(dict(original_sample_range=w['original_sample_range'],alignment=w['alignment'],stages=delta))
        require(len(measured['windows'])==len(old['windows']),'D39 fixed window count')
    inactive_control=case['kind']=='field' and baseline['observation']['frequency_res_frames']==0
    if inactive_control:
        require(all((directory/name).read_bytes()==(baseline_directory/name).read_bytes() for name in ORIGINAL_OUTPUTS),'D39 inactive full-case byte exact')
    if mode=='monitor':
        require(all((directory/name).read_bytes()==(baseline_directory/name).read_bytes() for name in ORIGINAL_OUTPUTS),'monitor D39 all outputs exact')
    guard_rows=list(csv.DictReader(io.StringIO((directory/'protection.csv').read_text())))
    require(len(guard_rows)==frames,'protection count')
    d41_directory=D41/(mode+'-'+arm+'-'+case['name'])
    d41_guard_rows=list(csv.DictReader(io.StringIO((d41_directory/'protection.csv').read_text())))
    require(len(d41_guard_rows)==frames,'D41 protection count')
    if mode=='monitor':
        require(all((directory/name).read_bytes()==(d41_directory/name).read_bytes() for name in ORIGINAL_OUTPUTS),'monitor D41 outputs exact')
    count=0;historical_monotone=True;historical_above_frames=0;historical_max_excess=0.0
    for i,r in enumerate(guard_rows):
        far,dt=gates[2*i:2*i+2];freq=int(far and not dt);after=min(10,count+1) if freq else 0
        require([r[k] for k in ('frame','far','dt','count_before','count_after')]==list(map(str,(i,far,dt,count,after))),'protection causal count')
        valid=int(r['valid_bins']);raised=int(r['raised_bins']);mean=float(r['floor_mean'])
        require(0<=raised<=valid<=257 and math.isfinite(mean) and 0<=mean<=1,'protection bounds')
        require((freq and count>=10) or (valid==0 and raised==0 and mean==0),'protection warmup/inactive')
        require(mode!='monitor' or raised==0,'monitor no target change')
        previous=d41_guard_rows[i]
        require(all(r[k]==previous[k] for k in ('frame','far','dt','count_before','count_after','valid_bins')),'D41 protection state identity')
        excess=mean-float(previous['floor_mean'])
        historical_monotone=historical_monotone and excess<=0.0
        historical_above_frames+=int(excess>0.0)
        historical_max_excess=max(historical_max_excess,excess)
        count=after
    return dict(historical_floor_diagnostic=dict(reference='D41',monotone=historical_monotone,above_frames=historical_above_frames,max_mean_excess=historical_max_excess),vad_active_frames=active,frequency_res_frames=frequency,measurement=measured,baseline_differences=differences,
        ordinary_ns_statistics_exact=True,inactive_baseline_control=inactive_control)

def preflight():
    """Preserve the full frozen D47 domain; add exact D48 phase identities."""
    for p,h in FROZEN_D47_SOURCES.items():
        require(sha(bounded(p,4*1024*1024))==h,'frozen D47 algorithm/helper source')
    cases,locks=d47.preflight()
    require(len(locks)==11727,'complete original D47 input domain')
    pins={
        PLAN:'6c751db7cd1832e5aa0db958011f23c8ff5ca3bf4fb56ad0a102bc2ab51724ca',
        REVIEW:'9f8e05a570551a0df39d5353c51a585ae0215792c463441c1ad0b23401d93086',
        PLAN.with_name('DEVICE_CURRENT_MEASUREMENT_D48_HANDOFF.zh-CN.md'):'2e30b3c173d8edf3509147987556a289a81390a9a8e99eeabc0168c7692c4b01',
        PLAN.with_name('DEVICE_CURRENT_INNOVATION_D47_RESULT.zh-CN.md'):'d5fffe95a58f65121053f7117aa65a5ee116e7a49b42770e4b0b47d8fe4a7ccc',
        PLAN.with_name('DEVICE_CURRENT_INNOVATION_D47_REVIEW.zh-CN.md'):'c0707a4ddeeddf9e79033ef71e118b9478f1f56620e2b9f35bd8d649f63d950f',
        PLAN.with_name('DEVICE_CURRENT_INNOVATION_D47_CLOSEOUT.zh-CN.md'):'879b90205a1fc8cf5bee916dfa6ebac0196eb987933503b931431e6ba0adedff',
        Path('/tmp/audio-device-d47-invalid-snapshot-v1.json'):'361463948e6ac2fd872c6040c49d2ae0018da6f6e4a729229016de5f6aad7200',
        Path('/tmp/audio-device-d48-parity-v1.py'):'99ba0f4198fcc6e124acbeb645273d8e6fd9c8c5d49fd30cd15893719a60071a',
        Path('/tmp/audio-device-d48-parity-v1-intent.json'):'225ba240efb588b1cda1af5a204125acf1641047cdb4370e52ea9c48ef1adffc',
        Path('/tmp/audio-device-d48-parity-v1.json'):'902ec0a5fc66a47c186e253d7846f8f45035b982c22b9a94d595ddf27e7355f6',
        Path('/tmp/audio-device-d48-negative-v1.py'):'7f0d454d804ce01d1c1cd35925172e60f81f523514cd476d8a267ec44bfdab9e',
        Path('/tmp/audio-device-d48-negative-v1-intent.json'):'333355d9551b295a9df0977a9fe2600fdc5860bdaed89eae434cb9bde98050e5',
        Path('/tmp/audio-device-d48-negative-v1.json'):'436216ea12a2a62c11ac2bf66de59d15f6b54137fb1247fcae5ba7173b457ce7',
        Path('/tmp/audio-device-d48-observe-draft-v1-source.py'):'aaa135292a42de9818938007f3575661d47535cb62cb71d0b73de8b449d8c18f',
        Path('/tmp/audio-device-d48-observe-draft-v1-test.py'):'9e7763f1984fe9c800746faa2032ab8b543218688f2325a295139d998168561a',
    }
    require(locks[str(Path(d42.__file__).resolve())]==FROZEN_OBSERVE_SOURCE_SHA256,
            'old observe/development admission identity')
    for p,h in pins.items():
        require(str(p) not in locks or locks[str(p)]==h,'conflicting D48 phase SHA')
        require(sha(bounded(p,4*1024*1024))==h,'D48 phase input drift')
        locks[str(p)]=h
    for p in (Path(__file__).resolve(),TEST):
        h=sha(bounded(p,4*1024*1024))
        require(str(p) not in locks or locks[str(p)]==h,'conflicting new source SHA')
        locks[str(p)]=h
    return cases,locks

def run(output):
    require(output.is_absolute() and output==Path('/tmp/audio-fe-device-current-measurement-d48-20261013') and
        not output.exists() and not any(p.is_symlink() for p in (output,)+tuple(output.parents)) and
        output.absolute()==output.resolve(),'fixed new direct /tmp root required')
    cases,locks=preflight()
    require(shutil.disk_usage('/tmp').free>=3*1024**3,'startup disk budget')
    previous={r['name']:r for r in read_json(D45/'result.json')['cases']}
    require(len(previous)==184,'D45 execution set')
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
            for name in OUTPUTS:(directory/name).write_bytes(b'D45_SENTINEL '+name.encode())
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
                    require(set(summary)==set(previous[name]['execution_summary']),'summary schema')
                    original_summary={k:v for k,v in summary.items() if k not in ('observer_state_bytes','measurement_scoped_bytes')}
                    require(original_summary=={k:v for k,v in previous[name]['execution_summary'].items() if k not in ('observer_state_bytes','measurement_scoped_bytes')},'D45 algorithm resource/call identity')
                    require(type(summary['observer_state_bytes']) is int and summary['observer_state_bytes']>0 and
                        summary['measurement_scoped_bytes']==summary['scoped_bytes']+summary['observer_state_bytes'] and
                        summary['measurement_scoped_bytes']<=65536 and summary['measurement_scoped_bytes']+71224<=131072,'measurement resource budget')
                    d47.baseline_outputs(directory,D45/name,mode)
                    observation=observe(directory,case,arm,original_summary,mode)
                    if mode=='monitor':require(common_observation(observation)==common_observation(previous[name]['observation']),'monitor frozen common measurement identity')
                    diagnostic=d47.trace(directory,frames,mode,gates)
                    d47.baseline_trace(diagnostic,d47.d45.trace(D45/('monitor-'+arm+'-'+case['name']),frames,'monitor',gates));pair.append(diagnostic)
                    completed.append(dict(name=name,source_case=case['name'],kind=case['kind'],future=case['future'],arm=arm,mode=mode,
                        execution_summary=summary,observation=observation,
                        diagnostic=dict(snapshot_frames=diagnostic['snapshot_frames'],bin_rows=diagnostic['bin_rows'],power_rows=len(diagnostic['power']))))
                    d47.size_budget(output);d42.matrix_budget(matrix_started)
                    print('D48_CASE_PASS '+name,flush=True)
                d47.paired_traces(*pair)
                d47.paired_controls(output/('monitor-'+arm+'-'+case['name']),output/('candidate-'+arm+'-'+case['name']))
        d47.repeat_future(output)
        require(len(completed)==184 and sum(r['execution_summary']['frames'] for r in completed)==505944,'matrix coverage')
        require(all(sha(bounded(Path(p),4*1024*1024))==h for p,h in locks.items()),'source/input end drift')
        d47.size_budget(output);d42.matrix_budget(matrix_started)
        admission=d42.development_admission(completed,cases)
        decision='MEASUREMENT_CONTRACT_VERIFIED_NO_PROMOTION'
        dump(output/'result.json',dict(experiment='FE_DEVICE_CURRENT_MEASUREMENT_D48',executions=184,frames=505944,
            data_role='development-and-synthetic-engineering',decision=decision,measurement_only=True,
            promotion_allowed=False,shipping_approved=False,baseline_hashes=D45_HASHES,
            development_admission=admission,algorithm_basis='FE_DEVICE_CURRENT_INNOVATION_D47',frequency_enabled=1,integration_changed=False,shipping_algorithm_changed=False,
            cases=completed,matrix_elapsed_seconds=time.monotonic()-matrix_started))
        dump(output/'binding.json',dict(locked_files=locks,baseline_hashes=D45_HASHES,source_input_start_end_equal=True,
            runner_sha256=sha((output/'runner').read_bytes()),artifacts={str(p.relative_to(output)):sha(p.read_bytes()) for p in sorted(output.rglob('*')) if p.is_file()}))
        d47.size_budget(output)
        print('D48_MEASUREMENT_PASS 184 '+decision+' NO_PROMOTION',flush=True)
    except Exception as error:
        dump(output/'measurement-invalid.json',dict(decision='MEASUREMENT_INVALID_REPLAN',error=str(error),completed_executions=len(completed)))
        raise

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    mode=parser.add_mutually_exclusive_group()
    mode.add_argument('--dry-run',action='store_true',help='Complete read-only frozen preflight; no DSP')
    mode.add_argument('--run',action='store_true',help='Explicit independently reviewed formal measurement')
    parser.add_argument('--output-root',type=Path,help='Fixed new D48 /tmp root')
    args=parser.parse_args()
    if args.run:
        require(args.output_root is not None,'output root required')
        run(args.output_root);return 0
    require(args.output_root is None,'output root requires explicit --run')
    cases,locks=preflight()
    print(json.dumps(dict(experiment='FE_DEVICE_CURRENT_MEASUREMENT_D48',cases=len(cases),
        locked_files=len(locks),writes=False,dsp_executed=False,measurement_only=True,
        promotion_allowed=False,shipping_approved=False,formal_matrix_implemented=True)))
    return 0
if __name__=='__main__':
    try:raise SystemExit(main())
    except (ValueError,OSError,UnicodeError,KeyError,TypeError) as error:
        print(str(error),file=sys.stderr);raise SystemExit(2)
