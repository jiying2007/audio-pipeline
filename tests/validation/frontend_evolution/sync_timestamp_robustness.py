#!/usr/bin/env python3
"""Timestamp jitter/dropout robustness on frozen FE04 transport faults."""
from __future__ import annotations
import argparse, array, csv, json, math, shutil, subprocess, sys, tempfile
from pathlib import Path
import sync_faults as sync
import sync_route_reset as route_reset
import sync_timestamp_authority as authority
from contracts import ROOT, hex_digest, load_json, require, sha256
from libfvad_reference import write_json, seal_output, run_logged
from speech_fir import verify_seal

HERE=Path(__file__).resolve().parent
PLAN=ROOT/'.github/research/frontend-evolution-v1/sync-timestamp-robustness-v1.json'
RUNNER=HERE/'sync_timestamp_robustness_runner.c'
DECISION='SYNC_TIMESTAMP_ROBUSTNESS_DIAGNOSTIC_NO_PROMOTION'
ROLE='DISCLOSED_DEVELOPMENT_DIAGNOSTIC_NOT_HOLDOUT'
RATE,HOP,N=16000,160,256000
FAULTS=sync.FAULTS
PROFILES=('jitter','dropout','combined')
LABELS=sync.LABELS
CFLAGS=['-std=c11','-O2','-Wall','-Wextra','-Wpedantic','-Werror','-ffp-contract=off']
HEADER=['frame','true_lead_samples','timestamp_lead_samples','timestamp_observed','pushed_samples',
        'capture_timestamp_ns','render_timestamp_ns','sync_delay_samples','delay_error_samples',
        'route_jump','underrun','aec_reset','mic_energy','reference_energy','used_far','used_dt']

def case_map(r:dict)->dict:
    return {c['case_id']:c for c in r['cases']}

def profile_observed(profile:str,frame:int)->bool:
    return profile=='jitter' or not (frame>0 and frame%20==0)

def jitter(profile:str,frame:int)->int:
    return (0,1,0,-1)[frame%4] if profile in ('jitter','combined') else 0

def timestamp_lead(profile:str,true_lead:int,frame:int)->int:
    return true_lead+jitter(profile,frame)

def expected_route_frame(profile:str)->int:
    return 800 if profile=='jitter' else 801

def expected_observations(profile:str)->int:
    return 1600 if profile=='jitter' else 1521

def predecessor_receipt(sync_root:Path,reset_root:Path,exact_root:Path,revision:str,full:bool)->dict:
    if full:
        verified=authority.verify(sync_root,reset_root,exact_root,revision)
        require(verified['status']=='VERIFIED_SYNC_TIMESTAMP_AUTHORITY','exact predecessor full verify')
    else:
        verify_seal(sync_root);verify_seal(reset_root);verify_seal(exact_root)
    sr=load_json(sync_root/'result.json');rr=load_json(reset_root/'result.json');er=load_json(exact_root/'result.json')
    require(sr['experiment_id']=='FE04-SYNC-FAULTS-V1' and sr['execution_source_revision']==revision,'sync predecessor')
    require(rr['experiment_id']=='FE04-SYNC-ROUTE-RESET-V1' and rr['execution_source_revision']==revision,'reset predecessor')
    require(er['experiment_id']=='FE04-SYNC-TIMESTAMP-AUTHORITY-V1' and er['execution_source_revision']==revision,'exact predecessor')
    require(er['decision']=='SYNC_TIMESTAMP_AUTHORITY_DIAGNOSTIC_NO_PROMOTION' and er['case_count']==6,'exact authority')
    return {
      'sync_manifest_sha256':sha256((sync_root/'manifest.json').read_bytes()),
      'reset_manifest_sha256':sha256((reset_root/'manifest.json').read_bytes()),
      'exact_manifest_sha256':sha256((exact_root/'manifest.json').read_bytes()),
      'exact_result_sha256':sha256((exact_root/'result.json').read_bytes()),
      'source_revision':revision
    }

