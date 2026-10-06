#!/usr/bin/env python3
"""FE04 fixed render/capture transport faults through the existing public SYNC module."""
from __future__ import annotations
import argparse, array, csv, json, math, shutil, statistics, subprocess, sys, tempfile
from pathlib import Path
import activity_gates as activity
import bf_aec_order as order
import correlation_guard as guard
import speech_spatial as speech
from contracts import ROOT, hex_digest, load_json, require, sha256
from libfvad_reference import write_json, seal_output, run_logged
from speech_fir import verify_seal

HERE=Path(__file__).resolve().parent
PLAN=ROOT/'.github/research/frontend-evolution-v1/sync-faults-v1.json'
RUNNER=HERE/'sync_fault_runner.c'
DECISION='SYNC_FAULTS_DIAGNOSTIC_NO_PROMOTION'
ROLE='DISCLOSED_DEVELOPMENT_DIAGNOSTIC_NOT_HOLDOUT'
RATE,HOP,N=16000,160,256000
FAULTS=('static','route','drift')
ARMS=('oracle','raw','sync')
LABELS=('native','sanitized','arm')
HEADER=['frame','known_lead_samples','pushed_samples','sync_delay_samples','delay_error_samples',
        'estimated_drift_ppm','reference_sample_slips','delay_observed','route_jump','underrun',
        'mic_energy','reference_energy','used_far','used_dt']
CFLAGS=['-std=c11','-O2','-Wall','-Wextra','-Wpedantic','-Werror','-ffp-contract=off']

def packed(values):
    a=array.array('f',values)
    if sys.byteorder!='little':a.byteswap()
    return a.tobytes()

def floats(path,count=None):
    return order.floats(path,count)

def expected_lead(fault,frame,frames):
    end=(frame+1)*HOP
    if fault=='route':return 800 if frame>=frames//2 else 320
    if fault=='drift':return 320+(end*250)//1000000
    return 320

def trace_rows(path,fault,arm,frames):
    rows=[];cursor=0
    with path.open(newline='') as f:
        rd=csv.DictReader(f);require(rd.fieldnames==HEADER,'trace schema')
        for index,row in enumerate(rd):
            require(index<frames and None not in row.values(),'trace count/partial')
            item={}
            for key in HEADER:
                if key in ('estimated_drift_ppm','mic_energy','reference_energy'):
                    v=float(row[key]);require(math.isfinite(v),'nonfinite trace');item[key]=v
                else:item[key]=int(row[key])
            require(item['frame']==index,'trace order')
            lead=expected_lead(fault,index,frames);desired=(index+1)*HOP+lead;pushed=desired-cursor;cursor=desired
            require(item['known_lead_samples']==lead and item['pushed_samples']==pushed,'transport schedule drift')
            require(item['used_far'] in (0,1) and item['used_dt'] in (0,1),'gate flag')
            if arm!='sync':
                require(all(item[k]==0 for k in ('sync_delay_samples','delay_error_samples','reference_sample_slips',
                    'delay_observed','route_jump','underrun')) and item['estimated_drift_ppm']==0.0,'non-sync fabricated state')
            else:
                require(item['delay_observed'] in (0,1) and item['route_jump'] in (0,1) and item['underrun'] in (0,1),'sync flag')
            rows.append(item)
    require(len(rows)==frames,'trace frame count')
    return rows

def median_int(rows,key):
    return float(statistics.median([r[key] for r in rows]))

def alignment(rows,fault):
    pre=rows[500:590];post=rows[1200:1390]
    est_pre=median_int(pre,'sync_delay_samples');est_post=median_int(post,'sync_delay_samples')
    lead_pre=median_int(pre,'known_lead_samples');lead_post=median_int(post,'known_lead_samples')
    first_route=next((r['frame'] for r in rows if r['frame']>=800 and r['route_jump']),None)
    return {'baseline_delay_samples':est_pre,'post_delay_samples':est_post,
      'estimated_delay_change_samples':est_post-est_pre,'injected_lead_change_samples':lead_post-lead_pre,
      'delay_change_error_samples':(est_post-est_pre)-(lead_post-lead_pre),
      'route_jump_first_frame':first_route,
      'route_jump_latency_ms':None if first_route is None else (first_route-800)*10,
      'route_jump_events':sum(r['route_jump'] for r in rows),'reference_sample_slips':sum(r['reference_sample_slips'] for r in rows),
      'underruns':sum(r['underrun'] for r in rows),'delay_observations':sum(r['delay_observed'] for r in rows),
      'post_median_drift_ppm':statistics.median([r['estimated_drift_ppm'] for r in post]),
      'final_delay_samples':rows[-1]['sync_delay_samples'],'final_drift_ppm':rows[-1]['estimated_drift_ppm'],
      'fault':fault}

