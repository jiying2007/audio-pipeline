"""D26 field-development AEC replay with frozen gates and first rejected alert."""
from __future__ import annotations
import argparse
import csv
import io
import math
from pathlib import Path
import subprocess
import sys
if __package__ in (None,''):
    sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from tools.codex_assets.device_capture import ROOT,bounded,require,sha,strict_json,summary
from tools.codex_assets.device_exact_reference import dump,logged,read_json,preflight as intake_preflight
from tools.codex_assets.device_replay import FLAGS,metric_rows,window
from tools.codex_assets.device_stages import D18,D16,energy
from tools.codex_assets.device_timing import BASE as D19,preflight as d19_preflight,controls
from tools.codex_assets.device_return import preflight as d25_preflight
from tools.codex_assets.device_path import FIELDS as STATE_FIELDS
from tools.codex_assets.device_shadow import step
from tools.codex_assets.device_stages import floats

BASE=Path('/tmp/audio-fe-device-return-d25-20261011')
HASHES={'result.json':'5ceae16bc4e9587e669aac90c9f8fa8be55a60077b98733606190e7ea2a466d6',
        'binding.json':'d5b5e273b311bb38d91d3a68b16986a12f6c548af83d721ded774b6a2e6f626e'}
D16_FINAL='5d273d10dd9b63ab5fabd9da43d5bd55e52165ab725e5d6bf5a0b99963af815a'
PLAN=ROOT/'docs/research/frontend-evolution-v1/DEVICE_FIELD_D26_PLAN.zh-CN.md'
AMEND=ROOT/'docs/research/frontend-evolution-v1/DEVICE_FIELD_D26_AMENDMENT.zh-CN.md'
RUNNER=ROOT/'tests/validation/frontend_evolution/device_field_d26.c'
SELECTOR=ROOT/'tests/validation/frontend_evolution/device_shadow_selector_d24.h'
TEST=ROOT/'tests/validation/frontend_evolution/test_device_field.py'
TRACES=('echo','residual','primary_echo','primary_residual','shadow_echo','shadow_residual')
SELECT_FIELDS=['frame','active','far','dt','bank','streak','change','primary_energy','shadow_energy']


def alert_frames(rows):
    events=[]; previous=0; jumps=0
    for i,row in enumerate(rows):
        r,j=row['aec_resets'],row['delay_jumps']
        require(r-previous in (0,1) and j-jumps==r-previous,'counter event contract')
        if r>previous: events.append(i)
        previous,jumps=r,j
    return events


def preflight(root):
    d25_preflight(root)
    for name,expected in HASHES.items():require(sha(bounded(BASE/name,4*1024*1024))==expected,'D25 drift')
    old=read_json(BASE/'binding.json')
    for name,expected in old['source_files'].items():require(sha(bounded(Path(name),4*1024*1024))==expected,'D25 source drift')
    for name,expected in old['artifacts'].items():require(sha(bounded(BASE/name,4*1024*1024))==expected,'D25 artifact drift')
    captures=d19_preflight(root)
    p,again,_,_=intake_preflight(root,D16)
    require([c['case_id'] for c in captures]==[c['case_id'] for c in again],'case order')
    require(sha(bounded(D16/'final-binding.json',4*1024*1024))==D16_FINAL,'D16 final binding drift')
    old16=read_json(D16/'final-binding.json'); schedules=[]
    for i,c in enumerate(captures):
        rel='replay/case-'+str(i+1).zfill(2)+'/default.jsonl'
        require(sha(bounded(D16/rel,4*1024*1024))==old16['artifacts'][rel],'D16 alert source drift')
        events=alert_frames(metric_rows(D16/rel,summary(c)['replay_samples']))
        schedules.append(dict(case_id=c['case_id'],source=str(D16/rel),source_sha256=sha((D16/rel).read_bytes()),
                              all_event_frames=events,notify_frame=events[0] if events else None))
    return p,captures,schedules


def source_inputs(index,mode,n):
    directory=D19/('case-'+str(index+1).zfill(2)); stage=directory/mode
    mic_path=stage/'aec_input.f32le'; ref_path=directory/(mode+'.reference.f32le'); gate_path=stage/'control.csv'
    gates=controls(gate_path,metric_rows(directory/(mode+'.jsonl'),n))
    return mic_path,ref_path,gates,{str(p):sha(bounded(p,4*1024*1024)) for p in (mic_path,ref_path,gate_path,directory/(mode+'.jsonl'))}