def trace_rows(path:Path,profile:str,fault:str,frames:int)->list[dict]:
    rows=[];cursor=0;effective=None
    with path.open(newline='') as f:
        rd=csv.DictReader(f);require(rd.fieldnames==HEADER,'robustness trace schema')
        for index,row in enumerate(rd):
            require(index<frames and None not in row.values(),'robustness trace count/partial')
            item={}
            for key in HEADER:
                if key in ('mic_energy','reference_energy'):
                    value=float(row[key]);require(math.isfinite(value),'nonfinite robustness trace');item[key]=value
                else:item[key]=int(row[key])
            require(item['frame']==index,'robustness trace order')
            true=sync.expected_lead(fault,index,frames)
            ts=timestamp_lead(profile,true,index)
            observe=profile_observed(profile,index)
            desired=(index+1)*HOP+true;pushed=desired-cursor;cursor=desired
            require(item['true_lead_samples']==true and item['timestamp_lead_samples']==ts,'robustness lead schedule')
            require(item['timestamp_observed']==int(observe),'robustness observation schedule')
            require(item['pushed_samples']==pushed,'robustness render schedule')
            capture=20000000000+(index+1)*HOP*62500
            render=capture-ts*62500
            require(item['capture_timestamp_ns']==capture and item['render_timestamp_ns']==render,'robustness timestamp construction')
            if observe:
                previous=effective
                effective=ts
                expected_error=ts-(0 if previous is None else previous)
            else:
                expected_error=0
            require(effective is not None,'frame zero must observe')
            require(item['sync_delay_samples']==effective,'robustness effective delay')
            require(item['delay_error_samples']==expected_error,'robustness delay error')
            event_frame=expected_route_frame(profile)
            expected_route=int(fault=='route' and index==event_frame)
            require(item['route_jump']==expected_route and item['aec_reset']==expected_route,'robustness route/reset contract')
            require(item['underrun']==0,'robustness underrun')
            require(item['used_far'] in (0,1) and item['used_dt'] in (0,1),'robustness activity flags')
            rows.append(item)
    require(len(rows)==frames,'robustness trace frame count')
    return rows

def build(root:Path,revision:str,label:str)->Path:
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
    binary=root/('sync-ts-robust-'+label)
    cmd=[cc,*CFLAGS,*(['-O1','-g','-fsanitize=address,undefined','-fno-omit-frame-pointer'] if san else []),
      '-I'+str(ROOT/'include'),'-I'+str(b/'generated'),RUNNER,b/'libaudio_pipeline.a','-lm','-o',binary]
    run_logged(cmd,root/(label+'-link.log'));run_logged([cc,'--version'],root/(label+'-compiler.txt'))
    shutil.copyfile(b/'generated/audio_pipeline/audio_pipeline_build.h',root/(label+'-build.h'))
    shutil.copyfile(b/'libaudio_pipeline.a',root/(label+'-library.a'))
    if arm:run_logged(['arm-linux-gnueabihf-readelf','-h',binary],root/'arm-elf.txt')
    write_json(root/(label+'-build.json'),{'source_revision':revision,'processor_sha256':sha256(binary.read_bytes()),
      'library_sha256':sha256((root/(label+'-library.a')).read_bytes()),'compiler':cc,'sanitized':san,'arm':arm,
      'configure':list(map(str,opts)),'link':list(map(str,cmd))})
    shutil.rmtree(b);return binary

def command(binary:Path,profile:str,fault:str,inp:Path,dest:Path,under_arm:bool=False)->list:
    prefix=['qemu-arm','-L','/usr/arm-linux-gnueabihf'] if under_arm else []
    return [*prefix,binary,profile,fault,inp,dest.with_suffix('.f32'),dest.with_suffix('.json'),dest.with_suffix('.csv')]

def execute(binary:Path,profile:str,fault:str,inp:Path,dest:Path,under_arm:bool=False)->None:
    run_logged(command(binary,profile,fault,inp,dest,under_arm),dest.with_suffix('.log'))

def physical(inp:Path)->list[float]:
    return list(sync.floats(inp,N*4)[3::4])

def reference_values(out:Path)->list[float]:
    return list(sync.floats(out,N*2)[1::2])

