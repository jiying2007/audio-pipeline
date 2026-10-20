"""D28 fixed 320-sample output transition on frozen D27 controls."""
from __future__ import annotations
import argparse
import csv
import io
import math
from pathlib import Path
import subprocess
import sys
if __package__ in (None, ''):
    sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from tools.codex_assets.device_capture import ROOT,bounded,require,sha,strict_json
from tools.codex_assets.device_exact_reference import dump,logged,read_json
from tools.codex_assets.device_dwell import preflight as old_preflight,source_data,score,BANKS
from tools.codex_assets.device_stages import floats
from tools.codex_assets.device_path import encoded
from tools.codex_assets.device_multipath import f32
from tools.codex_assets.device_replay import FLAGS
BASE=Path('/tmp/audio-fe-device-dwell-d27-20261011')
HASHES={'result.json':'c8b7cf96ee67facb504e502a2b5ec5a13f5c6f06eb84c6436ff5aad0d5513985',
        'binding.json':'c1d340bfea936ba6c01661245097eaa3621994479100803d0d201243348d1b4f'}
DOC=ROOT/'docs/research/frontend-evolution-v1'
PLAN=DOC/'DEVICE_TRANSITION_D28_PLAN.zh-CN.md'
AMEND=DOC/'DEVICE_TRANSITION_D28_AMENDMENT.zh-CN.md'
C=ROOT/'tests/validation/frontend_evolution/device_transition_d28.c'
HEADER=C.with_suffix('.h')
TEST=C.parent/'test_device_transition.py'
FIELDS=['frame','active','far','dt','bank','change','remaining_after_frame','alpha_first','alpha_last']

def mix(old,new,pos):
    require(0<=pos<320,'mix position')
    if pos==0:return old
    if pos==319:return new
    return f32(old+(pos/319.0)*(new-old))

def preflight(root):
    sources=old_preflight(root)
    for name,expected in HASHES.items():require(sha(bounded(BASE/name,4*1024*1024))==expected,'D27 identity')
    binding=read_json(BASE/'binding.json')
    for group in ('source_files','input_files','artifacts'):
        for name,expected in binding[group].items():
            path=BASE/name if group=='artifacts' else Path(name)
            require(sha(bounded(path,4*1024*1024))==expected,'D27 bound drift')
    cases=[c for c in read_json(BASE/'result.json')['cases'] if c['mode']=='dwell' and c['name'] not in ('repeat','future')]
    require(len(cases)==44,'D27 sources')
    for source in sources:
        matches=[c for c in cases if (c['kind'],c['source_case'])==(source['kind'],source['case']['name'])]
        require(len(matches)==1,'D27 mapping');source['controller']=matches[0]
    return sources

def controller(source):
    directory=BASE/source['controller']['name']
    rows=list(csv.DictReader(io.StringIO(bounded(directory/'selector.csv',1024*1024).decode('ascii'))))
    controls=[tuple(int(r[k]) for k in FIELDS[1:6]) for r in rows]
    require(all(r['frame']==str(i) and all(v in (0,1) for v in c) for i,(r,c) in enumerate(zip(rows,controls))),'control range')
    return directory,controls

def mic_path(source,directory):
    if source['kind']=='return':return directory/'mic.f32le'
    paths=[Path(p) for p in source['case']['source_hashes'] if p.endswith('/aec_input.f32le')]
    require(len(paths)==1,'field mic identity');return paths[0]

