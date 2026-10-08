#!/usr/bin/env python3
"""FE05 ordinary NS vs existing frequency-domain residual-echo suppression."""
from __future__ import annotations
import argparse, array, csv, json, math, shutil, subprocess, sys, tempfile
from pathlib import Path
import sync_faults as sync
import aec_res_collab as aecres
from contracts import ROOT, hex_digest, load_json, require, sha256
from libfvad_reference import write_json, seal_output, run_logged
from speech_fir import verify_seal

HERE=Path(__file__).resolve().parent
PLAN=ROOT/'.github/research/frontend-evolution-v1/ns-frequency-res-v1.json'
RUNNER=HERE/'ns_frequency_res_runner.c'
DECISION='NS_FREQUENCY_RES_DIAGNOSTIC_NO_PROMOTION'
ROLE='DISCLOSED_DEVELOPMENT_DIAGNOSTIC_NOT_HOLDOUT'
RATE,HOP,N=16000,160,256000
FAULTS=sync.FAULTS
LABELS=sync.LABELS
PHASES=aecres.PHASES
CFLAGS=['-std=c11','-O2','-Wall','-Wextra','-Wpedantic','-Werror','-ffp-contract=off']
HEADER=['frame','known_lead_samples','timestamp_observed','route_jump','aec_reset','sync_delay_samples',
        'underrun','used_far','used_dt','aec_echo_energy','pre_ns_energy','ns_only_noise_dbfs',
        'ns_freq_noise_dbfs','ns_only_speech_probability','ns_freq_speech_probability',
        'ns_only_residual_echo_gain','ns_freq_residual_echo_gain','ns_freq_active',
        'output_diff_samples','protected','carryover_allowed']

def case_map(r:dict)->dict:
    return {c['case_id']:c for c in r['cases']}

def predecessor_receipt(sync_root:Path,reset_root:Path,exact_root:Path,aec_root:Path,
                        revision:str,full:bool)->dict:
    if full:
        v=aecres.verify(sync_root,reset_root,exact_root,aec_root,revision)
        require(v['status']=='VERIFIED_AEC_RES_COLLAB','AEC/RES predecessor verify')
    else:
        for root in (sync_root,reset_root,exact_root,aec_root):verify_seal(root)
    sr=load_json(sync_root/'result.json');ar=load_json(aec_root/'result.json')
    require(sr['execution_source_revision']==ar['execution_source_revision']==revision,'NS predecessor revision')
    require(ar['experiment_id']=='FE04-AEC-RES-COLLAB-V1' and ar['case_count']==6,'NS AEC predecessor')
    return {'sync_manifest_sha256':sha256((sync_root/'manifest.json').read_bytes()),
      'reset_manifest_sha256':sha256((reset_root/'manifest.json').read_bytes()),
      'exact_manifest_sha256':sha256((exact_root/'manifest.json').read_bytes()),
      'aec_res_manifest_sha256':sha256((aec_root/'manifest.json').read_bytes()),
      'aec_res_result_sha256':sha256((aec_root/'result.json').read_bytes()),'source_revision':revision}

