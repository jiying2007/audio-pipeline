"""D30 actual Activity integration; frozen DSP, development diagnostic only."""
from __future__ import annotations
import argparse
import csv
import io
import math
from pathlib import Path
import struct
import subprocess
import sys
if __package__ in (None,''):sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from tools.codex_assets.device_capture import ROOT,bounded,require,sha,strict_json
from tools.codex_assets.device_exact_reference import dump,logged,read_json
from tools.codex_assets.device_online import preflight as previous_preflight,input_info,OUTPUTS as OLD_OUTPUTS,TRACES,LIB_SHA
from tools.codex_assets.device_transition import mix,FIELDS as TRANS_FIELDS
from tools.codex_assets.device_dwell import FIELDS as SELECT_FIELDS,recurrence,score
from tools.codex_assets.device_stages import D18,floats
from tools.codex_assets.device_path import encoded
from tools.codex_assets.device_replay import FLAGS
BASE=Path('/tmp/audio-fe-device-online-d29-20261011')
HASHES={'result.json':'9ed85b81ee3487919b00cf441e84757c1fc7c72deb611cfdedf8c1944e0fa4ab','binding.json':'2120e2e139584972311fa2ac9a47b5984acf1159fb21d8234438846e49078520'}
PLAN=ROOT/'docs/research/frontend-evolution-v1/DEVICE_ACTIVITY_D30_PLAN.zh-CN.md'
AMEND=ROOT/'docs/research/frontend-evolution-v1/DEVICE_ACTIVITY_D30_AMENDMENT.zh-CN.md'
C=ROOT/'tests/validation/frontend_evolution/device_activity_d30.c'
TEST=C.parent/'test_device_activity.py'
OUTPUTS=(*OLD_OUTPUTS,'activity.csv')
ACT_FIELDS=['frame','mic_energy','reference_energy','smoothed_mic_energy','smoothed_reference_energy','far_hangover','dt_hangover','far','dt']
STATE_FIELDS=['frame','runtime_stride','steady_frames','adapt_phase','constrain_partition','x_head','x_power_total','weight_l2']

def f32(v):return struct.unpack('<f',struct.pack('<f',v))[0]

def frame_energy(values):
    require(len(values)==160 and all(math.isfinite(v) for v in values),'Activity finite 160-sample input')
    total=f32(1e-12)
    for v in values:total=f32(total+f32(v*v))
    return f32(total/160)

def activity_step(state,mic,ref):
    require(math.isfinite(mic) and math.isfinite(ref) and mic>=0 and ref>=0,'Activity nonnegative finite energy')
    sm,sr,fh,dh=state
    def smooth(old,v):return v if old<=0 else f32(old+f32(f32(.35 if v>old else .08)*f32(v-old)))
    sm,sr=smooth(sm,mic),smooth(sr,ref);threshold=f32(1e-7)
    if sr>threshold:fh=2
    elif sr<f32(f32(.55)*threshold):fh=max(0,fh-1)
    far=int(fh>0 or sr>threshold)
    ratio=f32(sm/f32(sr+f32(1e-12)));instant=f32(mic/f32(ref+f32(1e-12)))
    onset=far and ratio>f32(1.5) and instant>f32(f32(.90)*f32(1.5))
    hold=far and instant>f32(f32(.72)*f32(1.5))
    if onset:dh=3
    elif not hold:dh=max(0,dh-1)
    return (sm,sr,fh,dh),(far,int(far and dh>0))

def preflight(root):
    sources=previous_preflight(root)
    for name,expected in HASHES.items():require(sha(bounded(BASE/name,4*1024*1024))==expected,'D29 identity')
    binding=read_json(BASE/'binding.json')
    for group in ('source_files','input_files','artifacts'):
        for name,expected in binding[group].items():require(sha(bounded(BASE/name if group=='artifacts' else Path(name),4*1024*1024))==expected,'D29 drift')
    old=read_json(BASE/'result.json')['cases'];require(len(old)==46,'D29 case set')
    for s in sources:
        s['online']=next(c for c in old if c['name']==s['kind']+'-'+s['case']['name'])
    return sources