def observe(directory,source,mode,future,execution):
    original,values,_,_,n=source_data(source);old_dir,controls=controller(source)
    require(len(controls)*160==n,'controller length')
    if future:
        for name in BANKS:
            gain=1.125 if name.startswith('primary') else -0.875
            values[name]=[f32(v*gain) if controls[i//160][0] else v for i,v in enumerate(values[name])]
    selected={name:bounded(directory/(name+'.f32le'),4*1024*1024) for name in ('echo','residual')}
    for name in selected:values[name]=floats(directory/(name+'.f32le'),n)
    reader=csv.DictReader(io.StringIO(bounded(directory/'transition.csv',1024*1024).decode('ascii')))
    require(reader.fieldnames==FIELDS,'transition schema');rows=list(reader);require(len(rows)==len(controls),'transition rows')
    expected={k:[] for k in selected};bank=from_bank=pos=remaining=mixed=0;events=[]
    for frame,(row,c) in enumerate(zip(rows,controls)):
        active,far,dt,new,change=c;before=bank
        if not active:
            require(new==change==0,'inactive controls');bank=from_bank=pos=remaining=0
        elif change:
            require(not remaining and new!=bank,'overlap or same bank');from_bank=bank;bank=new;pos=0;remaining=320 if mode=='fade' else 0
            events.append(dict(frame=frame,from_bank=before,to_bank=bank))
        else:require(new==bank,'silent bank change')
        first=last=1.0
        for i in range(frame*160,(frame+1)*160):
            alpha=pos/319.0 if remaining else 1.0
            if i==frame*160:first=alpha
            last=alpha
            for name in expected:
                new_value=values[('shadow_' if bank else 'primary_')+name][i]
                old_value=values[('shadow_' if from_bank else 'primary_')+name][i]
                expected[name].append(mix(old_value,new_value,pos) if remaining else new_value)
            if remaining:pos+=1;remaining-=1;mixed+=1
        require([row[k] for k in FIELDS[:6]]==[str(frame),*[str(v) for v in c]] and
                int(row['remaining_after_frame'])==remaining and float(row['alpha_first'])==first and float(row['alpha_last'])==last,'transition recurrence')
    for name in expected:
        require(selected[name]==encoded(expected[name]),'exact float32 recurrence/endpoints/outside')
        if mode=='hard':require(selected[name]==bounded(old_dir/(name+'.f32le'),4*1024*1024),'hard D27 full bytes')
    require(set(execution)=={'frames','samples','transition_calls','switch_count','mixed_samples','remaining','transition_state_bytes','aec_calls','selector_calls'} and
            all(type(v) is int for v in execution.values()) and execution==dict(frames=n//160,samples=n,transition_calls=n//160,
            switch_count=len(events),mixed_samples=mixed,remaining=remaining,transition_state_bytes=16,aec_calls=0,selector_calls=0),'execution summary')
    algebra=None
    if not future:
        mic=floats(mic_path(source,original),n)
        algebra=max(abs(e+r-m) for e,r,m in zip(values['echo'],values['residual'],mic));require(algebra<=1e-6,'mic algebra')
    diagnostics=[]
    for event in events:
        a=event['frame']*160;b=min(a+319,n-1);channels={}
        for name in selected:
            y=values[name];old=values[('shadow_' if event['from_bank'] else 'primary_')+name]
            channels[name]=dict(start_injection=y[a]-old[a],adjacent_delta=y[a]-y[a-1],
                gradient_squared_sum=math.fsum((y[k]-y[k-1])**2 for k in range(a,b+1)))
        diagnostics.append(dict(**event,start_sample=a,end_sample=b,censored=a+320>n,channels=channels))
    measurement=None if future else score(source,values)
    if mode=='hard':require(measurement==source['controller']['observation']['measurement'],'hard original score/null')
    return dict(events=diagnostics,measurement=measurement,algebra_max_abs_error=algebra)

def candidate_checks(cases):
    lookup={c['name']:c for c in cases};pairs=[];grad={'hard':[],'fade':[]};injection=[];complete=[];near=[];counts={'field':0,'return':0}
    for c in cases:
        if c['mode']!='fade' or c['name'] in ('repeat','future'):continue
        old=lookup[c['name'].replace('-fade','-hard')];counts[c['kind']]+=c['execution_summary']['switch_count']
        for e in c['observation']['events']:
            complete.append(not e['censored']);injection.extend(abs(e['channels'][k]['start_injection'])<=1e-8 for k in ('echo','residual'))
        if c['kind']=='field':
            for item in (old,c):grad[item['mode']].extend(e['channels']['residual']['gradient_squared_sum'] for e in item['observation']['events'])
        x=old['observation']['measurement'];y=c['observation']['measurement'];deltas=[]
        for a,b in zip([x['whole'],*x['windows']],[y['whole'],*y['windows']]):
            d=dict(sample_range=a['sample_range'],selected_residual_rms_db_delta=b['channels']['selected']['residual']['rms_dbfs']-a['channels']['selected']['residual']['rms_dbfs'])
            if c['kind']=='return':
                d['selected_error_rms_db_delta']=b['channels']['selected']['error']['rms_dbfs']-a['channels']['selected']['error']['rms_dbfs'];near.append(d['selected_error_rms_db_delta']<=0.5)
            deltas.append(d)
        pairs.append(dict(name=c['name'],deltas=deltas))
    require(counts=={'field':243,'return':8},'frozen event counts')
    sums={k:math.fsum(v) for k,v in grad.items()}
    conditions=dict(start_injection=all(injection),complete_events=all(complete),residual_gradient=sums['fade']<=sums['hard'],known_near=all(near))
    return dict(accepted=all(conditions.values()),conditions=conditions,events=counts,residual_gradient_squared_sum=sums,pairs=pairs)

def run(root,output,created):
    sources=preflight(root)
    require(not output.exists() and not output.is_symlink() and Path('/tmp') in output.resolve().parents,'new /tmp output required')
    own=[Path(__file__).resolve(),PLAN,AMEND,C,HEADER,TEST,ROOT/'tools/codex_assets/device_dwell.py']
    initial={str(p):sha(bounded(p,4*1024*1024)) for p in own};inputs={}
    for s in sources:
        original,_,_,_,_=source_data(s);old_dir,_=controller(s)
        names=[original/(k+'.f32le') for k in BANKS]+[old_dir/'selector.csv',mic_path(s,original)]
        if s['kind']=='return':names.extend(original/(k+'.f32le') for k in ('near','true_echo'))
        for p in names:inputs[str(p)]=sha(bounded(p,4*1024*1024))
    output.mkdir();created.append(output)
    logged(output,'compile',['cc',*FLAGS,'-ffp-contract=off',str(C),'-lm','-o',str(output/'runner')],ROOT)
    runner_hash=sha((output/'runner').read_bytes());logged(output,'self-test',[str(output/'runner'),'--self-test'],ROOT)
    logged(output,'invalid',[str(output/'runner'),'invalid'],ROOT,expected=2)
    for label,frames,mode,future in [('frames','bad','fade','normal'),('zero','0','fade','normal'),('mode','1','bad','normal'),('future','1','hard','future')]:
        directory=output/('invalid-preserve-'+label);directory.mkdir()
        sentinels={n:b'D28_SENTINEL '+n.encode() for n in ('echo.f32le','residual.f32le','transition.csv')}
        for n,data in sentinels.items():(directory/n).write_bytes(data)
        logged(output,'invalid-preserve-'+label,[str(output/'runner'),*['missing']*5,frames,mode,str(directory),future],ROOT,expected=2)
        require({p.name:p.read_bytes() for p in directory.iterdir()}==sentinels,'invalid preservation')
        require(read_json(output/('command-invalid-preserve-'+label+'.json'))['stderr']=='D28_INVALID_ARGUMENT_REJECT transition_calls=0\n','zero calls')
    anchor=next(s for s in sources if s['kind']=='field' and s['case']['name']=='case-07-used0-shadow')
    jobs=[(s,m,False,None) for s in sources for m in ('hard','fade')]+[(anchor,'fade',False,'repeat'),(anchor,'fade',True,'future')]
    cases=[]
    for s,mode,future,label in jobs:
        original,_,_,_,n=source_data(s);_,controls=controller(s);name=label or s['kind']+'-'+s['case']['name']+'-'+mode
        directory=output/name;directory.mkdir();binary=bytes(v for row in controls for v in row);(directory/'control.bin').write_bytes(binary)
        execution=strict_json(logged(output,name,[str(output/'runner'),*[str(original/(k+'.f32le')) for k in BANKS],str(directory/'control.bin'),str(n//160),mode,str(directory),'future' if future else 'normal'],ROOT).encode())
        observation=observe(directory,s,mode,future,execution)
        if not observation['events'] and not future:
            for k in ('echo','residual'):require((directory/(k+'.f32le')).read_bytes()==(BASE/s['controller']['name']/(k+'.f32le')).read_bytes(),'no event byte equality')
        cases.append(dict(name=name,kind=s['kind'],source_case=s['case']['name'],source_directory=str(original),controller_case=s['controller']['name'],mode=mode,future=future,
            control_binary_sha256=sha(binary),execution_summary=execution,observation=observation))
        print('D28_CASE_PASS '+name,flush=True)
    notify=anchor['case']['notify_frame'];normal=output/'field-case-07-used0-shadow-fade'
    for name in ('echo.f32le','residual.f32le','transition.csv'):
        a=(normal/name).read_bytes();b=(output/'future'/name).read_bytes();require(a==(output/'repeat'/name).read_bytes(),'repeat')
        require(a[:notify*160*4]==b[:notify*160*4] if name.endswith('.f32le') else a.splitlines()[:notify+1]==b.splitlines()[:notify+1],'future prefix')
    acceptance=candidate_checks(cases);preflight(root)
    require(initial=={p:sha(bounded(Path(p),4*1024*1024)) for p in initial} and inputs=={p:sha(bounded(Path(p),4*1024*1024)) for p in inputs} and sha((output/'runner').read_bytes())==runner_hash,'start/end drift')
    dump(output/'result.json',dict(experiment='FE_DEVICE_TRANSITION_D28',executions=90,data_role='development-and-synthetic-engineering',
        decision='TRANSITION_DEVELOPMENT_CANDIDATE_ONLY' if acceptance['accepted'] else 'TRANSITION_DEVELOPMENT_REJECTED',
        research_algorithm_changed=True,shipping_algorithm_changed=False,promotion_allowed=False,shipping_approved=False,
        transition=dict(samples=320,rate_hz=16000,alpha='j/319',controller='frozen D27'),resources=dict(transition_state_bytes=16,aec_calls=0,selector_calls=0,scope='private state only; no DUT cost'),cases=cases,acceptance=acceptance))
    dump(output/'binding.json',dict(source_files=initial,input_files=inputs,baseline_hashes=HASHES,runner_sha256=runner_hash,
        source_start_end_equal=True,input_start_end_equal=True,artifacts={str(p.relative_to(output)):sha(p.read_bytes()) for p in sorted(output.rglob('*')) if p.is_file()}))
    print('D28_MEASUREMENT_PASS 90 transition executions '+('CANDIDATE_ONLY' if acceptance['accepted'] else 'CANDIDATE_REJECTED'),flush=True)

def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--root',type=Path,required=True);parser.add_argument('--output',type=Path,required=True);parser.add_argument('--dry-run',action='store_true')
    args=parser.parse_args(argv);created=[]
    try:
        if args.dry_run:print('D28_PREFLIGHT_PASS',len(preflight(args.root)),'sources; writes=False')
        else:run(args.root,args.output,created)
        return 0
    except (ValueError,OSError,KeyError,TypeError,subprocess.TimeoutExpired) as error:
        if created==[args.output]:dump(args.output/'measurement-invalid.json',dict(decision='MEASUREMENT_INVALID',error=str(error)))
        print('device_transition: '+str(error),file=sys.stderr);return 2
if __name__=='__main__':raise SystemExit(main())