def trace_rows(path:Path,fault:str)->list[dict]:
    rows=[];previous_active=False
    with path.open(newline='') as f:
        rd=csv.DictReader(f);require(rd.fieldnames==HEADER,'NS frequency-RES trace schema')
        for index,row in enumerate(rd):
            require(index<N//HOP and None not in row.values(),'NS trace count/partial')
            item={}
            for key in HEADER:
                if key in ('aec_echo_energy','pre_ns_energy','ns_only_noise_dbfs','ns_freq_noise_dbfs',
                           'ns_only_speech_probability','ns_freq_speech_probability',
                           'ns_only_residual_echo_gain','ns_freq_residual_echo_gain'):
                    value=float(row[key]);require(math.isfinite(value),'nonfinite NS trace');item[key]=value
                else:item[key]=int(row[key])
            require(item['frame']==index,'NS trace order')
            lead=sync.expected_lead(fault,index,N//HOP)
            require(item['known_lead_samples']==lead and item['timestamp_observed']==1
              and item['sync_delay_samples']==lead and item['underrun']==0,'NS timestamp authority')
            expected=int(fault=='route' and index==800)
            require(item['route_jump']==expected and item['aec_reset']==expected,'NS route/reset')
            require(item['used_far'] in (0,1) and item['used_dt'] in (0,1),'NS Activity flags')
            active=int(item['used_far'] and not item['used_dt'])
            protected=int(not active)
            carry=int(protected and previous_active)
            require(item['ns_freq_active']==active and item['protected']==protected
              and item['carryover_allowed']==carry,'NS active/protected contract')
            require(item['ns_only_residual_echo_gain']==1.0,'ordinary NS residual gain drift')
            if active:
                require(0.0 < item['ns_freq_residual_echo_gain'] <= 1.0,'frequency RES gain bounds')
            else:
                require(item['ns_freq_residual_echo_gain']==1.0,'frequency RES active while protected')
                if not carry:require(item['output_diff_samples']==0,'steady protected frame diverged')
            require(item['ns_only_noise_dbfs']==item['ns_freq_noise_dbfs']
              and item['ns_only_speech_probability']==item['ns_freq_speech_probability'],'NS tracker divergence')
            require(item['output_diff_samples']>=0 and item['output_diff_samples']<=HOP,'NS diff count')
            rows.append(item);previous_active=bool(active)
    require(len(rows)==N//HOP,'NS trace frame count')
    return rows

def build(root:Path,revision:str,label:str)->Path:
    arm=label=='arm';san=label=='sanitized';cc='arm-linux-gnueabihf-gcc' if arm else 'cc'
    flags=['-O1','-g','-fsanitize=address,undefined','-fno-omit-frame-pointer'] if san else ['-O2']
    b=root/('build-'+label)
    opts=['cmake','-S',ROOT,'-B',b,'-DCMAKE_BUILD_TYPE=Release','-DCMAKE_C_COMPILER='+cc,
      '-DCMAKE_C_FLAGS='+' '.join(flags+['-ffp-contract=off']),'-DAP_BUILD_SOURCE_REVISION='+revision,
      '-DAP_BUILD_PIPELINE=OFF','-DAP_MODULES=SYNC,ACTIVITY,AEC,NS,RES','-DAP_AEC_BACKEND=MDF','-DAP_SIMD_BACKEND=SCALAR',
      '-DAP_BUILD_TESTS=OFF','-DAP_BUILD_BENCH=OFF','-DAP_BUILD_EXAMPLES=OFF','-DAP_ENABLE_LINUX_RUNTIME=OFF',
      '-DAP_BUILD_MAX_AEC_TAIL_MS=64','-DAP_BUILD_MAX_DELAY_MS=120','-DAP_STRICT_WARNINGS=ON']
    if arm:opts+=['-DCMAKE_SYSTEM_NAME=Linux','-DCMAKE_SYSTEM_PROCESSOR=arm']
    run_logged(opts,root/(label+'-configure.log'));run_logged(['cmake','--build',b,'--parallel','2'],root/(label+'-build.log'))
    binary=root/('ns-frequency-res-'+label)
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

def command(binary:Path,fault:str,inp:Path,dest:Path,under_arm:bool=False)->list:
    prefix=['qemu-arm','-L','/usr/arm-linux-gnueabihf'] if under_arm else []
    return [*prefix,binary,fault,inp,dest.with_suffix('.f32'),dest.with_suffix('.json'),dest.with_suffix('.csv')]

def execute(binary:Path,fault:str,inp:Path,dest:Path,under_arm:bool=False)->None:
    run_logged(command(binary,fault,inp,dest,under_arm),dest.with_suffix('.log'))

def words(path:Path)->array.array:
    a=array.array('I');a.frombytes(path.read_bytes())
    if sys.byteorder!='little':a.byteswap()
    return a

def floats(path:Path,stride:int,lane:int)->list[float]:
    raw=sync.floats(path,N*stride)
    return list(raw[lane::stride])

def predecessor_identity(candidate:Path,aec_predecessor:Path)->dict:
    cw=words(candidate);pw=words(aec_predecessor)
    require(len(cw)==N*5 and len(pw)==N*3,'NS predecessor packed size')
    pre=sum(a!=b for a,b in zip(cw[0::5],pw[0::3]))
    ref=sum(a!=b for a,b in zip(cw[4::5],pw[2::3]))
    require(pre==0,'NS pre-AEC output diverged from AEC/RES predecessor')
    require(ref==0,'NS reference diverged from AEC/RES predecessor')
    return {'pre_ns_aec_bit_mismatches':pre,'reference_bit_mismatches':ref,
      'pre_ns_aec_bit_identity':True,'reference_bit_identity':True}

def metrics(inp:Path,out:Path,lane:int,fault:str)->dict:
    source=sync.floats(inp,N*4);target=list(source[1::4]);echo=list(source[2::4]);actual=floats(out,5,lane)
    return sync.metrics(target,echo,actual,fault)

def lane_words(path:Path,stride:int,lane:int)->list[int]:
    raw=words(path)
    require(len(raw)==N*stride,'NS packed word count')
    return list(raw[lane::stride])

def output_diff_stats(rows:list[dict],control_bits:list[int],candidate_bits:list[int])->dict:
    require(len(control_bits)==len(candidate_bits)==N,'NS output bit lengths')
    active_frames=steady_protected=carry_frames=0
    active_diff=steady_diff=carry_diff=0
    for frame,row in enumerate(rows):
        lo=frame*HOP;hi=lo+HOP
        diffs=sum(a!=b for a,b in zip(control_bits[lo:hi],candidate_bits[lo:hi]))
        require(diffs==row['output_diff_samples'],'NS trace/raw diff count')
        if row['ns_freq_active']:
            active_frames+=1;active_diff+=diffs
        elif row['carryover_allowed']:
            carry_frames+=1;carry_diff+=diffs
        else:
            steady_protected+=1;steady_diff+=diffs;require(diffs==0,'steady protected raw diff')
    return {'active_frames':active_frames,'active_diff_samples':active_diff,
      'steady_protected_frames':steady_protected,'steady_protected_diff_samples':steady_diff,
      'carryover_frames':carry_frames,'carryover_diff_samples':carry_diff}

def phase_stats(rows:list[dict],control:list[float],candidate:list[float])->dict:
    result={}
    for name,(a,b) in PHASES.items():
        subset=rows[a:b];lo=a*HOP;hi=b*HOP
        ce=sum(x*x for x in control[lo:hi])/max(1,hi-lo)
        ne=sum(x*x for x in candidate[lo:hi])/max(1,hi-lo)
        gains=[x['ns_freq_residual_echo_gain'] for x in subset]
        result[name]={'frames':len(subset),'far_frames':sum(x['used_far'] for x in subset),
          'double_talk_frames':sum(x['used_dt'] for x in subset),
          'frequency_res_active_frames':sum(x['ns_freq_active'] for x in subset),
          'carryover_frames':sum(x['carryover_allowed'] for x in subset),
          'candidate_res_gain_mean':sum(gains)/len(gains),
          'output_rms_delta_db':10.0*math.log10(max(ne,1e-30)/max(ce,1e-30))}
    return result

def run_one(binary:Path,label:str,inp:Path,fault:str,dest:Path)->dict:
    under_arm=label=='arm'
    execute(binary,fault,inp,dest,under_arm);execute(binary,fault,inp,dest.with_name(dest.name+'-repeat'),under_arm)
    for suffix in ('.f32','.json','.csv'):
        require(dest.with_suffix(suffix).read_bytes()==dest.with_name(dest.name+'-repeat').with_suffix(suffix).read_bytes(),'NS repeat')
        dest.with_name(dest.name+'-repeat').with_suffix(suffix).unlink()
    rows=trace_rows(dest.with_suffix('.csv'),fault);meta=load_json(dest.with_suffix('.json'))
    expected=1 if fault=='route' else 0
    require(meta['status']=='PASS' and meta['timestamp_authority'] is True
      and meta['route_jump_resets_aec'] is True and meta['time_domain_res_executed'] is False
      and meta['ns_quality']=='FULL' and meta['ns_floor_gain']==0.18,'NS meta')
    require(meta['timestamp_observations']==N//HOP and meta['route_jumps']==expected
      and meta['aec_resets']==expected and meta['underruns']==0,'NS counters')
    require(meta['noise_bits_mismatch_frames']==0 and meta['speech_bits_mismatch_frames']==0
      and meta['protected_steady_diff_samples']==0,'NS causal meta')
    return {'rows':rows,'meta':meta,'output_sha256':sha256(dest.with_suffix('.f32').read_bytes()),
      'trace_sha256':sha256(dest.with_suffix('.csv').read_bytes())}

def engineering(root:Path,binaries:dict,sync_root:Path,aec_root:Path,revision:str)->dict:
    root.mkdir();pc=case_map(load_json(sync_root/'result.json'))['p0-route'];inp=sync_root/pc['input']
    pred=aec_root/'cases'/'p0-route'/'candidate.f32';records={}
    for label in LABELS:
        d=root/label;d.mkdir()
        run_logged((['qemu-arm','-L','/usr/arm-linux-gnueabihf'] if label=='arm' else [])+[binaries[label],'--self-test'],d/'self-test.log')
        rec=run_one(binaries[label],label,inp,'route',d/'candidate')
        records[label]={'output_sha256':rec['output_sha256'],'trace_sha256':rec['trace_sha256'],
          'frequency_res_active_frames':rec['meta']['frequency_res_active_frames'],
          'ns_state_bytes_each':rec['meta']['ns_state_bytes_each']}
        if label=='native':records[label]['predecessor_identity']=predecessor_identity(d/'candidate.f32',pred)
    data=array.array('f');data.frombytes(inp.read_bytes())
    if sys.byteorder!='little':data.byteswap()
    cutoff=200000
    for k in range(cutoff,N):
        for c in range(4):data[4*k+c]*=-1.0
    if sys.byteorder!='little':data.byteswap()
    future=root/'future-input.f32';future.write_bytes(data.tobytes())
    execute(binaries['native'],'route',future,root/'future')
    a=sync.floats(root/'native/candidate.f32',N*5);b=sync.floats(root/'future.f32',N*5)
    require(a[:(cutoff-2*HOP)*5]==b[:(cutoff-2*HOP)*5] and a[(cutoff+2*HOP)*5:]!=b[(cutoff+2*HOP)*5:],'NS future causality')
    z=array.array('f');z.frombytes(inp.read_bytes())
    if sys.byteorder!='little':z.byteswap()
    for k in range(N):z[4*k+3]=0.0
    if sys.byteorder!='little':z.byteswap()
    zero=root/'zero-render.f32';zero.write_bytes(z.tobytes())
    execute(binaries['native'],'static',zero,root/'zero-render-output')
    zr=trace_rows(root/'zero-render-output.csv','static')
    require(all(not x['ns_freq_active'] and x['output_diff_samples']==0 for x in zr),'NS frequency RES active on zero render')
    bad=root/'partial.f32';bad.write_bytes(b'\0')
    p=subprocess.run(list(map(str,command(binaries['native'],'static',bad,root/'bad'))),capture_output=True)
    require(p.returncode!=0,'partial NS input accepted');(root/'bad.log').write_bytes(p.stderr)
    before=(root/'native/candidate.f32').read_bytes()
    p=subprocess.run(list(map(str,command(binaries['native'],'route',inp,root/'native/candidate'))),capture_output=True)
    require(p.returncode!=0 and before==(root/'native/candidate.f32').read_bytes(),'NS overwrite accepted');(root/'overwrite.log').write_bytes(p.stderr)
    result={'status':'PASS','fixed_case':'p0-route','records':records,'future':True,
      'zero_render_arm_identity':True,'invalid_transport_rejected':True,'overwrite_rejected':True,
      'ns_self_test':True}
    write_json(root/'result.json',result);return result

def run(sync_root:Path,reset_root:Path,exact_root:Path,aec_root:Path,root:Path,revision:str)->dict:
    require(not root.exists() and hex_digest(revision,40),'fresh output/exact revision')
    pred=predecessor_receipt(sync_root,reset_root,exact_root,aec_root,revision,full=True)
    sr=load_json(sync_root/'result.json');ar=load_json(aec_root/'result.json')
    root.mkdir(parents=True);shutil.copyfile(PLAN,root/'experiment.json');write_json(root/'predecessor-verification.json',pred)
    (root/'source').mkdir()
    for p in (RUNNER,Path(__file__)):shutil.copyfile(p,root/'source'/p.name)
    binaries={label:build(root,revision,label) for label in LABELS}
    eng=engineering(root/'engineering',binaries,sync_root,aec_root,revision)
    sm=case_map(sr);am=case_map(ar);cases=[]
    for case_id in sorted(sm,key=lambda x:(sm[x]['pair'],FAULTS.index(sm[x]['fault']))):
        pc=sm[case_id];ap=am[case_id];fault=pc['fault'];inp=sync_root/pc['input'];d=root/'cases'/case_id;d.mkdir(parents=True)
        rec=run_one(binaries['native'],'native',inp,fault,d/'candidate')
        identity=predecessor_identity(d/'candidate.f32',aec_root/'cases'/case_id/'candidate.f32')
        pre=floats(d/'candidate.f32',5,0);control=floats(d/'candidate.f32',5,2);candidate=floats(d/'candidate.f32',5,3)
        control_m=metrics(inp,d/'candidate.f32',2,fault);candidate_m=metrics(inp,d/'candidate.f32',3,fault)
        pre_m=sync.metrics(list(sync.floats(inp,N*4)[1::4]),list(sync.floats(inp,N*4)[2::4]),pre,fault)
        require(pre_m==ap['pre_res_metrics'],'NS pre-AEC metric identity')
        diffs=output_diff_stats(rec['rows'],lane_words(d/'candidate.f32',5,2),lane_words(d/'candidate.f32',5,3));phases=phase_stats(rec['rows'],control,candidate)
        cases.append({'case_id':case_id,'pair':pc['pair'],'fault':fault,'predecessor_identity':identity,
          'pre_ns_metrics':pre_m,'ns_only_metrics':control_m,'ns_freq_res_metrics':candidate_m,
          'delta_final_far_db':None if control_m['final_far_ratio_db'] is None or candidate_m['final_far_ratio_db'] is None
            else candidate_m['final_far_ratio_db']-control_m['final_far_ratio_db'],
          'output_diff':diffs,'phase_stats':phases,
          'frequency_res_active_frames':rec['meta']['frequency_res_active_frames'],
          'protected_carryover_frames':rec['meta']['protected_carryover_frames'],
          'carryover_diff_samples':rec['meta']['carryover_diff_samples'],
          'residual_echo_gain_mean_active':rec['meta']['residual_echo_gain_mean_active'],
          'residual_echo_gain_min_active':rec['meta']['residual_echo_gain_min_active'],
          'candidate_output_sha256':rec['output_sha256'],'trace_sha256':rec['trace_sha256']})
    report={'schema_version':1,'experiment_id':'FE05-NS-FREQUENCY-RES-V1','decision':DECISION,
      'shipping_authority':False,'data_role':ROLE,'execution_source_revision':revision,'case_count':6,
      'predecessor':pred,'transport':'EXACT_SYNTHETIC_TIMESTAMP_NOT_DUT','ns_quality':'FULL','floor_gain':0.18,
      'time_domain_res_executed':False,'engineering':eng,'cases':cases}
    write_json(root/'result.json',report);seal_output(root,report);return report

def verify(sync_root:Path,reset_root:Path,exact_root:Path,aec_root:Path,root:Path,revision:str,
           predecessors_verified=False)->dict:
    verify_seal(root);pred=predecessor_receipt(sync_root,reset_root,exact_root,aec_root,revision,full=False)
    r=load_json(root/'result.json');receipt=load_json(root/'predecessor-verification.json')
    require(r['predecessor']==receipt==pred,'NS predecessor receipt')
    require((root/'experiment.json').read_bytes()==PLAN.read_bytes(),'NS plan drift')
    require(r['experiment_id']=='FE05-NS-FREQUENCY-RES-V1' and r['decision']==DECISION
      and r['shipping_authority'] is False and r['data_role']==ROLE and r['execution_source_revision']==revision
      and r['case_count']==6,'NS authority')
    require(r['transport']=='EXACT_SYNTHETIC_TIMESTAMP_NOT_DUT' and r['ns_quality']=='FULL'
      and r['floor_gain']==0.18 and r['time_domain_res_executed'] is False,'NS scope')
    for name in ('ns_frequency_res_runner.c','ns_frequency_res.py'):
        require((root/'source'/name).read_bytes()==(HERE/name).read_bytes(),'NS source drift '+name)
    sr=load_json(sync_root/'result.json');ar=load_json(aec_root/'result.json');sm=case_map(sr);am=case_map(ar)
    require({c['case_id'] for c in r['cases']}==set(sm)==set(am),'NS case set')
    for c in r['cases']:
        pc=sm[c['case_id']];ap=am[c['case_id']];fault=c['fault'];inp=sync_root/pc['input'];d=root/'cases'/c['case_id']
        rows=trace_rows(d/'candidate.csv',fault)
        identity=predecessor_identity(d/'candidate.f32',aec_root/'cases'/c['case_id']/'candidate.f32')
        pre=floats(d/'candidate.f32',5,0);control=floats(d/'candidate.f32',5,2);candidate=floats(d/'candidate.f32',5,3)
        source=sync.floats(inp,N*4);target=list(source[1::4]);echo=list(source[2::4])
        pre_m=sync.metrics(target,echo,pre,fault);control_m=metrics(inp,d/'candidate.f32',2,fault);candidate_m=metrics(inp,d/'candidate.f32',3,fault)
        require(pre_m==ap['pre_res_metrics'],'NS predecessor metric drift')
        require(c['predecessor_identity']==identity and c['pre_ns_metrics']==pre_m
          and c['ns_only_metrics']==control_m and c['ns_freq_res_metrics']==candidate_m,'NS metric recomputation')
        require(c['output_diff']==output_diff_stats(rows,lane_words(d/'candidate.f32',5,2),lane_words(d/'candidate.f32',5,3))
          and c['phase_stats']==phase_stats(rows,control,candidate),'NS difference recomputation')
        meta=load_json(d/'candidate.json')
        require(c['frequency_res_active_frames']==meta['frequency_res_active_frames']
          and c['protected_carryover_frames']==meta['protected_carryover_frames']
          and c['carryover_diff_samples']==meta['carryover_diff_samples']
          and c['residual_echo_gain_mean_active']==meta['residual_echo_gain_mean_active']
          and c['residual_echo_gain_min_active']==meta['residual_echo_gain_min_active'],'NS meta receipt')
        require(c['candidate_output_sha256']==sha256((d/'candidate.f32').read_bytes())
          and c['trace_sha256']==sha256((d/'candidate.csv').read_bytes()),'NS hashes')
    for label in LABELS:
        info=load_json(root/(label+'-build.json'))
        require(info['source_revision']==revision and info['processor_sha256']==sha256((root/('ns-frequency-res-'+label)).read_bytes()),'NS binary')
    eng=load_json(root/'engineering/result.json');require(eng==r['engineering'] and eng['status']=='PASS','NS engineering')
    require('ARM' in (root/'arm-elf.txt').read_text() and 'ELF32' in (root/'arm-elf.txt').read_text(),'NS Arm ELF')
    return {'status':'VERIFIED_NS_FREQUENCY_RES','cases':6,'files':len(load_json(root/'manifest.json')['files']),'decision':DECISION}

def negatives(sync_root:Path,reset_root:Path,exact_root:Path,aec_root:Path,root:Path,revision:str)->dict:
    kinds=('promotion','predecessor','missing-case','metric','output','trace','carryover','binary');rejected=[]
    predecessor_receipt(sync_root,reset_root,exact_root,aec_root,revision,full=False)
    with tempfile.TemporaryDirectory(prefix='ns-freq-res-neg-') as temp:
        copy=Path(temp)/'copy';shutil.copytree(root,copy)
        keep={p:p.read_bytes() for p in (copy/'result.json',copy/'manifest.json',copy/'SHA256SUMS')}
        for kind in kinds:
            rr=json.loads(keep[copy/'result.json']);changed=[]
            if kind=='promotion':rr['shipping_authority']=True
            elif kind=='predecessor':rr['predecessor']['aec_res_manifest_sha256']='0'*64
            elif kind=='missing-case':rr['cases'].pop()
            elif kind=='metric':rr['cases'][0]['ns_freq_res_metrics']['final_far_ratio_db']=0.0
            elif kind=='carryover':rr['cases'][0]['protected_carryover_frames']+=1
            else:
                case=rr['cases'][0]['case_id'];base=copy/'cases'/case/'candidate'
                pth=base.with_suffix('.f32') if kind=='output' else base.with_suffix('.csv') if kind=='trace' else copy/'ns-frequency-res-native'
                blob=pth.read_bytes();changed.append((pth,blob));pth.write_bytes(blob+b'changed')
            write_json(copy/'result.json',rr);seal_output(copy,rr)
            try:verify(sync_root,reset_root,exact_root,aec_root,copy,revision,predecessors_verified=True)
            except (ValueError,KeyError,IndexError,AssertionError,RuntimeError):rejected.append(kind)
            else:raise AssertionError('resealed NS frequency-RES negative accepted '+kind)
            for pth,blob in changed:pth.write_bytes(blob)
            for pth,blob in keep.items():pth.write_bytes(blob)
    return {'status':'PASS','rejected':rejected}

def summary(r:dict)->dict:
    groups=[]
    for fault in FAULTS:
        rows=[x for x in r['cases'] if x['fault']==fault]
        before=[x['ns_only_metrics']['final_far_ratio_db'] for x in rows]
        after=[x['ns_freq_res_metrics']['final_far_ratio_db'] for x in rows]
        groups.append({'fault':fault,'cases':len(rows),
          'ns_only_mean_final_far_db':sum(before)/len(before),
          'ns_freq_res_mean_final_far_db':sum(after)/len(after),
          'delta_final_far_db':[x['delta_final_far_db'] for x in rows],
          'frequency_res_active_frames':[x['frequency_res_active_frames'] for x in rows],
          'protected_carryover_frames':[x['protected_carryover_frames'] for x in rows],
          'carryover_diff_samples':[x['carryover_diff_samples'] for x in rows],
          'double_before_rms_delta_db':[x['phase_stats']['double-before']['output_rms_delta_db'] for x in rows],
          'double_after_rms_delta_db':[x['phase_stats']['double-after']['output_rms_delta_db'] for x in rows]})
    return {'decision':DECISION,'descriptive_only':True,'groups':groups}

def main()->int:
    p=argparse.ArgumentParser()
    p.add_argument('--sync-predecessor',type=Path,required=True);p.add_argument('--reset-predecessor',type=Path,required=True)
    p.add_argument('--exact-predecessor',type=Path,required=True);p.add_argument('--aec-res-predecessor',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True);p.add_argument('--execution-source',required=True)
    p.add_argument('--verify',action='store_true');p.add_argument('--negative-evidence',action='store_true')
    a=p.parse_args();require(hex_digest(a.execution_source,40),'NS frequency-RES revision')
    if a.negative_evidence:r=negatives(a.sync_predecessor,a.reset_predecessor,a.exact_predecessor,a.aec_res_predecessor,a.output,a.execution_source)
    elif a.verify:r=verify(a.sync_predecessor,a.reset_predecessor,a.exact_predecessor,a.aec_res_predecessor,a.output,a.execution_source)
    else:
        r=run(a.sync_predecessor,a.reset_predecessor,a.exact_predecessor,a.aec_res_predecessor,a.output,a.execution_source)
        print('NS_FREQUENCY_RES_EFFECTS '+json.dumps(summary(r),sort_keys=True,allow_nan=False))
        r={'status':'EXECUTED_NS_FREQUENCY_RES','cases':6,'decision':DECISION}
    print(json.dumps(r,sort_keys=True,allow_nan=False));return 0
if __name__=='__main__':raise SystemExit(main())