def reference_error(inp:Path,out:Path)->dict:
    truth=physical(inp);ref=reference_values(out)
    require(len(truth)==len(ref)==N,'reference error count')
    mismatches=0;sse=0.0;maximum=0.0
    for a,b in zip(truth,ref):
        d=float(b)-float(a)
        if d!=0.0:mismatches+=1
        sse+=d*d
        maximum=max(maximum,abs(d))
    return {'numeric_mismatch_samples':mismatches,'rms_error':math.sqrt(sse/N),'max_abs_error':maximum}

def metrics(inp:Path,out:Path,fault:str)->dict:
    source=sync.floats(inp,N*4);target=list(source[1::4]);echo=list(source[2::4]);raw=sync.floats(out,N*2)
    return sync.metrics(target,echo,list(raw[0::2]),fault)

def run_one(binary:Path,label:str,profile:str,fault:str,inp:Path,dest:Path)->dict:
    under_arm=label=='arm'
    execute(binary,profile,fault,inp,dest,under_arm)
    execute(binary,profile,fault,inp,dest.with_name(dest.name+'-repeat'),under_arm)
    for suffix in ('.f32','.json','.csv'):
        require(dest.with_suffix(suffix).read_bytes()==dest.with_name(dest.name+'-repeat').with_suffix(suffix).read_bytes(),'robustness repeat')
        dest.with_name(dest.name+'-repeat').with_suffix(suffix).unlink()
    rows=trace_rows(dest.with_suffix('.csv'),profile,fault,N//HOP)
    meta=load_json(dest.with_suffix('.json'))
    expected_events=1 if fault=='route' else 0
    require(meta['status']=='PASS' and meta['timestamp_authority'] is True and meta['acoustic_tracking'] is False
      and meta['route_jump_resets_aec'] is True,'robustness meta authority')
    require(meta['timestamp_observations']==expected_observations(profile) and meta['timestamp_dropouts']==N//HOP-expected_observations(profile),'robustness observation count')
    require(meta['route_jumps']==expected_events and meta['aec_resets']==expected_events and meta['underruns']==0,'robustness event counters')
    require(abs(meta['final_estimated_drift_ppm'])<=1.0e-9,'robustness drift authority')
    return {'meta':meta,'rows':rows,'output_sha256':sha256(dest.with_suffix('.f32').read_bytes()),
      'trace_sha256':sha256(dest.with_suffix('.csv').read_bytes())}

def engineering(root:Path,binaries:dict,sync_root:Path,revision:str)->dict:
    root.mkdir();case=case_map(load_json(sync_root/'result.json'))['p0-route'];inp=sync_root/case['input'];records={}
    for label in LABELS:
        d=root/label;d.mkdir()
        run_logged((['qemu-arm','-L','/usr/arm-linux-gnueabihf'] if label=='arm' else [])+[binaries[label],'--self-test'],d/'self-test.log')
        records[label]={}
        for profile in ('jitter','combined'):
            rec=run_one(binaries[label],label,profile,'route',inp,d/profile)
            require(rec['meta']['route_jumps']==1 and rec['meta']['aec_resets']==1,'engineering route/reset')
            records[label][profile]={'output_sha256':rec['output_sha256'],'trace_sha256':rec['trace_sha256'],
              'reference_error':reference_error(inp,d/(profile+'.f32'))}
    data=array.array('f');data.frombytes(inp.read_bytes())
    if sys.byteorder!='little':data.byteswap()
    cutoff=200000
    for k in range(cutoff,N):
        for c in range(4):data[4*k+c]*=-1.0
    if sys.byteorder!='little':data.byteswap()
    future=root/'future-input.f32';future.write_bytes(data.tobytes())
    execute(binaries['native'],'combined','route',future,root/'future')
    a=sync.floats(root/'native/combined.f32',N*2);b=sync.floats(root/'future.f32',N*2)
    require(a[:(cutoff-2*HOP)*2]==b[:(cutoff-2*HOP)*2] and a[(cutoff+2*HOP)*2:]!=b[(cutoff+2*HOP)*2:],'robustness future causality')
    bad=root/'partial.f32';bad.write_bytes(b'\0')
    p=subprocess.run(list(map(str,command(binaries['native'],'jitter','static',bad,root/'bad'))),capture_output=True)
    require(p.returncode!=0,'partial robustness input accepted');(root/'bad.log').write_bytes(p.stderr)
    before=(root/'native/jitter.f32').read_bytes()
    p=subprocess.run(list(map(str,command(binaries['native'],'jitter','route',inp,root/'native/jitter'))),capture_output=True)
    require(p.returncode!=0 and before==(root/'native/jitter.f32').read_bytes(),'robustness overwrite accepted');(root/'overwrite.log').write_bytes(p.stderr)
    result={'status':'PASS','fixed_case':'p0-route','records':records,'future':True,
      'invalid_timestamp_self_test':True,'invalid_transport_rejected':True,'overwrite_rejected':True}
    write_json(root/'result.json',result);return result

def run(sync_root:Path,reset_root:Path,exact_root:Path,root:Path,revision:str)->dict:
    require(not root.exists() and hex_digest(revision,40),'fresh output/exact revision')
    pred=predecessor_receipt(sync_root,reset_root,exact_root,revision,full=True)
    sr=load_json(sync_root/'result.json');er=load_json(exact_root/'result.json')
    root.mkdir(parents=True);shutil.copyfile(PLAN,root/'experiment.json');write_json(root/'predecessor-verification.json',pred)
    (root/'source').mkdir()
    for p in (RUNNER,Path(__file__)):shutil.copyfile(p,root/'source'/p.name)
    binaries={label:build(root,revision,label) for label in LABELS}
    eng=engineering(root/'engineering',binaries,sync_root,revision)
    sm=case_map(sr);em=case_map(er);cases=[]
    for case_id in sorted(sm,key=lambda x:(sm[x]['pair'],FAULTS.index(sm[x]['fault']))):
        pc=sm[case_id];exact=em[case_id];fault=pc['fault'];inp=sync_root/pc['input']
        exact_metrics=exact['timestamp_reset_metrics']
        for profile in PROFILES:
            d=root/'cases'/case_id;d.mkdir(parents=True,exist_ok=True);dest=d/profile
            rec=run_one(binaries['native'],'native',profile,fault,inp,dest)
            cm=metrics(inp,dest.with_suffix('.f32'),fault);re=reference_error(inp,dest.with_suffix('.f32'))
            route_frames=[x['frame'] for x in rec['rows'] if x['route_jump']]
            reset_frames=[x['frame'] for x in rec['rows'] if x['aec_reset']]
            expected_frames=[expected_route_frame(profile)] if fault=='route' else []
            require(route_frames==expected_frames and reset_frames==expected_frames,'robustness event frame')
            cases.append({'case_id':case_id,'pair':pc['pair'],'fault':fault,'profile':profile,
              'timestamp_observations':rec['meta']['timestamp_observations'],'timestamp_dropouts':rec['meta']['timestamp_dropouts'],
              'route_frames':route_frames,'reset_frames':reset_frames,'reference_error':re,
              'exact_reset_metrics':exact_metrics,'candidate_metrics':cm,
              'delta_final_far_db':None if exact_metrics['final_far_ratio_db'] is None or cm['final_far_ratio_db'] is None
                else cm['final_far_ratio_db']-exact_metrics['final_far_ratio_db'],
              'output_sha256':rec['output_sha256'],'trace_sha256':rec['trace_sha256']})
    report={'schema_version':1,'experiment_id':'FE04-SYNC-TIMESTAMP-ROBUSTNESS-V1','decision':DECISION,
      'shipping_authority':False,'data_role':ROLE,'execution_source_revision':revision,'case_count':18,
      'predecessor':pred,'timestamp_authority':'SYNTHETIC_STRESS_NOT_DUT',
      'jitter_pattern_samples':[0,1,0,-1],'dropout_rule':'positive-frame-divisible-by-20',
      'res_enabled':False,'engineering':eng,'cases':cases}
    write_json(root/'result.json',report);seal_output(root,report);return report

def verify(sync_root:Path,reset_root:Path,exact_root:Path,root:Path,revision:str,predecessors_verified=False)->dict:
    verify_seal(root)
    pred=predecessor_receipt(sync_root,reset_root,exact_root,revision,full=False)
    r=load_json(root/'result.json');receipt=load_json(root/'predecessor-verification.json')
    require(receipt==pred==r['predecessor'],'robustness predecessor receipt')
    require((root/'experiment.json').read_bytes()==PLAN.read_bytes(),'robustness plan drift')
    require(r['experiment_id']=='FE04-SYNC-TIMESTAMP-ROBUSTNESS-V1' and r['decision']==DECISION
      and r['shipping_authority'] is False and r['data_role']==ROLE and r['execution_source_revision']==revision
      and r['case_count']==18,'robustness authority')
    require(r['timestamp_authority']=='SYNTHETIC_STRESS_NOT_DUT' and r['jitter_pattern_samples']==[0,1,0,-1]
      and r['dropout_rule']=='positive-frame-divisible-by-20' and r['res_enabled'] is False,'robustness scope')
    for name in ('sync_timestamp_robustness_runner.c','sync_timestamp_robustness.py'):
        require((root/'source'/name).read_bytes()==(HERE/name).read_bytes(),'robustness source drift '+name)
    for label in LABELS:
        info=load_json(root/(label+'-build.json'))
        require(info['source_revision']==revision and info['processor_sha256']==sha256((root/('sync-ts-robust-'+label)).read_bytes()),'robustness binary')
    sr=load_json(sync_root/'result.json');er=load_json(exact_root/'result.json');sm=case_map(sr);em=case_map(er)
    expected={(cid,p) for cid in sm for p in PROFILES}
    require({(c['case_id'],c['profile']) for c in r['cases']}==expected,'robustness case set')
    for c in sorted(r['cases'],key=lambda x:(x['case_id'],PROFILES.index(x['profile']))):
        pc=sm[c['case_id']];exact=em[c['case_id']];fault=c['fault'];profile=c['profile'];inp=sync_root/pc['input'];d=root/'cases'/c['case_id'];dest=d/profile
        rows=trace_rows(dest.with_suffix('.csv'),profile,fault,N//HOP)
        expected_frames=[expected_route_frame(profile)] if fault=='route' else []
        require(c['route_frames']==[x['frame'] for x in rows if x['route_jump']]==expected_frames,'robustness route frames')
        require(c['reset_frames']==[x['frame'] for x in rows if x['aec_reset']]==expected_frames,'robustness reset frames')
        require(c['timestamp_observations']==expected_observations(profile) and c['timestamp_dropouts']==N//HOP-expected_observations(profile),'robustness observations')
        re=reference_error(inp,dest.with_suffix('.f32'));cm=metrics(inp,dest.with_suffix('.f32'),fault)
        require(c['reference_error']==re and c['candidate_metrics']==cm,'robustness recomputation')
        require(c['exact_reset_metrics']==exact['timestamp_reset_metrics'],'robustness exact baseline')
        require(c['output_sha256']==sha256(dest.with_suffix('.f32').read_bytes())
          and c['trace_sha256']==sha256(dest.with_suffix('.csv').read_bytes()),'robustness hashes')
    eng=load_json(root/'engineering/result.json');require(eng==r['engineering'] and eng['status']=='PASS','robustness engineering')
    require('ARM' in (root/'arm-elf.txt').read_text() and 'ELF32' in (root/'arm-elf.txt').read_text(),'robustness Arm ELF')
    return {'status':'VERIFIED_SYNC_TIMESTAMP_ROBUSTNESS','cases':18,'files':len(load_json(root/'manifest.json')['files']),'decision':DECISION}

def negatives(sync_root:Path,reset_root:Path,exact_root:Path,root:Path,revision:str)->dict:
    kinds=('promotion','predecessor','missing-case','metric','output','trace','observation-count','binary');rejected=[]
    predecessor_receipt(sync_root,reset_root,exact_root,revision,full=False)
    with tempfile.TemporaryDirectory(prefix='sync-ts-robust-neg-') as temp:
        copy=Path(temp)/'copy';shutil.copytree(root,copy)
        keep={p:p.read_bytes() for p in (copy/'result.json',copy/'manifest.json',copy/'SHA256SUMS')}
        for kind in kinds:
            rr=json.loads(keep[copy/'result.json']);changed=[]
            if kind=='promotion':rr['shipping_authority']=True
            elif kind=='predecessor':rr['predecessor']['exact_manifest_sha256']='0'*64
            elif kind=='missing-case':rr['cases'].pop()
            elif kind=='metric':rr['cases'][0]['candidate_metrics']['final_far_ratio_db']=0.0
            elif kind=='observation-count':rr['cases'][0]['timestamp_observations']+=1
            else:
                c=rr['cases'][0];base=copy/'cases'/c['case_id']/c['profile']
                pth=base.with_suffix('.f32') if kind=='output' else base.with_suffix('.csv') if kind=='trace' else copy/'sync-ts-robust-native'
                blob=pth.read_bytes();changed.append((pth,blob));pth.write_bytes(blob+b'changed')
            write_json(copy/'result.json',rr);seal_output(copy,rr)
            try:verify(sync_root,reset_root,exact_root,copy,revision,predecessors_verified=True)
            except (ValueError,KeyError,IndexError,AssertionError,RuntimeError):rejected.append(kind)
            else:raise AssertionError('resealed timestamp robustness negative accepted '+kind)
            for pth,blob in changed:pth.write_bytes(blob)
            for pth,blob in keep.items():pth.write_bytes(blob)
    return {'status':'PASS','rejected':rejected}

def summary(r:dict)->dict:
    groups=[]
    for fault in FAULTS:
        for profile in PROFILES:
            rows=[x for x in r['cases'] if x['fault']==fault and x['profile']==profile]
            vals=[x['candidate_metrics']['final_far_ratio_db'] for x in rows]
            exact=[x['exact_reset_metrics']['final_far_ratio_db'] for x in rows]
            groups.append({'fault':fault,'profile':profile,'cases':len(rows),
              'mean_final_far_db':sum(vals)/len(vals),'exact_mean_final_far_db':sum(exact)/len(exact),
              'delta_final_far_db':[x['delta_final_far_db'] for x in rows],
              'route_frames':[x['route_frames'] for x in rows],
              'reference_rms_error':[x['reference_error']['rms_error'] for x in rows],
              'reference_max_abs_error':[x['reference_error']['max_abs_error'] for x in rows],
              'reference_mismatch_samples':[x['reference_error']['numeric_mismatch_samples'] for x in rows]})
    return {'decision':DECISION,'descriptive_only':True,'groups':groups}

def main()->int:
    p=argparse.ArgumentParser()
    p.add_argument('--sync-predecessor',type=Path,required=True);p.add_argument('--reset-predecessor',type=Path,required=True)
    p.add_argument('--exact-predecessor',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--execution-source',required=True);p.add_argument('--verify',action='store_true');p.add_argument('--negative-evidence',action='store_true')
    a=p.parse_args();require(hex_digest(a.execution_source,40),'robustness revision')
    if a.negative_evidence:r=negatives(a.sync_predecessor,a.reset_predecessor,a.exact_predecessor,a.output,a.execution_source)
    elif a.verify:r=verify(a.sync_predecessor,a.reset_predecessor,a.exact_predecessor,a.output,a.execution_source)
    else:
        r=run(a.sync_predecessor,a.reset_predecessor,a.exact_predecessor,a.output,a.execution_source)
        print('SYNC_TIMESTAMP_ROBUSTNESS_EFFECTS '+json.dumps(summary(r),sort_keys=True,allow_nan=False))
        r={'status':'EXECUTED_SYNC_TIMESTAMP_ROBUSTNESS','cases':18,'decision':DECISION}
    print(json.dumps(r,sort_keys=True,allow_nan=False));return 0
if __name__=='__main__':raise SystemExit(main())
