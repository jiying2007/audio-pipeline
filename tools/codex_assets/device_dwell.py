"""D27 selector-only fixed dwell on frozen D26/D25 bank trajectories."""
from __future__ import annotations
import argparse
import csv
import io
import math
from pathlib import Path
import sys
import subprocess
if __package__ in (None, ''):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from tools.codex_assets.device_capture import ROOT, bounded, require, sha, strict_json
from tools.codex_assets.device_exact_reference import dump, logged, read_json
from tools.codex_assets.device_field import preflight as field_preflight, measure_window
from tools.codex_assets.device_return import window as near_window
from tools.codex_assets.device_stages import floats
from tools.codex_assets.device_multipath import f32
from tools.codex_assets.device_replay import FLAGS

BASES = {'field':Path('/tmp/audio-fe-device-field-d26-20261011'),
         'return':Path('/tmp/audio-fe-device-return-d25-20261011')}
HASHES = {'field':{'result.json':'51c2007f9dfa74a8f6ea032dd8caba79137b34a0379da55c79e69dac016ef42c',
                  'binding.json':'4dc0a3459d686abc5a86b6c7ad423bfa4294102ee5dfbbc0b63451ae2a097309'},
          'return':{'result.json':'5ceae16bc4e9587e669aac90c9f8fa8be55a60077b98733606190e7ea2a466d6',
                   'binding.json':'d5b5e273b311bb38d91d3a68b16986a12f6c548af83d721ded774b6a2e6f626e'}}
PLAN=ROOT/'docs/research/frontend-evolution-v1/DEVICE_DWELL_D27_PLAN.zh-CN.md'
C=ROOT/'tests/validation/frontend_evolution/device_dwell_d27.c'
HEADER=ROOT/'tests/validation/frontend_evolution/device_dwell_selector_d27.h'
OLD_HEADER=ROOT/'tests/validation/frontend_evolution/device_shadow_selector_d24.h'
TEST=ROOT/'tests/validation/frontend_evolution/test_device_dwell.py'
BANKS=('primary_echo','primary_residual','shadow_echo','shadow_residual')
FIELDS=['frame','active','far','dt','bank','streak','change','primary_energy','shadow_energy','hold_remaining']


def recurrence(bank,streak,last,frame,dwell,active,eligible,pe,se):
    require(bank in (0,1) and all(math.isfinite(v) and v>=0 for v in (pe,se)), 'selector values')
    if not active:return 0,0,None,0,0
    if last is not None and frame-last<dwell:return bank,0,last,0,dwell-(frame-last)
    current,other=(se,pe) if bank else (pe,se)
    streak=streak+1 if eligible and current>1e-20 and other<0.8*current else 0
    change=int(streak==3)
    if change:bank=1-bank;streak=0;last=frame
    remaining=max(0,dwell-(frame-last)) if last is not None else 0
    return bank,streak,last,change,remaining


def preflight(root):
    field_preflight(root)
    sources=[]
    for kind,base in BASES.items():
        for name,expected in HASHES[kind].items():require(sha(bounded(base/name,4*1024*1024))==expected,'baseline identity')
        binding=read_json(base/'binding.json')
        for group in ('source_files','field_source_files','artifacts'):
            for name,expected in binding.get(group,{}).items():
                path=base/name if group=='artifacts' else Path(name)
                require(sha(bounded(path,4*1024*1024))==expected,'baseline file drift')
        result=read_json(base/'result.json')
        require(result['data_role'] in ('development','synthetic-engineering'), 'data role')
        main=[c for c in result['cases'] if c['policy']=='shadow' and c['name'] not in ('repeat','future')]
        require(len(main)==(32 if kind=='field' else 12),'source set')
        for case in main:sources.append(dict(kind=kind,base=base,case=case))
    return sources


def source_data(source):
    case=source['case'];directory=source['base']/case['name'];frames=case['execution_summary']['frames'];n=frames*160
    values={name:floats(directory/(name+'.f32le'),n) for name in BANKS}
    old=list(csv.DictReader(io.StringIO(bounded(directory/'selector.csv',1024*1024).decode('ascii'))))
    require(len(old)==frames,'gate rows')
    gates=[]
    for frame,row in enumerate(old):
        far=int(row['far']) if source['kind']=='field' else 1
        gate=(int(row['active']),far,int(row['dt']))
        require(row['frame']==str(frame) and all(v in (0,1) for v in gate),'gate range')
        gates.append(gate)
    if source['kind']=='field':
        require(bytes(v for a,f,d in gates for v in (f,d))==bounded(directory/'gates.bin',10000),'field original gates')
    else:
        for name in ('near','true_echo'):values[name]=floats(directory/(name+'.f32le'),n)
    return directory,values,old,gates,n