def windows(actual,echo):
    rows=[]
    for k in range(0,N,1600):
        ee=sum(v*v for v in echo[k:k+1600])/1600;rr=sum(v*v for v in actual[k:k+1600])/1600
        valid=21<=k//1600<60 or 101<=k//1600<140
        rows.append({'start_sample':k,'echo_energy':ee,'residual_energy':rr,
          'erle_db':10*math.log10(ee/max(rr,1e-30)) if valid and ee>1e-12 else None})
    return rows

def metrics(target,echo,actual,fault):
    w=windows(actual,echo);phases={}
    for tag,a,b in [('near-initial',.1,1.9),('double-before',6.1,7.9),('double-after',8.1,9.9),('near-final',14.1,15.9)]:
        lo,hi=int(a*RATE),int(b*RATE);phases[tag]=speech.si_sdr_span(target,actual,lo,lo,hi-lo)
    base=order.recovery(w);recovery=base['recovery_after_event_ms'] if fault=='route' else None
    ee=sum(x['echo_energy'] for x in w[120:139]);rr=sum(x['residual_energy'] for x in w[120:139])
    final=10*math.log10(ee/max(rr,1e-30)) if ee/19>1e-12 else None
    return {'phases_si_sdr_relative_to_bf_target_db':phases,'far_only_windows':w,'final_far_ratio_db':final,
      'baseline_erle_db':base['baseline_erle_db'],'recovery_after_event_ms':recovery,
      'recovery_confirmed_after_event_ms':None if recovery is None else recovery+300}

def selected(base):
    rows=[x for x in load_json(base/'order/result.json')['cases'] if x['geometry']=='ula4-70' and x['bank']=='fir33' and x['event']=='none']
    require(len(rows)==2 and {x['pair'] for x in rows}=={0,1},'fixed no-event pair selection')
    return sorted(rows,key=lambda x:x['pair'])

def make_input(base,correlation,row,dest):
    raw=floats(base/'order/cases'/row['case_id']/'output.f32',N*6)
    observed=floats(correlation/'cases'/row['case_id']/'guard.csv.observed.f32',N*2)
    target=list(raw[0::6]);echo=list(raw[1::6]);mic=list(observed[0::2]);ref=list(observed[1::2])
    require(max(abs(mic[k]-float(target[k])-float(echo[k])) for k in range(N))<=5e-6,'BF observation/component disagreement')
    data=array.array('f')
    for k in range(N):data.extend((mic[k],target[k],echo[k],ref[k]))
    if sys.byteorder!='little':data.byteswap()
    dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(data.tobytes())
    receipt={'sha256':sha256(dest.read_bytes()),'samples':N,'columns':['mic','bf_target','known_echo','physical_render'],
      'mic_sha256':sha256(packed(mic)),'target_sha256':sha256(packed(target)),'echo_sha256':sha256(packed(echo)),'render_sha256':sha256(packed(ref))}
    write_json(dest.with_suffix('.json'),receipt);return receipt

