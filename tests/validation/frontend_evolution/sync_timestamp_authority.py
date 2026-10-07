#!/usr/bin/env python3
"""Exact timestamp authority versus acoustic-correlation SYNC on frozen FE04 faults."""
from __future__ import annotations
import argparse, array, csv, json, math, shutil, subprocess, sys, tempfile
from pathlib import Path
import sync_faults as sync
import sync_route_reset as route_reset
from contracts import ROOT, hex_digest, load_json, require, sha256
from libfvad_reference import write_json, seal_output, run_logged
from speech_fir import verify_seal

HERE=Path(__file__).resolve().parent
PLAN=ROOT/'.github/research/frontend-evolution-v1/sync-timestamp-authority-v1.json'
RUNNER=HERE/'sync_timestamp_runner.c'
DECISION='SYNC_TIMESTAMP_AUTHORITY_DIAGNOSTIC_NO_PROMOTION'
ROLE='DISCLOSED_DEVELOPMENT_DIAGNOSTIC_NOT_HOLDOUT'
RATE,HOP,N=16000,160,256000
FAULTS=sync.FAULTS
ARMS=('timestamp','timestamp-reset')
LABELS=sync.LABELS
CFLAGS=['-std=c11','-O2','-Wall','-Wextra','-Wpedantic','-Werror','-ffp-contract=off']
HEADER=['frame','known_lead_samples','pushed_samples','capture_timestamp_ns','render_timestamp_ns',
        'sync_delay_samples','delay_error_samples','timestamp_observed','route_jump','underrun','aec_reset',
        'mic_energy','reference_energy','used_far','used_dt']

def predecessors(sync_root:Path,reset_root:Path,revision:str)->tuple[dict,dict]:
    # Route-reset verifier recursively validates the sealed SYNC predecessor without
    # requiring the much larger spatial/correlation artifacts in this downstream job.
    route_reset.verify(sync_root,reset_root,revision)
    sr=load_json(sync_root/'result.json');rr=load_json(reset_root/'result.json')
    require(sr['decision']=='SYNC_FAULTS_DIAGNOSTIC_NO_PROMOTION' and sr['case_count']==6,'SYNC predecessor')
    require(rr['decision']=='SYNC_ROUTE_RESET_DIAGNOSTIC_NO_PROMOTION' and rr['case_count']==6,'reset predecessor')
    require(sr['execution_source_revision']==rr['execution_source_revision']==revision,'predecessor revision')
    return sr,rr

def case_map(r:dict)->dict:
    return {c['case_id']:c for c in r['cases']}

def trace_rows(path:Path,fault:str,arm:str,frames:int)->list[dict]:
    rows=[];cursor=0
    with path.open(newline='') as f:
        rd=csv.DictReader(f);require(rd.fieldnames==HEADER,'timestamp trace schema')
        for index,row in enumerate(rd):
            require(index<frames and None not in row.values(),'timestamp trace count/partial')
            item={}
            for key in HEADER:
                if key in ('mic_energy','reference_energy'):
                    value=float(row[key]);require(math.isfinite(value),'nonfinite timestamp trace');item[key]=value
                else:item[key]=int(row[key])
            require(item['frame']==index,'timestamp trace order')
            lead=sync.expected_lead(fault,index,frames);desired=(index+1)*HOP+lead;pushed=desired-cursor;cursor=desired
            require(item['known_lead_samples']==lead and item['pushed_samples']==pushed,'timestamp transport schedule')
            capture=10000000000+(index+1)*HOP*62500
            render=capture-lead*62500
            require(item['capture_timestamp_ns']==capture and item['render_timestamp_ns']==render,'timestamp construction')
            require(item['timestamp_observed']==1 and item['sync_delay_samples']==lead and item['underrun']==0,'timestamp authority')
            expected_route=1 if fault=='route' and index==800 else 0
            require(item['route_jump']==expected_route,'timestamp route event')
            require(item['aec_reset']==(expected_route if arm=='timestamp-reset' else 0),'timestamp reset trace')
            require(item['used_far'] in (0,1) and item['used_dt'] in (0,1),'timestamp gate flags')
            rows.append(item)
    require(len(rows)==frames,'timestamp trace frame count')
    return rows

def trace_without_reset(rows:list[dict])->list[dict]:
    return [{k:v for k,v in row.items() if k!='aec_reset'} for row in rows]

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
    binary=root/('sync-timestamp-'+label)
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