def score(source,values):
    case=source['case'];old=case['measurement'];windows=[]
    for index,w in enumerate([old['whole'],*old['windows']]):
        a,b=w['sample_range']
        measured=measure_window(values,a,b,case['notify_frame'],'shadow') if source['kind']=='field' else near_window(values,a,b,'shadow')
        if index:
            key='scene_time_s' if source['kind']=='field' else 'seconds';measured[key]=w[key]
        windows.append(measured)
    return dict(whole=windows[0],windows=windows[1:])


def observe(directory,source,mode,future,execution):
    original,values,old,gates,n=source_data(source)
    if future:
        for name in BANKS:
            gain=1.125 if name.startswith('primary') else -0.875
            values[name]=[f32(v*gain) if gates[i//160][0] else v for i,v in enumerate(values[name])]
    for name in ('echo','residual'):values[name]=floats(directory/(name+'.f32le'),n)
    reader=csv.DictReader(io.StringIO(bounded(directory/'selector.csv',1024*1024).decode('ascii')))
    require(reader.fieldnames==FIELDS,'selector schema');rows=list(reader);require(len(rows)==n//160,'selector length')
    bank,streak,last=0,0,None;events=[];dwell=50 if mode=='dwell' else 0
    selected={name:bounded(directory/(name+'.f32le'),4*1024*1024) for name in ('echo','residual')}
    from tools.codex_assets.device_path import encoded
    bank_bytes={name:encoded(values[name]) for name in BANKS}
    for frame,(row,gate) in enumerate(zip(rows,gates)):
        a,b=frame*160,(frame+1)*160;active,far,dt=gate;before=bank
        pe=sum(v*v for v in values['primary_residual'][a:b]);se=sum(v*v for v in values['shadow_residual'][a:b])
        bank,streak,last,change,hold=recurrence(bank,streak,last,frame,dwell,active,far and not dt,pe,se)
        require([row[k] for k in FIELDS[:7]]==[str(frame),str(active),str(far),str(dt),str(bank),str(streak),str(change)] and
                float(row['primary_energy'])==pe and float(row['shadow_energy'])==se and row['hold_remaining']==str(hold),'recurrence/energy')
        for name in ('echo','residual'):
            require(selected[name][a*4:b*4]==bank_bytes[('shadow_' if bank else 'primary_')+name][a*4:b*4],'selected bytes')
        if change:events.append(dict(frame=frame,from_bank=before,to_bank=bank,
            adjacent_sample_delta=values['residual'][a]-values['residual'][a-1],
            banks_first_sample_delta=values['shadow_residual'][a]-values['primary_residual'][a]))
    require(set(execution)=={'frames','samples','selector_calls','switch_count','eligible_frames','selection_state_bytes','aec_calls'} and
            all(type(v) is int for v in execution.values()) and execution['frames']==n//160 and execution['samples']==n and
            execution['selector_calls']==n//160 and execution['switch_count']==len(events) and execution['aec_calls']==0 and
            execution['eligible_frames']==sum(f and not d for _,f,d in gates) and execution['selection_state_bytes']>0,'execution summary')
    if mode=='legacy':
        for name in selected:require(selected[name]==bounded(original/(name+'.f32le'),4*1024*1024),'legacy exact bytes')
        projection=[k for k in FIELDS if k!='hold_remaining' and (source['kind']=='field' or k!='far')]
        require([{k:r[k] for k in projection} for r in rows]==old,'legacy field projection')
    previous=source['case']['measurement']['events']
    first=lambda e:e[0]['frame'] if e else None
    require(future or first(events)==first(previous),'first switch changed')
    gaps=[b['frame']-a['frame'] for a,b in zip(events,events[1:])]
    require(mode=='legacy' or all(g>=52 for g in gaps),'minimum spacing')
    notify=source['case'].get('notify_frame',1000)
    if notify is not None:
        for name in selected:require(selected[name][:notify*160*4]==bounded(original/(name+'.f32le'),4*1024*1024)[:notify*160*4],'notification prefix')
    measurement=None if future else score(source,values)
    if mode=='legacy':
        require(measurement['whole']==source['case']['measurement']['whole'] and measurement['windows']==source['case']['measurement']['windows'],'legacy scores')
    return dict(events=events,final_bank=bank,minimum_event_gap_frames=min(gaps) if gaps else None,measurement=measurement)


def candidate_checks(cases):
    lookup={c['name']:c for c in cases};pairs=[];total_old=total_new=0;checks=[]
    for c in cases:
        if c['mode']!='dwell' or c['name'] in ('repeat','future'):continue
        previous=lookup[c['name'].replace('-dwell','-legacy')];deltas=[]
        a=previous['observation']['measurement'];b=c['observation']['measurement']
        for x,y in zip([a['whole'],*a['windows']],[b['whole'],*b['windows']]):
            d=dict(sample_range=x['sample_range'],selected_residual_rms_db_delta=y['channels']['selected']['residual']['rms_dbfs']-
                   x['channels']['selected']['residual']['rms_dbfs'])
            if c['kind']=='return':
                d['selected_error_rms_db_delta']=y['channels']['selected']['error']['rms_dbfs']-x['channels']['selected']['error']['rms_dbfs']
                checks.append(d['selected_error_rms_db_delta']<=0.5)
            deltas.append(d)
        if c['kind']=='field':total_old+=previous['execution_summary']['switch_count'];total_new+=c['execution_summary']['switch_count']
        else:
            source=c['source_case'];frames=[e['frame'] for e in c['observation']['events']]
            checks.append(frames==([1002,1202] if source.startswith('ABA-') and '-dt-' not in source else []))
        pairs.append(dict(name=c['name'],legacy_switches=previous['execution_summary']['switch_count'],
                          dwell_switches=c['execution_summary']['switch_count'],deltas=deltas))
    require(total_old==538,'field frozen switch count')
    return dict(field_legacy_switches=total_old,field_dwell_switches=total_new,
                field_switch_reduction_fraction=(total_old-total_new)/total_old,
                field_count_condition=total_new<=403,return_conditions=all(checks),
                accepted=total_new<=403 and all(checks),pairs=pairs)


def run(root,output,created):
    sources=preflight(root)
    require(not output.exists() and not output.is_symlink() and Path('/tmp') in output.resolve().parents,'new /tmp output required')
    own=[Path(__file__).resolve(),PLAN,C,HEADER,OLD_HEADER,TEST]
    initial={str(p):sha(bounded(p,4*1024*1024)) for p in own};input_hashes={}
    for source in sources:
        directory,_,_,_,_=source_data(source)
        names=[n+'.f32le' for n in BANKS]+['selector.csv']+(['gates.bin'] if source['kind']=='field' else ['near.f32le','true_echo.f32le'])
        for name in names:input_hashes[str(directory/name)]=sha(bounded(directory/name,4*1024*1024))
    output.mkdir();created.append(output)
    logged(output,'compile',['cc',*FLAGS,'-ffp-contract=off',str(C),'-lm','-o',str(output/'runner')],ROOT)
    runner_hash=sha((output/'runner').read_bytes())
    logged(output,'self-test',[str(output/'runner'),'--self-test'],ROOT)
    logged(output,'invalid',[str(output/'runner'),'invalid'],ROOT,expected=2)
    for label,frames,dwell,mode in [('frames','bad','50','normal'),('dwell','1','49','normal'),('mode','1','50','bad'),('future','1','0','future')]:
        directory=output/('invalid-preserve-'+label);directory.mkdir()
        sentinels={name:b'D27_SENTINEL '+name.encode('ascii') for name in ('echo.f32le','residual.f32le','selector.csv')}
        for name,data in sentinels.items():(directory/name).write_bytes(data)
        logged(output,'invalid-preserve-'+label,[str(output/'runner'),*['missing']*5,frames,dwell,str(directory),mode],ROOT,expected=2)
        require({p.name:p.read_bytes() for p in directory.iterdir()}==sentinels,'invalid preservation')
        require(read_json(output/('command-invalid-preserve-'+label+'.json'))['stderr']=='D27_INVALID_ARGUMENT_REJECT selector_calls=0\n','invalid zero calls')
    jobs=[(s,mode,False,None) for s in sources for mode in ('legacy','dwell')]
    anchor=next(s for s in sources if s['kind']=='field' and s['case']['name']=='case-07-used0-shadow')
    jobs += [(anchor,'dwell',False,'repeat'),(anchor,'dwell',True,'future')]
    cases=[]
    for source,mode,future,label in jobs:
        original,_,_,gates,n=source_data(source);name=label or source['kind']+'-'+source['case']['name']+'-'+mode
        directory=output/name;directory.mkdir();gate_data=bytes(v for row in gates for v in row);(directory/'gates.bin').write_bytes(gate_data)
        execution=strict_json(logged(output,name,[str(output/'runner'),*[str(original/(t+'.f32le')) for t in BANKS],str(directory/'gates.bin'),
                              str(n//160),'50' if mode=='dwell' else '0',str(directory),'future' if future else 'normal'],ROOT).encode())
        observation=observe(directory,source,mode,future,execution)
        if not observation['events'] and not future:
            for t in ('echo','residual'):require((directory/(t+'.f32le')).read_bytes()==(original/(t+'.f32le')).read_bytes(),'static unchanged')
        cases.append(dict(name=name,kind=source['kind'],source_case=source['case']['name'],source_directory=str(original),mode=mode,future=future,
                          gate_binary_sha256=sha(gate_data),execution_summary=execution,observation=observation))
    first=anchor['case']['notify_frame'];normal=output/'field-case-07-used0-shadow-dwell'
    for name in ('echo.f32le','residual.f32le','selector.csv'):
        a=(normal/name).read_bytes();require(a==(output/'repeat'/name).read_bytes(),'repeat')
        b=(output/'future'/name).read_bytes()
        require(a[:first*160*4]==b[:first*160*4] if name.endswith('.f32le') else a.splitlines()[:first+1]==b.splitlines()[:first+1],'future prefix')
    acceptance=candidate_checks(cases)
    preflight(root)
    require(initial=={p:sha(bounded(Path(p),4*1024*1024)) for p in initial} and
            input_hashes=={p:sha(bounded(Path(p),4*1024*1024)) for p in input_hashes} and sha((output/'runner').read_bytes())==runner_hash,'identity drift')
    dump(output/'result.json',dict(experiment='FE_DEVICE_DWELL_D27',executions=90,data_role='development-and-synthetic-engineering',
        decision='DWELL_DEVELOPMENT_CANDIDATE_ONLY' if acceptance['accepted'] else 'DWELL_DEVELOPMENT_REJECTED',
        research_algorithm_changed=True,shipping_algorithm_changed=False,promotion_allowed=False,shipping_approved=False,
        selector=dict(ratio=0.8,confirmation_frames=3,dwell_frames=50,minimum_switch_gap_frames=52,crossfade=False),
        resources=dict(selection_state_bytes=cases[0]['execution_summary']['selection_state_bytes'],aec_calls=0,scope='selector sizeof/calls only; no DUT cost'),
        cases=cases,acceptance=acceptance))
    dump(output/'binding.json',dict(source_files=initial,input_files=input_hashes,baseline_hashes=HASHES,runner_sha256=runner_hash,
        source_start_end_equal=True,input_start_end_equal=True,
        artifacts={str(p.relative_to(output)):sha(p.read_bytes()) for p in sorted(output.rglob('*')) if p.is_file()}))
    print('D27_MEASUREMENT_PASS 90 selector executions '+('CANDIDATE_ONLY' if acceptance['accepted'] else 'CANDIDATE_REJECTED'),flush=True)


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--root',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True);parser.add_argument('--dry-run',action='store_true')
    args=parser.parse_args(argv);created=[]
    try:
        if args.dry_run:print('D27_PREFLIGHT_PASS',len(preflight(args.root)),'sources; writes=False')
        else:run(args.root,args.output,created)
        return 0
    except (ValueError,OSError,KeyError,TypeError,subprocess.TimeoutExpired) as error:
        if created==[args.output]:dump(args.output/'measurement-invalid.json',dict(decision='MEASUREMENT_INVALID',error=str(error)))
        print('device_dwell: '+str(error),file=sys.stderr);return 2


if __name__=='__main__':raise SystemExit(main())