def measure_window(values,first,last,notify,policy):
    result=dict(sample_range=[first,last],samples=last-first,channels={})
    for bank in ('selected','primary','shadow'):
        if bank=='shadow' and (policy!='shadow' or notify is None or first<notify*160):
            result['channels'][bank]=None;continue
        prefix='' if bank=='selected' else bank+'_'
        result['channels'][bank]={name:energy(values[prefix+name],first,last) for name in ('echo','residual')}
    return result


def read_state(path,frames):
    reader=csv.DictReader(io.StringIO(bounded(path,1024*1024).decode('ascii')))
    require(reader.fieldnames==STATE_FIELDS,'state schema');states=list(reader);require(len(states)==frames,'state count')
    for i,row in enumerate(states):
        require(row['frame']==str(i) and all(math.isfinite(float(v)) for v in row.values()) and row['runtime_stride']=='2' and row['adapt_phase'] in ('0','1') and
                0<=int(row['constrain_partition'])<48 and 0<=int(row['x_head'])<48 and 0<=int(row['steady_frames'])<=50 and
                float(row['x_power_total'])>=0 and float(row['weight_l2'])>=0,'state range')
    return states


def observe(directory,mic_path,ref_path,gates,n,notify,policy,future,c,p,execution):
    expected=dict(frames=n//160,samples=n,primary_calls=n//160,shadow_calls=n//160-notify if policy=='shadow' and notify is not None else 0,
                  shadow_reset_calls=int(policy=='shadow' and notify is not None),sync_calls=0)
    require(set(execution)==set(expected)|{'switch_count','state_bytes'} and all(type(v) is int for v in execution.values()) and
            all(execution[k]==v for k,v in expected.items()) and execution['state_bytes']>0,'execution summary')
    values={name:floats(directory/(name+'.f32le'),n) for name in TRACES}
    mic=floats(mic_path,n)
    if future:
        for i in range(notify*160,n):mic[i]=-mic[i]
    first=notify*160 if policy=='shadow' and notify is not None else n
    require(not any(values['shadow_echo'][:first]) and not any(values['shadow_residual'][:first]),'inactive shadow zeros')
    arithmetic={}
    for bank in ('selected','primary','shadow'):
        if bank=='shadow' and first==n:continue
        prefix='' if bank=='selected' else bank+'_';start=first if bank=='shadow' else 0
        arithmetic[bank]=max(abs(a-b-r) for a,b,r in zip(mic[start:],values[prefix+'echo'][start:],values[prefix+'residual'][start:]))
        require(arithmetic[bank]<=1e-6,'AEC identity')
    read_state(directory/'state.csv',n//160)
    reader=csv.DictReader(io.StringIO(bounded(directory/'selector.csv',1024*1024).decode('ascii')))
    require(reader.fieldnames==SELECT_FIELDS,'selector schema');rows=list(reader);require(len(rows)==n//160,'selector count')
    data={name:bounded(directory/(name+'.f32le'),4*1024*1024) for name in TRACES};bank,streak=0,0;events=[]
    for frame,row in enumerate(rows):
        a,b=frame*160,(frame+1)*160;far,dt=gates[frame]['far'],gates[frame]['dt'];old=bank
        active=policy=='shadow' and notify is not None and frame>=notify
        pe=sum(v*v for v in values['primary_residual'][a:b]);se=sum(v*v for v in values['shadow_residual'][a:b])
        bank,streak,change=step(bank,streak,active,bool(far and not dt),pe,se)
        require([row[k] for k in SELECT_FIELDS[:7]]==[str(frame),str(int(active)),str(far),str(dt),str(bank),str(streak),str(change)] and
                float(row['primary_energy'])==pe and float(row['shadow_energy'])==se,'selector/gate recurrence')
        for name in ('echo','residual'):
            chosen=('shadow_' if bank else 'primary_')+name
            require(data[name][a*4:b*4]==data[chosen][a*4:b*4],'selected bytes')
        if change:
            require(frame>0 and far and not dt,'gated event')
            events.append(dict(frame=frame,from_bank=old,to_bank=bank,adjacent_sample_delta=values['residual'][a]-values['residual'][a-1],
                               banks_first_sample_delta=values['shadow_residual'][a]-values['primary_residual'][a]))
    require(execution['switch_count']==len(events),'switch count')
    windows=[]
    for lo,hi in p['primary_windows_seconds']:
        a,b=window(c,lo,hi,n,0);windows.append(dict(scene_time_s=[lo,hi],**measure_window(values,a,b,notify,policy)))
    return dict(arithmetic_max_abs_error=arithmetic,events=events,final_bank=bank,
                gates=dict(far_frames=sum(r['far'] for r in gates),dt_frames=sum(r['dt'] for r in gates),eligible_frames=sum(r['far'] and not r['dt'] for r in gates)),
                whole=measure_window(values,0,n,notify,policy),windows=windows)


def deltas(a,b):
    return [dict(sample_range=x['sample_range'],selected_residual_rms_db_delta=y['channels']['selected']['residual']['rms_dbfs']-
                 x['channels']['selected']['residual']['rms_dbfs']) for x,y in zip([a['whole'],*a['windows']],[b['whole'],*b['windows']])]


def run(root,output,created):
    p,captures,schedules=preflight(root)
    require(not output.exists() and not output.is_symlink() and Path('/tmp') in output.resolve().parents,'new /tmp output required')
    sources=[Path(__file__).resolve(),PLAN,AMEND,RUNNER,SELECTOR,TEST,ROOT/'tools/codex_assets/device_timing.py',D19/'binding.json',D19/'result.json',D16/'final-binding.json',
             *[Path(n) for n in read_json(BASE/'binding.json')['source_files']],*[Path(s['source']) for s in schedules]]
    initial={str(f):sha(bounded(f,4*1024*1024)) for f in sources};source_files={}
    output.mkdir();created.append(output)
    flags=(D18/'build/CMakeFiles/audio_pipeline.dir/flags.make').read_text()
    definitions=[line.split('=',1)[1].split() for line in flags.splitlines() if line.startswith('C_DEFINES =')]
    require(len(definitions)==1 and definitions[0] and all(v.startswith('-DAP_BUILD_') for v in definitions[0]),'definitions')
    logged(output,'compile',['cc',*FLAGS,'-ffp-contract=off',*definitions[0],'-I',str(D18/'source/src'),'-I',str(D18/'source/include'),
           '-I',str(D18/'build/generated'),str(RUNNER),str(D18/'build/libaudio_pipeline.a'),'-lm','-lpthread','-o',str(output/'runner')],ROOT)
    runner_hash=sha((output/'runner').read_bytes());logged(output,'invalid',[str(output/'runner'),'invalid'],ROOT,expected=2)
    for label,frames,notify,policy,mode in [('frames','bad','none','shadow','normal'),('notify','1','1','shadow','normal'),
            ('policy','1','none','bad','normal'),('mode','1','none','shadow','bad'),('future','1','none','shadow','future')]:
        directory=output/('invalid-preserve-'+label);directory.mkdir()
        sentinel={n+'.f32le':b'D26_SENTINEL '+n.encode('ascii') for n in TRACES}
        sentinel.update({n:b'D26_SENTINEL '+n.encode('ascii') for n in ('state.csv','selector.csv')})
        for name,data in sentinel.items():(directory/name).write_bytes(data)
        logged(output,'invalid-preserve-'+label,[str(output/'runner'),'missing-mic','missing-ref','missing-gates',frames,notify,str(directory),policy,mode],ROOT,expected=2)
        require({f.name:f.read_bytes() for f in directory.iterdir()}==sentinel,'invalid file preservation')
        require(read_json(output/('command-invalid-preserve-'+label+'.json'))['stderr']=='D26_INVALID_ARGUMENT_REJECT primary_calls=0 shadow_calls=0\n','invalid zero calls')
    jobs=[(i,mode,policy,False,None) for i in range(16) for mode in ('fixed1','used0') for policy in ('keep','shadow')]+[
          (6,'used0','shadow',False,'repeat'),(6,'used0','shadow',True,'future')]
    cases=[]
    for i,mode,policy,future,label in jobs:
        c=captures[i];n=summary(c)['replay_samples'];notify=schedules[i]['notify_frame']
        name=label or f'case-{i+1:02d}-{mode}-{policy}';directory=output/name;directory.mkdir()
        mic_path,ref_path,gates,origin=source_inputs(i,mode,n);source_files.update(origin)
        gate_data=bytes(v for row in gates for v in (row['far'],row['dt']))
        (directory/'gates.bin').write_bytes(gate_data)
        execution=strict_json(logged(output,name,[str(output/'runner'),str(mic_path),str(ref_path),str(directory/'gates.bin'),str(n//160),
                    'none' if notify is None else str(notify),str(directory),policy,'future' if future else 'normal'],ROOT).encode())
        for current,old in [('primary_echo','echo'),('primary_residual','aec_residual')]:
            got=(directory/(current+'.f32le')).read_bytes();expected=(D19/f'case-{i+1:02d}'/mode/(old+'.f32le')).read_bytes()
            require(got[:notify*160*4]==expected[:notify*160*4] if future else got==expected,'primary D19 exact equivalence')
        measured=observe(directory,mic_path,ref_path,gates,n,notify,policy,future,c,p,execution)
        cases.append(dict(name=name,case_id=c['case_id'],case_index=i+1,mode=mode,policy=policy,future=future,zero_reference=not any(c['raw'].samples[::2]),
                          notify_frame=notify,source_hashes=origin,gate_binary_sha256=sha(gate_data),execution_summary=execution,measurement=measured))
    records={r['name']:r for r in cases};pairs=[]
    for i,c in enumerate(captures):
        for mode in ('fixed1','used0'):
            prefix=f'case-{i+1:02d}-{mode}';a=output/(prefix+'-keep');b=output/(prefix+'-shadow')
            notify=schedules[i]['notify_frame'];first=summary(c)['replay_samples'] if notify is None else notify*160
            for name in ('primary_echo.f32le','primary_residual.f32le','state.csv','gates.bin'):
                require((a/name).read_bytes()==(b/name).read_bytes(),'primary independence')
            for name in ('echo.f32le','residual.f32le'):
                require((a/name).read_bytes()==(a/('primary_'+name)).read_bytes(),'keep selected')
                require((a/name).read_bytes()[:first*4]==(b/name).read_bytes()[:first*4],'notification prefix')
            if not any(c['raw'].samples[::2]):
                require(notify is None,'zero reference alert control')
                for name in TRACES:
                    require((b/(name+'.f32le')).read_bytes()==(output/f'case-{i+1:02d}-fixed1-shadow'/(name+'.f32le')).read_bytes(),'zero coordinate control')
            pairs.append(dict(case_id=c['case_id'],case_index=i+1,mode=mode,notify_frame=notify,
                              shadow_minus_keep=deltas(records[a.name]['measurement'],records[b.name]['measurement'])))
    first=schedules[6]['notify_frame'];require(first is not None,'registered future notification')
    for name in [n+'.f32le' for n in TRACES]+['state.csv','selector.csv']:
        original=(output/'case-07-used0-shadow'/name).read_bytes()
        require(original==(output/'repeat'/name).read_bytes(),'repeat exact')
        future=(output/'future'/name).read_bytes()
        require(original[:first*160*4]==future[:first*160*4] if name.endswith('.f32le') else
                original.splitlines()[:first+1]==future.splitlines()[:first+1],'future prefix')
    preflight(root)
    require(initial=={str(f):sha(bounded(f,4*1024*1024)) for f in sources} and source_files==
            {name:sha(bounded(Path(name),4*1024*1024)) for name in source_files} and runner_hash==sha((output/'runner').read_bytes()),'identity drift')
    dump(output/'result.json',dict(experiment='FE_DEVICE_FIELD_D26',decision='FIELD_SHADOW_DIAGNOSTIC_NO_PROMOTION',data_role='development',
         executions=66,research_algorithm_changed=False,shipping_algorithm_changed=False,promotion_allowed=False,shipping_approved=False,
         alert_authority='first frozen D16 rejected-candidate reset counter; external research schedule, not physical truth',
         schedules=schedules,cases=cases,shadow_minus_keep=pairs,selector=dict(ratio=0.8,confirmation_frames=3,crossfade=False),
         resources=dict(extra_shadow_state_bytes=cases[0]['execution_summary']['state_bytes'],scope='state sizeof/calls only; not CPU/peak/DUT')))
    dump(output/'binding.json',dict(source_files=initial,field_source_files=source_files,runner_sha256=runner_hash,d25_hashes=HASHES,
         library_sha256=initial[str(D18/'build/libaudio_pipeline.a')],source_start_end_equal=True,input_start_end_equal=True,
         artifacts={str(f.relative_to(output)):sha(f.read_bytes()) for f in sorted(output.rglob('*')) if f.is_file()}))
    print('D26_FIELD_PASS 66 executions',flush=True)


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root',type=Path,required=True);parser.add_argument('--output',type=Path,required=True);parser.add_argument('--dry-run',action='store_true')
    args=parser.parse_args(argv);created=[]
    try:
        if args.dry_run:
            _,cases,schedules=preflight(args.root);print('D26_PREFLIGHT_PASS',len(cases),'cases; writes=False; alert_cases',sum(s['notify_frame'] is not None for s in schedules))
        else:run(args.root,args.output,created)
        return 0
    except (ValueError,OSError,KeyError,TypeError,subprocess.TimeoutExpired) as error:
        if created==[args.output]:dump(args.output/'measurement-invalid.json',dict(decision='MEASUREMENT_INVALID',error=str(error)))
        print('device_field: '+str(error),file=sys.stderr);return 2


if __name__=='__main__':raise SystemExit(main())