def build(root,revision,label):
    arm=label=='arm';san=label=='sanitized';cc='arm-linux-gnueabihf-gcc' if arm else 'cc'
    flags=['-O1','-g','-fsanitize=address,undefined','-fno-omit-frame-pointer'] if san else ['-O2']
    b=root/('build-'+label)
    opts=['cmake','-S',ROOT,'-B',b,'-DCMAKE_BUILD_TYPE=Release','-DCMAKE_C_COMPILER='+cc,
      '-DCMAKE_C_FLAGS='+' '.join(flags+['-ffp-contract=off']),'-DAP_BUILD_SOURCE_REVISION='+revision,
      '-DAP_BUILD_PIPELINE=OFF','-DAP_MODULES=SYNC,ACTIVITY,AEC','-DAP_AEC_BACKEND=MDF','-DAP_SIMD_BACKEND=SCALAR',
      '-DAP_BUILD_TESTS=OFF','-DAP_BUILD_BENCH=OFF','-DAP_BUILD_EXAMPLES=OFF','-DAP_ENABLE_LINUX_RUNTIME=OFF',
      '-DAP_BUILD_MAX_AEC_TAIL_MS=64','-DAP_BUILD_MAX_DELAY_MS=120','-DAP_STRICT_WARNINGS=ON']
    if arm:opts+=['-DCMAKE_SYSTEM_NAME=Linux','-DCMAKE_SYSTEM_PROCESSOR=arm']
    run_logged(opts,root/(label+'-configure.log'));run_logged(['cmake','--build',b,'--parallel','2'],root/(label+'-build.log'))
    binary=root/('sync-fault-'+label)
    cmd=[cc,*CFLAGS,*(['-O1','-g','-fsanitize=address,undefined','-fno-omit-frame-pointer'] if san else []),
      '-I'+str(ROOT/'include'),'-I'+str(b/'generated'),RUNNER,b/'libaudio_pipeline.a','-lm','-o',binary]
    link_log=root/(label+'-link.log')
    try:
        run_logged(cmd,link_log)
    except ValueError:
        if link_log.exists():
            print(link_log.read_text(errors='replace'),file=sys.stderr)
        raise
    run_logged([cc,'--version'],root/(label+'-compiler.txt'))
    shutil.copyfile(b/'generated/audio_pipeline/audio_pipeline_build.h',root/(label+'-build.h'))
    shutil.copyfile(b/'libaudio_pipeline.a',root/(label+'-library.a'))
    if arm:run_logged(['arm-linux-gnueabihf-readelf','-h',binary],root/'arm-elf.txt')
    write_json(root/(label+'-build.json'),{'source_revision':revision,'processor_sha256':sha256(binary.read_bytes()),
      'library_sha256':sha256((root/(label+'-library.a')).read_bytes()),'compiler':cc,'sanitized':san,'arm':arm,
      'configure':list(map(str,opts)),'link':list(map(str,cmd))})
    shutil.rmtree(b);return binary

def command(binary,arm,fault,inp,dest,under_arm=False):
    prefix=['qemu-arm','-L','/usr/arm-linux-gnueabihf'] if under_arm else []
    return [*prefix,binary,arm,fault,inp,dest.with_suffix('.f32'),dest.with_suffix('.json'),dest.with_suffix('.csv')]

def execute(binary,arm,fault,inp,dest,under_arm=False):
    run_logged(command(binary,arm,fault,inp,dest,under_arm),dest.with_suffix('.log'))