def command(binary:Path,arm:str,fault:str,inp:Path,dest:Path,under_arm:bool=False)->list:
    prefix=['qemu-arm','-L','/usr/arm-linux-gnueabihf'] if under_arm else []
    return [*prefix,binary,arm,fault,inp,dest.with_suffix('.f32'),dest.with_suffix('.json'),dest.with_suffix('.csv')]

def execute(binary:Path,arm:str,fault:str,inp:Path,dest:Path,under_arm:bool=False)->None:
    run_logged(command(binary,arm,fault,inp,dest,under_arm),dest.with_suffix('.log'))

def physical(inp:Path)->list[float]:
    source=sync.floats(inp,N*4);return list(source[3::4])

def metrics(inp:Path,out:Path,fault:str)->dict:
    source=sync.floats(inp,N*4);target=list(source[1::4]);echo=list(source[2::4])
    raw=sync.floats(out,N*2);return sync.metrics(target,echo,list(raw[0::2]),fault)

def reference_values(out:Path)->list[float]:
    return list(sync.floats(out,N*2)[1::2])

def run_case(binary:Path,label:str,inp:Path,fault:str,dest:Path)->dict:
    under_arm=label=='arm'
    execute(binary,'timestamp',fault,inp,dest/'timestamp',under_arm)
    execute(binary,'timestamp-reset',fault,inp,dest/'timestamp-reset',under_arm)
    execute(binary,'timestamp',fault,inp,dest/'timestamp-repeat',under_arm)
    execute(binary,'timestamp-reset',fault,inp,dest/'timestamp-reset-repeat',under_arm)
    for arm in ARMS:
        for suffix in ('.f32','.json','.csv'):
            require((dest/(arm+suffix)).read_bytes()==(dest/(arm+'-repeat'+suffix)).read_bytes(),'timestamp repeat')
            (dest/(arm+'-repeat'+suffix)).unlink()
    rows0=trace_rows(dest/'timestamp.csv',fault,'timestamp',N//HOP)
    rows1=trace_rows(dest/'timestamp-reset.csv',fault,'timestamp-reset',N//HOP)
    require(trace_without_reset(rows0)==trace_without_reset(rows1),'reset changed timestamp trace')
    expected=1 if fault=='route' else 0
    m0=load_json(dest/'timestamp.json');m1=load_json(dest/'timestamp-reset.json')
    for meta,arm in ((m0,'timestamp-no-reset'),(m1,'timestamp-reset')):
        require(meta['status']=='PASS' and meta['arm']==arm and meta['timestamp_authority'] is True
          and meta['acoustic_tracking'] is False and meta['drift_compensation'] is False,'timestamp meta')
        require(meta['timestamp_observations']==N//HOP and meta['route_jumps']==expected and meta['underruns']==0,'timestamp counters')
    require(m0['aec_resets']==0 and m0['route_jump_resets_aec'] is False,'no-reset meta')
    require(m1['aec_resets']==expected and m1['route_jump_resets_aec'] is True,'reset meta')
    return {'timestamp_meta':m0,'reset_meta':m1,'timestamp_rows':rows0,'reset_rows':rows1}

def engineering(root:Path,binaries:dict,sync_root:Path,revision:str)->dict:
    root.mkdir();case=case_map(load_json(sync_root/'result.json'))['p0-route'];inp=sync_root/case['input'];records={}
    for label in LABELS:
        d=root/label;d.mkdir()
        run_logged((['qemu-arm','-L','/usr/arm-linux-gnueabihf'] if label=='arm' else [])+[binaries[label],'--self-test'],d/'self-test.log')
        rec=run_case(binaries[label],label,inp,'route',d)
        require(rec['timestamp_meta']['route_jumps']==1 and rec['reset_meta']['aec_resets']==1,'engineering route/reset')
        require(reference_values(d/'timestamp.f32')==physical(inp),'engineering exact reference')
        records[label]={'timestamp_sha256':sha256((d/'timestamp.f32').read_bytes()),
          'reset_sha256':sha256((d/'timestamp-reset.f32').read_bytes()),'route_jumps':1,'aec_resets':1}
    # Native common-prefix causality: future input mutation cannot change the retained prefix.
    data=array.array('f');data.frombytes(inp.read_bytes())
    if sys.byteorder!='little':data.byteswap()
    cutoff=200000
    for k in range(cutoff,N):
        for c in range(4):data[4*k+c]*=-1.0
    if sys.byteorder!='little':data.byteswap()
    future=root/'future-input.f32';future.write_bytes(data.tobytes())
    execute(binaries['native'],'timestamp-reset','route',future,root/'future')
    a=sync.floats(root/'native/timestamp-reset.f32',N*2);b=sync.floats(root/'future.f32',N*2)
    require(a[:(cutoff-2*HOP)*2]==b[:(cutoff-2*HOP)*2] and a[(cutoff+2*HOP)*2:]!=b[(cutoff+2*HOP)*2:],'timestamp future causality')
    bad=root/'partial.f32';bad.write_bytes(b'\0')
    p=subprocess.run(list(map(str,command(binaries['native'],'timestamp','static',bad,root/'bad'))),capture_output=True)
    require(p.returncode!=0,'partial timestamp input accepted');(root/'bad.log').write_bytes(p.stderr)
    before=(root/'native/timestamp.f32').read_bytes()
    p=subprocess.run(list(map(str,command(binaries['native'],'timestamp','route',inp,root/'native/timestamp'))),capture_output=True)
    require(p.returncode!=0 and before==(root/'native/timestamp.f32').read_bytes(),'timestamp overwrite accepted');(root/'overwrite.log').write_bytes(p.stderr)
    result={'status':'PASS','fixed_case':'p0-route','records':records,'future':True,'invalid_timestamp_self_test':True,
      'invalid_transport_rejected':True,'overwrite_rejected':True}
    write_json(root/'result.json',result);return result

def run(sync_root:Path,reset_root:Path,root:Path,revision:str)->dict:
    require(not root.exists() and hex_digest(revision,40),'fresh output/exact revision')
    sr,rr=predecessors(sync_root,reset_root,revision);root.mkdir(parents=True)
    shutil.copyfile(PLAN,root/'experiment.json');(root/'source').mkdir()
    for p in (RUNNER,Path(__file__)):shutil.copyfile(p,root/'source'/p.name)
    binaries={label:build(root,revision,label) for label in LABELS}
    eng=engineering(root/'engineering',binaries,sync_root,revision)
    sm=case_map(sr);rm=case_map(rr);cases=[]
    for case_id in sorted(sm,key=lambda x:(sm[x]['pair'],FAULTS.index(sm[x]['fault']))):
        pc=sm[case_id];rc=rm[case_id];fault=pc['fault'];inp=sync_root/pc['input'];d=root/'cases'/case_id;d.mkdir(parents=True)
        rec=run_case(binaries['native'],'native',inp,fault,d)
        oracle=sync_root/'cases'/case_id/'oracle.f32';acoustic=reset_root/'cases'/case_id/'reset.f32'
        require((d/'timestamp.f32').read_bytes()==oracle.read_bytes(),'timestamp no-reset not oracle-identical')
        require(reference_values(d/'timestamp.f32')==physical(inp),'timestamp reference not physical render')
        if fault!='route':require((d/'timestamp.f32').read_bytes()==(d/'timestamp-reset.f32').read_bytes(),'zero-event reset changed output')
        tm=metrics(inp,d/'timestamp.f32',fault);trm=metrics(inp,d/'timestamp-reset.f32',fault)
        om=metrics(inp,oracle,fault);arm=metrics(inp,acoustic,fault)
        require(tm==om,'timestamp/oracle metric drift')
        rows=rec['reset_rows'];reset_frames=[x['frame'] for x in rows if x['aec_reset']]
        cases.append({'case_id':case_id,'pair':pc['pair'],'fault':fault,
          'expected_timestamp_route_events':1 if fault=='route' else 0,
          'timestamp_route_events':rec['timestamp_meta']['route_jumps'],'timestamp_reset_count':rec['reset_meta']['aec_resets'],
          'timestamp_reset_frames':reset_frames,'timestamp_no_reset_oracle_byte_identity':True,
          'zero_event_reset_output_identity':(d/'timestamp.f32').read_bytes()==(d/'timestamp-reset.f32').read_bytes(),
          'oracle_metrics':om,'acoustic_reset_metrics':arm,'timestamp_no_reset_metrics':tm,'timestamp_reset_metrics':trm,
          'timestamp_output_sha256':sha256((d/'timestamp.f32').read_bytes()),
          'timestamp_reset_output_sha256':sha256((d/'timestamp-reset.f32').read_bytes()),
          'timestamp_trace_sha256':sha256((d/'timestamp.csv').read_bytes()),
          'timestamp_reset_trace_sha256':sha256((d/'timestamp-reset.csv').read_bytes())})
    report={'schema_version':1,'experiment_id':'FE04-SYNC-TIMESTAMP-AUTHORITY-V1','decision':DECISION,
      'shipping_authority':False,'data_role':ROLE,'execution_source_revision':revision,'case_count':6,
      'sync_predecessor_manifest_sha256':sha256((sync_root/'manifest.json').read_bytes()),
      'route_reset_predecessor_manifest_sha256':sha256((reset_root/'manifest.json').read_bytes()),
      'timestamp_authority':'EXACT_SYNTHETIC_TRANSPORT_NOT_DUT','acoustic_tracking':False,'res_enabled':False,
      'engineering':eng,'cases':cases}
    write_json(root/'result.json',report);seal_output(root,report);return report

def verify(sync_root:Path,reset_root:Path,root:Path,revision:str,predecessors_verified=False)->dict:
    verify_seal(root)
    if predecessors_verified:
        sr=load_json(sync_root/'result.json');rr=load_json(reset_root/'result.json')
    else:
        sr,rr=predecessors(sync_root,reset_root,revision)
    r=load_json(root/'result.json');require((root/'experiment.json').read_bytes()==PLAN.read_bytes(),'timestamp plan drift')
    require(r['experiment_id']=='FE04-SYNC-TIMESTAMP-AUTHORITY-V1' and r['decision']==DECISION and r['shipping_authority'] is False
      and r['data_role']==ROLE and r['execution_source_revision']==revision and r['case_count']==6,'timestamp authority drift')
    require(r['timestamp_authority']=='EXACT_SYNTHETIC_TRANSPORT_NOT_DUT' and r['acoustic_tracking'] is False and r['res_enabled'] is False,'timestamp scope')
    require(r['sync_predecessor_manifest_sha256']==sha256((sync_root/'manifest.json').read_bytes())
      and r['route_reset_predecessor_manifest_sha256']==sha256((reset_root/'manifest.json').read_bytes()),'timestamp predecessor binding')
    for name in ('sync_timestamp_runner.c','sync_timestamp_authority.py'):
        require((root/'source'/name).read_bytes()==(HERE/name).read_bytes(),'timestamp source drift '+name)
    sm=case_map(sr);rm=case_map(rr);require({c['case_id'] for c in r['cases']}==set(sm)==set(rm),'timestamp case set')
    for c in r['cases']:
        pc=sm[c['case_id']];fault=c['fault'];inp=sync_root/pc['input'];d=root/'cases'/c['case_id']
        rows0=trace_rows(d/'timestamp.csv',fault,'timestamp',N//HOP);rows1=trace_rows(d/'timestamp-reset.csv',fault,'timestamp-reset',N//HOP)
        require(trace_without_reset(rows0)==trace_without_reset(rows1),'timestamp trace causal guard')
        expected=1 if fault=='route' else 0
        require(c['timestamp_route_events']==expected==c['expected_timestamp_route_events'] and c['timestamp_reset_count']==expected,'timestamp event contract')
        require(c['timestamp_reset_frames']==([800] if fault=='route' else []),'timestamp reset frame')
        oracle=sync_root/'cases'/c['case_id']/'oracle.f32';acoustic=reset_root/'cases'/c['case_id']/'reset.f32'
        require((d/'timestamp.f32').read_bytes()==oracle.read_bytes() and c['timestamp_no_reset_oracle_byte_identity'] is True,'oracle byte identity')
        require(reference_values(d/'timestamp.f32')==physical(inp),'physical reference identity')
        zero=(d/'timestamp.f32').read_bytes()==(d/'timestamp-reset.f32').read_bytes()
        require(c['zero_event_reset_output_identity']==zero and (zero if fault!='route' else True),'zero-event reset identity')
        om=metrics(inp,oracle,fault);am=metrics(inp,acoustic,fault);tm=metrics(inp,d/'timestamp.f32',fault);trm=metrics(inp,d/'timestamp-reset.f32',fault)
        require(c['oracle_metrics']==om and c['acoustic_reset_metrics']==am and c['timestamp_no_reset_metrics']==tm and c['timestamp_reset_metrics']==trm,'timestamp metric recomputation')
        require(tm==om,'timestamp no-reset metric/oracle')
        require(c['timestamp_output_sha256']==sha256((d/'timestamp.f32').read_bytes())
          and c['timestamp_reset_output_sha256']==sha256((d/'timestamp-reset.f32').read_bytes())
          and c['timestamp_trace_sha256']==sha256((d/'timestamp.csv').read_bytes())
          and c['timestamp_reset_trace_sha256']==sha256((d/'timestamp-reset.csv').read_bytes()),'timestamp case hashes')
    for label in LABELS:
        info=load_json(root/(label+'-build.json'));require(info['source_revision']==revision and info['processor_sha256']==sha256((root/('sync-timestamp-'+label)).read_bytes()),'timestamp binary')
    eng=load_json(root/'engineering/result.json');require(eng==r['engineering'] and eng['status']=='PASS','timestamp engineering')
    require('ARM' in (root/'arm-elf.txt').read_text() and 'ELF32' in (root/'arm-elf.txt').read_text(),'timestamp Arm ELF')
    return {'status':'VERIFIED_SYNC_TIMESTAMP_AUTHORITY','cases':6,'files':len(load_json(root/'manifest.json')['files']),'decision':DECISION}

def negatives(sync_root:Path,reset_root:Path,root:Path,revision:str)->dict:
    kinds=('promotion','predecessor','missing-case','metric','output','trace','reset-count','binary');rejected=[]
    predecessors(sync_root,reset_root,revision)
    with tempfile.TemporaryDirectory(prefix='sync-ts-neg-') as temp:
        copy=Path(temp)/'copy';shutil.copytree(root,copy)
        keep={p:p.read_bytes() for p in (copy/'result.json',copy/'manifest.json',copy/'SHA256SUMS')}
        for kind in kinds:
            rr=json.loads(keep[copy/'result.json']);changed=[]
            if kind=='promotion':rr['shipping_authority']=True
            elif kind=='predecessor':rr['sync_predecessor_manifest_sha256']='0'*64
            elif kind=='missing-case':rr['cases'].pop()
            elif kind=='metric':rr['cases'][0]['timestamp_reset_metrics']['final_far_ratio_db']=0.0
            elif kind=='reset-count':rr['cases'][0]['timestamp_reset_count']+=1
            else:
                case=rr['cases'][0]['case_id'];pth=copy/'cases'/case/'timestamp-reset.f32' if kind=='output' else copy/'cases'/case/'timestamp-reset.csv' if kind=='trace' else copy/'sync-timestamp-native'
                blob=pth.read_bytes();changed.append((pth,blob));pth.write_bytes(blob+b'changed')
            write_json(copy/'result.json',rr);seal_output(copy,rr)
            try:verify(sync_root,reset_root,copy,revision,predecessors_verified=True)
            except (ValueError,KeyError,IndexError,AssertionError,RuntimeError):rejected.append(kind)
            else:raise AssertionError('resealed timestamp negative accepted '+kind)
            for pth,blob in changed:pth.write_bytes(blob)
            for pth,blob in keep.items():pth.write_bytes(blob)
    return {'status':'PASS','rejected':rejected}

def summary(r:dict)->dict:
    groups=[]
    for fault in FAULTS:
        rows=[x for x in r['cases'] if x['fault']==fault]
        def mean(key):
            vals=[x[key]['final_far_ratio_db'] for x in rows];return sum(vals)/len(vals)
        groups.append({'fault':fault,'cases':len(rows),
          'acoustic_reset_mean_final_far_db':mean('acoustic_reset_metrics'),
          'timestamp_no_reset_mean_final_far_db':mean('timestamp_no_reset_metrics'),
          'timestamp_reset_mean_final_far_db':mean('timestamp_reset_metrics'),
          'timestamp_route_events':[x['timestamp_route_events'] for x in rows],
          'timestamp_reset_counts':[x['timestamp_reset_count'] for x in rows],
          'oracle_byte_identity':[x['timestamp_no_reset_oracle_byte_identity'] for x in rows]})
    return {'decision':DECISION,'descriptive_only':True,'groups':groups}

def main()->int:
    p=argparse.ArgumentParser();p.add_argument('--sync-predecessor',type=Path,required=True);p.add_argument('--reset-predecessor',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True);p.add_argument('--execution-source',required=True)
    p.add_argument('--verify',action='store_true');p.add_argument('--negative-evidence',action='store_true')
    a=p.parse_args();require(hex_digest(a.execution_source,40),'timestamp revision')
    if a.negative_evidence:r=negatives(a.sync_predecessor,a.reset_predecessor,a.output,a.execution_source)
    elif a.verify:r=verify(a.sync_predecessor,a.reset_predecessor,a.output,a.execution_source)
    else:
        r=run(a.sync_predecessor,a.reset_predecessor,a.output,a.execution_source)
        print('SYNC_TIMESTAMP_AUTHORITY_EFFECTS '+json.dumps(summary(r),sort_keys=True,allow_nan=False))
        r={'status':'EXECUTED_SYNC_TIMESTAMP_AUTHORITY','cases':6,'decision':DECISION}
    print(json.dumps(r,sort_keys=True,allow_nan=False));return 0
if __name__=='__main__':raise SystemExit(main())
