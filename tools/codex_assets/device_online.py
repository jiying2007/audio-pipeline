"""D29 actual MDF + frozen dwell/transition research integration."""
from __future__ import annotations
import argparse
import csv
import io
import math
from pathlib import Path
import subprocess
import sys
if __package__ in (None,''):sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from tools.codex_assets.device_capture import ROOT,bounded,require,sha,strict_json
from tools.codex_assets.device_exact_reference import dump,logged,read_json
from tools.codex_assets.device_transition import preflight as old_preflight,mic_path,mix,FIELDS as TRANS_FIELDS
from tools.codex_assets.device_dwell import BASES,BANKS,FIELDS as SELECT_FIELDS,recurrence,score
from tools.codex_assets.device_stages import D18,floats
from tools.codex_assets.device_path import encoded
from tools.codex_assets.device_replay import FLAGS
BASE=Path('/tmp/audio-fe-device-transition-d28-20261011')
D27=Path('/tmp/audio-fe-device-dwell-d27-20261011')
HASHES={'result.json':'67b5a3f3a11b27a167e1d4ac7e59211cc7f92f9c865f4f891ae8ee49cd7175ae','binding.json':'d34ca0be4f597297de80a16f78940146b276bdde648a03fc2dbfb5187bea2102'}
LIB_SHA='eb5b0c784c316e71d6ed9f58db6cb66f190b631daa00c55a94032168d5a47aa4'
PLAN=ROOT/'docs/research/frontend-evolution-v1/DEVICE_ONLINE_D29_PLAN.zh-CN.md'
AMEND=ROOT/'docs/research/frontend-evolution-v1/DEVICE_ONLINE_D29_AMENDMENT.zh-CN.md'
C=ROOT/'tests/validation/frontend_evolution/device_online_d29.c'
TEST=C.parent/'test_device_online.py'
TRACES=('mic','reference','echo','residual',*BANKS)
OUTPUTS=tuple(k+'.f32le' for k in TRACES)+('state.csv','selector.csv','transition.csv')

def preflight(root):
    sources=old_preflight(root)
    for name,expected in HASHES.items():require(sha(bounded(BASE/name,4*1024*1024))==expected,'D28 identity')
    binding=read_json(BASE/'binding.json')
    for group in ('source_files','input_files','artifacts'):
        for name,expected in binding[group].items():require(sha(bounded(BASE/name if group=='artifacts' else Path(name),4*1024*1024))==expected,'D28 drift')
    require(sha(bounded(D18/'build/libaudio_pipeline.a',4*1024*1024))==LIB_SHA,'DSP identity')
    cases=[c for c in read_json(BASE/'result.json')['cases'] if c['mode']=='fade' and c['name'] not in ('repeat','future')]
    require(len(cases)==44,'D28 case set')
    for s in sources:
        found=[c for c in cases if (c['kind'],c['source_case'])==(s['kind'],s['case']['name'])]
        require(len(found)==1,'D28 mapping');s['offline']=found[0]
    return sources