def runner_command(runner,source,directory,future):
    _,mic,ref,_,n,notify=input_info(source)
    return [str(runner),str(mic),str(ref),str(n//160),'none' if notify is None else str(notify),str(directory),'future' if future else 'normal']

def observe(directory,source,future,execution):
    original,mic_path,ref_path,old_gates,n,notify=input_info(source)
    values={k:floats(directory/(k+'.f32le'),n) for k in TRACES}
    for k,p in [('mic',mic_path),('reference',ref_path)]:
        expected=floats(p,n)
        if future:expected=[-v if i>=notify*160 else v for i,v in enumerate(expected)]
        require((directory/(k+'.f32le')).read_bytes()==encoded(expected),'actual inputs '+k)
    tables=[]
    for name,fields in [('activity.csv',ACT_FIELDS),('selector.csv',SELECT_FIELDS),('transition.csv',TRANS_FIELDS),('state.csv',STATE_FIELDS)]:
        reader=csv.DictReader(io.StringIO(bounded(directory/name,1024*1024).decode('ascii')))
        require(reader.fieldnames==fields,'CSV schema');rows=list(reader)
        require(len(rows)==n//160 and all(all(math.isfinite(float(v)) for v in r.values()) for r in rows),'CSV finite/count');tables.append(rows)
    activity,selectors,transitions,states=tables
    require(all(r['frame']==str(i) and int(r['runtime_stride'])==2 and int(r['adapt_phase']) in (0,1) and
        float(r['x_power_total'])>=0 and float(r['weight_l2'])>=0 for i,r in enumerate(states)),'primary diagnostic CSV')
    state=(0.0,0.0,0,0);gates=[];disagreement={'far':0,'dt':0,'either':0}
    for frame,row in enumerate(activity):
        a,b=frame*160,(frame+1)*160;me,re=frame_energy(values['mic'][a:b]),frame_energy(values['reference'][a:b]);state,flag=activity_step(state,me,re)
        require(row['frame']==str(frame) and [f32(float(row[k])) for k in ACT_FIELDS[1:5]]==[me,re,state[0],state[1]] and
            [int(row[k]) for k in ACT_FIELDS[5:]]==[state[2],state[3],*flag],'actual Activity recurrence')
        gates.extend(flag);old=old_gates[2*frame:2*frame+2]
        disagreement['far']+=flag[0]!=old[0];disagreement['dt']+=flag[1]!=old[1];disagreement['either']+=tuple(old)!=flag
    bank=streak=from_bank=pos=remaining=mixed=0;last_switch=None;expected={k:[] for k in ('echo','residual')};events=[]
    for frame,(sel,tr) in enumerate(zip(selectors,transitions)):
        a,b=frame*160,(frame+1)*160;far,dt=gates[2*frame:2*frame+2];active=int(notify is not None and frame>=notify);before=bank
        pe=sum(v*v for v in values['primary_residual'][a:b]);se=sum(v*v for v in values['shadow_residual'][a:b])
        bank,streak,last_switch,change,hold=recurrence(bank,streak,last_switch,frame,50,active,far and not dt,pe,se)
        require([sel[k] for k in SELECT_FIELDS[:7]]==[str(frame),str(active),str(far),str(dt),str(bank),str(streak),str(change)] and
            float(sel['primary_energy'])==pe and float(sel['shadow_energy'])==se and int(sel['hold_remaining'])==hold,'actual selection')
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
            int(tr['remaining_after_frame'])==remaining and float(tr['alpha_first'])==first and float(tr['alpha_last'])==last,'actual transition')
    for k in expected:require((directory/(k+'.f32le')).read_bytes()==encoded(expected[k]),'actual exact mix')
    algebra={}
    for label in ('selected','primary','shadow'):
        first=notify*160 if label=='shadow' and notify is not None else n if label=='shadow' else 0
        if first==n:continue
        prefix='' if label=='selected' else label+'_'
        algebra[label]=max(abs(values[prefix+'echo'][i]+values[prefix+'residual'][i]-values['mic'][i]) for i in range(first,n));require(algebra[label]<=1e-6,'mic algebra')
    fixed=dict(frames=n//160,samples=n,primary_calls=n//160,shadow_calls=n//160-notify if notify is not None else 0,shadow_reset_calls=int(notify is not None),
        selector_calls=n//160,transition_calls=n//160,mixed_samples=mixed,remaining=remaining,switch_count=len(events),sync_calls=0,aec_state_bytes=33020,two_aec_state_bytes=66040,
        selector_state_bytes=20,transition_state_bytes=16,frame_buffer_bytes=5120,scoped_bytes=71224,activity_calls=n//160,activity_state_bytes=28)
    require(all(type(v) is int for v in execution.values()) and execution==fixed and fixed['scoped_bytes']<=131072,'actual counts/resources')
    baseline=BASE/('future' if future else source['online']['name']);equivalence={p:(directory/p).read_bytes()==bounded(baseline/p,4*1024*1024) for p in OLD_OUTPUTS}
    if source['kind']=='field':require(all(equivalence.values()) and not any(disagreement.values()),'field baseline/gates byte equality')
    measurement=None;deltas=[]
    if not future:
        if source['kind']=='return':
            for k in ('near','true_echo'):values[k]=floats(original/(k+'.f32le'),n)
        measurement=score(source,values);previous=source['online']['observation']['measurement']
        for old,new in zip([previous['whole'],*previous['windows']],[measurement['whole'],*measurement['windows']]):
            require(old['sample_range']==new['sample_range'] and {k:v is None for k,v in old['channels'].items()}=={k:v is None for k,v in new['channels'].items()},'old ranges/null')
            d=dict(sample_range=old['sample_range'],selected_residual_rms_db_delta=new['channels']['selected']['residual']['rms_dbfs']-old['channels']['selected']['residual']['rms_dbfs'])
            if source['kind']=='return':d['selected_error_rms_db_delta']=new['channels']['selected']['error']['rms_dbfs']-old['channels']['selected']['error']['rms_dbfs']
            deltas.append(d)
        if source['kind']=='field':require(measurement==previous,'field score equality')
    return dict(events=events,measurement=measurement,algebra_max_abs_error=algebra,external_gate_disagreement=disagreement,baseline_file_equivalence=equivalence,deltas=deltas)

def run(root,output,created):
    sources=preflight(root);require(not output.exists() and not output.is_symlink() and Path('/tmp') in output.resolve().parents,'new /tmp output required')
    own=[Path(__file__).resolve(),PLAN,AMEND,C,TEST,ROOT/'tools/codex_assets/device_online.py',C.parent/'device_online_d29.c',D18/'build/CMakeFiles/audio_pipeline.dir/flags.make',D18/'build/libaudio_pipeline.a']
    own.extend(C.parent/p for p in ('device_field_d26.c','device_dwell_selector_d27.h','device_shadow_selector_d24.h','device_transition_d28.h'))
    own.extend(D18/'source'/p for p in ('src/activity/ap_activity.c','src/activity/ap_activity.h','src/core/ap_pipeline.c'))
    initial={str(p):sha(bounded(p,4*1024*1024)) for p in own};inputs={}
    for s in sources:
        original,mic,ref,_,_,_=input_info(s);paths=[mic,ref,original/('gates.bin' if s['kind']=='field' else 'selector.csv')]
        if s['kind']=='return':paths.extend(original/(k+'.f32le') for k in ('near','true_echo'))
        for p in paths:inputs[str(p)]=sha(bounded(p,4*1024*1024))
    output.mkdir();created.append(output);flags=(D18/'build/CMakeFiles/audio_pipeline.dir/flags.make').read_text()
    definitions=[r.split('=',1)[1].split() for r in flags.splitlines() if r.startswith('C_DEFINES =')];require(len(definitions)==1 and definitions[0] and all(v.startswith('-DAP_BUILD_') for v in definitions[0]),'definitions')
    logged(output,'compile',['cc',*FLAGS,'-ffp-contract=off',*definitions[0],'-I',str(D18/'source/src'),'-I',str(D18/'source/include'),'-I',str(D18/'build/generated'),str(C),str(D18/'build/libaudio_pipeline.a'),'-lm','-lpthread','-o',str(output/'runner')],ROOT)
    runner_sha=sha((output/'runner').read_bytes());logged(output,'self-test',[str(output/'runner'),'--self-test'],ROOT);logged(output,'invalid',[str(output/'runner'),'invalid'],ROOT,expected=2)
    for label,frames,notify,mode in [('frames','bad','none','normal'),('notify','1','1','normal'),('mode','1','none','bad'),('future','1','none','future')]:
        d=output/('invalid-preserve-'+label);d.mkdir();sentinels={p:b'D30_SENTINEL '+p.encode() for p in OUTPUTS}
        for p,data in sentinels.items():(d/p).write_bytes(data)
        logged(output,'invalid-preserve-'+label,[str(output/'runner'),'missing','missing',frames,notify,str(d),mode],ROOT,expected=2)
        require({p.name:p.read_bytes() for p in d.iterdir()}==sentinels,'invalid preservation')
        require(read_json(output/('command-invalid-preserve-'+label+'.json'))['stderr']=='D30_INVALID_ARGUMENT_REJECT primary_calls=0 shadow_calls=0 activity_calls=0\n','invalid zero calls')
    anchor=next(s for s in sources if s['kind']=='field' and s['case']['name']=='case-07-used0-shadow');jobs=[(s,False,None) for s in sources]+[(anchor,False,'repeat'),(anchor,True,'future')];cases=[]
    for s,future,label in jobs:
        original,_,_,_,_,notify=input_info(s);name=label or s['kind']+'-'+s['case']['name'];directory=output/name;directory.mkdir()
        execution=strict_json(logged(output,name,runner_command(output/'runner',s,directory,future),ROOT).encode());observation=observe(directory,s,future,execution)
        cases.append(dict(name=name,kind=s['kind'],source_case=s['case']['name'],source_directory=str(original),future=future,notify_frame=notify,execution_summary=execution,observation=observation));print('D30_CASE_PASS '+name,flush=True)
    normal=output/'field-case-07-used0-shadow';notify=anchor['case']['notify_frame']
    for p in OUTPUTS:
        a=(normal/p).read_bytes();b=(output/'future'/p).read_bytes();require(a==(output/'repeat'/p).read_bytes(),'repeat all outputs')
        require(a[:notify*160*4]==b[:notify*160*4] if p.endswith('.f32le') else a.splitlines()[:notify+1]==b.splitlines()[:notify+1],'future all prefixes')
    require((normal/'activity.csv').read_bytes()==(output/'future/activity.csv').read_bytes(),'future Activity all equality');preflight(root)
    require(initial=={p:sha(bounded(Path(p),4*1024*1024)) for p in initial} and inputs=={p:sha(bounded(Path(p),4*1024*1024)) for p in inputs} and sha((output/'runner').read_bytes())==runner_sha,'source/input/runner drift')
    dump(output/'result.json',dict(experiment='FE_DEVICE_ACTIVITY_D30',executions=46,data_role='development-and-synthetic-engineering',decision='ACTIVITY_INTEGRATION_DIAGNOSTIC_NO_PROMOTION',research_algorithm_changed=False,
        integration_changed=True,shipping_algorithm_changed=False,promotion_allowed=False,shipping_approved=False,cases=cases,
        resource_budget=dict(scoped_bytes=71224,budget_bytes=131072,b0_arena_bytes=50000,b0_changed=False,target_resource_qualified=False)))
    dump(output/'binding.json',dict(source_files=initial,input_files=inputs,baseline_hashes=HASHES,library_sha256=LIB_SHA,runner_sha256=runner_sha,source_start_end_equal=True,input_start_end_equal=True,
        artifacts={str(p.relative_to(output)):sha(p.read_bytes()) for p in sorted(output.rglob('*')) if p.is_file()}));print('D30_MEASUREMENT_PASS 46 actual Activity integrations NO_PROMOTION',flush=True)

def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--root',type=Path,required=True);parser.add_argument('--output',type=Path,required=True);parser.add_argument('--dry-run',action='store_true');args=parser.parse_args(argv);created=[]
    try:
        if args.dry_run:print('D30_PREFLIGHT_PASS',len(preflight(args.root)),'sources; writes=False')
        else:run(args.root,args.output,created)
        return 0
    except (ValueError,OSError,KeyError,TypeError,OverflowError,subprocess.TimeoutExpired) as error:
        if created==[args.output]:dump(args.output/'measurement-invalid.json',dict(decision='MEASUREMENT_INVALID',error=str(error)))
        print('device_activity: '+str(error),file=sys.stderr);return 2
if __name__=='__main__':raise SystemExit(main())