def engineering(root,binary,label):
    root.mkdir();under_arm=label=='arm';count=32000;seed=1907;far=[];target=[]
    for k in range(count):
        seed=(1664525*seed+1013904223)&0xffffffff;far.append(((seed>>8)/16777216-.5)*.15)
        target.append((.06*math.sin(.019*k)+.025*math.cos(.041*k)) if 9000<=k<19000 else 0.0)
    echo=[(.55*far[k-64] if k>=64 else 0)+(-.18*far[k-173] if k>=173 else 0) for k in range(count)]
    data=array.array('f')
    for k in range(count):data.extend((target[k]+echo[k],target[k],echo[k],far[k]))
    if sys.byteorder!='little':data.byteswap()
    inp=root/'input.f32';inp.write_bytes(data.tobytes());records=[]
    for fault in FAULTS:
        dest=root/('sync-'+fault);execute(binary,'sync',fault,inp,dest,under_arm)
        rows=trace_rows(dest.with_suffix('.csv'),fault,'sync',count//HOP);meta=load_json(dest.with_suffix('.json'))
        require(meta['status']=='PASS' and meta['route_jump_resets_aec'] is False and meta['samples']==count,'engineering identity')
        records.append({'fault':fault,'sha256':sha256(dest.with_suffix('.f32').read_bytes()),'route_jumps':sum(x['route_jump'] for x in rows)})
    for arm in ('oracle','raw'):
        dest=root/(arm+'-static');execute(binary,arm,'static',inp,dest,under_arm);trace_rows(dest.with_suffix('.csv'),'static',arm,count//HOP)
    execute(binary,'sync','static',inp,root/'repeat',under_arm)
    for suffix in ('.f32','.json','.csv'):require((root/('sync-static'+suffix)).read_bytes()==(root/('repeat'+suffix)).read_bytes(),'engineering repeat')
    changed=array.array('f');changed.frombytes(inp.read_bytes())
    if sys.byteorder!='little':changed.byteswap()
    for k in range(21000,count):
        changed[k*4]*=-1;changed[k*4+1]*=-1;changed[k*4+2]*=-1;changed[k*4+3]*=-1
    future=root/'future-input.f32';future.write_bytes(packed(changed))
    execute(binary,'sync','static',future,root/'future-output',under_arm)
    a=floats(root/'sync-static.f32');b=floats(root/'future-output.f32')
    require(a[:19000*2]==b[:19000*2] and a[22000*2:]!=b[22000*2:],'engineering future causality')
    bad=root/'partial.f32';bad.write_bytes(b'\0')
    p=subprocess.run(list(map(str,command(binary,'sync','static',bad,root/'bad',under_arm))),capture_output=True)
    require(p.returncode!=0,'partial input accepted');(root/'bad.log').write_bytes(p.stderr)
    before=(root/'sync-static.f32').read_bytes();p=subprocess.run(list(map(str,command(binary,'sync','static',inp,root/'sync-static',under_arm))),capture_output=True)
    require(p.returncode!=0 and before==(root/'sync-static.f32').read_bytes(),'overwrite accepted');(root/'overwrite.log').write_bytes(p.stderr)
    p=subprocess.run(list(map(str,command(binary,'wrong','static',inp,root/'wrong',under_arm))),capture_output=True)
    require(p.returncode!=0,'invalid arm accepted');(root/'wrong.log').write_bytes(p.stderr)
    result={'status':'PASS','label':label,'samples':count,'records':records,'repeat':True,'future':True,'invalid_rejected':True,'overwrite_rejected':True}
    write_json(root/'result.json',result);return result

def run(base,correlation,root,revision):
    require(not root.exists() and hex_digest(revision,40),'fresh output/exact revision')
    activity.verify(base/'order',base/'activity',revision);guard.verify(base,correlation,revision)
    root.mkdir(parents=True);shutil.copyfile(PLAN,root/'experiment.json');(root/'source').mkdir()
    for p in (RUNNER,Path(__file__)):shutil.copyfile(p,root/'source'/p.name)
    bins={};tests={}
    for label in LABELS:bins[label]=build(root,revision,label);tests[label]=engineering(root/('engineering-'+label),bins[label],label)
    cases=[]
    for old in selected(base):
        pair=old['pair'];inp=root/'inputs'/f'p{pair}.f32';receipt=make_input(base,correlation,old,inp)
        for fault in FAULTS:
            key=f'p{pair}-{fault}';d=root/'cases'/key;d.mkdir(parents=True);results={}
            source=floats(inp,N*4);target=list(source[1::4]);echo=list(source[2::4])
            for arm in ARMS:
                dest=d/arm;execute(bins['native'],arm,fault,inp,dest);execute(bins['native'],arm,fault,inp,d/(arm+'-repeat'))
                for suffix in ('.f32','.json','.csv'):require((d/(arm+suffix)).read_bytes()==(d/(arm+'-repeat'+suffix)).read_bytes(),'full repeat')
                raw=floats(d/(arm+'.f32'),N*2);actual=list(raw[0::2]);rows=trace_rows(d/(arm+'.csv'),fault,arm,N//HOP)
                results[arm]={'metrics':metrics(target,echo,actual,fault),'alignment':alignment(rows,fault) if arm=='sync' else None,
                  'meta':load_json(d/(arm+'.json'))}
                write_json(d/(arm+'-repeat-receipt.json'),{'output_sha256':sha256((d/(arm+'.f32')).read_bytes()),
                  'meta_sha256':sha256((d/(arm+'.json')).read_bytes()),'trace_sha256':sha256((d/(arm+'.csv')).read_bytes())})
                for suffix in ('.f32','.json','.csv'):(d/(arm+'-repeat'+suffix)).unlink()
            cases.append({'case_id':key,'pair':pair,'fault':fault,'input':inp.relative_to(root).as_posix(),'input_receipt':receipt,'arms':results})
    report={'schema_version':1,'experiment_id':'FE04-SYNC-FAULTS-V1','decision':DECISION,'shipping_authority':False,'data_role':ROLE,
      'execution_source_revision':revision,'case_count':6,'arms':3,'cases':cases,'engineering':tests,
      'order_manifest_sha256':sha256((base/'order/manifest.json').read_bytes()),'activity_manifest_sha256':sha256((base/'activity/manifest.json').read_bytes()),
      'correlation_manifest_sha256':sha256((correlation/'manifest.json').read_bytes()),'timing_authority':'NONE_TARGET',
      'route_jump_resets_aec':False,'timestamp_assistance':False,'res_enabled':False}
    write_json(root/'result.json',report);seal_output(root,report);return report

def verify(base,correlation,root,revision):
    verify_seal(root);activity.verify(base/'order',base/'activity',revision);guard.verify(base,correlation,revision)
    r=load_json(root/'result.json');p=load_json(PLAN)
    require((root/'experiment.json').read_bytes()==PLAN.read_bytes(),'plan drift')
    require(r['decision']==DECISION and r['shipping_authority'] is False and r['data_role']==ROLE and r['case_count']==6 and r['arms']==3,'authority/matrix')
    require(r['execution_source_revision']==revision and r['timing_authority']=='NONE_TARGET'
      and r['route_jump_resets_aec'] is False and r['timestamp_assistance'] is False and r['res_enabled'] is False,'scope drift')
    require(r['order_manifest_sha256']==sha256((base/'order/manifest.json').read_bytes()) and
      r['activity_manifest_sha256']==sha256((base/'activity/manifest.json').read_bytes()) and
      r['correlation_manifest_sha256']==sha256((correlation/'manifest.json').read_bytes()),'predecessor binding')
    require(p['faults']=={'static-lead':320,'route-jump':[320,800,128000],'drift-plus-ppm':250},'frozen fault contract')
    for name in ('sync_fault_runner.c','sync_faults.py'):require((root/'source'/name).read_bytes()==(HERE/name).read_bytes(),'source drift '+name)
    expected={(x['pair'],f) for x in selected(base) for f in FAULTS};require({(x['pair'],x['fault']) for x in r['cases']}==expected,'case set')
    inputs={}
    for old in selected(base):
        pair=old['pair']
        with tempfile.TemporaryDirectory(prefix='sync-input-') as tmp:
            pth=Path(tmp)/'x.f32';rec=make_input(base,correlation,old,pth)
            real=root/'inputs'/f'p{pair}.f32';require(real.read_bytes()==pth.read_bytes() and rec==load_json(real.with_suffix('.json')),'input regeneration')
        inputs[pair]=floats(root/'inputs'/f'p{pair}.f32',N*4)
    for case in r['cases']:
        d=root/'cases'/case['case_id'];source=inputs[case['pair']];target=list(source[1::4]);echo=list(source[2::4])
        require(case['input']==f"inputs/p{case['pair']}.f32" and case['input_receipt']==load_json((root/case['input']).with_suffix('.json')),'input receipt')
        for arm in ARMS:
            raw=floats(d/(arm+'.f32'),N*2);actual=list(raw[0::2]);rows=trace_rows(d/(arm+'.csv'),case['fault'],arm,N//HOP)
            expected_arm={'metrics':metrics(target,echo,actual,case['fault']),'alignment':alignment(rows,case['fault']) if arm=='sync' else None,'meta':load_json(d/(arm+'.json'))}
            require(case['arms'][arm]==expected_arm,'metric/alignment recomputation')
            meta=expected_arm['meta'];require(meta['status']=='PASS' and meta['source_revision']==revision and meta['samples']==N and meta['frame_samples']==HOP
              and meta['sample_rate_hz']==RATE and meta['route_jump_resets_aec'] is False,'output identity')
            if arm=='sync':
                require(meta['arm']=='public-sync' and meta['max_delay_ms']==120 and meta['delay_tracking'] is True and meta['drift_compensation'] is True,'sync config')
            repeat=load_json(d/(arm+'-repeat-receipt.json'));require(repeat=={'output_sha256':sha256((d/(arm+'.f32')).read_bytes()),
              'meta_sha256':sha256((d/(arm+'.json')).read_bytes()),'trace_sha256':sha256((d/(arm+'.csv')).read_bytes())},'repeat receipt')
    for label in LABELS:
        info=load_json(root/(label+'-build.json'));require(info['source_revision']==revision and info['processor_sha256']==sha256((root/('sync-fault-'+label)).read_bytes()),'binary identity')
        require(load_json(root/('engineering-'+label)/'result.json')==r['engineering'][label],'engineering receipt')
    require('ARM' in (root/'arm-elf.txt').read_text() and 'ELF32' in (root/'arm-elf.txt').read_text(),'Arm ELF')
    return {'status':'VERIFIED_SYNC_FAULTS','cases':6,'arms':3,'files':len(load_json(root/'manifest.json')['files']),'decision':DECISION}

def negatives(base,correlation,root,revision):
    kinds=('promotion','predecessor','missing-case','metric','input','output','trace','binary');rejected=[]
    with tempfile.TemporaryDirectory(prefix='sync-neg-') as temp:
        copy=Path(temp)/'copy';shutil.copytree(root,copy);keep={p:p.read_bytes() for p in (copy/'result.json',copy/'manifest.json',copy/'SHA256SUMS')}
        for kind in kinds:
            rr=json.loads(keep[copy/'result.json']);changed=[]
            if kind=='promotion':rr['shipping_authority']=True
            elif kind=='predecessor':rr['correlation_manifest_sha256']='0'*64
            elif kind=='missing-case':rr['cases'].pop()
            elif kind=='metric':rr['cases'][0]['arms']['sync']['metrics']['final_far_ratio_db']=0.0
            else:
                case=rr['cases'][0]['case_id'];pth=copy/'inputs/p0.f32' if kind=='input' else copy/'cases'/case/'sync.f32' if kind=='output' else copy/'cases'/case/'sync.csv' if kind=='trace' else copy/'sync-fault-native'
                blob=pth.read_bytes();changed.append((pth,blob));pth.write_bytes(blob+b'changed')
            write_json(copy/'result.json',rr);seal_output(copy,rr)
            try:verify(base,correlation,copy,revision)
            except (ValueError,KeyError,IndexError,AssertionError,RuntimeError):rejected.append(kind)
            else:raise AssertionError('resealed negative accepted '+kind)
            for pth,blob in changed:pth.write_bytes(blob)
            for pth,blob in keep.items():pth.write_bytes(blob)
    return {'status':'PASS','rejected':rejected}

def summary(r):
    groups=[]
    for fault in FAULTS:
        rows=[x for x in r['cases'] if x['fault']==fault];g={'fault':fault,'cases':len(rows)}
        for arm in ARMS:
            vals=[x['arms'][arm]['metrics'] for x in rows];nums=[x['final_far_ratio_db'] for x in vals if x['final_far_ratio_db'] is not None]
            g[arm]={'mean_final_far_db':sum(nums)/len(nums) if nums else None,'double_after_si_sdr':[x['phases_si_sdr_relative_to_bf_target_db']['double-after'] for x in vals],
              'recovered':sum(x['recovery_after_event_ms'] is not None for x in vals)}
        g['sync_alignment']=[x['arms']['sync']['alignment'] for x in rows];groups.append(g)
    return {'decision':DECISION,'descriptive_only':True,'groups':groups}

def main():
    p=argparse.ArgumentParser();p.add_argument('--base-evidence',type=Path,required=True);p.add_argument('--correlation-evidence',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True);p.add_argument('--execution-source',required=True);p.add_argument('--verify',action='store_true');p.add_argument('--negative-evidence',action='store_true')
    a=p.parse_args();require(hex_digest(a.execution_source,40),'revision')
    if a.negative_evidence:r=negatives(a.base_evidence,a.correlation_evidence,a.output,a.execution_source)
    elif a.verify:r=verify(a.base_evidence,a.correlation_evidence,a.output,a.execution_source)
    else:
        r=run(a.base_evidence,a.correlation_evidence,a.output,a.execution_source);print('SYNC_FAULT_EFFECTS '+json.dumps(summary(r),sort_keys=True,allow_nan=False))
        r={'status':'EXECUTED_SYNC_FAULTS','cases':6,'decision':DECISION}
    print(json.dumps(r,sort_keys=True,allow_nan=False));return 0
if __name__=='__main__':raise SystemExit(main())