def input_info(source):
    directory=source['base']/source['case']['name'];n=source['case']['execution_summary']['frames']*160
    mic=mic_path(source,directory)
    if source['kind']=='field':
        refs=[Path(k) for k in source['case']['source_hashes'] if k.endswith('.reference.f32le')]
        require(len(refs)==1,'field reference identity');ref=refs[0];gates=bounded(directory/'gates.bin',20000)
        notify=source['case']['notify_frame']
    else:
        ref=directory/'reference.f32le';rows=list(csv.DictReader(io.StringIO(bounded(directory/'selector.csv',1024*1024).decode('ascii'))))
        gates=bytes(v for row in rows for v in (1,int(row['dt'])));notify=1000
    require(len(gates)==n//160*2 and all(v in (0,1) for v in gates),'gate identity')
    return directory,mic,ref,gates,n,notify

def observe(directory,source,future,execution):
    original,mic_path_,ref_path,gates,n,notify=input_info(source)
    values={k:floats(directory/(k+'.f32le'),n) for k in TRACES}
    for k,p in [('mic',mic_path_),('reference',ref_path)]:
        expected=floats(p,n)
        if future:expected=[-v if i>=notify*160 else v for i,v in enumerate(expected)]
        require((directory/(k+'.f32le')).read_bytes()==encoded(expected),'actual inputs '+k)
    baseline=source['base']/('future' if future else source['case']['name'])
    for k in BANKS:require((directory/(k+'.f32le')).read_bytes()==bounded(baseline/(k+'.f32le'),4*1024*1024),'actual bank byte equality')
    require((directory/'state.csv').read_bytes()==bounded(baseline/'state.csv',1024*1024),'primary state CSV equality')
    readers=[csv.DictReader(io.StringIO(bounded(directory/p,1024*1024).decode('ascii'))) for p in ('selector.csv','transition.csv')]
    require(readers[0].fieldnames==SELECT_FIELDS and readers[1].fieldnames==TRANS_FIELDS,'CSV schema')
    selectors,transitions=[list(r) for r in readers];require(len(selectors)==len(transitions)==n//160,'CSV counts')
    bank=streak=0;last_switch=None;from_bank=pos=remaining=mixed=0;expected={k:[] for k in ('echo','residual')};events=[]
    for frame,(sel,tr) in enumerate(zip(selectors,transitions)):
        a,b=frame*160,(frame+1)*160;far,dt=gates[frame*2:frame*2+2];active=int(notify is not None and frame>=notify);before=bank
        pe=sum(v*v for v in values['primary_residual'][a:b]);se=sum(v*v for v in values['shadow_residual'][a:b])
        bank,streak,last_switch,change,hold=recurrence(bank,streak,last_switch,frame,50,active,far and not dt,pe,se)
        require([sel[k] for k in SELECT_FIELDS[:7]]==[str(frame),str(active),str(far),str(dt),str(bank),str(streak),str(change)] and
            float(sel['primary_energy'])==pe and float(sel['shadow_energy'])==se and int(sel['hold_remaining'])==hold,'actual selector recurrence')
        if not active:from_bank=pos=remaining=0
        elif change:
            require(not remaining,'transition overlap');from_bank=before;pos=0;remaining=320;events.append(dict(frame=frame,from_bank=before,to_bank=bank))
        first=last=1.0
        for i in range(a,b):
            alpha=pos/319.0 if remaining else 1.0
            if i==a:first=alpha
            last=alpha
            for k in expected:
                old=values[('shadow_' if from_bank else 'primary_')+k][i];new=values[('shadow_' if bank else 'primary_')+k][i]
                expected[k].append(mix(old,new,pos) if remaining else new)
            if remaining:pos+=1;remaining-=1;mixed+=1
        require([tr[k] for k in TRANS_FIELDS[:6]]==[str(frame),str(active),str(far),str(dt),str(bank),str(change)] and
            int(tr['remaining_after_frame'])==remaining and float(tr['alpha_first'])==first and float(tr['alpha_last'])==last,'actual transition recurrence')
    for k in expected:require((directory/(k+'.f32le')).read_bytes()==encoded(expected[k]),'actual exact mix/endpoints/outside')
    algebra={}
    for bank_name in ('selected','primary','shadow'):
        first=notify*160 if bank_name=='shadow' and notify is not None else n if bank_name=='shadow' else 0
        if first==n:continue
        prefix='' if bank_name=='selected' else bank_name+'_'
        algebra[bank_name]=max(abs(values[prefix+'echo'][i]+values[prefix+'residual'][i]-values['mic'][i]) for i in range(first,n))
        require(algebra[bank_name]<=1e-6,'actual mic algebra')
    fixed=dict(frames=n//160,samples=n,primary_calls=n//160,shadow_calls=n//160-notify if notify is not None else 0,
        shadow_reset_calls=int(notify is not None),selector_calls=n//160,transition_calls=n//160,mixed_samples=mixed,remaining=remaining,
        switch_count=len(events),sync_calls=0,aec_state_bytes=33020,two_aec_state_bytes=66040,selector_state_bytes=20,
        transition_state_bytes=16,frame_buffer_bytes=5120,scoped_bytes=71196)
    require(all(type(v) is int for v in execution.values()) and execution==fixed and execution['scoped_bytes']<=128*1024,'actual counts/resources')
    diagnostics=[]
    for e in events:
        a=e['frame']*160;b=min(a+319,n-1);channels={}
        for k in ('echo','residual'):
            y=values[k];old=values[('shadow_' if e['from_bank'] else 'primary_')+k]
            channels[k]=dict(start_injection=y[a]-old[a],adjacent_delta=y[a]-y[a-1],gradient_squared_sum=math.fsum((y[i]-y[i-1])**2 for i in range(a,b+1)))
        diagnostics.append(dict(**e,start_sample=a,end_sample=b,censored=a+320>n,channels=channels))
    measurement=None
    if not future:
        if source['kind']=='return':
            for k in ('near','true_echo'):values[k]=floats(original/(k+'.f32le'),n)
        measurement=score(source,values)
        require(measurement==source['offline']['observation']['measurement'] and diagnostics==source['offline']['observation']['events'],'offline measure/event equality')
        for p in ('echo.f32le','residual.f32le','transition.csv'):require((directory/p).read_bytes()==bounded(BASE/source['offline']['name']/p,4*1024*1024),'offline selected/transition byte equality')
        require((directory/'selector.csv').read_bytes()==bounded(D27/source['controller']['name']/'selector.csv',1024*1024),'offline selector byte equality')
    return dict(events=diagnostics,measurement=measurement,algebra_max_abs_error=algebra)

def inherited_acceptance(cases):
    old=read_json(BASE/'result.json')['acceptance'];grad=[];injection=[];complete=[];near=[];counts={'field':0,'return':0}
    pairs={p['name']:p for p in old['pairs']};old_cases={c['name']:c for c in read_json(BASE/'result.json')['cases']}
    for c in cases:
        if c['name'] in ('repeat','future'):continue
        counts[c['kind']]+=len(c['observation']['events'])
        for e in c['observation']['events']:
            complete.append(not e['censored']);injection.extend(abs(e['channels'][k]['start_injection'])<=1e-8 for k in ('echo','residual'))
            if c['kind']=='field':grad.append(e['channels']['residual']['gradient_squared_sum'])
        name=c['kind']+'-'+c['source_case']+'-fade';hard=old_cases[name.replace('-fade','-hard')]['observation']['measurement'];m=c['observation']['measurement'];deltas=[]
        for a,b in zip([hard['whole'],*hard['windows']],[m['whole'],*m['windows']]):
            d=dict(sample_range=a['sample_range'],selected_residual_rms_db_delta=b['channels']['selected']['residual']['rms_dbfs']-a['channels']['selected']['residual']['rms_dbfs'])
            if c['kind']=='return':
                d['selected_error_rms_db_delta']=b['channels']['selected']['error']['rms_dbfs']-a['channels']['selected']['error']['rms_dbfs'];near.append(d['selected_error_rms_db_delta']<=.5)
            deltas.append(d)
        require(deltas==pairs[name]['deltas'],'original delta equality')
    conditions=dict(start_injection=all(injection),complete_events=all(complete),residual_gradient=math.fsum(grad)<=old['residual_gradient_squared_sum']['hard'],known_near=all(near))
    require(counts==old['events'] and conditions==old['conditions'] and math.fsum(grad)==old['residual_gradient_squared_sum']['fade'],'candidate rule equality')
    return dict(events=counts,conditions=conditions,residual_gradient_squared_sum=old['residual_gradient_squared_sum'],accepted=all(conditions.values()),scope='inherited D28 engineering conditions only')

def run(root,output,created):
    sources=preflight(root);require(not output.exists() and not output.is_symlink() and Path('/tmp') in output.resolve().parents,'new /tmp output required')
    own=[Path(__file__).resolve(),PLAN,AMEND,C,TEST,C.parent/'device_field_d26.c',C.parent/'device_dwell_selector_d27.h',C.parent/'device_shadow_selector_d24.h',C.parent/'device_transition_d28.h',
        ROOT/'tools/codex_assets/device_transition.py',ROOT/'tools/codex_assets/device_dwell.py',D18/'build/CMakeFiles/audio_pipeline.dir/flags.make',D18/'build/libaudio_pipeline.a']
    initial={str(p):sha(bounded(p,4*1024*1024)) for p in own};inputs={}
    for s in sources:
        original,mic,ref,_,_,_=input_info(s)
        paths=[mic,ref,original/('gates.bin' if s['kind']=='field' else 'selector.csv')]
        if s['kind']=='return':paths.extend(original/(k+'.f32le') for k in ('near','true_echo'))
        for p in paths:inputs[str(p)]=sha(bounded(p,4*1024*1024))
    output.mkdir();created.append(output)
    flags=(D18/'build/CMakeFiles/audio_pipeline.dir/flags.make').read_text();definitions=[r.split('=',1)[1].split() for r in flags.splitlines() if r.startswith('C_DEFINES =')]
    require(len(definitions)==1 and definitions[0] and all(v.startswith('-DAP_BUILD_') for v in definitions[0]),'frozen definitions')
    logged(output,'compile',['cc',*FLAGS,'-ffp-contract=off',*definitions[0],'-I',str(D18/'source/src'),'-I',str(D18/'source/include'),'-I',str(D18/'build/generated'),str(C),str(D18/'build/libaudio_pipeline.a'),'-lm','-lpthread','-o',str(output/'runner')],ROOT)
    runner_sha=sha((output/'runner').read_bytes());logged(output,'self-test',[str(output/'runner'),'--self-test'],ROOT);logged(output,'invalid',[str(output/'runner'),'invalid'],ROOT,expected=2)
    for label,frames,notify,mode in [('frames','bad','none','normal'),('notify','1','1','normal'),('mode','1','none','bad'),('future','1','none','future')]:
        d=output/('invalid-preserve-'+label);d.mkdir();sentinels={p:b'D29_SENTINEL '+p.encode() for p in OUTPUTS}
        for p,data in sentinels.items():(d/p).write_bytes(data)
        logged(output,'invalid-preserve-'+label,[str(output/'runner'),*['missing']*3,frames,notify,str(d),mode],ROOT,expected=2)
        require({p.name:p.read_bytes() for p in d.iterdir()}==sentinels,'invalid preservation')
        require(read_json(output/('command-invalid-preserve-'+label+'.json'))['stderr']=='D29_INVALID_ARGUMENT_REJECT primary_calls=0 shadow_calls=0\n','invalid zero DSP calls')
    anchor=next(s for s in sources if s['kind']=='field' and s['case']['name']=='case-07-used0-shadow');jobs=[(s,False,None) for s in sources]+[(anchor,False,'repeat'),(anchor,True,'future')];cases=[]
    for s,future,label in jobs:
        original,mic,ref,gates,n,notify=input_info(s);name=label or s['kind']+'-'+s['case']['name'];directory=output/name;directory.mkdir();(directory/'gates.bin').write_bytes(gates)
        execution=strict_json(logged(output,name,[str(output/'runner'),str(mic),str(ref),str(directory/'gates.bin'),str(n//160),'none' if notify is None else str(notify),str(directory),'future' if future else 'normal'],ROOT).encode())
        observation=observe(directory,s,future,execution)
        cases.append(dict(name=name,kind=s['kind'],source_case=s['case']['name'],source_directory=str(original),future=future,notify_frame=notify,gate_binary_sha256=sha(gates),execution_summary=execution,observation=observation))
        print('D29_CASE_PASS '+name,flush=True)
    normal=output/'field-case-07-used0-shadow';notify=anchor['case']['notify_frame']
    for p in OUTPUTS:
        a=(normal/p).read_bytes();b=(output/'future'/p).read_bytes();require(a==(output/'repeat'/p).read_bytes(),'repeat all outputs')
        require(a[:notify*160*4]==b[:notify*160*4] if p.endswith('.f32le') else a.splitlines()[:notify+1]==b.splitlines()[:notify+1],'future all prefixes')
    inherited=inherited_acceptance(cases);require(inherited['accepted'],'inherited conditions');preflight(root)
    require(initial=={p:sha(bounded(Path(p),4*1024*1024)) for p in initial} and inputs=={p:sha(bounded(Path(p),4*1024*1024)) for p in inputs} and sha((output/'runner').read_bytes())==runner_sha,'source/input/runner drift')
    dump(output/'result.json',dict(experiment='FE_DEVICE_ONLINE_D29',executions=46,data_role='development-and-synthetic-engineering',decision='ONLINE_INTEGRATION_ENGINEERING_PASS_NO_PROMOTION',
        research_algorithm_changed=False,integration_changed=True,shipping_algorithm_changed=False,promotion_allowed=False,shipping_approved=False,
        online_scope='actual AEC -> actual D27 selector -> D28 transition; frozen external gates; no full product chain',cases=cases,inherited_acceptance=inherited,
        resource_budget=dict(scoped_bytes=71196,budget_bytes=131072,b0_arena_bytes=50000,b0_changed=False,target_resource_qualified=False)))
    dump(output/'binding.json',dict(source_files=initial,input_files=inputs,baseline_hashes=HASHES,library_sha256=LIB_SHA,runner_sha256=runner_sha,
        source_start_end_equal=True,input_start_end_equal=True,artifacts={str(p.relative_to(output)):sha(p.read_bytes()) for p in sorted(output.rglob('*')) if p.is_file()}))
    print('D29_MEASUREMENT_PASS 46 actual integrated executions NO_PROMOTION',flush=True)

def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--root',type=Path,required=True);parser.add_argument('--output',type=Path,required=True);parser.add_argument('--dry-run',action='store_true');args=parser.parse_args(argv);created=[]
    try:
        if args.dry_run:print('D29_PREFLIGHT_PASS',len(preflight(args.root)),'sources; writes=False')
        else:run(args.root,args.output,created)
        return 0
    except (ValueError,OSError,KeyError,TypeError,subprocess.TimeoutExpired) as error:
        if created==[args.output]:dump(args.output/'measurement-invalid.json',dict(decision='MEASUREMENT_INVALID',error=str(error)))
        print('device_online: '+str(error),file=sys.stderr);return 2
if __name__=='__main__':raise SystemExit(main())
